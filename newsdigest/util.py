import datetime as dt
import html
import re

STOP = set("""a an the of to in on for and or but with at by from as is are was were be been it its this that these those
into over after before about than amid says said say will would can could may might new has have had not no his her their
our we you they he she who what when where why how all more most also up out off said india's indian india""".split())

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9


def clean_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", " - ").replace("�", "'").replace("­", "")  # soft hyphen
    s = re.sub(r"#(\w+)", lambda m: m.group(1).replace("_", " "), s)  # '#Daily_Brief' -> 'Daily Brief'
    return re.sub(r"\s+", " ", s).strip()


def strip_source_suffix(title):
    """Google News titles end with ' - Publisher' (some sites add ' | Publisher')."""
    title = re.sub(r"\s+\|\s+[^|]{2,40}$", "", title)
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", title).strip()


CUT_END = re.compile(r"(\.\.\.|…|\[…\]|\[\.\.\.\])\s*$")


def is_cut(text):
    """True for feed snippets that stop mid-sentence ('... sent to the...')."""
    return bool(CUT_END.search(text or ""))


def tidy_cut(text):
    """A feed title cut by the publisher ('... IAF's new satellite, Agniv...') ends at its last full phrase."""
    if not is_cut(text):
        return text
    body = CUT_END.sub("", text).rstrip()
    m = list(re.finditer(r"[.?!:;,](?=\s)", body))
    if m and m[-1].end() >= len(body) * 0.4:
        return body[:m[-1].end()].rstrip(",;:")
    return body.rsplit(" ", 1)[0].rstrip(",;:-") if " " in body else body


CREDIT_RE = re.compile(r"\|?\s*((photo|image|picture|video)\s*(credit|courtesy|source)s?|file (photo|image|picture))\s*:\s*"
                       r"(special arrangement|getty images|\S+)", re.I)
JUNK_SENT = re.compile(r"(sign ?in|sign up|subscribe|unlock|download the app|click here|newsletter|read more|"
                       r"also read|follow us|log ?in to|whatsapp channel|google news|all rights reserved|"
                       r"cookie|advertisement|watch the video|listen to|report feedback|"
                       r"thank you for your feedback|feedback has been|translated by ai|share this (article|story)|copy link|"
                       r"font size|story continues|trending now)", re.I)
# "Newswise - ATLANTA - ", "NEW DELHI (PTI): ", "THE SI DIPLOMAT Donald Trump ..." (caps kicker before the text)
DATELINE = re.compile(r"^(?:[A-Z][\w.]+\s+-\s+)?(?:[A-Z][A-Z .,/]{2,40}(?:\(\w+\))?\s*[:\-]\s+|(?:[A-Z]{2,}\s+){3,}(?=[A-Z][a-z]))")


def is_english(text):
    """False for text that is partly in another script (the PDF font can't show it)."""
    letters = re.findall(r"[^\W\d_]", text)
    return bool(letters) and sum(1 for ch in letters if ch.isascii() or ch in "éèàçñüöäóíá") / len(letters) > 0.97


def sentences(text):
    """Split into sentences, dropping photo credits, website buttons, other-language notices,
    half sentences and repeated sentences."""
    text = CREDIT_RE.sub(" ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+×\s+", " ¶ ", text)  # a website close button glued between two sentences
    parts = re.split(r"(?<=[.!?।])\s+(?=[A-Z\"'(])|\s*¶\s*", text)
    out = []
    for p in parts:
        p = re.sub(r"^Loading\W*", "", p.strip(" |"))  # web-page spinner text before the article
        p = DATELINE.sub("", p)
        if len(p) <= 25 or JUNK_SENT.search(p) or is_cut(p) or not is_english(p):
            continue
        if not re.search(r"[.!?][\"'’”)]*$", p):  # a half sentence (text cut off, or a menu/button label)
            continue
        if any(similarity(p, q) > 0.8 for q in out):
            continue
        out.append(p)
    return out


def tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 2]


def similarity(a, b):
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb)) * 0.5 + len(ta & tb) / len(ta | tb) * 0.5


def parse_date(s):
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def nice_date(d):
    return d.strftime("%A, %d %B %Y").replace(" 0", " ")


