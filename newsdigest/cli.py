"""news-digest: free daily current-affairs PDF digest for competitive / defence exams.

Run `digest` with no arguments for the menu, or `digest <command> -h` for help.
Add --plain to any command to turn off colours and animations."""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

from . import draft as D
from . import render, ui, util
from .config import (DEFAULT_CONFIG, load_config, load_json, read_user_config, save_config, save_json,
                     user_file)


# ------------------------------------------------------------------ helpers
def parse_day(s):
    s = (s or "today").strip().lower()
    today = dt.date.today()
    if s == "today":
        return today
    if s == "yesterday":
        return today - dt.timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%d %b", "%d %B"):
        try:
            d = dt.datetime.strptime(s, fmt).date()
            return d.replace(year=today.year) if "%Y" not in fmt else d
        except ValueError:
            pass
    raise SystemExit(f"Could not read the date '{s}'. Use YYYY-MM-DD, e.g. {today.isoformat()}")


def find_page(draft, key):
    for p in draft["pages"]:
        if str(p["n"]) == str(key) or p["name"].lower().startswith(str(key).lower()):
            return p
    raise SystemExit(f"No page '{key}'. Use a number 1-{len(draft['pages'])} or a section name.")


def open_file(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])
    except Exception as e:
        print(f"(Could not open automatically: {e})")


def out_pdf(cfg, date):
    name = re.sub(r"[^A-Za-z0-9]+", "_", cfg["title"]).strip("_")
    return os.path.join(cfg["paths"]["output"], f"{name}_{date.isoformat()}.pdf")


def set_by_path(obj, path, value):
    keys = path.split(".")
    for k in keys[:-1]:
        obj = obj.setdefault(k, {})
    obj[keys[-1]] = value


def get_by_path(obj, path):
    for k in path.split("."):
        obj = obj[int(k)] if isinstance(obj, list) else obj[k]
    return obj


def coerce(v):
    try:
        return json.loads(v)
    except (ValueError, TypeError):
        return v


# ------------------------------------------------------------------ main commands
def cmd_init(cfg, a):
    if os.path.exists(os.path.join(os.path.dirname(cfg["paths"]["inbox"]), "config.json")) and not a.force:
        print("config.json already exists (use --force to reset it to defaults).")
    else:
        save_config(DEFAULT_CONFIG)
        ui.ok("Wrote config.json with all default settings.")
    for k, p in cfg["paths"].items():
        print(f"  {k:9} -> {p}")
    print("\nDrop newspaper PDFs into the 'inbox' folder, then run:  digest run today")


def cmd_collect(cfg, a):
    if a.llm:
        cfg["llm"]["mode"] = a.llm
    date = parse_day(a.date)
    with ui.Loader(f"Collecting news for {util.nice_date(date)}") as ld:
        d = D.collect(cfg, date, pdfs=a.pdf or [], war=a.war, expect=a.expect or [], no_web=a.no_web,
                      log=ld.log, progress=ld.progress, headline=ld.headline)
    summary(d)
    print()
    ui.ok(f"Draft saved: {D.draft_path(cfg, date)}")
    print(ui.c("Edit anything with `digest edit`, `digest open`, then make the PDF with `digest build`.", "grey"))
    return d


def summary(d):
    print("")
    for f in d.get("files", []):
        print(ui.c(f"  FILE {f['file']}: {f['status']}", "green" if "match" in f["status"] else "yellow"))
    import shutil
    hw = max(30, min(72, shutil.get_terminal_size((120, 24)).columns - 66))  # fit the terminal width
    print(ui.c(f"  {'#':>2}  {'SECTION':<30} {'LEAD HEADLINE':<{hw}} CONFIDENCE", "grey", bold=True))
    for p in d["pages"]:
        num = ui.c(f"{p['n']:>2}", "orange", bold=True)
        name = ui.c(f"{util.short(p['name'], 30):<30}", "sky")
        conf = util.short(p.get("confidence", "-"), 26)
        print(f"  {num}. {name} {util.short(p['headline'], hw - 2):<{hw}} [{ui.confidence(conf)}]")
    if d.get("missing"):
        print()
        ui.warn("Not found in sources: " + "; ".join(d["missing"]))
    if d.get("unknown_abbreviations"):
        print()
        ui.warn("Abbreviations with no full form yet (add with `digest glossary add`): "
                + ", ".join(d["unknown_abbreviations"][:20]))


