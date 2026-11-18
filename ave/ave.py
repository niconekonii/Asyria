# -*- coding: utf-8 -*-
"""
Ave - a no-killswitch focus timer for Windows, watched over by Oblivionis.

One file, Python standard library only.
  * Timer opens first: pick a preset or adjust minutes, press Start.
  * Presets = focus minutes / break minutes / rounds. Breaks lift blocks,
    the next round puts them back.
  * During focus, chosen .exe files are force-closed (ctypes snapshot every
    2 s, no subprocess) and - with admin - refused at launch (IFEO) and
    chosen websites are blocked (hosts file).
  * No stop button, close is refused, settings locked, survives reboot,
    relaunches itself if killed (scheduled task).
  * Fail-safe: anything that fails falls back to plain process killing,
    and every block is removed when the session ends. If removal needs
    admin and we don't have it, Ave asks Windows for it ("--cleanup").

Emergency unblock (only if something was ever left blocked):
    Ave.exe --cleanup        (or: python ave.py --cleanup)
"""

import os
import sys
import json
import time
import random
import ctypes
import subprocess

APP = "Ave"
IS_WIN = os.name == "nt"
FROZEN = getattr(sys, "frozen", False)
SELF = sys.executable if FROZEN else os.path.abspath(__file__)

DATA = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.dirname(SELF), APP)
try:
    os.makedirs(DATA, exist_ok=True)
except Exception:
    DATA = os.path.dirname(SELF)
STATE_FILE = os.path.join(DATA, "state.json")
CONFIG_FILE = os.path.join(DATA, "config.json")

HOSTS = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                     "System32", "drivers", "etc", "hosts")
MARK_A, MARK_B = "# Ave begin", "# Ave end"
IFEO_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
IFEO_DEBUGGER = "systray.exe"   # harmless Windows stub: blocked exe just never opens
TASK = "AveGuard"
NOWIN = 0x08000000              # CREATE_NO_WINDOW for helper commands

# Never killable, whatever the list says (Task Manager stays free on purpose).
PROTECTED = {
    "explorer.exe", "taskmgr.exe", "csrss.exe", "winlogon.exe", "wininit.exe",
    "services.exe", "lsass.exe", "smss.exe", "svchost.exe", "dwm.exe",
    "system", "registry", "ave.exe", "python.exe", "pythonw.exe",
}

# ---- palette: pure black, greys, one accent (Oblivionis stage-blue) -------
BG = "#000000"
SURFACE = "#0b0b0e"
SURFACE2 = "#15151b"
LINE = "#1d1d24"
FAINT = "#26262e"
FG = "#f2f2f4"
DIM = "#6e6e78"
ACCENT = "#3d63e0"
ACCENT_HI = "#5a7ef0"
ACCENT_DIM = "#0e1735"
ACCENT_MUTED = "#2a3f86"

# ---- Oblivionis: original lines, written in her voice -----------------------
IDLE = [
    "Choose your hour. Then surrender it to me.",
    "The stage is empty. Are you prepared to stand on it?",
    "Hesitation is unbecoming. Begin.",
    "I do not need your promises. I need your hours.",
    "Masks on. Hearts quiet. Whenever you are ready.",
]
FOCUS = [
    "The curtain has risen. No one leaves the stage mid-act.",
    "Your distractions were not invited to this performance.",
    "I did not ask for your comfort. I asked for your time.",
    "Play your part. Perfectly. Nothing less is acceptable.",
    "Oblivion is a gift. You will earn it at the end.",
    "Weakness may wait outside. It has no ticket.",
    "Stay. The music is not finished.",
    "You gave me this hour. I intend to keep it.",
    "Endure it. That is all I ask, and it is everything.",
    "Do not look for the door. There was never a door.",
]
CAUGHT = [
    "{n}? How shameless. Denied.",
    "Did you think I was not watching? {n} is closed.",
    "{n} has no role in this act.",
    "Again? Your resolve is thinner than paper. {n}, gone.",
    "I took {n} from you. You may thank me later.",
]
BREAK = [
    "Intermission. Breathe. I will call you back.",
    "A brief rest. Do not mistake it for freedom.",
    "The curtain falls, for now. Only for now.",
]
DONE = [
    "The act is over. You may remove your mask.",
    "Well performed. I release you.",
    "It is finished. Remember this feeling.",
]
REFUSE = [
    "There is no exit. Only the end of the act.",
    "You may not leave. You chose this, remember.",
    "Close me? How amusing. No.",
]
GLYPHS = "01#%&*+=<>/\\|"


# =============================================================================
# Helpers
# =============================================================================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except Exception:
        pass


def is_admin():
    try:
        return IS_WIN and ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def beep(freq=880, ms=120):
    if IS_WIN:
        try:
            import winsound
            winsound.Beep(freq, ms)
        except Exception:
            pass


def launch_parts():
    """(exe, args) to start this app again, without a console window."""
    if FROZEN:
        return SELF, ""
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return (w if os.path.exists(w) else exe), '"%s"' % SELF


