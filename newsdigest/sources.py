"""Free news sources: publisher RSS feeds, Google News RSS search, full-text fetch, newspaper PDFs."""
import datetime as dt
import os
import re
import shutil
import subprocess
import threading
import urllib.parse

from . import util
from .config import GN

# lxml (inside trafilatura) can crash Python when several threads parse pages at once;
# downloads still run in parallel, only the parsing takes turns
_PARSE_LOCK = threading.Lock()

try:
    import feedparser
except ImportError:  # pragma: no cover
    feedparser = None


def _when(entry, tz):
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            return (dt.datetime(*t[:6], tzinfo=dt.timezone.utc).astimezone(tz))
    return None


def in_window(when, date, cfg, tz):
    if when is None:
        return True
    start = dt.datetime.combine(date - dt.timedelta(days=cfg["days_back"]), dt.time.min, tz)
    end = dt.datetime.combine(date, dt.time.max, tz)
    return start <= when <= end


def fetch_feed(url, name, hint, date, cfg, tz, log):
    if feedparser is None:
        log("  ! feedparser not installed; run: pip install -r requirements.txt")
        return []
    try:
        f = feedparser.parse(url, agent=cfg["web"]["user_agent"],
                             request_headers={"Accept": "application/rss+xml,*/*"})
    except Exception as e:  # network problems should never stop the run
        log(f"  ! {name}: {e}")
        return []
    items = []
    for e in f.entries:
        when = _when(e, tz)
        if not in_window(when, date, cfg, tz):
            continue
        title = util.clean_html(e.get("title", ""))
        src = name
        if "news.google.com" in url:
            src = (e.get("source") or {}).get("title") or util.clean_html(title.rsplit(" - ", 1)[-1])
            title = util.strip_source_suffix(title)
            summary = ""
        else:
            summary = util.clean_html(e.get("summary", ""))
        title = util.tidy_cut(util.strip_source_suffix(title))
        if not title or not util.is_english(title):  # the PDF is in English; other scripts print as blanks
            continue
        if summary and not util.is_english(summary):
            summary = ""
        if not title:
            continue
        items.append({
            "title": title, "summary": summary, "source": src, "link": e.get("link", ""),
            "when": when.strftime("%Y-%m-%d %H:%M") if when else "", "hint": hint, "kind": "web",
        })
    return items


def google_news(query, date, cfg, tz, hint, log):
    after = (date - dt.timedelta(days=cfg["days_back"] + 1)).isoformat()
    before = (date + dt.timedelta(days=1)).isoformat()
    q = urllib.parse.quote_plus(f"{query} after:{after} before:{before}")
    return fetch_feed(GN.format(q=q), "Google News", hint, date, cfg, tz, log)