def cmd_build(cfg, a):
    date = parse_day(a.date)
    d = D.load_draft(cfg, date)
    out = a.out or out_pdf(cfg, date)
    with ui.Loader(f"Building the PDF for {d['day']}", min_seconds=cfg.get("ui", {}).get("min_build_seconds", 4)) as ld:
        for p in d["pages"]:  # the monitor shows the 12 lead headlines going into the PDF
            m = re.search(r"(\d+) sources", p.get("confidence", ""))
            hot = (m is not None and int(m.group(1)) >= 6) or bool(D.HOT_RE.search(p["headline"]))
            ld.headline(p["headline"], f"page {p['n']}", "WAR" if p["n"] == len(d["pages"]) else p["name"], hot)
        render.render(cfg, d, out, progress=ld.progress)
        record_history(cfg, d)
    if a.text:
        tp = os.path.splitext(out)[0] + ".txt"
        with open(tp, "w", encoding="utf-8") as f:
            f.write(render.text_digest(d))
        ui.ok(f"Text version: {tp}")
    ui.rocket(f"PDF ready: {out}")
    if a.open:
        open_file(out)


def record_history(cfg, d):
    hp = os.path.join(cfg["paths"]["state"], "history.json")
    hist = load_json(hp, {})
    hist[d["date"]] = {"titles": [p["headline"] for p in d["pages"]] +
                                 [s["title"] for p in d["pages"] for s in p.get("stories", [])[:6]],
                       "war": d["war"]["name"], "built": dt.datetime.now().isoformat(timespec="seconds")}
    save_json(hp, hist)
    wp = user_file(cfg, "wars.json")
    wars = load_json(wp, {})
    wars.setdefault("log", {})[d["date"]] = d["war"]["name"]
    save_json(wp, wars)
    cp = os.path.join(cfg["paths"]["state"], "corrections.json")
    corr = load_json(cp, [])
    for c in corr:
        if c["id"] in d.get("corrections", []):
            c["applied_in"] = d["date"]
    save_json(cp, corr)


def cmd_run(cfg, a):
    cmd_collect(cfg, a)
    a.out = None
    cmd_build(cfg, a)


def cmd_text(cfg, a):
    date = parse_day(a.date)
    t = render.text_digest(D.load_draft(cfg, date))
    print(t)
    if a.save:
        p = os.path.splitext(out_pdf(cfg, date))[0] + ".txt"
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
        print(f"\nSaved: {p}")


def cmd_show(cfg, a):
    d = D.load_draft(cfg, parse_day(a.date))
    if not a.page:
        summary(d)
        return
    p = find_page(d, a.page)
    print(json.dumps({k: v for k, v in p.items() if k != "stories"}, indent=2, ensure_ascii=False))
    print("\nStories found for this page (use `digest edit ... --use N` to make one the lead):")
    for i, s in enumerate(p.get("stories", []), 1):
        print(f"  [{i}] {s['title']}  ({', '.join(s['sources'])}{'; verify' if s['verify'] else ''})")


LIST_FIELDS = {"key_points", "benefit", "also", "sources", "notes", "flow.steps", "tiles", "full_forms"}
TEXT_FIELDS = {"headline", "paragraph", "advanced", "benefit_label", "confidence", "flow.title", "flow.mode", "name"}


