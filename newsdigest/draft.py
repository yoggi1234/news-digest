"""`collect`: gather news for a date and write an editable draft (drafts/YYYY-MM-DD.json)."""
import datetime as dt
import glob
import os
import re
from concurrent.futures import ThreadPoolExecutor

from . import sources, util
from .config import load_json, save_json, user_file
from .writer import Writer, pick_fact

STATES = ["andhra pradesh", "arunachal", "assam", "bihar", "chhattisgarh", "goa", "gujarat", "haryana",
          "himachal", "jharkhand", "karnataka", "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya",
          "mizoram", "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu", "telangana", "tripura",
          "uttar pradesh", "uttarakhand", "west bengal", "delhi", "jammu", "kashmir", "ladakh", "puducherry",
          "chandigarh", "bengaluru", "chennai", "kolkata", "mumbai", "hyderabad", "lucknow", "patna", "thrissur",
          "kochi", "bhopal", "jaipur", "guwahati", "imphal", "andaman"]
UPDATE_WORDS = re.compile(r"\b(update|latest|fresh|again|rises?|toll|now|second|another|final|verdict|result)\b", re.I)
JUNK = re.compile(r"(gold (rate|price)|silver (rate|price)|petrol.{0,10}price|price today|horoscope|"
                  r"live updates|\blive:|\bwatch:|photos:|in pics|quiz|wordle|how to |recipe|bigg boss|"
                  r"weather today|lottery|result live|box office|ott release|news and video|latest news, )", re.I)
SPORTS = re.compile(r"\b(ipl|cricket|fifa|football|hockey|tennis|badminton|chess|olympic|medal|tournament|"
                    r"t20|odi|test match|wicket|pacer|batter|squad|coach|league|grand prix|kabaddi)\b", re.I)
EDITABLE = ["headline", "paragraph", "tiles", "flow", "key_points", "full_forms", "benefit_label", "benefit",
            "advanced", "also", "sources", "confidence", "notes"]


def draft_path(cfg, date):
    return os.path.join(cfg["paths"]["drafts"], f"{date.isoformat()}.json")


def load_draft(cfg, date):
    d = load_json(draft_path(cfg, date))
    if d is None:
        raise SystemExit(f"No draft for {date}. Run: digest collect {date}")
    return d


def _score(item, sec):
    title, body = item["title"].lower(), (item.get("summary") or "").lower()[:600]
    if any(k in title for k in sec.get("exclude", [])):
        return 0
    if SPORTS.search(item["title"]):
        return 5 if sec["name"] == "Miscellaneous" else 0
    s = 0
    for k in sec.get("keywords", []):
        if k in title:
            s += 3
        elif k in body:
            s += 1
    if sec["name"].startswith("Regional"):
        hits = sum(1 for st in STATES if st in title) * 3 + sum(1 for st in STATES if st in body)
        s += hits
    if item.get("hint") == sec["name"] and s:
        s += 2
    return s


def _cluster(items):
    clusters = []
    for it in items:
        for c in clusters:
            if util.similarity(it["title"], c["title"]) >= 0.55:
                c["items"].append(it)
                if it["source"] not in c["sources"]:
                    c["sources"].append(it["source"])
                if len(it.get("summary", "")) > len(c.get("summary", "")):
                    c["summary"] = it["summary"]
                if it.get("text") and not c.get("text"):
                    c["text"] = it["text"]
                if not c.get("link") and it.get("link") and "news.google" not in it["link"]:
                    c["link"] = it["link"]
                break
        else:
            clusters.append({"title": it["title"], "summary": it.get("summary", ""), "text": it.get("text", ""),
                             "link": it.get("link", ""), "sources": [it["source"]], "items": [it],
                             "hint": it.get("hint", ""), "kind": it.get("kind", "web")})
    return clusters


def _disagreements(cluster):
    """Same kind of number reported differently by different sources -> note it."""
    by_unit = {}
    for it in cluster["items"]:
        for f in util.key_figures(it["title"] + ". " + (it.get("summary") or ""), 8):
            unit = f["value"].split()[-1].lower() if " " in f["value"] else ("%" if "%" in f["value"] else "")
            # only casualty/force counts: money and % figures in one story are usually different measures
            if unit in ("killed", "dead", "soldiers", "troops"):
                by_unit.setdefault(unit, {}).setdefault(f["value"], set()).add(it["source"])
    notes = []
    for unit, vals in by_unit.items():
        srcs = [s for v in vals.values() for s in v]
        if len(vals) > 1 and len(set(srcs)) > 1:
            notes.append("Sources differ on figures: " + "; ".join(
                f"{', '.join(sorted(s))}: {v}" for v, s in list(vals.items())[:3]) + " (verify)")
    return notes


