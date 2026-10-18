"""Draws the one-page-per-section infographic PDF with reportlab. Every text box shrinks its font
until the text fits, so nothing ever overflows."""
import os
import re
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

FONT, BOLD = "Helvetica", "Helvetica-Bold"


def setup_fonts(cfg):
    global FONT, BOLD
    reg = next((p for p in cfg["fonts"]["regular"] if os.path.exists(p)), None)
    bold = next((p for p in cfg["fonts"]["bold"] if os.path.exists(p)), None)
    if reg and bold:
        pdfmetrics.registerFont(TTFont("Body", reg))
        pdfmetrics.registerFont(TTFont("Body-Bold", bold))
        from reportlab.lib.fonts import addMapping
        addMapping("Body", 0, 0, "Body")
        addMapping("Body", 1, 0, "Body-Bold")
        addMapping("Body", 0, 1, "Body")
        addMapping("Body", 1, 1, "Body-Bold")
        FONT, BOLD = "Body", "Body-Bold"


def DOT():
    """Round bullet; the built-in Helvetica fallback font has no ●, so use a plain bullet there."""
    return "●" if FONT == "Body" else "•"


def safe(text):
    t = escape(str(text or "").translate(ODD_CHARS))
    if FONT == "Helvetica":
        t = t.replace("₹", "Rs ")
    return t


# special dashes/spaces many fonts lack (they print as empty boxes)
ODD_CHARS = {0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2015: "-", 0x2212: "-", 0x00A0: " ", 0x202F: " ",
             0x2009: " ", 0x200A: " ", 0x2007: " ", 0x200B: "", 0x00AD: ""}