def cmd_edit(cfg, a):
    date = parse_day(a.date)
    d = D.load_draft(cfg, date)
    p = find_page(d, a.page)
    if a.value_opt is not None:
        a.value = a.value_opt
    field = a.field.replace("-", "_").replace("steps", "flow.steps") if a.field else None
    if field == "flow.flow.steps":
        field = "flow.steps"
    if a.use:
        st = p["stories"][a.use - 1]
        p["headline"] = st["title"]
        p["headline_verify"] = st["verify"]
        ui.ok(f"Lead headline set to story [{a.use}]. (Paragraph unchanged - edit it with `paragraph`.)")
        field = "headline"
    elif field in TEXT_FIELDS:
        if a.value is None:
            raise SystemExit("Give the new text, e.g.: digest edit today 4 headline \"New headline\"")
        val = a.value
        if field == "paragraph" and not a.raw:
            w = _writer(cfg)
            have = {f["abbr"] for f in p.get("full_forms", [])}
            p.setdefault("full_forms", []).extend(f for f in w.full_forms_for(val) if f["abbr"] not in have)
            val = w.annotate(val)
        set_by_path(p, field, val)
        if field == "headline":
            p["headline_verify"] = a.verify
    elif field in LIST_FIELDS:
        cur = get_by_path(p, field)
        if a.add is not None:
            cur.append(_list_value(cfg, field, a.add, a.raw))
        elif a.remove is not None:
            cur.pop(a.remove - 1)
        elif a.value is not None:
            cur[:] = [_list_value(cfg, field, v.strip(), a.raw) for v in a.value.split("|") if v.strip()]
        else:
            for i, v in enumerate(cur, 1):
                print(f"  [{i}] {v}")
            return
    else:
        raise SystemExit("Field must be one of: " + ", ".join(sorted(TEXT_FIELDS | LIST_FIELDS)))
    lock = field.split(".")[0]
    if lock not in p["locked"]:
        p["locked"].append(lock)
    save_json(D.draft_path(cfg, date), d)
    ui.ok(f"Updated page {p['n']} ({p['name']}) -> {field}. Run `digest build {date}` to remake the PDF.")


def _writer(cfg):
    from .writer import Writer
    return Writer(cfg, load_json(user_file(cfg, "glossary.json"), {}),
                  load_json(user_file(cfg, "hardwords.json"), {}), log=lambda *x: None)


def _list_value(cfg, field, v, raw):
    if field == "tiles":
        val, _, label = v.partition("|") if "|" in v else v.partition("=")
        return {"value": val.strip(), "label": label.strip()}
    if field == "full_forms":
        g = load_json(user_file(cfg, "glossary.json"), {})
        if v not in g:
            raise SystemExit(f"'{v}' is not in the glossary. Add it first: digest glossary add {v} \"Full\" \"what it does\"")
        return {"abbr": v, **g[v]}
    if field in ("key_points", "benefit") and not raw:
        return _writer(cfg).annotate(v)
    return v


def cmd_open(cfg, a):
    p = D.draft_path(cfg, parse_day(a.date))
    if not os.path.exists(p):
        raise SystemExit("No draft yet; run `digest collect` first.")
    print(f"Opening {p}  (after editing, run `digest build`)")
    if sys.platform.startswith("win"):
        subprocess.Popen(["notepad.exe", p])
    else:
        open_file(p)


def cmd_check(cfg, a):
    d = D.load_draft(cfg, parse_day(a.date))
    problems = 0
    for p in d["pages"]:
        issues = []
        if p["headline"].startswith("No major story"):
            issues.append("no story found")
        if "single source" in p.get("confidence", "").lower():
            issues.append("lead story is single-source (verify)")
        if p.get("notes"):
            issues += p["notes"]
        if not p.get("full_forms"):
            issues.append("no full forms")
        if p.get("benefit", [""])[0].startswith("No direct India angle"):
            issues.append("benefit/why-it-matters needs writing")
        if issues:
            problems += 1
            print(f"  {p['n']:>2}. {p['name']}: " + "; ".join(issues))
    if d.get("unknown_abbreviations"):
        print("  Unknown abbreviations: " + ", ".join(d["unknown_abbreviations"]))
    for f in d.get("files", []):
        if "match" not in f["status"]:
            print(f"  FILE {f['file']}: {f['status']}")
    print("All pages look fine." if not problems else f"\n{problems} page(s) worth a look before building.")


def cmd_files(cfg, a):
    date = parse_day(a.date)
    from .sources import read_pdfs
    import glob
    paths = a.pdf or sorted(glob.glob(os.path.join(cfg["paths"]["inbox"], "*.pdf")))
    if not paths:
        print("No PDFs given and the inbox folder is empty.")
        return
    _, _, rep = read_pdfs(paths, date, print)