def previous_titles(cfg, date, days=3):
    hist = load_json(os.path.join(cfg["paths"]["state"], "history.json"), {})
    out = []
    for k, v in hist.items():
        try:
            d = util.parse_date(k)
        except ValueError:
            continue
        if date - dt.timedelta(days=days) <= d < date:
            out += v.get("titles", [])
    return out, hist


def choose_war(cfg, wars, date, items, forced, log):
    if forced:
        for w in wars["wars"]:
            if forced.lower() in w["name"].lower():
                return w, f"chosen by you ({w['name']})"
        log(f"  ! War '{forced}' not in wars list; add it with `digest war add`. Picking automatically.")
    counts = []
    for w in wars["wars"]:
        n = sum(1 for it in items if any(k in it["title"].lower() for k in w["keywords"]))
        counts.append((n, w))
    counts.sort(key=lambda x: -x[0])
    yday = wars.get("log", {}).get((date - dt.timedelta(days=1)).isoformat())
    top_n, top = counts[0]
    if top["name"] == yday and len(counts) > 1:
        second_n, second = counts[1]
        if top_n < 2 * max(second_n, 1) or top_n < 8:
            return second, (f"auto: most in the news after {top['name']} (covered yesterday; "
                            f"{second_n} headlines today)")
        return top, f"auto: covered yesterday too, but big news today ({top_n} headlines)"
    return top, f"auto: most in the news today ({top_n} headlines)"


HOT_RE = re.compile(r"\b(breaking|killed|kills|dead|deaths?|blast|explosion|crash|earthquake|terror attack|"
                    r"stampede|cyclone|emergency|landslide)\b", re.I)


def _monitor_feed(cfg, headline):
    """Returns a function that sends each collected headline to the live monitor with its section and a
    'hot' flag (breaking words, or the same story seen from 5+ outlets)."""
    if headline is None:
        return lambda items: None
    sections = [s for s in cfg["sections"] if not s.get("war")]
    counts = {}

    def send(items):
        for it in items:
            if JUNK.search(it["title"]):
                continue
            key = tuple(sorted(sorted(set(util.tokens(it["title"])), key=len)[-3:]))
            counts[key] = counts.get(key, 0) + 1
            best = max(sections, key=lambda s: _score(it, s))
            cat = it.get("hint") if it.get("hint") == "WAR SECTION" else (best["name"] if _score(it, best) > 0 else "Miscellaneous")
            headline(it["title"], it["source"], cat, bool(HOT_RE.search(it["title"])) or counts[key] >= 5)
    return send


