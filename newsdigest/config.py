"""Default settings. Everything here can be overridden in config.json
(use `digest config set <key> <value>` or edit the file)."""
import copy
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CONFIG_PATH = os.path.join(ROOT, "config.json")

GN = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"

DEFAULT_CONFIG = {
    "title": "Daily News Digest",
    "timezone_offset_hours": 5.5,          # IST
    "days_back": 1,                        # news window = (date - days_back) .. date
    "paths": {
        "inbox": "inbox",                  # drop newspaper PDFs here (or use --pdf)
        "drafts": "drafts",
        "output": "output",
        "state": "state",
        "user_data": "user_data",
    },
    "web": {
        "enabled": True,
        "google_news": True,               # free Google News RSS search, used for gaps + verification
        "fetch_articles": True,            # download full text of lead stories (free, trafilatura)
        "articles_per_section": 3,
        "timeout": 15,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsDigestCLI/1.0",
    },
    "ui": {
        "animations": True,                # spinning radioactive loader, rocket launch, typing banner
        "colors": True,
        "unicode": "auto",                 # auto | true | false (false = plain ASCII symbols)
        "min_build_seconds": 4,            # keep the live monitor on screen this long while drawing the PDF
    },
    "llm": {
        # Optional FREE local model via Ollama (https://ollama.com). "auto" = use it if running.
        "mode": "auto",                    # auto | on | off
        "url": "http://localhost:11434",
        "model": "llama3.2",
        "parallel": 4,                     # requests at once (cloud models); use 1 for a slow local model
        "think": "low",                    # for thinking models (gpt-oss ...): low = fast answers
    },
    "layout": {
        "page_size": "A4",
        "max_key_points": 5,
        "max_flow_steps": 6,
        "max_snapshot_stories": 4,         # "other stories" cards, each with 2-3 lines of context
        "max_tiles": 4,
        "max_full_forms": 6,
        "max_also": 3,
        "inline_meanings": True,           # add (meaning) after hard words in paragraphs
        "max_meanings_per_paragraph": 6,
        "inline_full_forms": True,         # add (Full form - role) after abbreviations
    },
    "colors": {
        "navy": "#14365d",
        "orange": "#f08a24",
        "light": "#eef3f8",
        "teal": "#0b8aa6",
        "green": "#2e8b57",
        "grey": "#f3f4f6",
        "text": "#1d2733",
        "muted": "#5b6675",
    },
    "fonts": {
        "regular": ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf",
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
        "bold": ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
    },
    "feeds": [
        {"name": "The Hindu", "url": "https://www.thehindu.com/news/national/feeder/default.rss", "hint": "National"},
        {"name": "The Hindu", "url": "https://www.thehindu.com/news/international/feeder/default.rss", "hint": "International"},
        {"name": "The Hindu", "url": "https://www.thehindu.com/news/national/other-states/feeder/default.rss", "hint": "Regional (States)"},
        {"name": "The Hindu", "url": "https://www.thehindu.com/business/Economy/feeder/default.rss", "hint": "Economic"},
        {"name": "The Hindu", "url": "https://www.thehindu.com/sci-tech/science/feeder/default.rss", "hint": "Major Inventions and Science"},
        {"name": "Times of India", "url": "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "hint": "National"},
        {"name": "Times of India", "url": "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "hint": "International"},
        {"name": "Times of India", "url": "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms", "hint": "Financial"},
        {"name": "Indian Express", "url": "https://indianexpress.com/section/india/feed/", "hint": "National"},
        {"name": "PIB", "url": "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "hint": "National"},
        {"name": "Mint", "url": "https://www.livemint.com/rss/economy", "hint": "Economic"},
        {"name": "BBC", "url": "https://feeds.bbci.co.uk/news/world/rss.xml", "hint": "International"},
        {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml", "hint": "International"},
        {"name": "ScienceDaily", "url": "https://www.sciencedaily.com/rss/top/science.xml", "hint": "Major Inventions and Science"},
    ],
    # The 12 pages. Rename, reorder or change keywords/queries freely.
    "sections": [
        {"name": "National", "queries": ["India government", "Union Cabinet India", "Supreme Court India"],
         "keywords": ["union government", "centre", "ministry", "cabinet", "supreme court", "high court", "scheme",
                      "pib", "pm modi", "prime minister", "president murmu", "nationwide", "union minister",
                      "railway", "census", "ugc", "education", "health ministry", "lok sabha", "rajya sabha"]},
        {"name": "International", "queries": ["world news", "United Nations"],
         "keywords": ["un ", "united nations", "us ", "president trump", "europe", "uk ", "france", "germany",
                      "japan", "africa", "global", "world", "summit", "election in", "who ", "foreign"]},
        {"name": "Regional (States)", "queries": ["state government India chief minister"],
         "keywords": ["chief minister", "state government", "assembly", "district", "governor"],
         "exclude": ["gold", "silver", "share price", "sensex"]},
        {"name": "Defence", "queries": ["Indian Army OR Indian Navy OR Indian Air Force OR DRDO",
                                        "India defence ministry"],
         "keywords": ["army", "navy", "air force", "iaf", "drdo", "missile", "defence", "military", "exercise",
                      "warship", "submarine", "fighter jet", "rafale", "tejas", "brahmos", "soldier", "jawan",
                      "border", "crpf", "bsf", "coast guard", "itbp", "cds", "agniveer"]},
        {"name": "Politics", "queries": ["India politics BJP Congress", "Election Commission India"],
         "keywords": ["bjp", "congress", "party", "election", "poll", "vote", "candidate", "opposition", "mla",
                      "mp ", "rally", "alliance", "nda", "india bloc", "aap", "tmc", "dmk", "manifesto"]},
        {"name": "Financial", "queries": ["Sensex Nifty", "RBI SEBI banking"],
         "keywords": ["rbi", "sebi", "bank", "sensex", "nifty", "stock", "share", "ipo", "rupee", "loan",
                      "repo", "investor", "market", "fund", "insurance", "credit", "bond", "crypto"]},
        {"name": "Economic", "queries": ["India GDP inflation economy", "India trade exports"],
         "keywords": ["gdp", "inflation", "economy", "economic", "growth", "trade", "export", "import", "tariff",
                      "gst", "tax", "fiscal", "budget", "cpi", "wpi", "iip", "manufacturing", "pmi", "fdi",
                      "deficit", "imf", "world bank"]},
        {"name": "Neighbouring Countries", "queries": ["Pakistan OR Bangladesh OR Nepal OR Sri Lanka India",
                                                       "China OR Bhutan OR Maldives OR Myanmar OR Afghanistan India"],
         "keywords": ["pakistan", "china", "chinese", "nepal", "bhutan", "bangladesh", "sri lanka", "myanmar",
                      "maldives", "afghanistan", "taliban", "dhaka", "kathmandu", "colombo", "islamabad",
                      "beijing", "male", "thimphu", "kabul"]},
        {"name": "Major Inventions and Science", "queries": ["ISRO", "science discovery research"],
         "keywords": ["isro", "nasa", "space", "satellite", "launch", "scientist", "research", "study",
                      "discovery", "technology", "ai ", "artificial intelligence", "quantum", "vaccine", "gene",
                      "climate", "species", "invention", "rocket", "moon", "mars", "chip", "semiconductor"]},
        {"name": "Geopolitical", "queries": ["India foreign policy", "Quad OR BRICS OR SCO OR G20"],
         "keywords": ["strategic", "geopolitic", "alliance", "quad", "brics", "sco", "g20", "g7", "nato",
                      "indo-pacific", "sanction", "treaty", "bilateral", "diplomat", "external affairs",
                      "jaishankar", "foreign minister", "talks", "visit", "ties"]},
        {"name": "Miscellaneous", "queries": ["India award sports"],
         "keywords": ["award", "sport", "cricket", "olympic", "medal", "prize", "festival", "day ", "index",
                      "report", "ranking", "heritage", "appointed", "died", "book", "film"]},
        {"name": "WAR SECTION", "war": True},
    ],
}


def deep_merge(base, extra):
    out = copy.deepcopy(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config():
    cfg = DEFAULT_CONFIG
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = deep_merge(DEFAULT_CONFIG, json.load(f))
    cfg = copy.deepcopy(cfg)
    for k, p in cfg["paths"].items():
        if not os.path.isabs(p):
            cfg["paths"][k] = os.path.join(ROOT, p)
        os.makedirs(cfg["paths"][k], exist_ok=True)
    ensure_user_data(cfg)
    return cfg


def save_config(user_cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(user_cfg, f, indent=2, ensure_ascii=False)


def read_user_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def ensure_user_data(cfg):
    """Copy the built-in glossary/words/facts/wars into user_data/ once, so the user can edit them."""
    ud = cfg["paths"]["user_data"]
    for name in os.listdir(PKG_DATA):
        dst = os.path.join(ud, name)
        if not os.path.exists(dst):
            shutil.copy(os.path.join(PKG_DATA, name), dst)


def user_file(cfg, name):
    return os.path.join(cfg["paths"]["user_data"], name)


def load_json(path, default=None):
    if not os.path.exists(path):
        return copy.deepcopy(default)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