def cmd_correct(cfg, a):
    cp = os.path.join(cfg["paths"]["state"], "corrections.json")
    corr = load_json(cp, [])
    corr.append({"id": len(corr) + 1, "for_date": parse_day(a.for_date).isoformat(), "text": a.text,
                 "added": dt.date.today().isoformat(), "applied_in": None})
    save_json(cp, corr)
    ui.ok("Correction saved; it will appear on the Miscellaneous page of the next edition you collect.")


def cmd_history(cfg, a):
    hist = load_json(os.path.join(cfg["paths"]["state"], "history.json"), {})
    for k in sorted(hist)[-a.n:]:
        print(f"  {k}: war = {hist[k].get('war')}, {len(hist[k].get('titles', []))} stories recorded")
    if not hist:
        print("No editions built yet.")


# ------------------------------------------------------------------ knowledge / customisation tools
def cmd_glossary(cfg, a):
    path = user_file(cfg, "glossary.json")
    g = load_json(path, {})
    if a.action == "add":
        g[a.abbr] = {"full": a.full, "does": a.does or ""}
        save_json(path, g)
        ui.ok(f"Added {a.abbr} = {a.full} ({a.does})")
    elif a.action == "remove":
        print("Removed." if g.pop(a.abbr, None) else "Not found.")
        save_json(path, g)
    elif a.action == "list":
        for k in sorted(g, key=str.lower):
            if not a.abbr or a.abbr.lower() in (k + g[k]["full"]).lower():
                print(f"  {k:<10} {g[k]['full']} - {g[k]['does']}")
    elif a.action == "lookup":
        txt = wiki_summary(a.abbr)
        print(txt or "Nothing found on Wikipedia.")
        if txt and a.save:
            full = a.full or txt.split(" is ")[0].split(" was ")[0][:80]
            g[a.abbr] = {"full": full, "does": util.short(txt, 90)}
            save_json(path, g)
            ui.ok(f"Saved {a.abbr} = {full}  (check it; edit with `glossary add`)")


def wiki_summary(term):
    """Free Wikipedia REST API, no key needed."""
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(term.replace(" ", "_"))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "news-digest-cli/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if data.get("type") == "disambiguation":
            return f"'{term}' has several meanings on Wikipedia; search a fuller name instead."
        return util.sentences(data.get("extract", ""))[0] if data.get("extract") else ""
    except Exception as e:
        return f"(lookup failed: {e})"


def cmd_words(cfg, a):
    path = user_file(cfg, "hardwords.json")
    w = load_json(path, {})
    if a.action == "add":
        w[a.word.lower()] = a.meaning
        save_json(path, w)
        ui.ok(f"Added: {a.word} ({a.meaning})")
    elif a.action == "remove":
        print("Removed." if w.pop(a.word.lower(), None) else "Not found.")
        save_json(path, w)
    else:
        for k in sorted(w):
            print(f"  {k:<18} {w[k]}")


def cmd_facts(cfg, a):
    path = user_file(cfg, "facts.json")
    f = load_json(path, [])
    if a.action == "add":
        item = {"fact": a.text}
        if a.keys:
            item["keys"] = [k.strip().lower() for k in a.keys.split(",")]
        if a.section:
            item["section"] = a.section
        if not (a.keys or a.section):
            raise SystemExit("Give --keys (words that trigger the fact) and/or --section.")
        f.append(item)
        save_json(path, f)
        ui.ok("Fact added.")
    elif a.action == "remove":
        f.pop(int(a.text) - 1)
        save_json(path, f)
        print("Removed.")
    else:
        for i, x in enumerate(f, 1):
            if not a.text or a.text.lower() in json.dumps(x).lower():
                print(f"  [{i}] ({', '.join(x.get('keys', [])) or x.get('section')}) {x['fact']}")


