"""Turns collected stories into page text. Works fully offline/rule-based; if a free local
Ollama model is running it is used to rewrite paragraphs in simpler, connected English."""
import json
import re
import threading
import time
import urllib.error
import urllib.request

from . import util

IGNORE_CAPS = {"I", "A", "AM", "PM", "OK", "TV", "ID", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI", "XII",
               "AND", "THE", "OF", "FOR", "IN", "ON", "TO", "BY", "AT", "IS", "IT", "BE", "NO", "AS", "OR", "SO",
               "HE", "WE", "US$", "AN", "UP", "MR", "DR", "ST", "NEW", "ALL", "NOT", "BUT", "HAS", "WAS", "ARE",
               "NOW", "OUT", "SAYS", "LIVE", "WATCH", "VIDEO", "PHOTOS", "NEWS", "BREAKING", "UPDATE"}

STARTERS = {"The", "A", "An", "This", "That", "These", "Those", "It", "In", "On", "At", "After", "Over", "With",
            "Amid", "As", "According", "Two", "Three", "Four", "Five", "Several", "Many", "Some", "Its", "Their",
            "Recently", "Earlier", "Last", "Meanwhile", "However", "Now", "Today", "Yesterday", "On", "During"}

NEGATIVE = re.compile(r"\b(war|attack|strike|killed|dead|clash|protest|row|tension|terror|blast|crisis|"
                      r"sanction|tariff|riot|violence|border|dispute|ban|accused|arrest|fire|flood|cyclone|"
                      r"earthquake|missile|drone|hostage|conflict|deficit|slump|fall)\w*", re.I)

BENEFIT_HINT = re.compile(r"\b(will help|help|boost|benefit|strengthen|improve|aims? to|aimed at|enable|"
                          r"create|jobs|self-relian|atmanirbhar|cheaper|faster|security|for india|india's)\w*",
                          re.I)