def collect(cfg, date, pdfs=(), war=None, expect=(), no_web=False, log=print, progress=None, headline=None):
    progress = progress or (lambda *a: None)
    monitor = _monitor_feed(cfg, headline)
    tz = dt.timezone(dt.timedelta(hours=cfg["timezone_offset_hours"]))
    glossary = load_json(user_file(cfg, "glossary.json"), {})
    hardwords = load_json(user_file(cfg, "hardwords.json"), {})
    facts = load_json(user_file(cfg, "facts.json"), [])
    wars = load_json(user_file(cfg, "wars.json"), {"wars": [], "log": {}})
    writer = Writer(cfg, glossary, hardwords, log)

    # 1. newspaper PDFs (from --pdf and the inbox folder)
    pdfs = list(pdfs) + sorted(glob.glob(os.path.join(cfg["paths"]["inbox"], "*.pdf")))
    log(f"Collecting news for {util.nice_date(date)}")
    if pdfs:
        progress(f"Reading {len(pdfs)} newspaper PDF(s)")
    pdf_items, background, files = sources.read_pdfs(pdfs, date, log) if pdfs else ([], [], [])
    monitor(pdf_items)

    # 2. web: publisher feeds + Google News searches (all free)
    web_items = []
    if cfg["web"]["enabled"] and not no_web:
        jobs = [(f["url"], f["name"], f.get("hint", "")) for f in cfg["feeds"]]
        if cfg["web"]["google_news"]:
            for sec in cfg["sections"]:
                for q in sec.get("queries", []):
                    jobs.append(("GN:" + q, "Google News", sec["name"]))
            for w in wars["wars"]:
                jobs.append(("GN:" + w["query"], "Google News", "WAR SECTION"))

        def run(job):
            url, name, hint = job
            if url.startswith("GN:"):
                return sources.google_news(url[3:], date, cfg, tz, hint, log)
            return sources.fetch_feed(url, name, hint, date, cfg, tz, log)

        with ThreadPoolExecutor(8) as ex:
            for i, res in enumerate(ex.map(run, jobs), 1):
                web_items += res
                monitor(res)
                progress("Fetching free news feeds", i, len(jobs))
        log(f"  Web: {len(web_items)} headlines from {len(jobs)} free feeds/searches")
    if not pdf_items and not web_items:
        raise SystemExit("No news found. Check your internet connection or pass newspaper PDFs with --pdf.")

    # 3. drop repeats from earlier editions (keep real updates)
    old_titles, _ = previous_titles(cfg, date)
    all_items, repeats = [], 0
    for it in pdf_items + web_items:
        if JUNK.search(it["title"]):
            continue
        if any(util.similarity(it["title"], t) >= 0.7 for t in old_titles):
            if UPDATE_WORDS.search(it["title"]):
                it["title"] = "UPDATE: " + it["title"]
            else:
                repeats += 1
                continue
        all_items.append(it)
    if repeats:
        log(f"  Skipped {repeats} headlines already covered in the last 3 editions")

    progress(f"Merging {len(all_items)} headlines into stories")
    clusters = _cluster(all_items)
    log(f"  {len(clusters)} distinct stories after merging duplicates")

    # 4. war page pool
    w, why = choose_war(cfg, wars, date, all_items, war, log)
    log(f"  War section: {w['name']} ({why})")
    war_clusters = [c for c in clusters if any(k in c["title"].lower() for k in w["keywords"])]
    war_clusters.sort(key=lambda c: len(c["sources"]), reverse=True)
    war_top = {id(c) for c in war_clusters[:8]}

    # 5. assign stories to sections
    sections = [s for s in cfg["sections"] if not s.get("war")]
    buckets = {s["name"]: [] for s in sections}
    for c in clusters:
        if id(c) in war_top or (c["hint"] == "WAR SECTION" and c in war_clusters):
            continue
        best = max(sections, key=lambda s: _score(c, s))
        sc = _score(c, best)
        if sc <= 0:
            continue
        c["score"] = sc
        buckets[best["name"]].append(c)
    for name, b in buckets.items():
        b.sort(key=lambda c: (c["score"] * 2 + min(len(c["sources"]), 6) * 2 + (4 if c["kind"] == "pdf" else 0)
                              + (1 if c.get("summary") else 0)), reverse=True)

    # 6. full text for lead stories (free; skipped if blocked)
    if cfg["web"]["enabled"] and cfg["web"]["fetch_articles"] and not no_web:
        kp, snap = cfg["layout"]["max_key_points"], cfg["layout"]["max_snapshot_stories"]
        todo = [c for b in list(buckets.values()) + [war_clusters]
                for c in b[:cfg["web"]["articles_per_section"]] + b[1 + kp:1 + kp + snap + 3] if not c.get("text")]
        todo = list({id(c): c for c in todo}.values())

        def grab(c):
            links = [c.get("link")] + [i.get("link") for i in c["items"]]
            for link in list(dict.fromkeys(l for l in links if l))[:3]:
                txt = sources.fetch_article_text(link, cfg)
                if len(txt) > 300:
                    return txt
            return ""

        with ThreadPoolExecutor(10) as ex:
            for i, (c, txt) in enumerate(zip(todo, ex.map(grab, todo)), 1):
                if txt:
                    c["text"] = txt[:6000]
                progress("Downloading full articles", i, len(todo))
        log(f"  Fetched full text for {sum(1 for c in todo if c.get('text'))}/{len(todo)} lead stories")

    # 7. build pages (AI text, when a model is available, is written first in parallel)
    if writer.llm_ok:
        prewrite(cfg, writer, buckets, w, war_clusters, progress)
    used_facts = set()
    pages = []
    for i, sec in enumerate(cfg["sections"], 1):
        progress(f"Writing page {i}: {sec['name']}", i, len(cfg["sections"]))
        if sec.get("war"):
            pages.append(build_war_page(i, sec, w, why, war_clusters, writer, facts, used_facts, cfg))
        else:
            pages.append(build_page(i, sec, buckets[sec["name"]], writer, facts, used_facts, cfg))

    # 8. corrections, expected items, background files
    corrections = [c for c in load_json(os.path.join(cfg["paths"]["state"], "corrections.json"), [])
                   if not c.get("applied_in")]
    misc = next((p for p in pages if p["name"] == "Miscellaneous"), pages[-1])
    for c in corrections:
        misc["also"].insert(0, f"CORRECTION to {c['for_date']} edition: {c['text']}")
    missing = []
    for e in expect:
        toks = util.tokens(e)
        hit = any(sum(t in util.tokens(c["title"] + " " + c.get("summary", "")) for t in toks) >= max(1, len(toks) * 0.7)
                  for c in clusters)
        if not hit:
            missing.append(e)
            misc["notes"].append(f"Expected '{e}' - not found in today's sources (maybe not announced yet).")
    if background:
        misc["notes"].append("Some uploaded files were from another date and were used only as background.")

    draft = {
        "date": date.isoformat(), "day": util.nice_date(date), "title": cfg["title"],
        "war": {"name": w["name"], "why": why}, "files": files, "missing": missing,
        "corrections": [c["id"] for c in corrections],
        "unknown_abbreviations": sorted(k for k, v in writer.unknown_abbr.items() if v >= 1)[:40],
        "llm_used": writer.llm_ok, "pages": pages,
    }
    old = load_json(draft_path(cfg, date))
    if old:  # keep fields the user edited by hand
        for p_old, p_new in zip(old.get("pages", []), pages):
            for f in p_old.get("locked", []):
                p_new[f] = p_old[f]
            p_new["locked"] = p_old.get("locked", [])
    save_json(draft_path(cfg, date), draft)
    return draft