def run_elevated(args):
    """Ask Windows (UAC) to run Ave as admin with extra args. True if started."""
    if not IS_WIN:
        return False
    exe, base = launch_parts()
    try:
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe,
                                                (base + " " + args).strip(), None, 1)
        return r > 32
    except Exception:
        return False


def online_time():
    """Trusted wall time from an HTTP Date header, or None if offline."""
    try:
        import urllib.request
        import email.utils
        req = urllib.request.Request("https://www.google.com/generate_204", method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as r:
            d = r.headers.get("Date")
        return email.utils.mktime_tz(email.utils.parsedate_tz(d)) if d else None
    except Exception:
        return None


# =============================================================================
# Processes (ctypes snapshot - no subprocess per tick)
# =============================================================================

if IS_WIN:
    import ctypes.wintypes as wt

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD),
                    ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    _k32 = ctypes.windll.kernel32
    _k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _INVALID = wt.HANDLE(-1).value


def processes():
    """[(pid, 'name.exe')] for every running process."""
    out = []
    if not IS_WIN:
        return out
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == _INVALID:
        return out
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append((e.th32ProcessID, e.szExeFile.lower()))
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    return out


def kill(pid):
    if not IS_WIN:
        return
    h = _k32.OpenProcess(0x0001, False, pid)
    if h:
        _k32.TerminateProcess(h, 1)
        _k32.CloseHandle(h)


# =============================================================================
# Blockers - every one returns True/False and never raises
# =============================================================================

def _clean_domain(d):
    d = d.strip().lower()
    for p in ("https://", "http://"):
        if d.startswith(p):
            d = d[len(p):]
    d = d.split("/")[0]
    return d[4:] if d.startswith("www.") else d


def _strip_hosts(text):
    out, skip = [], False
    for line in text.splitlines():
        s = line.strip()
        if s == MARK_A:
            skip = True
        elif s == MARK_B:
            skip = False
        elif not skip:
            out.append(line)
    return "\n".join(out).rstrip() + "\n"


def _flush_dns():
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True, creationflags=NOWIN)
    except Exception:
        pass


def hosts_block(sites):
    if not (IS_WIN and sites):
        return False
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            text = _strip_hosts(f.read())
        lines = [MARK_A]
        for s in sites:
            d = _clean_domain(s)
            if d:
                lines += ["0.0.0.0 " + d, "0.0.0.0 www." + d]
        lines.append(MARK_B)
        with open(HOSTS, "w", encoding="utf-8") as f:
            f.write(text + "\n".join(lines) + "\n")
        _flush_dns()
        return True
    except Exception:
        return False


def hosts_unblock():
    """True when the hosts file has no Ave section left."""
    if not IS_WIN:
        return True
    try:
        with open(HOSTS, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if MARK_A not in text:
            return True
        with open(HOSTS, "w", encoding="utf-8") as f:
            f.write(_strip_hosts(text))
        _flush_dns()
        return True
    except Exception:
        return False


def ifeo_block(exes):
    if not (IS_WIN and exes and is_admin()):
        return False
    import winreg
    ok = False
    for n in exes:
        try:
            k = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + n)
            winreg.SetValueEx(k, "Debugger", 0, winreg.REG_SZ, IFEO_DEBUGGER)
            winreg.CloseKey(k)
            ok = True
        except Exception:
            pass
    return ok


def ifeo_unblock(exes):
    """Removes only Ave's own Debugger values. True when none are left."""
    if not IS_WIN:
        return True
    import winreg
    ok = True
    for n in exes:
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + n)
            val, _ = winreg.QueryValueEx(k, "Debugger")
            winreg.CloseKey(k)
        except Exception:
            continue                      # no key / no value = nothing to undo
        if val != IFEO_DEBUGGER:
            continue                      # not ours, leave it alone
        try:
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + n,
                               0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(k, "Debugger")
            winreg.CloseKey(k)
        except Exception:
            ok = False
    return ok


def guard_install():
    """Scheduled task that relaunches Ave every minute while a session runs."""
    if not IS_WIN:
        return False
    exe, base = launch_parts()
    tr = ('"%s" %s --guard' % (exe, base)).strip()
    cmd = ["schtasks", "/Create", "/TN", TASK, "/TR", tr, "/SC", "MINUTE", "/MO", "1", "/F"]
    if is_admin():
        cmd += ["/RL", "HIGHEST"]
    try:
        return subprocess.run(cmd, capture_output=True, creationflags=NOWIN).returncode == 0
    except Exception:
        return False


def guard_remove():
    if IS_WIN:
        try:
            subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"],
                           capture_output=True, creationflags=NOWIN)
        except Exception:
            pass


def autostart(on):
    """Login autostart (HKCU Run) - only used when the guard task failed."""
    if not IS_WIN:
        return
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Run",
                           0, winreg.KEY_SET_VALUE)
        if on:
            exe, base = launch_parts()
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, ('"%s" %s' % (exe, base)).strip())
        else:
            try:
                winreg.DeleteValue(k, APP)
            except Exception:
                pass
        winreg.CloseKey(k)
    except Exception:
        pass


