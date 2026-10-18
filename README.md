# Daily News Digest (free CLI)

Makes a 12-page, colour-coded A4 current-affairs PDF for defence and competitive exam preparation, one page per
section: National, International, Regional (States), Defence, Politics, Financial, Economic, Neighbouring
Countries, Science, Geopolitical, Miscellaneous and a WAR SECTION.

**Completely free: no paid API, no account, no API key, no server.** It reads free publisher RSS feeds
(The Hindu, Times of India, Indian Express, PIB, Mint, BBC, Al Jazeera, ScienceDaily), free Google News
search and your own newspaper PDFs. Everything runs on your own computer. All it needs is an internet connection.

---

## Quick start on Windows

1. Install **Python 3.9+** from https://www.python.org/downloads/ and **tick "Add python.exe to PATH"** in the installer.
2. On this page click the green **Code** button → **Download ZIP**, and unzip it to e.g. `C:\news-digest`.
3. Open that folder in File Explorer, click the address bar, type `cmd` and press Enter. In the black window run:
   ```bat
   python -m pip install -r requirements.txt
   ```
4. Double-click **`install.bat`** in the folder (lets you type `digest` from any terminal).
5. Close the window, open a **new** Command Prompt (`Win` → `cmd` → Enter) and run:
   ```bat
   digest run today --open
   ```
   After about a minute your 12-page PDF opens. It is saved in the `output` folder.

Type `digest` alone for the menu. Skipped step 4? Run it from inside the folder with `digest.bat run today --open`
(cmd) or `.\digest.bat run today --open` (PowerShell). Something wrong? See [Troubleshooting](#troubleshooting).

---

## Install (step by step, about 5 minutes)

### 1. Install Python (once)
- Download **Python 3.9 or newer** (free) from https://www.python.org/downloads/
- **Windows: on the first installer screen, tick "Add python.exe to PATH"**, then click *Install Now*.
- Check it worked: open a new terminal (press `Win`, type `cmd`, Enter) and type `python --version`.
  You should see something like `Python 3.12.x`.

### 2. Get this tool
**Option A, no Git needed:** on this GitHub page click the green **Code** button, then **Download ZIP**.
Unzip it to a folder you'll keep, e.g. `C:\news-digest` (or `Documents\news-digest`).

**Option B, with Git:**
```
git clone https://github.com/yoggi1234/news-digest.git
cd news-digest
```

### 3. Install the dependencies (once)
Open a terminal **inside the tool's folder** (in File Explorer, open the folder, click the address bar,
type `cmd`, press Enter) and run:
```
python -m pip install -r requirements.txt
```
That installs four free Python libraries:

| Library | What it does in this tool |
|---|---|
| `reportlab` | draws the 12-page PDF |
| `pypdf` | reads text from newspaper PDFs you give it |
| `feedparser` | reads the free news RSS feeds |
| `trafilatura` | downloads the full text of the lead articles |

Everything else comes with Python itself.

### 4. Make `digest` work in any terminal (Windows, once)
Double-click **`install.bat`** in the folder. It adds the folder to your user PATH (no admin rights needed), so you
can type `digest` in any **new** cmd, PowerShell or Git Bash window, from any folder. `uninstall.bat` undoes it.