def cmd_war(cfg, a):
    path = user_file(cfg, "wars.json")
    w = load_json(path, {"wars": [], "log": {}})

    def find(n, required=False):
        x = next((x for x in w["wars"] if n and n.lower() in x["name"].lower()), None)
        if required and not x:
            raise SystemExit(f"No war matching '{n}'. See `digest war list`.")
        return x
    if a.action == "list":
        for x in w["wars"]:
            last = max((k for k, v in w["log"].items() if v == x["name"]), default="never")
            print(f"  {x['name']:<45} last covered: {last}")
    elif a.action == "log":
        for k in sorted(w["log"]):
            print(f"  {k}: {w['log'][k]}")
    elif a.action == "show":
        x = find(a.name, required=True)
        print(json.dumps(x, indent=2, ensure_ascii=False))
    elif a.action == "add":
        if find(a.name):
            raise SystemExit("Already exists.")
        w["wars"].append({"name": a.name, "query": a.query or a.name,
                          "keywords": [k.strip().lower() for k in (a.keywords or a.name).split(",")],
                          "timeline": [], "full_forms": []})
        save_json(path, w)
        ui.ok(f"Added war '{a.name}'. Add history steps with: digest war add-event \"{a.name}\" \"Mon YYYY: what happened\"")
    elif a.action == "add-event":
        x = find(a.name, required=True)
        x["timeline"].append(a.query)
        save_json(path, w)
        ui.ok(f"Added event to {x['name']} ({len(x['timeline'])} steps).")
    elif a.action == "set-log":
        w["log"][parse_day(a.query).isoformat()] = (find(a.name) or {"name": a.name})["name"]
        save_json(path, w)
        ui.ok("War log updated.")


def cmd_feeds(cfg, a):
    user = read_user_config()
    feeds = user.get("feeds", DEFAULT_CONFIG["feeds"])
    if a.action == "list":
        for i, f in enumerate(feeds, 1):
            print(f"  [{i}] {f['name']:<16} {f.get('hint', ''):<28} {f['url']}")
        return
    if a.action == "add":
        feeds.append({"name": a.name, "url": a.url, "hint": a.hint or ""})
    elif a.action == "remove":
        feeds.pop(int(a.name) - 1)
    elif a.action == "test":
        import feedparser
        for f in feeds:
            n = len(feedparser.parse(f["url"], agent=cfg["web"]["user_agent"]).entries)
            print(f"  {'OK ' if n else 'BAD'} {n:>4} items  {f['name']} {f['url']}")
        return
    user["feeds"] = feeds
    save_config(user)
    ui.ok("Feeds updated.")


def cmd_section(cfg, a):
    user = read_user_config()
    secs = user.get("sections", DEFAULT_CONFIG["sections"])
    if a.action == "list":
        for i, s in enumerate(secs, 1):
            extra = "war page" if s.get("war") else f"{len(s.get('keywords', []))} keywords, queries: {s.get('queries', [])}"
            print(f"  {i:>2}. {s['name']:<30} {extra}")
        return
    s = secs[int(a.n) - 1]
    if a.action == "rename":
        s["name"] = a.value
    elif a.action == "keywords":
        s.setdefault("keywords", []).extend(k.strip().lower() for k in a.value.split(","))
    elif a.action == "unkeyword":
        s["keywords"] = [k for k in s.get("keywords", []) if k not in {x.strip().lower() for x in a.value.split(",")}]
    elif a.action == "query":
        s.setdefault("queries", []).append(a.value)
    elif a.action == "move":
        secs.insert(int(a.value) - 1, secs.pop(int(a.n) - 1))
    user["sections"] = secs
    save_config(user)
    ui.ok("Sections updated (takes effect from the next `collect`).")


def cmd_config(cfg, a):
    user = read_user_config()
    if a.action == "show":
        print(json.dumps(get_by_path(cfg, a.key) if a.key else
                         {k: v for k, v in cfg.items() if k not in ("feeds", "sections")}, indent=2, ensure_ascii=False))
    elif a.action == "set":
        set_by_path(user, a.key, coerce(a.value))
        save_config(user)
        ui.ok(f"Set {a.key} = {coerce(a.value)!r}")
    elif a.action == "reset":
        save_config({} if not a.key else {k: v for k, v in user.items() if k != a.key})
        print("Reset to defaults." if not a.key else f"Reset {a.key}.")


