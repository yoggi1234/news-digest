"""Terminal look and feel: colours, a spinning radioactive loader, a rocket launch, an arrow-key menu.

Everything here uses only the Python standard library and ANSI escape codes. When output is not a real
terminal (piped, redirected, tests), or with --plain / NO_COLOR / ui.animations=false, it falls back to
plain text, so the tool never depends on any of this to work."""
import math
import os
import shutil
import sys
import threading
import time

ESC = "\x1b["
STATE = {"color": False, "anim": False, "fancy": False}

PALETTE = {  # matches the PDF colours
    "navy": (20, 54, 93), "orange": (240, 138, 36), "teal": (11, 138, 166), "green": (46, 170, 87),
    "yellow": (250, 204, 21), "red": (230, 70, 70), "grey": (140, 150, 160), "white": (240, 240, 240),
    "sky": (120, 190, 255),
}


# ------------------------------------------------------------------ setup
def _enable_windows_ansi():
    if os.name != "nt":
        return True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        return False


def setup(cfg, plain=False):
    ui = cfg.get("ui", {})
    tty = sys.stdout.isatty() or bool(os.environ.get("DIGEST_FORCE_UI"))  # FORCE_UI: for testing the looks
    ok = tty and not plain and not os.environ.get("NO_COLOR") and not os.environ.get("DIGEST_PLAIN")
    ok = ok and (_enable_windows_ansi() or bool(os.environ.get("DIGEST_FORCE_UI")))
    STATE["color"] = ok and ui.get("colors", True)
    STATE["anim"] = ok and ui.get("animations", True)
    fancy = ui.get("unicode", "auto")
    if fancy == "auto":  # Windows Terminal, VS Code and non-Windows terminals have the symbols we use
        fancy = bool(os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM") or os.name != "nt")
    STATE["fancy"] = bool(fancy)


# ------------------------------------------------------------------ colours
def rgb(name):
    r, g, b = PALETTE.get(name, PALETTE["white"])
    return f"{ESC}38;2;{r};{g};{b}m"


def c(text, color=None, bold=False, bg=None, rev=False):
    if not STATE["color"]:
        return str(text)
    pre = ""
    if bold:
        pre += f"{ESC}1m"
    if rev:
        pre += f"{ESC}7m"
    if color:
        pre += rgb(color)
    if bg:
        r, g, b = PALETTE[bg]
        pre += f"{ESC}48;2;{r};{g};{b}m"
    return f"{pre}{text}{ESC}0m"


def sym(fancy, plain):
    return fancy if STATE["fancy"] else plain


def ok(msg):
    print(c(sym("✔ ", "OK ") + msg, "green", bold=True))


def warn(msg):
    print(c(sym("⚠ ", "! ") + msg, "yellow"))


def err(msg):
    print(c(sym("✖ ", "X ") + msg, "red", bold=True), file=sys.stderr)


def info(msg):
    print(c(msg, "sky"))


def confidence(text):
    t = str(text)
    col = "green" if t.startswith("High") else "yellow" if t.startswith("Medium") else "red" if t.startswith("Low") else "grey"
    return c(t, col, bold=True)


# ------------------------------------------------------------------ banner
FONT = {
    "D": [" ____  ", "|  _ \\ ", "| | | |", "| |_| |", "|____/ "],
    "I": [" ___ ", "|_ _|", " | | ", " | | ", "|___|"],
    "G": ["  ____ ", " / ___|", "| |  _ ", "| |_| |", " \\____|"],
    "E": [" _____ ", "| ____|", "|  _|  ", "| |___ ", "|_____|"],
    "S": [" ____  ", "/ ___| ", "\\___ \\ ", " ___) |", "|____/ "],
    "T": [" _____ ", "|_   _|", "  | |  ", "  | |  ", "  |_|  "],
}


def _gradient(line, start=(240, 138, 36), end=(11, 166, 200)):
    if not STATE["color"]:
        return line
    out, n = [], max(len(line) - 1, 1)
    for i, ch in enumerate(line):
        t = i / n
        r, g, b = (int(start[k] + (end[k] - start[k]) * t) for k in range(3))
        out.append(f"{ESC}1;38;2;{r};{g};{b}m{ch}")
    return "".join(out) + f"{ESC}0m"


def banner(subtitle="Daily News Digest  |  free  |  for defence and competitive exams"):
    rows = ["".join(FONT[ch][i] for ch in "DIGEST") for i in range(5)]
    print()
    for r in rows:
        print("  " + _gradient(r))
        if STATE["anim"]:
            time.sleep(0.04)
    sub = sym("☢  ", "") + subtitle + sym("  🚀", "")
    if STATE["anim"]:
        sys.stdout.write("  ")
        for ch in sub:
            sys.stdout.write(c(ch, "grey"))
            sys.stdout.flush()
            time.sleep(0.008)
        print()
    else:
        print("  " + c(sub, "grey"))
    print()


# ------------------------------------------------------------------ spinning radioactive sign
def trefoil(angle, rows=9, cols=19):
    """Radiation symbol drawn from maths, rotated by `angle` degrees (so it can spin)."""
    full = sym("█", "#")
    dot = sym("●", "@")
    cx, cy = (cols - 1) / 2, (rows - 1) / 2
    out = []
    for j in range(rows):
        line = []
        for i in range(cols):
            x, y = (i - cx) / cx, (j - cy) / cy
            r = math.hypot(x, y)
            th = (math.degrees(math.atan2(-y, x)) - angle) % 120
            if r < 0.2:
                line.append(c(dot, "yellow", bold=True))
            elif 0.32 < r < 1.0 and th < 60:
                line.append(c(full, "yellow"))
            elif 0.98 < r < 1.12:
                line.append(c(sym("·", "."), "grey"))
            else:
                line.append(" ")
        out.append("".join(line))
    return out


def bar(done, total, width=26):
    total = max(total, 1)
    filled = int(width * min(done, total) / total)
    if STATE["fancy"]:
        return c("█" * filled, "orange") + c("░" * (width - filled), "grey")
    return "[" + "#" * filled + "-" * (width - filled) + "]"


CATEGORY_COLORS = {  # glow colour per section (RGB), matched by the start of the section name
    "National": (255, 160, 70), "International": (110, 190, 255), "Regional": (120, 220, 140),
    "Defence": (150, 210, 90), "Politics": (235, 120, 220), "Financial": (255, 205, 80),
    "Economic": (200, 230, 110), "Neighbouring": (90, 225, 225), "Major Inventions": (185, 145, 255),
    "Geopolitical": (140, 170, 255), "Miscellaneous": (255, 245, 160), "WAR": (255, 90, 90),
}
SHORT_TAG = {"National": "NATIONAL", "International": "WORLD", "Regional": "STATES", "Defence": "DEFENCE",
             "Politics": "POLITICS", "Financial": "MARKETS", "Economic": "ECONOMY", "Neighbouring": "NEIGHBOURS",
             "Major Inventions": "SCIENCE", "Geopolitical": "GEOPOLITICS", "Miscellaneous": "MISC", "WAR": "WAR"}
HOT_RGB = ((255, 30, 30), (255, 150, 150))


def _cat_key(category):
    for k in CATEGORY_COLORS:
        if str(category or "").startswith(k):
            return k
    return "Miscellaneous"


def _glow(text, base, level, bold=False):
    """Text in colour `base` scaled by brightness `level` (0..1.2) - redrawing with a changing level glows."""
    if not STATE["color"]:
        return text
    r, g, b = (max(0, min(255, int(v * level))) for v in base)
    return f"{ESC}{'1;' if bold else ''}38;2;{r};{g};{b}m{text}{ESC}0m"


class Loader:
    """Context manager: spinning radioactive sign + status + progress bar + recent log lines, and below it a
    LIVE NEWS MONITOR where real headlines scroll slowly upward, each section glowing in its own colour and
    hot news pulsing red. Falls back to plain log printing when animations are off."""
    TOP = 9
    MON_LINES = 10

    def __init__(self, title, min_seconds=0.0):
        self.title, self.min_seconds = title, min_seconds
        self.lines, self.stage, self.done, self.total = [], "Starting", 0, 0
        self.start = time.time()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        cols, rows = shutil.get_terminal_size((80, 24))
        self.cols = cols
        self.big = STATE["anim"] and cols >= 76
        self.small = STATE["anim"] and not self.big
        self.monitor = self.big and rows >= self.TOP + self.MON_LINES + 6
        self.rows = self.TOP + (self.MON_LINES + 3 if self.monitor else 0)
        # one small queue per section, shown in turn so every colour appears; shown: [title, source, cat, hot, age]
        self.queues, self.order, self.turn, self.shown, self.seen = {}, [], 0, [], 0

    # called by the collector -------------------------------------------------
    def log(self, msg):
        if str(msg).strip() == self.title:  # the panel already shows the title
            return
        with self.lock:
            self.lines.append(str(msg))
        if not (self.big or self.small):
            print(msg)

    def progress(self, stage, done=0, total=0):
        with self.lock:
            self.stage, self.done, self.total = stage, done, total

    def headline(self, title, source="", category="", hot=False):
        """Queue a headline for the monitor. Each section keeps only its newest few, hot news first."""
        if not self.monitor:
            return
        cat = _cat_key(category)
        with self.lock:
            self.seen += 1
            q = self.queues.setdefault(cat, [])
            if cat not in self.order:
                self.order.append(cat)
            q.append([str(title), str(source), cat, bool(hot), 0])
            if len(q) > 4:  # keep only the newest few per section
                q.pop(0)

    def _next(self):
        """Next headline, taking sections in turn (caller holds the lock)."""
        for _ in range(len(self.order)):
            cat = self.order[self.turn % len(self.order)]
            self.turn += 1
            if self.queues.get(cat):
                return self.queues[cat].pop(0)
        return None

    # drawing -----------------------------------------------------------------
    def _top(self, k):
        el = time.time() - self.start
        with self.lock:
            stage, done, total, recent = self.stage, self.done, self.total, self.lines[-6:]
        prog = (bar(done, total) + c(f" {done}/{total}", "white")) if total else \
            c(sym("·" * (k % 4 + 1), "." * (k % 4 + 1)), "orange")
        right = [c(self.title, "orange", bold=True), c(f"{stage}", "sky") + c(f"   {el:5.1f}s", "grey"), prog, ""]
        right += [c("  " + l.strip()[:60], "grey") for l in recent]
        right += [""] * (self.TOP - len(right))
        left = trefoil(k * 7)
        return [f"  {left[i]}   {right[i]}" for i in range(self.TOP)]

    def _monitor(self, k):
        w = min(self.cols - 4, 118)
        inner = w - 2
        h, v = sym("═", "="), sym("║", "|")
        tl, tr, bl, br = sym("╔", "+"), sym("╗", "+"), sym("╚", "+"), sym("╝", "+")
        frame_col = (60, 120, 170)
        pulse = 0.85 + 0.15 * math.sin(k * 0.25)
        with self.lock:
            nxt = self._next() if k % 5 == 0 else None  # slow upward scroll: one new headline every ~0.4 s
            if nxt:
                self.shown.append(nxt)
                self.shown = self.shown[-self.MON_LINES:]
            for s in self.shown:
                s[4] += 1
            shown, waiting, seen = list(self.shown), sum(len(q) for q in self.queues.values()), self.seen
        live = c(sym(" ● ", " * "), "red", bold=True) if k % 10 < 6 else "   "
        title = f"{live}{c('LIVE NEWS MONITOR', 'white', bold=True)}" + c(f"  {seen} headlines seen, {waiting} waiting ", "grey")
        title_len = 3 + 17 + len(f"  {seen} headlines seen, {waiting} waiting ")
        out = ["  " + _glow(tl + h * 2, frame_col, pulse) + title + _glow(h * max(0, inner - 2 - title_len) + tr, frame_col, pulse)]
        pad_rows = self.MON_LINES - len(shown)
        rows = [None] * pad_rows + shown
        for i, s in enumerate(rows):
            if s is None:
                body = " " * inner
            else:
                text, source, cat, hot, age = s
                tag = SHORT_TAG.get(cat, "NEWS")
                badge = sym("🔥 HOT ", "!HOT ") if hot else ""
                plain = f" {badge}{tag:<11} {text}" + (f"  - {source}" if source else "")
                vis = len(plain) + (1 if hot and STATE["fancy"] else 0)  # the flame emoji is 2 columns wide
                if vis > inner:
                    plain = plain[:inner - 4 - (vis - len(plain))] + "... "
                    vis = inner
                fade = min(1.0, 0.25 + age * 0.15)  # new lines fade in at the bottom
                if i == 0 and pad_rows == 0:
                    fade *= 0.55  # the oldest line fades out at the top
                if hot:
                    t = 0.5 + 0.5 * math.sin(k * 0.6 + i)
                    col = tuple(int(HOT_RGB[0][j] + (HOT_RGB[1][j] - HOT_RGB[0][j]) * t) for j in range(3))
                    body = _glow(plain, col, fade * 1.0, bold=True)
                else:
                    glow = 0.78 + 0.22 * math.sin(k * 0.18 + i * 0.7)
                    body = _glow(plain, CATEGORY_COLORS[cat], fade * glow)
                body += " " * max(0, inner - vis)
            out.append("  " + _glow(v, frame_col, pulse) + body + _glow(v, frame_col, pulse))
        legend = "  ".join(_glow(SHORT_TAG[kk], CATEGORY_COLORS[kk], 1.0) for kk in
                           ("National", "Defence", "Politics", "Financial", "Economic", "Major Inventions", "WAR"))
        out.append("  " + _glow(bl + h * inner + br, frame_col, pulse))
        out.append("   " + _glow(sym("🔥 HOT", "!HOT"), HOT_RGB[0], 1.0, bold=True) + c(" = many outlets / breaking   ", "grey") + legend)
        return out

    def _run(self):
        k = 0
        spin = sym("◐◓◑◒", "|/-\\")
        drawn = False
        while not self.stop.is_set():
            if self.big:
                frame = self._top(k) + (self._monitor(k) if self.monitor else [])
                if drawn:
                    sys.stdout.write(f"{ESC}{self.rows}A")
                sys.stdout.write("".join(f"\r{ESC}2K{line}\n" for line in frame))
                drawn = True
            else:
                with self.lock:
                    stage, done, total = self.stage, self.done, self.total
                extra = f" {bar(done, total, 16)} {done}/{total}" if total else ""
                sys.stdout.write(f"\r{ESC}2K  " + c(sym("☢", "*"), "yellow", bold=True) + " "
                                 + c(spin[k % len(spin)], "orange") + " " + c(stage, "sky") + extra)
            sys.stdout.flush()
            k += 1
            time.sleep(0.08)
        if self.big and drawn:  # wipe the animation, leave a tidy log behind
            sys.stdout.write(f"{ESC}{self.rows}A" + "".join(f"\r{ESC}2K\n" for _ in range(self.rows))
                             + f"{ESC}{self.rows}A")
        elif self.small:
            sys.stdout.write(f"\r{ESC}2K")
        sys.stdout.flush()

    def __enter__(self):
        if self.big or self.small:
            sys.stdout.write(f"{ESC}?25l")  # hide cursor
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
        return self

    def __exit__(self, *exc):
        if self.big or self.small:
            left = self.min_seconds - (time.time() - self.start)
            if left > 0 and exc[0] is None:  # let short jobs (PDF drawing) show the monitor for a moment
                time.sleep(left)
            self.stop.set()
            self.thread.join()
            sys.stdout.write(f"{ESC}?25h")
            sys.stdout.flush()
            for l in self.lines:
                print(c(l, "grey") if l.startswith("  ") else c(l, "white", bold=True))
            print(c(f"  done in {time.time() - self.start:.1f}s", "grey"))
        return False


# ------------------------------------------------------------------ rocket launch
ROCKET = [
    "     /\\     ",
    "    /  \\    ",
    "   | DN |   ",
    "   |    |   ",
    "   | () |   ",
    "  /|    |\\  ",
    " /_|____|_\\ ",
    "    /  \\    ",
]
FLAMES = [["   ' )( '   ", "    )**(    ", "     ''     "],
          ["    (**)    ", "   ' )( '   ", "     ..     "],
          ["   ( ** )   ", "    '**'    ", "     ''     "]]


def rocket(message, height=14):
    """Countdown and lift-off, then the final message. Plain one-liner when animations are off."""
    if not STATE["anim"] or shutil.get_terminal_size((80, 24)).columns < 40:
        ok(message)
        return
    width = 44
    pad = " " * 6

    def paint(rows):
        sys.stdout.write("".join(f"\r{ESC}2K{pad}{r}\n" for r in rows))
        sys.stdout.flush()

    def colour_rocket(i, line):
        if i == 2:
            return c(line, "white", bold=True).replace("DN", c("DN", "orange", bold=True)) if STATE["color"] else line
        return c(line, "white")

    sys.stdout.write(f"{ESC}?25l")
    first = True
    total_frames = 3 * 6 + height + 6
    for f in range(total_frames):
        countdown = f < 18
        lift = 0 if countdown else f - 18
        rows = [""] * height
        top = height - len(ROCKET) - 3 - lift  # rocket row position
        for i, line in enumerate(ROCKET):
            y = top + i
            if 0 <= y < height:
                rows[y] = colour_rocket(i, line)
        fl = FLAMES[f % 3]
        if not countdown:
            for i, line in enumerate(fl):
                y = top + len(ROCKET) + i
                if 0 <= y < height:
                    rows[y] = c(line, "orange" if i == 0 else "yellow" if i == 1 else "red")
            for y in range(max(top + len(ROCKET) + 3, 0), height):  # smoke trail
                rows[y] = c(("  .  ' .  " if (y + f) % 2 else " '  .  '  ")[: width // 3], "grey")
        else:
            base = height - 3
            rows[base] = c("   ________   ", "grey")
            n = 3 - f // 6
            rows[1] = c(f"  T-minus {n} ...", "yellow", bold=True) if n > 0 else c("  IGNITION!", "red", bold=True)
            if f % 6 > 2:
                rows[base + 1] = c("  ~ ~ ~ ~ ~ ~ ", "grey")
        if not first:
            sys.stdout.write(f"{ESC}{height}A")
        paint(rows)
        first = False
        time.sleep(0.12 if countdown else 0.06)
    sys.stdout.write(f"{ESC}{height}A" + "".join(f"\r{ESC}2K\n" for _ in range(height)) + f"{ESC}{height}A")
    sys.stdout.write(f"{ESC}?25h")
    print(c(sym("🚀 ", ">> ") + "LIFT-OFF!  ", "orange", bold=True) + c(message, "green", bold=True))


# ------------------------------------------------------------------ arrow-key menu
def _read_key():
    """Returns 'up', 'down', 'enter', 'quit', a digit, or None."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            ch2 = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(ch2)
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = sys.stdin.read(2)
                return {"[A": "up", "[B": "down"}.get(seq, "quit")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if ch in ("\r", "\n"):
        return "enter"
    if ch in ("q", "Q", "\x1b", "\x03"):
        return "quit"
    if ch in ("k", "w"):
        return "up"
    if ch in ("j", "s"):
        return "down"
    if ch.isdigit():
        return ch
    return None


def choose(title, options):
    """Highlighted arrow-key menu. Returns the chosen index, or None to quit.
    Falls back to typing a number when not in an interactive terminal."""
    if not (STATE["color"] and sys.stdin.isatty()):
        print(title)
        for i, o in enumerate(options, 1):
            print(f"  {i}. {o}")
        try:
            n = int(input("Choose: ").strip() or "0")
        except (ValueError, EOFError):
            return None
        return n - 1 if 1 <= n <= len(options) else None
    sel, first = 0, True
    print(c(title, "orange", bold=True) + c("   (arrow keys / number, Enter to choose, q to quit)", "grey"))
    sys.stdout.write(f"{ESC}?25l")
    try:
        while True:
            if not first:
                sys.stdout.write(f"{ESC}{len(options)}A")
            first = False
            for i, o in enumerate(options):
                if i == sel:
                    line = c(f" {sym('▶', '>')} {i + 1}. {o} ", "white", bold=True, bg="orange")
                else:
                    line = c(f"   {i + 1}. ", "grey") + c(o, "white")
                sys.stdout.write(f"\r{ESC}2K  {line}\n")
            sys.stdout.flush()
            k = _read_key()
            if k == "up":
                sel = (sel - 1) % len(options)
            elif k == "down":
                sel = (sel + 1) % len(options)
            elif k == "enter":
                return sel
            elif k == "quit":
                return None
            elif k and k.isdigit() and 1 <= (int(k) or 10) <= len(options):  # '0' picks option 10
                return (int(k) or 10) - 1
    finally:
        sys.stdout.write(f"{ESC}?25h")
        sys.stdout.flush()


def ask(prompt, default=""):
    try:
        v = input(c(sym("› ", "> ") + prompt, "sky")).strip()
    except EOFError:
        v = ""
    return v or default