**macOS / Linux:** run `chmod +x digest` once, then add the folder to your PATH, e.g. add
`export PATH="$PATH:$HOME/news-digest"` to `~/.bashrc` or `~/.zshrc` (use `python3` if `python` isn't found).

### 5. First run
Open a **new** terminal and type:
```
digest run today --open
```
After about a minute your PDF opens. It's saved in the tool's `output` folder as
`Daily_News_Digest_YYYY-MM-DD.pdf`. Or just type `digest` for the menu.

### Optional extras (all free)
| Extra | Why | How |
|---|---|---|
| **Ollama** (local AI, runs on your PC) | smoother, simpler English in the paragraphs | install from https://ollama.com, then `ollama pull llama3.2`; the tool finds it on its own |
| **pdftotext** (Poppler) | slightly better reading of newspaper PDF layouts | comes with Git for Windows; without it the tool uses `pypdf` |
| **ocrmypdf** | scanned (photo) newspaper PDFs have no text; this adds it | `pip install ocrmypdf` (also needs Tesseract) |

**Ollama cloud (no download, runs over the internet):** install Ollama, run `ollama signin` (free account), then
`ollama pull gemma4:31b-cloud` and `digest config set llm.model gemma4:31b-cloud` (in the Free plan; tested best for simple English). Free tier has usage limits;
if it is reached or the internet drops, that run simply falls back to normal writing. `llm.parallel` (default 4)
sets how many requests go at once.

Without Ollama the tool still works fully: it builds paragraphs from real sentences taken from the articles.

### Troubleshooting
| Problem | Fix |
|---|---|
| `python` is not recognized | Reinstall Python and tick "Add python.exe to PATH", or use `py` instead of `python` |
| `pip` is not recognized | Use `python -m pip install -r requirements.txt` |
| `digest` is not recognized | Run `install.bat`, then open a **new** terminal. Or run `python digest.py ...` inside the folder |
| PowerShell says `digest` not found inside the folder | Type `.\digest` (PowerShell needs `.\` for the current folder), or run install.bat |
| "No news found" | Check the internet connection, or give newspaper PDFs with `--pdf` |
| A feed shows 0 items | Websites sometimes change feed addresses: `digest feeds test`, then `digest feeds add` a new one |
| Strange symbols / boxes in the terminal | `digest config set ui.unicode false`, or use Windows Terminal |
| Animations too slow or not wanted | add `--plain` to any command, or `digest config set ui.animations false` |

Your PDFs, drafts, history and settings always stay inside the tool's folder (`output`, `drafts`, `state`,
`user_data`, `config.json`), wherever you run the command from. To start fresh, delete those folders.

---

## Looks
Type `digest` alone for the menu: a colour banner, then an arrow-key menu (↑/↓ or number keys, Enter, `q` to quit)
with the chosen option highlighted. While news is collected, a radioactive sign spins next to a progress bar and
live status lines, and below it a **LIVE NEWS MONITOR** shows real headlines as they arrive, drifting slowly
upward (new ones fade in at the bottom). Each section glows in its own colour (Defence green, Politics magenta,
Science purple, Markets gold, War red, ...), and **hot news** pulses bright red with a 🔥 HOT badge: breaking
words like killed / blast / earthquake, or the same story from 5 or more outlets. While the PDF is drawn,
the monitor shows the 12 lead headlines going into it. When the PDF is ready, a rocket counts down and lifts
off. Confidence shows in colour: High in green, Medium in yellow, Low in red.
The monitor needs a terminal at least 76 columns wide and about 25 lines tall; smaller windows get a one-line
spinner. `digest config set ui.min_build_seconds 0` skips the short monitor pause while the PDF is drawn.
- Turn it off for one command: add `--plain` (e.g. `digest run today --plain`).
- Turn it off for good: `digest config set ui.animations false` and/or `digest config set ui.colors false`.
- Old console without the symbols? `digest config set ui.unicode false` (uses plain ASCII).
- When output goes to a file or another program, colours and animations switch off on their own.

## Daily use
After install.bat, type `digest ...` in any terminal. (Without install.bat: open a terminal in this folder;
in PowerShell type `.\digest ...`, because PowerShell runs programs from the current folder only with `.\`.)
```
digest                         # simple menu
digest run today --open        # collect + make PDF + open it
digest run 2026-10-17 --pdf "D:\papers\TOI.pdf" "D:\papers\Hindu.pdf" --war Sudan
digest run today --expect "CDS 2 result" "RBI policy"    # says so if an expected item is missing
digest run today --no-web      # newspapers only
digest text today --save       # bullet-point text version
```
Or drop PDFs into `inbox\`; every run reads them. Each PDF's **date is checked**: a file from another day is
reported and used only as background, never as that day's news.

Output: `output\Daily_News_Digest_YYYY-MM-DD.pdf` (+ `.txt` with `--text`).

## Review and edit before building (customisation)
`collect` writes an editable draft (`drafts\YYYY-MM-DD.json`); `build` turns it into the PDF.
Fields you edit are **locked**, so running `collect` again won't overwrite them.
```
digest collect today
digest check today                       # weak spots: single-source leads, missing India angle, unknown abbreviations
digest show today 4                      # page 4 content + all stories found for it
digest edit today 4 --use 3              # make story 3 the lead headline
digest edit today Defence headline "New headline"
digest edit today 4 paragraph "Your text..."     # meanings, full forms and Full Forms column are added for you (--raw to skip)
digest edit today 6 tiles --value "6.5%=repo rate|4.1%=CPI inflation"
digest edit today 6 key_points --add "Another point (The Hindu)"
digest edit today 6 key_points --remove 2
digest edit today 12 steps --value "2014: ...|2022: ...|Now: ..."
digest edit today 3 flow.mode flow       # flow (arrows, numbers) or snapshot (boxes only)
digest edit today 5 benefit_label "WHY IT MATTERS FOR INDIA"
digest edit today 9 advanced "Your exam fact"
digest open today                        # edit the whole draft in Notepad
digest build today --open
```

## Knowledge tools (all saved in `user_data\`, all editable)
```
digest glossary add NPPA "National Pharmaceutical Pricing Authority" "fixes and watches medicine prices"
digest glossary list bank          # search
digest glossary lookup HUMINT --save   # free Wikipedia lookup (check what it saved)
digest words add "deterrence" "stopping an attack by showing strength"
digest facts add "The CAG is appointed under Article 148." --keys "cag,audit"   # Advanced-point bank
digest war list                    # wars and when each was last covered
digest war add "Israel-Hezbollah conflict" "Hezbollah Israel Lebanon" --keywords "hezbollah,lebanon,beirut"
digest war add-event "Sudan" "Mar 2025: Army retakes Khartoum palace"
digest war set-log Russia 2026-10-13      # record a war you covered by hand
digest correct 2026-10-16 "Deficit was $30.2 bn, not $32 bn"   # printed on the next edition's Misc page
```

## Look and sources
```
digest config set colors.navy "#14365d"        # any colour in the spec
digest config set title "ACC Daily Digest"
digest config set layout.max_key_points 4
digest config set layout.max_snapshot_stories 4   # "other stories" cards (headline + 2-3 lines each)
digest config set layout.inline_meanings false
digest config set llm.mode off
digest config show
digest config reset colors
digest section list
digest section rename 11 "Awards and Sports"
digest section keywords 4 "agni,prithvi"
digest section query 4 "Indian Navy"
digest section move 10 2
digest feeds list
digest feeds add "Hindustan Times" "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml" --hint National
digest feeds test
```

## How it decides (honesty rules)
- Stories are merged across outlets. A lead with only one source is marked **verify**, and so is any key point with only one source.
  The footer shows Confidence (High = 3+ sources).
- If outlets give different casualty or troop numbers for the same story, the page gets a **Note: Sources differ...**
- Headlines already in the last 3 editions are skipped unless they look like updates (marked UPDATE).
- War page: rotates wars and avoids yesterday's war unless it is clearly bigger news. It says which war it chose and why.
  The background timeline comes from `user_data\wars.json`; the "NOW" step and the paragraph come from today's news.
- Benefit for India: uses sentences from the articles. If there is none, the box says it needs writing; it is never made up.
- Without Ollama, paragraphs are made of real sentences picked from the articles, so they are accurate but less smooth.
  Read the `check` output before you build.

Scanned (image-only) newspapers have no text; run them through OCR first, e.g. `pip install ocrmypdf`.