# ------------------------------------------------------------------ simple menu
def menu(cfg):
    ui.banner()
    opts = [("Make today's PDF (collect + build)", ["run", "today", "--open"]),
            ("Make PDF for another date / choose the war", "date"),
            ("Add newspaper PDFs and make today's PDF", "pdf"),
            ("Collect only (then edit before building)", ["collect", "today"]),
            ("Build PDF from today's draft", ["build", "today", "--open"]),
            ("Check today's draft for problems", ["check", "today"]),
            ("Show today's pages", ["show", "today"]),
            ("Text-only bullet version of today", ["text", "today"]),
            ("Open today's draft in Notepad", ["open", "today"]),
            ("Quit", [])]
    while True:
        ch = ui.choose("What would you like to do?", [t for t, _ in opts])
        if ch is None or not opts[ch][1]:
            print(ui.c("  Bye! Good luck with your preparation.", "orange", bold=True))
            return
        args = opts[ch][1]
        if args == "date":
            day = ui.ask("Date (YYYY-MM-DD, Enter = today): ", "today")
            war = ui.ask("War for page 12 (Enter = auto): ")
            args = ["run", day, "--open"] + (["--war", war] if war else [])
        elif args == "pdf":
            paths = ui.ask("PDF file path(s), separated by ; : ")
            args = ["run", "today", "--open", "--pdf"] + [p.strip().strip('"') for p in paths.split(";") if p.strip()]
        print()
        try:
            main(args)
        except SystemExit as e:
            if isinstance(e.code, str):
                ui.err(e.code)
        print()
        if not sys.stdin.isatty():
            return
        ui.ask("Press Enter to go back to the menu ")
        print()