def lift_all(exes):
    """Remove every block. True only if nothing is left behind."""
    a = hosts_unblock()
    b = ifeo_unblock(exes)
    return a and b


# =============================================================================
# Session - there is deliberately no stop()
# =============================================================================

class Session:
    def __init__(self):
        self.active = False
        self.phases = []          # [["focus"|"break", seconds], ...]
        self.idx = 0
        self.phase_end = 0.0      # trusted wall-clock seconds
        self.exes, self.sites = [], []
        self.guard = False
        self.pending_cleanup = False
        self._sync()

    # Trusted clock: online time (if any) + monotonic, so changing the PC clock
    # mid-session does nothing.
    def _sync(self):
        self.anchor = online_time() or time.time()
        self.mono = time.monotonic()

    def now(self):
        return self.anchor + (time.monotonic() - self.mono)

    @property
    def kind(self):
        return self.phases[self.idx][0] if self.active else None

    def remaining(self):
        return max(0, int(round(self.phase_end - self.now())))

    def phase_len(self):
        return self.phases[self.idx][1] if self.active else 1

    def focus_pos(self):
        done = sum(1 for k, _ in self.phases[:self.idx + 1] if k == "focus")
        total = sum(1 for k, _ in self.phases if k == "focus")
        return done, total

    def total_left(self):
        return self.remaining() + sum(s for _, s in self.phases[self.idx + 1:])

    def save(self):
        save_json(STATE_FILE, {
            "active": self.active, "phases": self.phases, "idx": self.idx,
            "phase_end": self.phase_end, "exes": self.exes, "sites": self.sites,
            "guard": self.guard, "pending_cleanup": self.pending_cleanup})

    def restore(self, st):
        self.active = bool(st.get("active"))
        self.phases = st.get("phases") or []
        self.idx = int(st.get("idx", 0))
        self.phase_end = float(st.get("phase_end", 0))
        self.exes = st.get("exes", [])
        self.sites = st.get("sites", [])
        self.guard = st.get("guard", False)
        self.pending_cleanup = st.get("pending_cleanup", False)
        if not self.phases or self.idx >= len(self.phases):
            self.active = False

    def start(self, phases, exes, sites):
        self._sync()
        self.phases, self.idx = phases, 0
        self.exes = sorted({os.path.basename(e).lower() for e in exes} - PROTECTED)
        self.sites = list(sites)
        self.phase_end = self.now() + phases[0][1]
        self.active = True
        self.guard = guard_install()
        if not self.guard:
            autostart(True)
        self.apply()
        self.save()

    def apply(self):
        ifeo_block(self.exes)
        hosts_block(self.sites)

    def lift(self):
        return lift_all(self.exes)

    def tick(self):
        """Advance through any phases whose time is up. Returns events."""
        events = []
        while self.active and self.now() >= self.phase_end:
            self.idx += 1
            if self.idx >= len(self.phases):
                self.finish()
                events.append("done")
                break
            self.phase_end += self.phases[self.idx][1]
            if self.kind == "focus":
                self.apply()
            else:
                self.lift()
            events.append(self.kind)
            self.save()
        return events

    def enforce(self):
        """Kill blocked programs. Returns names that were killed."""
        if self.kind != "focus" or not self.exes:
            return []
        targets, me, hit = set(self.exes), os.getpid(), []
        for pid, name in processes():
            if name in targets and pid != me:
                kill(pid)
                hit.append(name)
        return hit

    def finish(self):
        self.active = False
        clean = self.lift()
        guard_remove()
        autostart(False)
        self.guard = False
        if not clean and not run_elevated("--cleanup"):
            self.pending_cleanup = True    # retried on every launch until clean
        self.save()


def cleanup_everything():
    """--cleanup: lift every block Ave could have set, then exit."""
    cfg = load_json(CONFIG_FILE, {})
    st = load_json(STATE_FILE, {})
    exes = set(cfg.get("exes", [])) | set(st.get("exes", []))
    ok = lift_all(sorted(exes))
    guard_remove()
    autostart(False)
    st.update(active=False, guard=False, pending_cleanup=not ok)
    save_json(STATE_FILE, st)


# =============================================================================
# UI
# =============================================================================

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

SCALE = 1.0
UI = UI_LIGHT = MONO = "TkDefaultFont"


def S(px):
    return int(round(px * SCALE))


def setup_fonts(root):
    global UI, UI_LIGHT, MONO, SCALE
    fams = set(tkfont.families(root))

    def pick(*names):
        return next((n for n in names if n in fams), "TkDefaultFont")
    UI = pick("Segoe UI Variable Text", "Segoe UI", "Helvetica")
    UI_LIGHT = pick("Segoe UI Light", "Segoe UI Variable Display", "Segoe UI", "Helvetica")
    MONO = pick("Cascadia Mono", "Cascadia Code", "Consolas", "Courier New")
    try:
        SCALE = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        SCALE = 1.0


def dark_titlebar(win):
    if not IS_WIN:
        return
    try:
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        v = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (new, old)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4) == 0:
                break
    except Exception:
        pass