def decode_google_news(url, ua):
    """Google News RSS links hide the publisher URL; ask Google's own page for it (free, no key)."""
    import json
    import urllib.request
    gid = urllib.parse.urlparse(url).path.split("/")[-1]
    req = urllib.request.Request(f"https://news.google.com/rss/articles/{gid}", headers={"User-Agent": ua})
    page = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    sg = re.search(r'data-n-a-sg="([^"]+)"', page).group(1)
    ts = re.search(r'data-n-a-ts="([^"]+)"', page).group(1)
    inner = ["garturlreq", [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None, None, None,
                             None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0], gid, int(ts), sg]
    body = urllib.parse.urlencode({"f.req": json.dumps([[["Fbv4je", json.dumps(inner), None, "generic"]]])}).encode()
    req = urllib.request.Request("https://news.google.com/_/DotsSplashUi/data/batchexecute", data=body, headers={
        "User-Agent": ua, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"})
    txt = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
    return json.loads(json.loads(txt.split("\n\n", 1)[1])[0][2])[1]


def fetch_article_text(url, cfg):
    """Full article text with trafilatura (free). Returns '' when blocked/paywalled."""
    if not url:
        return ""
    try:
        import trafilatura
        if "news.google.com" in url:
            url = decode_google_news(url, cfg["web"]["user_agent"])
        raw = trafilatura.fetch_url(url)
        if not raw:
            return ""
        with _PARSE_LOCK:
            text = trafilatura.extract(raw, include_comments=False, include_tables=False)
        return util.clean_html(text or "")
    except Exception:
        return ""


# ---------------------------------------------------------------- newspaper PDFs

def pdf_text(path):
    exe = shutil.which("pdftotext")
    if exe:
        try:
            out = subprocess.run([exe, "-layout", "-enc", "UTF-8", path, "-"], capture_output=True, timeout=180)
            txt = out.stdout.decode("utf-8", "ignore")
            if txt.strip():
                return txt
        except Exception:
            pass
    from pypdf import PdfReader
    return "\n\f".join((p.extract_text() or "") for p in PdfReader(path).pages)


def guess_paper(path, text):
    low = (os.path.basename(path) + " " + text[:3000]).lower()
    for key, name in (("hindu", "The Hindu"), ("times of india", "Times of India"), ("toi", "Times of India"),
                      ("acc", "ACC Defence Academy"), ("express", "Indian Express"), ("mint", "Mint"),
                      ("hindustan times", "Hindustan Times"), ("business standard", "Business Standard")):
        if key in low:
            return name
    return os.path.splitext(os.path.basename(path))[0]


def pdf_date(path, text):
    """Most common date on the first pages; falls back to a date in the file name."""
    dates = util.find_dates(text[:6000])
    m = re.search(r"(20\d\d)[-_.]?(\d\d)[-_.]?(\d\d)", os.path.basename(path))
    if m:
        try:
            dates.append(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    if not dates:
        return None
    return max(set(dates), key=dates.count)


def pdf_articles(text, paper, kind):
    """Split newspaper text into rough story blocks: a short headline line + following paragraph text."""
    blocks = []
    for page_no, page in enumerate(text.split("\f"), 1):  # pdftotext/pypdf separate pages with \f
        blocks += [(page_no, b) for b in re.split(r"\n\s*\n", page)]
    items = []
    for page_no, b in blocks:
        lines = [re.sub(r"\s{3,}", "  ", l).strip() for l in b.splitlines() if l.strip()]
        if not lines:
            continue
        body = " ".join(lines)
        body = re.sub(r"-\s+(?=[a-z])", "", body)
        if len(body) < 160:
            continue
        head = lines[0]
        if len(head) > 110 or len(head) < 15:
            head = util.short(util.sentences(body)[0] if util.sentences(body) else body, 100)
        items.append({"title": util.clean_html(head), "summary": util.clean_html(body[:1800]),
                      "source": paper, "link": "", "when": "", "hint": "", "kind": kind, "text": body[:6000],
                      "page": page_no})
    return items


def read_pdfs(paths, date, log):
    """Returns (items_for_today, background_items, file_report)."""
    today, background, report = [], [], []
    for p in paths:
        try:
            text = pdf_text(p)
        except Exception as e:
            report.append({"file": os.path.basename(p), "status": f"could not read: {e}"})
            continue
        paper = guess_paper(p, text)
        d = pdf_date(p, text)
        words = len(text.split())
        if words < 60:
            status = "almost no text (scanned PDF? OCR it first, e.g. ocrmypdf)"
        elif d is None:
            status = "date not found - used as TODAY (verify)"
        elif d == date:
            status = "date matches"
        else:
            status = f"dated {d.isoformat()} - NOT {date.isoformat()}, used only as background"
        is_today = d is None or d == date
        arts = pdf_articles(text, paper, "pdf" if is_today else "background")
        for a in arts:
            a["paper_date"] = d.strftime("%d %b %Y").lstrip("0") if d else ""
        (today if is_today else background).extend(arts)
        report.append({"file": os.path.basename(p), "paper": paper, "date": d.isoformat() if d else None,
                       "words": words, "stories": len(arts), "status": status})
        log(f"  PDF {os.path.basename(p)}: {paper}, {status}, {len(arts)} story blocks")
    return today, background, report