# ------------------------------------------------------------------ argument parser
def build_parser():
    ap = argparse.ArgumentParser(prog="digest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd")

    def dated(name, help_, fn):
        p = sp.add_parser(name, help=help_)
        p.add_argument("date", nargs="?", default="today", help="today | yesterday | YYYY-MM-DD")
        p.set_defaults(fn=fn)
        return p

    p = sp.add_parser("init", help="create config.json and folders")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_init)

    for name, fn, h in (("collect", cmd_collect, "gather news and write an editable draft"),
                        ("run", cmd_run, "collect + build in one go")):
        p = dated(name, h, fn)
        p.add_argument("--pdf", nargs="*", help="newspaper / ACC PDF files (inbox/*.pdf are always read)")
        p.add_argument("--war", help="war for page 12, e.g. 'Sudan' (default: auto, rotated)")
        p.add_argument("--expect", nargs="*", help="items you expect today; reported if missing")
        p.add_argument("--no-web", action="store_true", help="use only the PDFs, no internet")
        p.add_argument("--llm", choices=["auto", "on", "off"], help="free local Ollama rewriting")
        if name == "run":
            p.add_argument("--open", action="store_true", help="open the PDF when done")
            p.add_argument("--text", action="store_true", help="also save a bullet-point .txt")

    p = dated("build", "render the PDF from the draft", cmd_build)
    p.add_argument("--out", help="output file")
    p.add_argument("--open", action="store_true")
    p.add_argument("--text", action="store_true", help="also save a bullet-point .txt")

    p = dated("text", "bullet-point text version", cmd_text)
    p.add_argument("--save", action="store_true")
    p = dated("show", "list pages, or show one page's content", cmd_show)
    p.add_argument("page", nargs="?", help="page number or name")
    dated("open", "open the draft JSON in Notepad", cmd_open)
    dated("check", "find weak spots in the draft", cmd_check)
    p = dated("files", "check uploaded PDFs' dates", cmd_files)
    p.add_argument("--pdf", nargs="*")

    p = sp.add_parser("edit", help="change any part of a page in the draft",
                      description="Examples:\n"
                                  "  digest edit today 4 headline \"Navy commissions new frigate\"\n"
                                  "  digest edit today Defence paragraph \"...\"\n"
                                  "  digest edit today 6 tiles --add \"6.5%|repo rate\"\n"
                                  "  digest edit today 12 steps --value \"Step one|Step two|Step three\"\n"
                                  "  digest edit today 3 flow.mode flow\n"
                                  "  digest edit today 1 key_points --remove 2\n"
                                  "  digest edit today 9 --use 3   (make story 3 the lead)",
                      formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("date")
    p.add_argument("page")
    p.add_argument("field", nargs="?", help="headline paragraph advanced benefit_label confidence flow.title "
                                            "flow.mode | key_points benefit also sources notes steps tiles full_forms")
    p.add_argument("value", nargs="?", help="new text (for lists: items separated by |)")
    p.add_argument("--value", dest="value_opt", help="same as giving VALUE")
    p.add_argument("--add")
    p.add_argument("--remove", type=int)
    p.add_argument("--use", type=int, help="make story N (see `digest show DATE PAGE`) the lead headline")
    p.add_argument("--raw", action="store_true", help="don't auto-add meanings/full forms")
    p.add_argument("--verify", action="store_true", help="mark the new headline 'verify'")
    p.set_defaults(fn=cmd_edit)

    p = sp.add_parser("correct", help="note a correction to an earlier edition")
    p.add_argument("for_date")
    p.add_argument("text")
    p.set_defaults(fn=cmd_correct)
    p = sp.add_parser("history", help="past editions")
    p.add_argument("-n", type=int, default=10)
    p.set_defaults(fn=cmd_history)

    p = sp.add_parser("glossary", help="abbreviation full forms: add/remove/list/lookup")
    p.add_argument("action", choices=["add", "remove", "list", "lookup"])
    p.add_argument("abbr", nargs="?")
    p.add_argument("full", nargs="?")
    p.add_argument("does", nargs="?", help="what it does (short)")
    p.add_argument("--save", action="store_true", help="with lookup: save the Wikipedia result")
    p.set_defaults(fn=cmd_glossary)

    p = sp.add_parser("words", help="hard-word meanings: add/remove/list")
    p.add_argument("action", choices=["add", "remove", "list"])
    p.add_argument("word", nargs="?")
    p.add_argument("meaning", nargs="?")
    p.set_defaults(fn=cmd_words)

    p = sp.add_parser("facts", help="'Advanced point' fact bank: add/remove/list")
    p.add_argument("action", choices=["add", "remove", "list"])
    p.add_argument("text", nargs="?")
    p.add_argument("--keys", help="comma-separated trigger words")
    p.add_argument("--section")
    p.set_defaults(fn=cmd_facts)

    p = sp.add_parser("war", help="war list for page 12: list/log/show/add/add-event/set-log")
    p.add_argument("action", choices=["list", "log", "show", "add", "add-event", "set-log"])
    p.add_argument("name", nargs="?")
    p.add_argument("query", nargs="?", help="search query (add) | event text (add-event) | date (set-log)")
    p.add_argument("--keywords", help="comma-separated words (add)")
    p.set_defaults(fn=cmd_war)

    p = sp.add_parser("feeds", help="news feeds: list/add/remove/test")
    p.add_argument("action", choices=["list", "add", "remove", "test"])
    p.add_argument("name", nargs="?", help="feed name (add) or number (remove)")
    p.add_argument("url", nargs="?")
    p.add_argument("--hint", help="section this feed usually belongs to")
    p.set_defaults(fn=cmd_feeds)

    p = sp.add_parser("section", help="sections: list/rename/keywords/unkeyword/query/move")
    p.add_argument("action", choices=["list", "rename", "keywords", "unkeyword", "query", "move"])
    p.add_argument("n", nargs="?", help="section number")
    p.add_argument("value", nargs="?")
    p.set_defaults(fn=cmd_section)

    p = sp.add_parser("config", help="settings: show/set/reset (e.g. config set colors.navy \"#123456\")")
    p.add_argument("action", choices=["show", "set", "reset"])
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(fn=cmd_config)
    return ap


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    plain = any(x in argv for x in ("--plain", "--no-anim"))
    argv = [x for x in argv if x not in ("--plain", "--no-anim")]
    cfg = load_config()
    ui.setup(cfg, plain)
    try:
        if not argv:
            return menu(cfg)
        a = build_parser().parse_args(argv)
        if not getattr(a, "fn", None):
            ui.banner()
            build_parser().print_help()
            return
        a.fn(cfg, a)
    except KeyboardInterrupt:
        sys.stdout.write("\x1b[?25h" if ui.STATE["color"] else "")
        print()
        ui.warn("Stopped.")
        raise SystemExit(130)
    except SystemExit as e:
        if isinstance(e.code, str):  # our own error messages: show them in red
            ui.err(e.code)
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