def _round_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class Pill(tk.Canvas):
    """Rounded button. kind: 'accent' | 'ghost' | 'chip'."""

    def __init__(self, master, text, command, w=150, h=40, kind="ghost", size=10):
        super().__init__(master, width=S(w), height=S(h), bg=master.cget("bg"),
                         highlightthickness=0, bd=0, cursor="hand2")
        W, H = S(w), S(h)
        self.command, self.kind = command, kind
        self.hover = self.selected = False
        self.shape = self.create_polygon(_round_pts(1, 1, W - 1, H - 1, H // 2), smooth=True)
        bold = "bold" if kind == "accent" else "normal"
        self.label = self.create_text(W / 2, H / 2, text=text, font=(UI, size, bold))
        self.bind("<Enter>", lambda e: self._hov(True))
        self.bind("<Leave>", lambda e: self._hov(False))
        self.bind("<ButtonRelease-1>", self._click)
        self.paint()

    def _hov(self, v):
        self.hover = v
        self.paint()

    def _click(self, e):
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self.command:
            self.command()

    def set_text(self, t):
        self.itemconfig(self.label, text=t)

    def paint(self):
        h = self.hover
        if self.kind == "accent":
            fill = out = ACCENT_HI if h else ACCENT
            fg = "#ffffff"
        elif self.kind == "chip" and self.selected:
            fill, out, fg = ACCENT_DIM, ACCENT, FG
        else:
            fill = SURFACE2 if h else SURFACE
            out = FAINT if h else LINE
            fg = FG if (h or self.kind != "chip") else DIM
        self.itemconfig(self.shape, fill=fill, outline=out)
        self.itemconfig(self.label, fill=fg)


class Ring(tk.Canvas):
    """Thin progress ring with big centered digits."""

    def __init__(self, master, size=250):
        D = S(size)
        super().__init__(master, width=D, height=D, bg=BG, highlightthickness=0, bd=0)
        p = S(12)
        self.create_oval(p, p, D - p, D - p, outline=FAINT, width=S(2))
        self.arc = self.create_arc(p, p, D - p, D - p, start=90, extent=-359.9,
                                   style="arc", outline=ACCENT, width=S(5))
        self.big = self.create_text(D / 2, D / 2 - S(6), fill=FG, font=(UI_LIGHT, 44))
        self.small = self.create_text(D / 2, D / 2 + S(42), fill=DIM, font=(UI, 8, "bold"))

    def set(self, frac, big, small):
        frac = max(0.0, min(1.0, frac))
        if frac <= 0.001:
            self.itemconfig(self.arc, state="hidden")
        else:
            self.itemconfig(self.arc, state="normal", extent=-359.9 * frac)
        self.itemconfig(self.big, text=big)
        self.itemconfig(self.small, text=small)


def spaced(s):
    return " ".join(s.upper())


class Oracle:
    """Oblivionis's terminal line: types slowly, matrix-style, then waits."""

    def __init__(self, master, root):
        self.root = root
        self.frame = tk.Frame(master, bg=BG)
        tk.Frame(self.frame, bg=LINE, height=1).pack(fill="x")
        tk.Label(self.frame, text="OBLIVIONIS  //", bg=BG, fg=ACCENT_MUTED,
                 font=(MONO, 8, "bold"), anchor="w").pack(fill="x", padx=S(26), pady=(S(14), S(4)))
        self.label = tk.Label(self.frame, text="", bg=BG, fg=ACCENT, font=(MONO, 10),
                              anchor="nw", justify="left", wraplength=S(400), height=3)
        self.label.pack(fill="x", padx=S(26), pady=(0, S(14)))
        self.job = None
        self.full = ""
        self.i = 0
        self.blinks = 0
        self.pool = None
        self.last = ""

    def _cancel(self):
        if self.job:
            try:
                self.root.after_cancel(self.job)
            except Exception:
                pass
            self.job = None

    def say(self, text):
        self._cancel()
        self.full = "> " + text
        self.last = text
        self.i = 0
        self._type()

    def say_from(self, lines, **fmt):
        choices = [l for l in lines if l != self.last] or lines
        self.say(random.choice(choices).format(**fmt))

    def _type(self):
        if self.i <= len(self.full):
            noise = random.choice(GLYPHS) if self.i < len(self.full) else ""
            self.label.config(text=self.full[:self.i] + noise + "\u2588")
            ch = self.full[self.i - 1] if self.i else ""
            self.i += 1
            delay = 32 + random.randint(0, 38)
            if ch in ".?!":
                delay += 280
            elif ch in ",;:":
                delay += 130
            self.job = self.root.after(delay, self._type)
        else:
            self.blinks = 0
            self._blink()

    def _blink(self):
        self.blinks += 1
        self.label.config(text=self.full + ("\u2588" if self.blinks % 2 else " "))
        if self.blinks >= 26 and self.pool:
            self.say_from(self.pool())
        else:
            self.job = self.root.after(520, self._blink)


DEFAULT_CFG = {
    "exes": [], "sites": [], "sel": 0,
    "presets": [
        {"name": "Deep", "focus": 50, "brk": 10, "rounds": 2},
        {"name": "Pomodoro", "focus": 25, "brk": 5, "rounds": 4},
        {"name": "Sprint", "focus": 15, "brk": 0, "rounds": 1},
    ],
}


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_json(CONFIG_FILE, None) or json.loads(json.dumps(DEFAULT_CFG))
        for k, v in DEFAULT_CFG.items():
            self.cfg.setdefault(k, v)
        if not self.cfg["presets"]:
            self.cfg["presets"] = list(DEFAULT_CFG["presets"])
        self.cfg["sel"] = min(self.cfg.get("sel", 0), len(self.cfg["presets"]) - 1)
        self.session = Session()
        self.arm_job = None
        self.armed = False

        root.title(APP)
        root.configure(bg=BG)
        root.geometry("%dx%d" % (S(460), S(700)))
        root.minsize(S(420), S(640))
        dark_titlebar(root)

        self._build_header()
        self.body = tk.Frame(root, bg=BG)
        self.oracle = Oracle(root, root)
        self.oracle.frame.pack(side="bottom", fill="x")
        self.body.pack(fill="both", expand=True)
        self._build_home()
        self._build_run()
        self._build_settings()

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._resume()

    # ---------------------------------------------------------------- startup
    def _resume(self):
        st = load_json(STATE_FILE, {}) or {}
        self.session.restore(st)
        if self.session.pending_cleanup:
            if is_admin():
                cleanup_everything()
                self.session.pending_cleanup = False
            else:
                run_elevated("--cleanup")
        if self.session.active:
            ev = self.session.tick()          # catch up on time spent off/rebooted
            if self.session.active:
                if self.session.kind == "focus":
                    self.session.apply()
                if not self.session.guard:
                    self.session.guard = guard_install()
                self.session.save()
                self.show("run")
                self.oracle.say_from(FOCUS if self.session.kind == "focus" else BREAK)
                self._loop()
                return
            if "done" in ev:
                self.show("home")
                self.oracle.pool = lambda: IDLE
                self.oracle.say_from(DONE)
                return
        else:
            # Fail-safe: nothing should be blocked when no session runs.
            lift_all(self.cfg["exes"])
        self.show("home")
        self.oracle.pool = lambda: IDLE
        self.oracle.say_from(IDLE)

    # ----------------------------------------------------------------- header
    def _build_header(self):
        h = tk.Frame(self.root, bg=BG)
        h.pack(fill="x", padx=S(26), pady=(S(20), 0))
        tk.Label(h, text="A V E", bg=BG, fg=FG, font=(UI, 11, "bold")).pack(side="left")
        tk.Label(h, text="  \u25cf", bg=BG, fg=ACCENT, font=(UI, 7)).pack(side="left")
        self.hdr_right = tk.Label(h, text="settings", bg=BG, fg=DIM, font=(UI, 10), cursor="hand2")
        self.hdr_right.pack(side="right")
        self.hdr_right.bind("<Button-1>", lambda e: self._header_click())
        self.hdr_right.bind("<Enter>", lambda e: self._hdr_hover(True))
        self.hdr_right.bind("<Leave>", lambda e: self._hdr_hover(False))

    def _hdr_hover(self, on):
        if not self.session.active:
            self.hdr_right.config(fg=FG if on else DIM)

    def _header_click(self):
        if self.session.active:
            self.oracle.say("Settings are sealed until the curtain falls.")
        elif self.current == "settings":
            self.show("home")
        else:
            self.show("settings")

    def show(self, name):
        self.current = name
        for f in (self.home, self.run, self.settings):
            f.pack_forget()
        {"home": self.home, "run": self.run, "settings": self.settings}[name].pack(
            fill="both", expand=True)
        if self.session.active:
            self.hdr_right.config(text="\u25cf locked", fg=ACCENT, cursor="arrow")
        else:
            self.hdr_right.config(text="done" if name == "settings" else "settings",
                                  fg=DIM, cursor="hand2")
        if name == "home":
            self._refresh_home()
        if name == "settings":
            self._refresh_settings()

    # ------------------------------------------------------------------- home
    def _build_home(self):
        f = self.home = tk.Frame(self.body, bg=BG)
        self.home_ring = Ring(f)
        self.home_ring.pack(pady=(S(26), S(10)))

        adj = tk.Frame(f, bg=BG)
        adj.pack()
        Pill(adj, "\u2212", lambda: self._bump(-5), w=46, h=40, size=13).pack(side="left")
        self.home_meta = tk.Label(adj, text="", bg=BG, fg=DIM, font=(UI, 10), width=20)
        self.home_meta.pack(side="left", padx=S(8))
        Pill(adj, "+", lambda: self._bump(5), w=46, h=40, size=13).pack(side="left")

        self.chips = tk.Frame(f, bg=BG)
        self.chips.pack(pady=(S(22), S(22)))

        self.start_btn = Pill(f, "Start", self._start, w=300, h=54, kind="accent", size=12)
        self.start_btn.pack()
        self.home_note = tk.Label(f, text="", bg=BG, fg=DIM, font=(UI, 9))
        self.home_note.pack(pady=(S(12), 0))

    def _preset(self):
        return self.cfg["presets"][self.cfg["sel"]]

    def _refresh_home(self):
        p = self._preset()
        self.home_ring.set(1.0, str(p["focus"]), spaced("min focus"))
        brk = ("%d min break" % p["brk"]) if p["brk"] and p["rounds"] > 1 else "no break"
        self.home_meta.config(text="%s  \u00b7  %d round%s" % (brk, p["rounds"], "" if p["rounds"] == 1 else "s"))
        total = p["focus"] * p["rounds"] + (p["brk"] * (p["rounds"] - 1))
        end = time.strftime("%H:%M", time.localtime(time.time() + total * 60))
        self.home_note.config(text="locked until %s  \u00b7  no stop button" % end)
        for w in self.chips.winfo_children():
            w.destroy()
        for i, pr in enumerate(self.cfg["presets"][:4]):
            c = Pill(self.chips, pr["name"], lambda i=i: self._select(i), w=96, h=34, kind="chip", size=9)
            c.selected = i == self.cfg["sel"]
            c.paint()
            c.pack(side="left", padx=S(4))
        self._disarm()

    def _select(self, i):
        self.cfg["sel"] = i
        self._save_cfg()
        self._refresh_home()

    def _bump(self, d):
        p = self._preset()
        p["focus"] = max(5, min(600, p["focus"] + d))
        self._save_cfg()
        self._refresh_home()

    def _disarm(self):
        self.armed = False
        if self.arm_job:
            self.root.after_cancel(self.arm_job)
            self.arm_job = None
        self.start_btn.set_text("Start")

    def _start(self):
        if not self.armed:                       # two-click confirm, no popups
            self.armed = True
            self.start_btn.set_text("Click again to lock in")
            self.oracle.say("Are you certain? Once it begins, I will not let you go.")
            self.arm_job = self.root.after(4000, self._disarm)
            return
        self._disarm()
        if not is_admin() and (self.cfg["sites"] or self.cfg["exes"]):
            if messagebox.askyesno(
                    APP, "Ave isn't running as administrator.\n\n"
                         "Without it, websites can't be blocked and games are only "
                         "closed after they open.\n\nRelaunch as administrator?"):
                release_lock()
                if run_elevated(""):
                    self.root.destroy()
                    return
                acquire_lock()
        p = self._preset()
        phases = []
        for r in range(p["rounds"]):
            phases.append(["focus", p["focus"] * 60])
            if p["brk"] and r < p["rounds"] - 1:
                phases.append(["break", p["brk"] * 60])
        self.session.start(phases, self.cfg["exes"], self.cfg["sites"])
        beep(880, 90)
        beep(1320, 120)
        self.show("run")
        self.oracle.pool = lambda: FOCUS if self.session.kind == "focus" else BREAK
        self.oracle.say_from(FOCUS)
        self._loop()
        self.root.after(300, self._poll)

    # -------------------------------------------------------------------- run
    def _build_run(self):
        f = self.run = tk.Frame(self.body, bg=BG)
        self.run_ring = Ring(f, size=280)
        self.run_ring.pack(pady=(S(30), S(14)))
        self.run_end = tk.Label(f, text="", bg=BG, fg=DIM, font=(UI, 10))
        self.run_end.pack()
        tk.Label(f, text="there is no stop button.", bg=BG, fg=FAINT,
                 font=(UI, 9)).pack(side="bottom", pady=S(12))

    def _loop(self):
        """1 s UI tick, only while a session is active."""
        if not self.session.active:
            return
        for ev in self.session.tick():
            if ev == "done":
                self._complete()
                return
            self._phase_changed(ev)
        s = self.session
        rem = s.remaining()
        m, sec = divmod(rem, 60)
        h, m = divmod(m, 60)
        big = ("%d:%02d:%02d" % (h, m, sec)) if h else ("%02d:%02d" % (m, sec))
        if s.kind == "focus":
            a, b = s.focus_pos()
            label = spaced("focus") + "   %d / %d" % (a, b)
        else:
            label = spaced("break")
        self.run_ring.set(rem / max(1, s.phase_len()), big, label)
        free = time.strftime("%H:%M", time.localtime(time.time() + s.total_left()))
        self.run_end.config(text="free at %s" % free)
        self.root.after(1000, self._loop)

    def _poll(self):
        """2 s enforcement tick (cheap ctypes snapshot)."""
        if not self.session.active:
            return
        hit = self.session.enforce()
        if hit:
            beep(330, 160)
            name = os.path.splitext(hit[0])[0]
            self.oracle.say_from(CAUGHT, n=name)
        self.root.after(2000, self._poll)

    def _phase_changed(self, kind):
        self._raise()
        if kind == "break":
            beep(660, 120)
            self.oracle.say_from(BREAK)
        else:
            beep(880, 120)
            self.oracle.say_from(FOCUS)

    def _complete(self):
        beep(660, 100)
        beep(880, 100)
        beep(1320, 180)
        self._raise()
        self.oracle.pool = lambda: IDLE
        self.show("home")
        self.oracle.say_from(DONE)

    def _raise(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(400, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _on_close(self):
        if self.session.active:
            beep(330, 120)
            self.oracle.say_from(REFUSE)
            return
        self.root.destroy()

    # --------------------------------------------------------------- settings
    def _build_settings(self):
        f = self.settings = tk.Frame(self.body, bg=BG)
        tabs = tk.Frame(f, bg=BG)
        tabs.pack(fill="x", padx=S(26), pady=(S(22), S(14)))
        self.tab_btns = {}
        for name in ("Programs", "Websites", "Presets"):
            b = tk.Label(tabs, text=name, bg=BG, fg=DIM, font=(UI, 11), cursor="hand2")
            b.pack(side="left", padx=(0, S(20)))
            b.bind("<Button-1>", lambda e, n=name: self._tab(n))
            self.tab_btns[name] = b
        tk.Frame(f, bg=LINE, height=1).pack(fill="x", padx=S(26))
        self.tab_body = tk.Frame(f, bg=BG)
        self.tab_body.pack(fill="both", expand=True, padx=S(26), pady=(S(14), 0))
        self.admin_lbl = tk.Label(f, text="", bg=BG, font=(UI, 9), anchor="w")
        self.admin_lbl.pack(fill="x", padx=S(26), pady=(0, S(10)))
        self.tab_name = "Programs"

    def _refresh_settings(self):
        if is_admin():
            self.admin_lbl.config(text="\u25cf administrator  \u00b7  full blocking", fg=ACCENT)
        else:
            self.admin_lbl.config(text="\u25cb not administrator  \u00b7  programs are closed, sites not blocked", fg=DIM)
        self._tab(self.tab_name)

    def _listbox(self, parent, h=8, multi=False):
        return tk.Listbox(parent, bg=SURFACE, fg=FG, selectbackground=ACCENT,
                          selectforeground="#ffffff", relief="flat", bd=0,
                          highlightthickness=1, highlightbackground=LINE,
                          highlightcolor=ACCENT, activestyle="none", height=h,
                          font=(UI, 10), selectmode="multiple" if multi else "browse")

    def _entry(self, parent, width=None):
        e = tk.Entry(parent, bg=SURFACE, fg=FG, insertbackground=FG, relief="flat",
                     highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=ACCENT, font=(UI, 10))
        if width:
            e.config(width=width)
        return e

    def _note(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=DIM, font=(UI, 9), anchor="w",
                 justify="left", wraplength=S(400)).pack(fill="x", pady=(S(10), 0))

    def _tab(self, name):
        self.tab_name = name
        for n, b in self.tab_btns.items():
            b.config(fg=FG if n == name else DIM,
                     font=(UI, 11, "bold" if n == name else "normal"))
        for w in self.tab_body.winfo_children():
            w.destroy()
        getattr(self, "_tab_" + name.lower())(self.tab_body)

    def _tab_programs(self, p):
        lb = self._listbox(p)
        lb.pack(fill="both", expand=True)
        for e in self.cfg["exes"]:
            lb.insert("end", "  " + e)
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(S(12), 0))
        Pill(row, "Browse\u2026", self._pick_file, w=110, h=36).pack(side="left")
        Pill(row, "Running\u2026", self._pick_running, w=110, h=36).pack(side="left", padx=S(8))
        Pill(row, "Remove", lambda: self._remove("exes", lb), w=96, h=36).pack(side="left")
        self._note(p, "Blocked programs close the moment they appear. Task Manager and "
                      "Windows system processes can never be blocked.")

    def _tab_websites(self, p):
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(0, S(10)))
        e = self._entry(row)
        e.pack(side="left", fill="x", expand=True, ipady=S(6))
        lb = self._listbox(p)

        def add(*_):
            d = _clean_domain(e.get())
            if d and d not in self.cfg["sites"]:
                self.cfg["sites"].append(d)
                self._save_cfg()
                lb.insert("end", "  " + d)
            e.delete(0, "end")
        e.bind("<Return>", add)
        Pill(row, "Add", add, w=70, h=34).pack(side="left", padx=(S(8), 0))
        lb.pack(fill="both", expand=True)
        for s in self.cfg["sites"]:
            lb.insert("end", "  " + s)
        Pill(p, "Remove", lambda: self._remove("sites", lb), w=96, h=36).pack(anchor="w", pady=(S(12), 0))
        self._note(p, "Type a site like youtube.com and press Enter. Needs administrator; "
                      "restart your browser if a site still loads.")

    def _tab_presets(self, p):
        lb = self._listbox(p, h=5)
        lb.pack(fill="x")
        for pr in self.cfg["presets"]:
            lb.insert("end", "  %s   %d / %d \u00d7 %d" % (pr["name"], pr["focus"], pr["brk"], pr["rounds"]))
        grid = tk.Frame(p, bg=BG)
        grid.pack(fill="x", pady=(S(14), 0))
        fields = {}
        for col, (key, label) in enumerate((("name", "Name"), ("focus", "Focus"),
                                            ("brk", "Break"), ("rounds", "Rounds"))):
            tk.Label(grid, text=label, bg=BG, fg=DIM, font=(UI, 9)).grid(row=0, column=col, sticky="w", padx=(0, S(8)))
            ent = self._entry(grid, width=12 if key == "name" else 6)
            ent.grid(row=1, column=col, sticky="we", padx=(0, S(8)), ipady=S(4))
            fields[key] = ent

        def fill(*_):
            sel = lb.curselection()
            if not sel:
                return
            pr = self.cfg["presets"][sel[0]]
            for k, ent in fields.items():
                ent.delete(0, "end")
                ent.insert(0, str(pr[k]))
        lb.bind("<<ListboxSelect>>", fill)

        def read():
            try:
                name = fields["name"].get().strip()[:14] or "Preset"
                return {"name": name,
                        "focus": max(1, min(600, int(fields["focus"].get()))),
                        "brk": max(0, min(120, int(fields["brk"].get() or 0))),
                        "rounds": max(1, min(12, int(fields["rounds"].get() or 1)))}
            except ValueError:
                self.oracle.say("Numbers, please. Minutes and rounds are not poetry.")
                return None

        def save_new():
            pr = read()
            if pr:
                self.cfg["presets"].append(pr)
                self._save_cfg()
                self._tab("Presets")

        def update():
            sel, pr = lb.curselection(), read()
            if sel and pr:
                self.cfg["presets"][sel[0]] = pr
                self._save_cfg()
                self._tab("Presets")

        def delete():
            sel = lb.curselection()
            if sel and len(self.cfg["presets"]) > 1:
                del self.cfg["presets"][sel[0]]
                self.cfg["sel"] = 0
                self._save_cfg()
                self._tab("Presets")

        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=(S(14), 0))
        Pill(row, "Save new", save_new, w=104, h=36).pack(side="left")
        Pill(row, "Update", update, w=96, h=36).pack(side="left", padx=S(8))
        Pill(row, "Delete", delete, w=96, h=36).pack(side="left")
        self._note(p, "Focus and break are minutes. The first four presets appear on the timer screen.")

    def _remove(self, key, lb):
        for i in reversed(lb.curselection()):
            del self.cfg[key][i]
            lb.delete(i)
        self._save_cfg()

    def _add_exes(self, names):
        for n in names:
            n = os.path.basename(n).lower()
            if n.endswith(".exe") and n not in PROTECTED and n not in self.cfg["exes"]:
                self.cfg["exes"].append(n)
        self._save_cfg()
        self._tab("Programs")

    def _pick_file(self):
        p = filedialog.askopenfilename(title="Choose a program to block",
                                       filetypes=[("Programs", "*.exe")])
        if p:
            self._add_exes([p])

    def _pick_running(self):
        names = sorted({n for _, n in processes() if n.endswith(".exe")} - PROTECTED)
        if not names:
            self.oracle.say("I see nothing running worth taking from you.")
            return
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Running programs")
        win.geometry("%dx%d" % (S(340), S(460)))
        win.transient(self.root)
        dark_titlebar(win)
        tk.Label(win, text="Select programs to block", bg=BG, fg=FG,
                 font=(UI, 11, "bold")).pack(anchor="w", padx=S(18), pady=(S(16), S(10)))
        lb = self._listbox(win, multi=True)
        lb.pack(fill="both", expand=True, padx=S(18))
        for n in names:
            lb.insert("end", "  " + n)

        def add():
            self._add_exes([names[i] for i in lb.curselection()])
            win.destroy()
        Pill(win, "Add selected", add, w=160, h=40, kind="accent").pack(pady=S(14))

    def _save_cfg(self):
        save_json(CONFIG_FILE, self.cfg)


# =============================================================================
# Single instance
# =============================================================================

_LOCK = None


def acquire_lock():
    global _LOCK
    if not IS_WIN:
        _LOCK = True
        return True
    k = ctypes.windll.kernel32
    k.CreateMutexW.restype = ctypes.c_void_p
    h = k.CreateMutexW(None, False, "Local\\AveSingleton")
    if k.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
        k.CloseHandle(ctypes.c_void_p(h))
        return False
    _LOCK = h
    return True


def release_lock():
    global _LOCK
    if IS_WIN and _LOCK:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(_LOCK))
    _LOCK = None


def focus_existing():
    try:
        u = ctypes.windll.user32
        hwnd = u.FindWindowW(None, APP)
        if hwnd:
            u.ShowWindow(hwnd, 9)
            u.SetForegroundWindow(hwnd)
    except Exception:
        pass


def main():
    if "--cleanup" in sys.argv:
        cleanup_everything()
        return
    if not acquire_lock():
        if "--guard" not in sys.argv:   # guard ticks stay silent
            focus_existing()
        return
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    setup_fonts(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