def _story_ref(c):
    return {"title": c["title"], "sources": c["sources"], "link": c.get("link", ""),
            "verify": len(c["sources"]) < 2, "kind": c["kind"]}


def _confidence(lead):
    n = len(lead["sources"])
    if lead["kind"] == "background":
        return "Low - background only (file from another date)"
    return {1: "Low - single source, verify", 2: "Medium - 2 sources"}.get(n, f"High - {n} sources")


PLACES = ["Pakistan", "China", "Nepal", "Bhutan", "Bangladesh", "Sri Lanka", "Myanmar", "Maldives", "Afghanistan",
          "Russia", "Ukraine", "Iran", "Israel", "Gaza", "Japan", "France", "Germany", "Saudi Arabia", "Yemen",
          "Sudan", "Taiwan", "Qatar", "Canada", "Australia", "Africa", "Europe", "Trump", "Supreme Court"]


def _label(text, glossary):
    """Bold lead-in like the reference editions: 'Bihar: ...', 'RBI: ...', 'UK: ...'."""
    text = re.sub(r"#(\w+)", lambda m: m.group(1).replace("_", " "), text)  # '#Daily_Brief' -> 'Daily Brief'
    if re.match(r"^[A-Za-z][^:]{1,27}:\s", text):
        return text
    best = None
    for st in STATES:
        m = re.search(r"\b" + re.escape(st) + r"\b", text, re.I)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), st.title())
    for name in PLACES + [k for k in glossary if any(ch.isupper() for ch in k) and len(k) <= 7]:
        m = re.search(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    # no label when the text already starts with that word ("US weighs ..." stays as it is)
    return f"{best[1]}: {text}" if best and 0 < best[0] < 120 else text


def _sources(stories):
    """Source names, with edition date and page numbers for uploaded newspapers."""
    order, pages, dates = [], {}, {}
    for c in stories[:8]:
        for it in c.get("items", []):
            s = it["source"]
            if s not in order:
                order.append(s)
            if it.get("page"):
                pages.setdefault(s, set()).add(it["page"])
                dates[s] = it.get("paper_date", "")
    out = []
    for s in order[:8]:
        if s in pages:
            pp = ", ".join(str(p) for p in sorted(pages[s]))
            out.append(f"{s} ({dates[s] + ', ' if dates[s] else ''}pp {pp})")
        else:
            out.append(s)
    return out


def _advanced(fact, page_text, writer, used_words):
    """Exam fact plus one word explained, as in the reference editions."""
    pts = [fact] if fact else []
    low = page_text.lower()
    for w, meaning in writer.hardwords.items():
        if w not in used_words and len(w) > 5 and re.search(r"\b" + re.escape(w) + r"\b", low):
            pts.append(f"{w.capitalize()} means {meaning}.")
            used_words.add(w)
            break
    return pts


def _snapshot_pool(others, lay):
    """Candidates for the 'other stories' cards (a few spares for stories with no readable article)."""
    kp_n, snap_n = lay["max_key_points"], lay["max_snapshot_stories"]
    pool = others[kp_n:kp_n + snap_n + 3]
    return pool if len(pool) >= 2 else others[:snap_n]


def prewrite(cfg, writer, buckets, war, war_clusters, progress):
    """Ask the AI model for all page text at once (a few requests in parallel) instead of one by one;
    build_page then reuses the answers."""
    jobs = []
    for sec in cfg["sections"]:
        if sec.get("war"):
            if war_clusters:
                lead = war_clusters[0]
                jobs.append((writer.paragraph, lead, war_clusters[1:], "WAR SECTION - " + war["name"]))
                if not war.get("india"):
                    jobs.append((writer.benefit, "WAR SECTION", war_clusters,
                                 util.strip_source_suffix(lead["title"])))
            continue
        b = buckets[sec["name"]]
        if not b:
            continue
        headline = util.strip_source_suffix(b[0]["title"]).replace("UPDATE: ", "UPDATE - ")
        jobs.append((writer.paragraph, b[0], b[1:], sec["name"]))
        jobs.append((writer.benefit, sec["name"], b, headline))
        jobs += [(writer.context, c) for c in _snapshot_pool(b[1:], cfg["layout"])]
    with ThreadPoolExecutor(max(1, int(cfg["llm"].get("parallel", 4)))) as ex:
        for i, _ in enumerate(ex.map(lambda j: j[0](*j[1:]), jobs), 1):
            progress("Writing with the AI model", i, len(jobs))


def build_page(n, sec, stories, writer, facts, used_facts, cfg):
    lay = cfg["layout"]
    name = sec["name"]
    page = {"n": n, "name": name, "locked": [], "notes": [], "stories": [_story_ref(c) for c in stories[:12]]}
    if not stories:
        page.update(headline="No major story found for this section today",
                    paragraph="The free sources checked today did not give a clear story for this section. "
                              "Add newspaper PDFs or write your own item with `digest edit`.",
                    tiles=[], flow={"mode": "snapshot", "title": "AT A GLANCE", "steps": []}, key_points=[],
                    full_forms=[], benefit_label="BENEFIT FOR INDIA", benefit=["-"],
                    advanced=pick_fact(facts, name, name, used_facts), also=[], sources=[], confidence="-")
        return page
    lead, others = stories[0], stories[1:]
    used = set()
    headline = util.strip_source_suffix(lead["title"]).replace("UPDATE: ", "UPDATE - ")
    raw_para = writer.paragraph(lead, others, name)
    para = writer.annotate(raw_para, used)
    page_text = " ".join([headline, raw_para] + [o["title"] for o in others[:8]])

    tiles = util.key_figures((lead.get("text") or "") + " " + lead.get("summary", "") + " " + lead["title"],
                             lay["max_tiles"])
    if len(tiles) < 3:
        verified = sum(1 for c in stories if len(c["sources"]) > 1)
        tiles += [{"value": str(len(stories)), "label": "stories today"},
                  {"value": str(len({s for c in stories for s in c["sources"]})), "label": "sources checked"},
                  {"value": str(verified), "label": "stories with 2+ sources"}][:lay["max_tiles"] - len(tiles)]

    def kp(c):
        s = util.sentences(c.get("summary") or "")
        txt = s[0] if s and len(s[0]) < 230 else util.strip_source_suffix(c["title"])
        mark = "" if len(c["sources"]) > 1 else "; verify"
        return _label(writer.annotate(txt, used), writer.glossary) + f" ({', '.join(c['sources'][:2])}{mark})"

    kps = [kp(c) for c in others[:lay["max_key_points"]]]
    kp_n, snap_n = lay["max_key_points"], lay["max_snapshot_stories"]
    pool = _snapshot_pool(others, lay)
    # each card: full headline, then a line break and 2-3 lines saying what the story is about;
    # stories whose article gave no context make way for the next ones
    ctx = [(c, writer.context(c)) for c in pool]
    snap = ([x for x in ctx if x[1]] + [x for x in ctx if not x[1]])[:snap_n]
    steps = [(util.strip_source_suffix(c["title"]) + "\n" + t).strip() for c, t in snap]
    shown = {id(c) for c, _ in snap}
    also = [_label(util.strip_source_suffix(c["title"]), writer.glossary) + ("" if len(c["sources"]) > 1 else " (verify)")
            for c in others[kp_n:] if id(c) not in shown][:lay["max_also"]]
    label, benefit = writer.benefit(name, stories, headline)
    fact = pick_fact(facts, name, page_text, used_facts)
    used_facts.add(fact)
    page.update(
        headline=headline, paragraph=para, tiles=tiles[:lay["max_tiles"]],
        flow={"mode": "snapshot", "title": "OTHER STORIES AT A GLANCE", "steps": steps},
        key_points=kps, full_forms=writer.full_forms_for(page_text)[:lay["max_full_forms"]],
        benefit_label=label, benefit=benefit, advanced=_advanced(fact, page_text, writer, used_facts),
        also=also, sources=_sources(stories),
        confidence=_confidence(lead),
    )
    page["notes"] += _disagreements(lead)
    if len(lead["sources"]) < 2:
        page["headline_verify"] = True
    return page


def build_war_page(n, sec, war, why, stories, writer, facts, used_facts, cfg):
    lay = cfg["layout"]
    used = set()
    page = {"n": n, "name": f"{sec['name']}: {war.get('short', war['name'])}", "locked": [],
            "notes": [f"War chosen: {war['name']} - {why}"],
            "stories": [_story_ref(c) for c in stories[:12]], "war_name": war["name"]}
    timeline = list(war.get("timeline", []))
    latest = stories[0] if stories else None
    room = 8 - (1 if latest else 0)
    steps = timeline[-room:] if len(timeline) > room else timeline
    if latest:
        steps.append("Now: " + util.strip_source_suffix(latest["title"]))
    if latest:
        raw = writer.paragraph(latest, stories[1:], "WAR SECTION - " + war["name"])
        headline = util.strip_source_suffix(latest["title"])
    else:
        raw = (f"No fresh {war['name']} story was found in today's free sources; the flowchart shows the "
               "background only. Check again or add newspaper PDFs.")
        headline = war["name"]
    page_text = " ".join([headline, raw] + [c["title"] for c in stories[:8]] + timeline)
    kps = []
    for c in stories[1:lay["max_key_points"] + 1]:
        mark = "" if len(c["sources"]) > 1 else "; verify"
        kps.append(_label(writer.annotate(util.strip_source_suffix(c["title"]), used), writer.glossary) + f" ({', '.join(c['sources'][:2])}{mark})")
    tiles = util.key_figures(" ".join((c.get("text") or c.get("summary") or c["title"]) for c in stories[:3]),
                             lay["max_tiles"])
    if len(tiles) < 3:
        tiles += [{"value": str(len(stories)), "label": "headlines today"},
                  {"value": str(len({s for c in stories for s in c["sources"]})), "label": "sources"},
                  {"value": timeline[0].split(":")[0] if timeline else "-", "label": "first event"}][:lay["max_tiles"] - len(tiles)]
    # India notes for each war are written into wars.json; fall back to sentences from the articles
    benefit = war.get("india") or writer.benefit("WAR SECTION", stories, headline)[1]
    war_text = " ".join([war["name"]] + war.get("keywords", []) + [headline])
    fact = pick_fact(facts, "WAR SECTION", war_text, used_facts) or pick_fact(facts, "WAR SECTION", page_text, used_facts)
    used_facts.add(fact)
    page.update(
        headline=headline, paragraph=writer.annotate(raw, used), tiles=tiles[:lay["max_tiles"]],
        flow={"mode": "flow", "title": "HOW IT STARTED AND MAIN EVENTS", "steps": steps},
        key_points=kps, full_forms=writer.full_forms_for(page_text, war.get("full_forms", []))[:lay["max_full_forms"]],
        benefit_label="WHY IT MATTERS FOR INDIA", benefit=benefit,
        advanced=_advanced(fact, page_text, writer, used_facts),
        also=[_label(util.strip_source_suffix(c["title"]), writer.glossary) + ("" if len(c["sources"]) > 1 else " (verify)")
              for c in stories[lay["max_key_points"] + 1:lay["max_key_points"] + 3]] +
             ["Wars covered recently: " + ", ".join(
                 f"{util.parse_date(k).strftime('%d %b')}: {v.split(' (')[0]}"
                 for k, v in sorted(load_war_log(cfg).items())[-3:])],
        sources=_sources(stories) + ["Background timeline: built-in history notes (wars.json)"],
        confidence=_confidence(latest) if latest else "Background only",
    )
    if latest:
        page["notes"] += _disagreements(latest)
    return page


def load_war_log(cfg):
    return load_json(user_file(cfg, "wars.json"), {}).get("log", {})