def find_dates(text):
    """All calendar dates written in the text (e.g. 'October 17, 2026', '17 Oct 2026', '17-10-2026')."""
    out = []
    t = text.lower()
    for m in re.finditer(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?,?\s+(20\d\d)\b", t):
        mo = MONTHS.get(m.group(2))
        if mo:
            out.append((int(m.group(3)), mo, int(m.group(1))))
    for m in re.finditer(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", t):
        mo = MONTHS.get(m.group(1))
        if mo:
            out.append((int(m.group(3)), mo, int(m.group(2))))
    for m in re.finditer(r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d\d)\b", t):
        out.append((int(m.group(3)), int(m.group(2)), int(m.group(1))))
    res = []
    for y, mo, d in out:
        try:
            res.append(dt.date(y, mo, d))
        except ValueError:
            pass
    return res


NUM_RE = re.compile(
    r"(?P<cur>₹|Rs\.?\s?|USD\s?|INR\s?|\$|US\$|€|£)?\s?(?P<num>\d{1,3}(?:,\d{2,3})+|\d+(?:\.\d+)?)[\s-]?"
    r"(?P<unit>%|per cent|percent|crore|lakh|billion|million|trillion|bn|km|kilometres|tonnes|MW|GW|"
    r"bps|basis points|years?|days?|people|killed|dead|soldiers|troops|drones|missiles|aircraft|jets|"
    r"satellites|seats|votes|states|countries|nations|children|students|passengers|families|villages|"
    r"workers|civilians|Indians|ships|vessels|patients|cases|deaths|injured|wounded|hostages|refugees)?\b", re.I)

LINK = {"is", "was", "were", "are", "has", "have", "had", "for", "in", "to", "of", "the", "and", "on", "at",
        "from", "by", "with", "as", "a", "an", "that", "which", "this", "it", "be", "been", "will", "would",
        "while", "but", "or", "so", "than", "about"}


def _figure_label(s, m):
    """Words that say what a number is: '13 people were killed' -> 'killed'."""
    after = re.findall(r"[A-Za-z][A-Za-z\-']*", re.split(r"[,.;:()\"]", s[m.end():], 1)[0])[:4]
    before = re.findall(r"[A-Za-z][A-Za-z\-']*", re.split(r"[,.;:()\"]", s[:m.start()])[-1])
    if after and after[0].lower() in {"is", "was", "were", "are", "has", "have", "had"} and len(after) > 1 \
            and after[1].lower() not in LINK:
        words = after[1:3]
    elif after and after[0].lower() not in LINK:
        words = after
    else:
        units = {"per", "cent", "percent", "crore", "lakh", "billion", "million", "trillion", "usd", "inr", "rs"}
        words = [w for w in before if w.lower() not in STOP | units][-3:]
    while words and words[-1].lower() in LINK | STOP:
        words = words[:-1]
    while words and words[0].lower() in LINK:
        words = words[1:]
    return " ".join(words)


def key_figures(text, limit=6):
    """Find numbers with a unit or currency, with a few words of context as the label."""
    found, seen = [], set()
    for s in sentences(text) or [text]:
        for m in NUM_RE.finditer(s):
            cur, num, unit = m.group("cur"), m.group("num"), m.group("unit")
            if not (cur or unit):
                continue
            if unit and unit.lower().startswith("year") and re.fullmatch(r"(19|20)\d\d", num):
                continue
            if re.fullmatch(r"(19|20)\d\d", num) and not cur:
                continue
            cur = (cur or "").strip()
            if cur[-1:].isalpha():  # 'USD 44.4', not 'USD44.4'
                cur += " "
            value = (cur + num + (" " + unit if unit and unit != "%" else (unit or ""))).strip()
            value = re.sub(r"^Rs\.?\s*", "Rs ", value).replace("  ", " ")
            if value.lower() in seen:
                continue
            before = re.findall(r"[A-Za-z][A-Za-z\-']+", s[:m.start()])[-4:]
            after = re.findall(r"[A-Za-z][A-Za-z\-']+", s[m.end():])[:3]
            label = (_figure_label(s, m) or " ".join(w for w in (before[-3:] or after) if w.lower() not in STOP)
                     or " ".join(after))
            seen.add(value.lower())
            found.append({"value": value, "label": label[:40]})
            if len(found) >= limit:
                return found
    return found


def short(text, n):
    text = (text or "").strip()
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") + "..."


def whole_sentences(text, n):
    """Keep whole sentences up to about n characters, so the text never stops mid-sentence."""
    text = (text or "").strip()
    if len(text) <= n:
        return text
    out = ""
    for s in re.split(r"(?<=[.!?\"])\s+(?=[A-Z\"'(])", text):
        if out and len(out) + 1 + len(s) > n:
            break
        out = (out + " " + s).strip()
    return out