class Writer:
    def __init__(self, cfg, glossary, hardwords, log=print):
        self.cfg, self.glossary, self.hardwords, self.log = cfg, glossary, hardwords, log
        self.llm_ok = self._llm_available()
        self.think = self.cfg["llm"].get("think", "low")
        self.unknown_abbr = {}
        self._cache, self._lock = {}, threading.Lock()

    def _memo(self, key, fn, *args):
        """Results are kept for the run, so text written ahead in parallel (draft.prewrite) is reused."""
        with self._lock:
            if key in self._cache:
                return self._cache[key]
        out = fn(*args)
        with self._lock:
            self._cache[key] = out
        return out

    # ------------------------------------------------------------- optional free LLM
    def _llm_available(self):
        mode = self.cfg["llm"]["mode"]
        if mode == "off":
            return False
        try:
            with urllib.request.urlopen(self.cfg["llm"]["url"] + "/api/tags", timeout=2) as r:
                models = [m["name"] for m in json.load(r).get("models", [])]
            want = self.cfg["llm"]["model"]
            if not any(m.split(":")[0] == want.split(":")[0] for m in models):
                self.log(f"  Ollama is running but model '{want}' is missing (run: ollama pull {want}); "
                         "using rule-based writing.")
                return False
            where = "cloud (over the internet)" if want.endswith("cloud") else "local"
            self.log(f"  Using free {where} model via Ollama: {want}")
            return True
        except Exception:
            if mode == "on":
                self.log("  ! llm.mode is 'on' but Ollama is not reachable; using rule-based writing.")
            return False

    def llm(self, prompt, max_tokens=400):
        if not self.llm_ok:
            return ""
        body = {"model": self.cfg["llm"]["model"], "prompt": prompt, "stream": False,
                # thinking models (gpt-oss, ...) think before answering; the extra room keeps the answer
                "options": {"temperature": 0.2, "num_predict": max_tokens + 400}}
        if self.think:
            body["think"] = self.think
        try:
            try:
                return self._generate(body)
            except urllib.error.HTTPError as e:
                if e.code != 400 or "think" not in body:
                    raise
                self.think = None  # this model can't think; ask it plainly from now on
                body.pop("think")
                return self._generate(body)
        except Exception as e:  # e.g. no internet for a cloud model, or not signed in: stop trying this run
            self.log(f"  ! Ollama error ({e}); using rule-based writing for the rest of this run.")
            self.llm_ok = False
            return ""

    def _generate(self, body):
        req = urllib.request.Request(self.cfg["llm"]["url"] + "/api/generate", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        for wait in (5, 15, 0):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r).get("response", "").strip()
            except urllib.error.HTTPError as e:
                # 429/503 = cloud busy (the free plan runs 1 request at a time): wait and try again
                if e.code not in (429, 503) or not wait:
                    raise
                time.sleep(wait)

    @staticmethod
    def _clean_llm(out):
        """Drop the model's chatty opener ("Here's a 2-sentence explanation ...:"), line breaks and
        special dashes/spaces the PDF font can't show."""
        out = out.translate({0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: " - ", 0x00A0: " ",
                             0x202F: " ", 0x2009: " ", 0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'})
        out = re.sub(r"^\s*(here('s| is| are)|sure|okay|certainly)\b[^:\n]*:\s*", "", out.strip(), flags=re.I)
        return re.sub(r"\s+", " ", out).strip().strip('"')

    @staticmethod
    def _numbers_ok(out, facts):
        """Every number the model wrote must appear in the facts; otherwise its text is not trusted."""
        have = set(re.findall(r"\d+(?:[.,]\d+)?", facts.replace(",", "")))
        return all(n in have for n in re.findall(r"\d+(?:[.,]\d+)?", out.replace(",", "")))

    def rewrite(self, prompt, facts, max_tokens=400):
        """Model text, or '' when the model is off, says nothing useful or adds a number of its own."""
        out = self._clean_llm(self.llm(prompt, max_tokens))
        return out if len(out) > 40 and self._numbers_ok(out, facts) else ""

    # ------------------------------------------------------------- annotation
    def find_abbrs(self, text):
        found = []
        for ab in self.glossary:
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(ab) + r"(?![A-Za-z0-9])", text):
                found.append(ab)
        for tok in re.findall(r"\b[A-Z][A-Z0-9&]{1,6}\b", text):
            if tok not in self.glossary and tok not in IGNORE_CAPS and not tok.isdigit():
                self.unknown_abbr[tok] = self.unknown_abbr.get(tok, 0) + 1
        found.sort(key=lambda a: text.find(a))
        return found

    def annotate(self, text, used=None):
        """Add '(Full form - role)' after the first abbreviation and '(meaning)' after hard words."""
        lay = self.cfg["layout"]
        used = used if used is not None else set()
        inserts = []
        if lay["inline_full_forms"]:
            for ab in self.find_abbrs(text):
                if ab in used:
                    continue
                g = self.glossary[ab]
                m = re.search(r"(?<![A-Za-z0-9])" + re.escape(ab) + r"(?![A-Za-z0-9])(?!\s*\()", text)
                is_term = g["full"].lower().startswith(ab.lower())  # e.g. Kremlin, Houthis: explain, don't expand
                if not m or (not is_term and g["full"].lower() in text.lower()):
                    used.add(ab)
                    continue
                if is_term:
                    inserts.append((m.end(), f" ({g['does']})"))
                else:
                    inserts.append((m.end(), f" ({g['full']} - {g['does']})"))
                used.add(ab)
        if lay["inline_meanings"]:
            n = 0
            for w, meaning in self.hardwords.items():
                if n >= lay["max_meanings_per_paragraph"]:
                    break
                if w in used:
                    continue
                m = re.search(r"\b" + re.escape(w) + r"\b(?!\s*\()", text, re.I)
                if m:
                    inserts.append((m.end(), f" ({meaning})"))
                    used.add(w)
                    n += 1
        out, last = [], 0
        for pos, ins in sorted(inserts):
            if pos < last:
                continue
            out.append(text[last:pos] + ins)
            last = pos
        out.append(text[last:])
        return "".join(out)

    def full_forms_for(self, text, extra=()):
        res = []
        for ab in list(extra) + self.find_abbrs(text):
            if ab in self.glossary and ab not in [r["abbr"] for r in res]:
                res.append({"abbr": ab, **self.glossary[ab]})
        return res

    # ------------------------------------------------------------- page text
    @staticmethod
    def _attribute(sentence, source):
        first = sentence.split(" ", 1)[0]
        if first in STARTERS:
            sentence = sentence[0].lower() + sentence[1:]
        return f"According to {source}, {sentence}"

    def paragraph(self, lead, others, section):
        return self._memo(("p", id(lead), section), self._paragraph, lead, others, section)

    def _paragraph(self, lead, others, section):
        lead_text = lead.get("text") or lead.get("summary") or ""
        sents = []
        for s in util.sentences(lead_text):
            s = re.sub(r"^[A-Z][A-Z .,/]{2,40}(\(\w+\))?\s*[:\-]\s+", "", s)  # drop datelines like "NEW DELHI:"
            if s.lower().startswith(("also read", "click", "subscribe", "follow us", "read more")):
                continue
            if any(util.similarity(s, x) > 0.75 for x in sents):
                continue
            sents.append(s)
        sources = ", ".join(lead["sources"][:3])
        facts = [lead["title"]] + sents[:6] + [o["title"] + ". " + (o.get("summary") or "")[:200] for o in others[:2]]
        if self.llm_ok:
            prompt = (
                "You write a daily current-affairs digest for Indian defence/competitive exam students.\n"
                "Write ONE paragraph of 5-6 connected sentences in very simple English about the main story below. "
                "Explain the background, the reason and the result. Use ONLY the facts given; do not add any "
                "fact, number or name that is not in them. Do not use brackets. Mention who reported it "
                f"(sources: {sources}). Start directly with the paragraph, no introduction.\nSection: {section}\n"
                "FACTS:\n- " + "\n- ".join(facts) + "\nPARAGRAPH:")
            out = self.rewrite(prompt, " ".join(facts))
            if len(out) > 120:
                return util.whole_sentences(out, 1050)
        body = sents[:5] or [lead["title"].rstrip(".") + "."]
        para = [self._attribute(body[0], lead["sources"][0])] + body[1:]
        if (lead.get("summary") and not lead.get("text") and not util.is_cut(lead["summary"])
                and lead["summary"] not in " ".join(para)):
            para.append(lead["summary"])
        # other outlets' headlines on the same story usually add a detail each
        seen = [lead["title"]]
        for it in lead.get("items", [])[1:]:
            if len(para) >= 6:
                break
            t = util.strip_source_suffix(it["title"])
            if it["source"] != lead["sources"][0] and all(util.similarity(t, x) < 0.8 for x in seen):
                para.append(f"{it['source']} reported it as: \"{t}\".")
                seen.append(t)
        for o in others[:1]:
            s = util.sentences(o.get("summary") or "")
            para.append(f"In related news, {o['sources'][0]} reported: " + (s[0] if s else o["title"].rstrip(".") + "."))
        return util.whole_sentences(" ".join(para), 1050)

    def context(self, story):
        return self._memo(("c", id(story)), self._context, story)

    def _context(self, story):
        """2-3 short lines saying what a story is about, from its own article text ('' if there is none)."""
        title = util.strip_source_suffix(story["title"])
        sents = []
        for s in util.sentences((story.get("text") or "") + " " + (story.get("summary") or "")):
            s = re.sub(r"^[A-Z][A-Z .,/]{2,40}(\(\w+\))?\s*[:\-]\s+", "", s)  # drop datelines like "NEW DELHI:"
            if len(s) < 300 and util.similarity(s, title) < 0.7 and not any(util.similarity(s, x) > 0.75 for x in sents):
                sents.append(s)
            if len(sents) >= 4:
                break
        if not sents:
            return ""
        if self.llm_ok:
            facts = title + " " + " ".join(sents)
            out = self.rewrite("Explain this news in 2 short sentences of very simple English for an exam student: "
                               "what happened and why it matters. Keep the names of people, organisations and "
                               "places, and the numbers. Use ONLY the facts given; add nothing new. Start directly "
                               "with the explanation, no introduction.\nHEADLINE: " + title + "\nFACTS:\n- "
                               + "\n- ".join(sents) + "\nEXPLANATION:", facts, 120)
            if out:
                return util.whole_sentences(out, 280)
        return util.whole_sentences(" ".join(sents[:2]), 260)

    def benefit(self, section, stories, headline):
        key = ("b", section, id(stories[0]) if stories else None, headline)
        return self._memo(key, self._benefit, section, stories, headline)

    def _benefit(self, section, stories, headline):
        negative = bool(NEGATIVE.search(headline)) or section in ("WAR SECTION",)
        label = "WHY IT MATTERS FOR INDIA" if negative else "BENEFIT FOR INDIA"
        pool = []
        for st in stories[:4]:
            for s in util.sentences((st.get("text") or "") + " " + (st.get("summary") or "")):
                if BENEFIT_HINT.search(s) and len(s) < 260:
                    pool.append(s)
        if not pool:  # fall back to headlines that name India directly
            pool = [f"{it['title']} ({it['source']})" for st in stories[:5] for it in st.get("items", [])[:3]
                    if re.search(r"\bindia", it["title"], re.I)][:2]
        if self.llm_ok:
            prompt = ("In 2 short bullet points (simple English, max 22 words each), say honestly "
                      f"{'why this matters for India' if negative else 'how this benefits India'}. Use only the "
                      "facts given; if no India link is in the facts, say what India should watch, without "
                      "inventing numbers.\nFACTS:\n- " + "\n- ".join([headline] + pool[:4] +
                                                                    [s['title'] for s in stories[:4]]) +
                      "\nBULLETS:")
            facts = " ".join([headline] + pool[:4] + [s['title'] for s in stories[:4]])
            out = [self._clean_llm(re.sub(r"^[\-\*•\d\.\s]+", "", l)) for l in self.llm(prompt, 160).splitlines()]
            out = [l for l in out if len(l) > 15 and not re.match(r"(here|sure|okay)\b", l, re.I)
                   and self._numbers_ok(l, facts)][:2]
            if out:
                return label, out
        if pool:
            return label, pool[:2]
        return label, ["No direct India angle was stated in today's sources - add one with "
                       "`digest edit` if needed (verify)."]


def pick_fact(facts, section, text, avoid):
    low = " " + text.lower() + " "
    best, best_score = None, 0
    for f in facts:
        if f["fact"] in avoid or "keys" not in f:
            continue
        score = sum(low.count(k) for k in f["keys"])
        if score > best_score:
            best, best_score = f["fact"], score
    if best:
        return best
    for f in facts:
        if f.get("section") == section:
            return f["fact"]
    return ""