class Page:
    def __init__(self, c, cfg, width, height):
        self.c, self.cfg, self.W, self.H = c, cfg, width, height
        self.col = {k: HexColor(v) for k, v in cfg["colors"].items()}
        self.M = 22

    # ---------------------------------------------------------------- primitives
    def fit_para(self, html, x, top, w, h, size=10.5, min_size=5.5, color=None, bold=False, align=TA_LEFT,
                 lead=1.25, valign="top"):
        """Draw rich text inside (x, top, w, h); shrink font until it fits; return used height."""
        color = color or self.col["text"]
        s = size
        while True:
            st = ParagraphStyle("p", fontName=BOLD if bold else FONT, fontSize=s, leading=s * lead,
                                textColor=color, alignment=align)
            p = Paragraph(html, st)
            _, ph = p.wrap(w, h)
            if ph <= h or s <= min_size:
                break
            s -= 0.25
        if ph > h:  # still too long at the smallest size: drop whole bullets, then whole sentences
            items = html.split("<br/>")
            while ph > h and len(items) > 1:
                items.pop()
                p = Paragraph("<br/>".join(items), st)
                _, ph = p.wrap(w, h)
            sents = re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(<])", items[0])
            while ph > h and len(sents) > 1:
                sents.pop()
                p = Paragraph(" ".join(sents), st)
                _, ph = p.wrap(w, h)
            words = " ".join(sents).split(" ")
            while ph > h and len(words) > 5:  # one very long sentence: last resort
                words = words[:int(len(words) * 0.9)]
                p = Paragraph(" ".join(words) + " ...", st)
                _, ph = p.wrap(w, h)
        dy = 0 if valign == "top" else (h - ph) / 2
        p.drawOn(self.c, x, top - dy - ph)
        return ph

    def fit_line(self, text, x, y, w, size, min_size, font, color, align="left"):
        text = str(text).translate(ODD_CHARS)
        s = size
        while pdfmetrics.stringWidth(text, font, s) > w and s > min_size:
            s -= 0.25
        while pdfmetrics.stringWidth(text, font, s) > w and len(text) > 4:
            text = text[:-4].rstrip() + "..."
        self.c.setFont(font, s)
        self.c.setFillColor(color)
        if align == "center":
            self.c.drawCentredString(x + w / 2, y, text)
        else:
            self.c.drawString(x, y, text)
        return s

    def rect(self, x, top, w, h, fill, stroke=None, r=5, lw=1):
        self.c.setFillColor(fill)
        if stroke is not None:
            self.c.setStrokeColor(stroke)
            self.c.setLineWidth(lw)
        self.c.roundRect(x, top - h, w, h, r, fill=1, stroke=1 if stroke is not None else 0)

    def bar_box(self, x, top, w, h, title, bar_color, html, size=8.5):
        bh = 16
        self.rect(x, top, w, h, self.col["grey"], r=4)
        self.c.setFillColor(bar_color)
        self.c.roundRect(x, top - bh, w, bh, 4, fill=1, stroke=0)
        self.c.rect(x, top - bh, w, bh / 2, fill=1, stroke=0)
        self.fit_line(title, x + 7, top - 11.5, w - 14, 8.5, 6, BOLD, white)
        self.fit_para(html, x + 7, top - bh - 5, w - 14, h - bh - 9, size=size, min_size=5)

    def bullets(self, items, color="teal"):
        dot = "<font color='%s'>%s</font>&nbsp; " % (self.cfg["colors"][color], DOT())
        out = []
        for i in items if isinstance(items, list) else [items]:
            t = safe(i).strip()
            if not t:
                continue
            m = re.match(r"^([A-Za-z][^:<>#]{1,29}):\s", t)
            if m:  # bold lead-in label, e.g. "Bihar: ..."
                t = f"<b>{m.group(1)}:</b> " + t[m.end():]
            out.append(dot + t)
        return "<br/>".join(out) or "-"

    # ---------------------------------------------------------------- sections of the page
    def header(self, draft, p, total):
        h = 80
        c = self.c
        c.setFillColor(self.col["navy"])
        c.rect(0, self.H - h, self.W, h, fill=1, stroke=0)
        r = 25
        cx, cy = self.W - self.M - r, self.H - h / 2
        c.setFillColor(self.col["orange"])
        c.circle(cx, cy, r, fill=1, stroke=0)
        self.fit_line(str(p["n"]), cx - r, cy - 9, 2 * r, 26, 12, BOLD, white, align="center")
        self.fit_line(p["name"].upper(), self.M, self.H - 44, self.W - 2 * self.M - 2 * r - 16, 30, 12, BOLD, white)
        sub = f"{draft.get('title', 'Daily News Digest')} | {draft['day']} | Category {p['n']} of {total}"
        self.fit_line(sub, self.M, self.H - 64, self.W - 2 * self.M - 2 * r - 16, 10.5, 7, FONT, HexColor("#cfd9e6"))
        return self.H - h

    def headline(self, p, top):
        h = 28
        self.rect(self.M, top, self.W - 2 * self.M, h, self.col["orange"], r=4)
        text = p["headline"] + ("  (verify)" if p.get("headline_verify") else "")
        self.fit_line(text, self.M + 10, top - 18.5, self.W - 2 * self.M - 20, 13, 7.5, BOLD, white)
        return top - h

    def main_box(self, p, top, h):
        w = self.W - 2 * self.M
        self.rect(self.M, top, w, h, self.col["light"], r=6)
        self.c.setFillColor(self.col["navy"])
        self.c.rect(self.M, top - h, 4, h, fill=1, stroke=0)
        html = safe(p["paragraph"])
        if p.get("notes"):
            html += "<br/><font color='%s'><b>Note:</b> %s</font>" % (
                self.cfg["colors"]["orange"], safe(" | ".join(p["notes"])))
        self.fit_para(html, self.M + 12, top - 8, w - 22, h - 14, size=10.5, min_size=6, lead=1.3)
        return top - h

    def tiles(self, p, top, h):
        tiles = p.get("tiles") or []
        if not tiles:
            return top
        n = len(tiles)
        gap = 8
        w = (self.W - 2 * self.M - gap * (n - 1)) / n
        for i, t in enumerate(tiles):
            x = self.M + i * (w + gap)
            self.rect(x, top, w, h, self.col["navy"], r=6)
            self.fit_line(str(t.get("value", "")), x + 6, top - 27, w - 12, 20, 9, BOLD, self.col["orange"],
                          align="center")
            self.fit_para(safe(t.get("label", "")), x + 6, top - 33, w - 12, h - 36, size=8, min_size=5.5,
                          color=white, align=TA_CENTER)
        return top - h

    def flow(self, p, top, h):
        fl = p.get("flow") or {}
        steps = [s for s in fl.get("steps", []) if str(s).strip()][:8]
        is_flow = fl.get("mode") == "flow"
        c = self.c
        self.fit_line((fl.get("title") or ("FLOWCHART" if is_flow else "SNAPSHOT")).upper(), self.M, top - 10,
                      300, 9, 7, BOLD, self.col["teal"])
        if not steps:
            self.fit_para("<i>No extra stories for this box today.</i>", self.M, top - 18, 300, 20, size=8)
            return top - h
        cards = not is_flow and any("\n" in str(s) for s in steps)  # headline + a few lines of context
        if cards:
            rows = [steps[i:i + 2] for i in range(0, len(steps), 2)]
        else:
            rows = [steps] if len(steps) <= 5 else [steps[:(len(steps) + 1) // 2], steps[(len(steps) + 1) // 2:]]
        area_top, area_h = top - 16, h - 16
        row_gap = 12 if len(rows) > 1 else 0
        bh = (area_h - row_gap * (len(rows) - 1)) / len(rows)
        arrow_w = 20 if is_flow else 8
        num = 0
        teal, orange = self.col["teal"], self.col["orange"]
        for ri, row in enumerate(rows):
            n = len(rows[0])
            bw = (self.W - 2 * self.M - arrow_w * (n - 1)) / n
            y_top = area_top - ri * (bh + row_gap)
            for i, s in enumerate(row):
                num += 1
                x = self.M + i * (bw + arrow_w)
                self.rect(x, y_top, bw, bh, white, stroke=teal, r=5, lw=1.3)
                pad_left = 6
                if is_flow:
                    c.setFillColor(teal)
                    c.circle(x + 11, y_top - 11, 8, fill=1, stroke=0)
                    self.fit_line(str(num), x + 3, y_top - 14.5, 16, 9, 6, BOLD, white, align="center")
                    pad_left = 22
                if cards:
                    head, _, ctx = str(s).partition("\n")
                    html = f"<b>{safe(head)}</b>" + (f"<br/>{safe(ctx)}" if ctx.strip() else "")
                    self.fit_para(html, x + 7, y_top - 5, bw - 14, bh - 9, size=8, min_size=5.5)
                    continue
                m = re.match(r"^([^:]{2,30}):\s+(.*)$", str(s))
                if m and pdfmetrics.stringWidth(m.group(1), BOLD, 6) > bw - pad_left - 6:
                    m = None  # label too long for one line: show the whole step as wrapped text instead
                if m:  # "28 Feb 2026: what happened" -> bold title next to the number, text below
                    self.fit_line(m.group(1), x + pad_left, y_top - 14.5, bw - pad_left - 6, 9, 6, BOLD, self.col["text"])
                    self.fit_para(safe(m.group(2)), x + 6, y_top - 21, bw - 11, bh - 24, size=8, min_size=5)
                else:
                    self.fit_para(safe(s), x + pad_left, y_top - 4, bw - pad_left - 5, bh - 8, size=8.5, min_size=5,
                                  valign="middle")
                if is_flow and i < len(row) - 1:
                    ay = y_top - bh / 2
                    c.setStrokeColor(orange)
                    c.setFillColor(orange)
                    c.setLineWidth(2)
                    c.line(x + bw + 2, ay, x + bw + arrow_w - 8, ay)
                    path = c.beginPath()
                    path.moveTo(x + bw + arrow_w - 1, ay)
                    path.lineTo(x + bw + arrow_w - 9, ay + 6)
                    path.lineTo(x + bw + arrow_w - 9, ay - 6)
                    path.close()
                    c.drawPath(path, fill=1, stroke=0)
            if is_flow and ri == 0 and len(rows) > 1:  # elbow arrow from end of row 1 to start of row 2
                x_end = self.M + (len(row) - 1) * (bw + arrow_w) + bw / 2
                y1, y2 = y_top - bh, y_top - bh - row_gap
                c.setStrokeColor(orange)
                c.setLineWidth(1.6)
                c.line(x_end, y1 - 1, x_end, y1 - row_gap / 2)
                c.line(x_end, y1 - row_gap / 2, self.M + bw / 2, y1 - row_gap / 2)
                c.line(self.M + bw / 2, y1 - row_gap / 2, self.M + bw / 2, y2 + 4)
                path = c.beginPath()
                path.moveTo(self.M + bw / 2, y2 + 1)
                path.lineTo(self.M + bw / 2 - 3.5, y2 + 5.5)
                path.lineTo(self.M + bw / 2 + 3.5, y2 + 5.5)
                path.close()
                c.setFillColor(orange)
                c.drawPath(path, fill=1, stroke=0)
        return top - h

    def columns(self, p, top, h):
        gap = 10
        w = (self.W - 2 * self.M - gap) / 2
        self.bar_box(self.M, top, w, h, "KEY POINTS", self.col["teal"], self.bullets(p.get("key_points", []), "teal"), 8.5)
        dot = "<font color='%s'>%s</font>&nbsp; " % (self.cfg["colors"]["orange"], DOT())
        ff = "<br/>".join(
            dot + (f"<b>{safe(f['abbr'])}</b> - {safe(f['does'])}" if f["full"].lower() == f["abbr"].lower()
                   else f"<b>{safe(f['abbr'])}</b> - {safe(f['full'])} ({safe(f['does'])})")
            for f in p.get("full_forms", [])) or "No abbreviations on this page."
        self.bar_box(self.M + w + gap, top, w, h, "FULL FORMS (WHAT IT DOES)", self.col["navy"], ff, 8.5)
        return top - h

    def bottom(self, p, top, h):
        gap = 8
        w = (self.W - 2 * self.M - 2 * gap) / 3
        self.bar_box(self.M, top, w, h, p.get("benefit_label", "BENEFIT FOR INDIA").upper(), self.col["green"],
                     self.bullets(p.get("benefit", []), "green"), 8)
        self.bar_box(self.M + w + gap, top, w, h, "ADVANCED POINT", self.col["orange"],
                     self.bullets(p.get("advanced") or ["-"], "orange"), 8)
        self.bar_box(self.M + 2 * (w + gap), top, w, h, "ALSO IN THE NEWS", self.col["navy"],
                     self.bullets(p.get("also", []), "navy"), 8)
        return top - h

    def footer(self, p, total, top, h):
        w = self.W - 2 * self.M
        self.rect(self.M, top, w, h, self.col["light"], r=4)
        txt = (f"<b>Sources:</b> {safe(', '.join(p.get('sources', [])) or '-')}. "
               f"<b>Confidence:</b> {safe(p.get('confidence', '-'))}")
        self.fit_para(txt, self.M + 8, top - 5, w - 16, h - 9, size=7.5, min_size=5, color=self.col["muted"],
                      valign="middle")
        self.fit_line(f"Page {p['n']} of {total}", self.M, top - h - 12, w, 7.5, 6, FONT, self.col["muted"],
                      align="center")

    def draw(self, draft, p, total):
        top = self.header(draft, p, total) - 8
        top = self.headline(p, top) - 8
        cards = (p.get("flow") or {}).get("mode") != "flow" and any("\n" in str(s) for s in p["flow"].get("steps", []))
        top = self.main_box(p, top, 152 - 12 * cards) - 8
        top = self.tiles(p, top, 58 - 6 * cards) - 8
        top = self.flow(p, top, 120 + 40 * cards) - 8
        top = self.columns(p, top, 174 - 16 * cards) - 8
        top = self.bottom(p, top, 106 - 6 * cards) - 6
        self.footer(p, total, top, min(34, top - 26))


def render(cfg, draft, out_path, progress=None):
    setup_fonts(cfg)
    size = letter if cfg["layout"]["page_size"].lower() == "letter" else A4
    c = canvas.Canvas(out_path, pagesize=size)
    c.setTitle(f"{draft.get('title', 'Daily News Digest')} - {draft['date']}")
    c.setAuthor("news-digest CLI")
    pages = draft["pages"]
    for i, p in enumerate(pages, 1):
        if progress:
            progress(f"Drawing page {i}: {p['name']}", i, len(pages))
        Page(c, cfg, *size).draw(draft, p, len(pages))
        c.showPage()
    c.save()
    return out_path


def text_digest(draft):
    """Plain bullet-point version (for 'text only' days)."""
    out = [f"{draft.get('title', 'Daily News Digest')} - {draft['day']}", ""]
    for p in draft["pages"]:
        out.append(f"{p['n']}. {p['name'].upper()}")
        out.append(f"  * {p['headline']}" + (" (verify)" if p.get("headline_verify") else ""))
        out.append(f"    {p['paragraph']}")
        for k in p.get("key_points", []):
            out.append(f"  * {k}")
        if (p.get("flow") or {}).get("mode") != "flow":
            for s in p.get("flow", {}).get("steps", []):
                head, _, ctx = str(s).partition("\n")
                out.append(f"  + {head}" + (f": {ctx}" if ctx.strip() else ""))
        for f in p.get("full_forms", []):
            out.append(f"  - {f['abbr']}: {f['full']} ({f['does']})")
        for b in p.get("benefit", []):
            out.append(f"  {p.get('benefit_label', 'BENEFIT FOR INDIA').title()}: {b}")
        adv = p.get("advanced") or []
        for a in adv if isinstance(adv, list) else [adv]:
            out.append(f"  Advanced point: {a}")
        for n in p.get("notes", []):
            out.append(f"  Note: {n}")
        out.append(f"  Sources: {', '.join(p.get('sources', []))}. Confidence: {p.get('confidence', '-')}")
        out.append("")
    return "\n".join(out)
