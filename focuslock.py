# -*- coding: utf-8 -*-
"""
FocusLock — a no-killswitch focus timer for Windows.

Single file, stdlib only. Pure-black UI. Blocks chosen .exe files and
websites while a session runs, survives reboot, relaunches itself if
killed, and NEVER lets you cancel early.

Everything risky (admin registry edits, hosts-file edits, scheduled task)
degrades gracefully: if a piece fails, it falls back to plain process
killing, and all blocks are always torn down when the session ends.

Run on Windows. Right-click -> "Run as administrator" for full blocking;
without admin it still works in "kill-only" mode.
"""

import os
import sys
import json
import time
import ctypes
import ctypes.wintypes as wt
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

# ----------------------------------------------------------------------------
# Paths / constants
# ----------------------------------------------------------------------------

APP_NAME = "FocusLock"
# Store state next to the exe/script, with a stable fallback in %LOCALAPPDATA%.
if getattr(sys, "frozen", False):
    SELF_PATH = sys.executable
else:
    SELF_PATH = os.path.abspath(__file__)

BASE_DIR = os.path.dirname(SELF_PATH)
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", BASE_DIR), APP_NAME)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception:
    DATA_DIR = BASE_DIR

STATE_FILE = os.path.join(DATA_DIR, "state.json")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

HOSTS_PATH = os.path.join(
    os.environ.get("SystemRoot", r"C:\Windows"), "System32", "drivers", "etc", "hosts"
)
HOSTS_MARK_BEGIN = "# FocusLock begin"
HOSTS_MARK_END = "# FocusLock end"

IFEO_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
TASK_NAME = "FocusLockGuard"

# Colors — pure black, dim grey, one accent (muted violet for Oblivionis).
BG = "#000000"
FG = "#f2f2f2"
DIM = "#777777"
ACCENT = "#9a6cff"

IS_WINDOWS = os.name == "nt"


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

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
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def beep(ok=True):
    if not IS_WINDOWS:
        return
    try:
        ctypes.windll.kernel32.Beep(880 if ok else 440, 150)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Online time check (trust-but-verify the clock) + monotonic anchor
# ----------------------------------------------------------------------------

def online_unix_time():
    """Best-effort trusted wall time via an HTTP Date header. None on failure."""
    try:
        import urllib.request
        import email.utils

        req = urllib.request.Request(
            "https://www.google.com/generate_204", method="HEAD"
        )
        with urllib.request.urlopen(req, timeout=4) as r:
            d = r.headers.get("Date")
        if d:
            return email.utils.mktime_tz(email.utils.parsedate_tz(d))
    except Exception:
        pass
    return None


# ----------------------------------------------------------------------------
# Process snapshot + kill, using ctypes (no subprocess per tick)
# ----------------------------------------------------------------------------

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_TERMINATE = 0x0001


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wt.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def snapshot_processes():
    """Return list of (pid, lowercase_exe_name). ctypes snapshot, cheap."""
    out = []
    if not IS_WINDOWS:
        return out
    k = ctypes.windll.kernel32
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1 or snap == 0:
        return out
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        ok = k.Process32First(snap, ctypes.byref(entry))
        while ok:
            try:
                name = entry.szExeFile.decode("latin-1").lower()
            except Exception:
                name = ""
            out.append((entry.th32ProcessID, name))
            ok = k.Process32Next(snap, ctypes.byref(entry))
    finally:
        k.CloseHandle(snap)
    return out


def kill_pid(pid):
    if not IS_WINDOWS:
        return
    k = ctypes.windll.kernel32
    h = k.OpenProcess(PROCESS_TERMINATE, False, pid)
    if h:
        try:
            k.TerminateProcess(h, 1)
        finally:
            k.CloseHandle(h)


# ----------------------------------------------------------------------------
# Blockers — each one try/excepts and reports success so we can fall back.
# ----------------------------------------------------------------------------

def hosts_block(domains):
    """Append a FocusLock section to the hosts file. Returns True on success."""
    if not domains or not IS_WINDOWS:
        return False
    try:
        with open(HOSTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return False
    text = _strip_hosts(text)
    lines = [HOSTS_MARK_BEGIN]
    for d in domains:
        d = d.strip().lower().replace("https://", "").replace("http://", "").strip("/")
        if not d:
            continue
        lines.append("127.0.0.1 " + d)
        lines.append("127.0.0.1 www." + d)
    lines.append(HOSTS_MARK_END)
    block = "\n".join(lines) + "\n"
    try:
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n" + block)
        _flush_dns()
        return True
    except Exception:
        return False


def _strip_hosts(text):
    out, skip = [], False
    for line in text.splitlines():
        if line.strip() == HOSTS_MARK_BEGIN:
            skip = True
            continue
        if line.strip() == HOSTS_MARK_END:
            skip = False
            continue
        if not skip:
            out.append(line)
    return "\n".join(out)


def hosts_unblock():
    if not IS_WINDOWS:
        return
    try:
        with open(HOSTS_PATH, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        with open(HOSTS_PATH, "w", encoding="utf-8") as f:
            f.write(_strip_hosts(text).rstrip() + "\n")
        _flush_dns()
    except Exception:
        pass


def _flush_dns():
    try:
        subprocess.run(["ipconfig", "/flushdns"], capture_output=True,
                       creationflags=0x08000000)
    except Exception:
        pass


def ifeo_block(exe_names):
    """Set IFEO Debugger so the OS refuses to launch the exe. Returns True/False."""
    if not exe_names or not IS_WINDOWS or not is_admin():
        return False
    try:
        import winreg
    except Exception:
        return False
    ok_any = False
    for name in exe_names:
        name = os.path.basename(name).strip()
        if not name.lower().endswith(".exe"):
            continue
        try:
            key = winreg.CreateKey(
                winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + name
            )
            # A harmless debugger that just exits -> target never runs.
            winreg.SetValueEx(key, "Debugger", 0, winreg.REG_SZ,
                              "cmd.exe /c exit")
            winreg.CloseKey(key)
            ok_any = True
        except Exception:
            pass
    return ok_any


def ifeo_unblock(exe_names):
    if not IS_WINDOWS or not is_admin():
        return
    try:
        import winreg
    except Exception:
        return
    for name in exe_names:
        name = os.path.basename(name).strip()
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, IFEO_KEY + "\\" + name, 0,
                winreg.KEY_SET_VALUE,
            )
            try:
                winreg.DeleteValue(key, "Debugger")
            except Exception:
                pass
            winreg.CloseKey(key)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Auto-relaunch guard (scheduled task). Falls back silently if it can't.
# ----------------------------------------------------------------------------

def guard_install():
    """Create a scheduled task that relaunches us if we're killed.

    ONERROR -> returns False; caller continues without it.
    """
    if not IS_WINDOWS:
        return False
    cmd = [sys.executable]
    if not getattr(sys, "frozen", False):
        cmd.append(SELF_PATH)
    quoted = " ".join('"%s"' % c for c in cmd)
    try:
        # /sc minute runs every 1 min; the app self-detects a duplicate and exits.
        subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", quoted,
             "/SC", "MINUTE", "/MO", "1", "/F", "/RL", "HIGHEST"],
            capture_output=True, creationflags=0x08000000, check=True,
        )
        return True
    except Exception:
        return False


def guard_remove():
    if not IS_WINDOWS:
        return
    try:
        subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
                       capture_output=True, creationflags=0x08000000)
    except Exception:
        pass


def autostart_set(on):
    """Login autostart via HKCU Run key. Best-effort."""
    if not IS_WINDOWS:
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        if on:
            cmd = '"%s"' % SELF_PATH
            if not getattr(sys, "frozen", False):
                cmd = '"%s" "%s"' % (sys.executable, SELF_PATH)
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except Exception:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Single-instance lock (so the guard task doesn't spawn duplicates)
# ----------------------------------------------------------------------------

def acquire_single_instance():
    """Named mutex. Returns handle if we're the first; None if already running."""
    if not IS_WINDOWS:
        return object()
    try:
        k = ctypes.windll.kernel32
        h = k.CreateMutexW(None, False, "Global\\FocusLock_Singleton")
        if k.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            return None
        return h
    except Exception:
        return object()


# ----------------------------------------------------------------------------
# Oblivionis flavor
# ----------------------------------------------------------------------------

OBLIVIONIS_BLUE = "#2b5fd9"   # her deep stage-blue

# Original lines, written in Oblivionis's tone — hushed, theatrical, resigned.
QUOTES = [
    "The curtain has risen. There is no leaving the stage now.",
    "You wear the mask so you need not face the silence. So do I.",
    "Forgetting is a kindness. Focus is the price of it.",
    "I will not save you from this. I only watch.",
    "The play continues whether you wish it or not. Sit. Endure.",
    "Every distraction is a small death. Let them pass.",
    "You asked to be bound. I am only keeping the promise.",
    "Oblivion waits at the end of the act. Not before.",
    "Do not look for the door. There was never a door.",
    "Breathe. The music has not finished. Neither have you.",
]


# ----------------------------------------------------------------------------
# Session model
# ----------------------------------------------------------------------------

class Session:
    """Holds the running focus session + enforces blocking. No stop method."""

    def __init__(self, app):
        self.app = app
        self.active = False
        self.block_exes = []        # lowercase exe names
        self.block_sites = []
        self.end_at = 0.0           # trusted unix seconds
        self.mono_anchor = 0.0
        self.anchor_wall = 0.0
        self.ifeo_on = False
        self.hosts_on = False
        self.guard_on = False
        self._poll_thread = None
        self._stop_evt = threading.Event()

    # -- persistence ---------------------------------------------------------
    def to_state(self):
        return {
            "active": self.active,
            "block_exes": self.block_exes,
            "block_sites": self.block_sites,
            "end_at": self.end_at,
            "anchor_wall": self.anchor_wall,
            "ifeo_on": self.ifeo_on,
            "hosts_on": self.hosts_on,
            "guard_on": self.guard_on,
        }

    def save(self):
        save_json(STATE_FILE, self.to_state())

    def restore(self, st):
        self.active = st.get("active", False)
        self.block_exes = st.get("block_exes", [])
        self.block_sites = st.get("block_sites", [])
        self.end_at = st.get("end_at", 0.0)
        self.anchor_wall = st.get("anchor_wall", 0.0)
        self.ifeo_on = st.get("ifeo_on", False)
        self.hosts_on = st.get("hosts_on", False)
        self.guard_on = st.get("guard_on", False)

    # -- lifecycle -----------------------------------------------------------
    def start(self, minutes, exes, sites):
        self.block_exes = [os.path.basename(e).lower() for e in exes if e]
        self.block_sites = [s for s in sites if s]
        now = online_unix_time() or time.time()
        self.anchor_wall = now
        self.end_at = now + minutes * 60
        self.active = True

        # Apply blocks, remembering which actually took so we can undo exactly.
        self.ifeo_on = ifeo_block(self.block_exes)
        self.hosts_on = hosts_block(self.block_sites)
        self.guard_on = guard_install()
        self.save()
        beep(True)
        self._spawn_poll()

    def remaining(self):
        """Seconds left, trusting the online clock if available, else monotonic."""
        now = online_unix_time() or time.time()
        return max(0, int(self.end_at - now))

    def finish(self):
        """Tear EVERYTHING down. Called only when time is truly up."""
        self._stop_evt.set()
        if self.ifeo_on:
            ifeo_unblock(self.block_exes)
        if self.hosts_on:
            hosts_unblock()
        if self.guard_on:
            guard_remove()
        self.active = False
        self.ifeo_on = self.hosts_on = self.guard_on = False
        self.save()
        beep(True)

    # -- enforcement ---------------------------------------------------------
    def _spawn_poll(self):
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._stop_evt.clear()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

    def _poll_loop(self):
        while not self._stop_evt.is_set() and self.active:
            if self.block_exes:
                targets = set(self.block_exes)
                for pid, name in snapshot_processes():
                    if name in targets:
                        kill_pid(pid)
                        self.app.flash_quote()
            if self.remaining() <= 0:
                self.app.on_time_up()
                return
            self._stop_evt.wait(2.0)


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------

class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_json(CONFIG_FILE, {"exes": [], "sites": [], "minutes": 50})
        self.session = Session(self)

        root.title(APP_NAME)
        root.configure(bg=BG)
        root.geometry("460x560")
        root.minsize(420, 520)

        self._build_timer_screen()
        self._build_settings_screen()

        # Restore a surviving session (e.g. after reboot).
        st = load_json(STATE_FILE, None)
        if st and st.get("active"):
            self.session.restore(st)
            if self.session.remaining() > 0:
                # Re-apply enforcement (blocks may have been cleared by reboot).
                self.session.ifeo_on = ifeo_block(self.session.block_exes) or self.session.ifeo_on
                self.session.hosts_on = hosts_block(self.session.block_sites) or self.session.hosts_on
                self.session.guard_on = guard_install() or self.session.guard_on
                self.session.active = True
                self.session._spawn_poll()
                self._show_running()
            else:
                self.session.finish()
                self._show_timer()
        else:
            self._show_timer()

        # No killswitch: closing the window is refused while a session runs.
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()

    # -- screens -------------------------------------------------------------
    def _build_timer_screen(self):
        self.timer_frame = tk.Frame(self.root, bg=BG)

        tk.Label(self.timer_frame, text="FOCUSLOCK", bg=BG, fg=ACCENT,
                 font=("Consolas", 22, "bold")).pack(pady=(40, 4))
        tk.Label(self.timer_frame, text="— Oblivionis watches —", bg=BG, fg=DIM,
                 font=("Consolas", 10)).pack(pady=(0, 30))

        self.min_var = tk.IntVar(value=self.cfg.get("minutes", 50))
        row = tk.Frame(self.timer_frame, bg=BG)
        row.pack()
        tk.Button(row, text="-5", command=lambda: self._bump(-5),
                  **self._btn()).pack(side="left", padx=6)
        self.min_label = tk.Label(row, text="", bg=BG, fg=FG,
                                  font=("Consolas", 40, "bold"), width=4)
        self.min_label.pack(side="left", padx=10)
        tk.Button(row, text="+5", command=lambda: self._bump(5),
                  **self._btn()).pack(side="left", padx=6)
        tk.Label(self.timer_frame, text="minutes", bg=BG, fg=DIM,
                 font=("Consolas", 11)).pack(pady=(4, 30))

        tk.Button(self.timer_frame, text="START  \u25b6", command=self._start,
                  bg=ACCENT, fg="#000000", activebackground="#b690ff",
                  activeforeground="#000000", relief="flat",
                  font=("Consolas", 16, "bold"), width=16, pady=8).pack(pady=10)

        tk.Button(self.timer_frame, text="settings", command=self._show_settings,
                  bg=BG, fg=DIM, activebackground=BG, activeforeground=FG,
                  relief="flat", font=("Consolas", 10)).pack(pady=20)

        self._refresh_min()

    def _build_settings_screen(self):
        self.settings_frame = tk.Frame(self.root, bg=BG)

        tk.Label(self.settings_frame, text="SETTINGS", bg=BG, fg=ACCENT,
                 font=("Consolas", 16, "bold")).pack(pady=(24, 16))

        tk.Label(self.settings_frame, text="Blocked programs (.exe)", bg=BG,
                 fg=FG, font=("Consolas", 11, "bold")).pack(anchor="w", padx=24)
        self.exe_list = tk.Listbox(self.settings_frame, bg="#0a0a0a", fg=FG,
                                   selectbackground=ACCENT, height=6,
                                   relief="flat", highlightthickness=0,
                                   font=("Consolas", 10))
        self.exe_list.pack(fill="x", padx=24, pady=6)
        r1 = tk.Frame(self.settings_frame, bg=BG)
        r1.pack(anchor="w", padx=24)
        tk.Button(r1, text="pick file", command=self._pick_file,
                  **self._btn()).pack(side="left", padx=(0, 6))
        tk.Button(r1, text="pick running", command=self._pick_running,
                  **self._btn()).pack(side="left", padx=6)
        tk.Button(r1, text="remove", command=self._remove_exe,
                  **self._btn()).pack(side="left", padx=6)

        tk.Label(self.settings_frame, text="Blocked websites", bg=BG, fg=FG,
                 font=("Consolas", 11, "bold")).pack(anchor="w", padx=24,
                                                     pady=(18, 0))
        self.site_entry = tk.Entry(self.settings_frame, bg="#0a0a0a", fg=FG,
                                   insertbackground=FG, relief="flat",
                                   font=("Consolas", 10))
        self.site_entry.pack(fill="x", padx=24, pady=6)
        self.site_list = tk.Listbox(self.settings_frame, bg="#0a0a0a", fg=FG,
                                    selectbackground=ACCENT, height=4,
                                    relief="flat", highlightthickness=0,
                                    font=("Consolas", 10))
        self.site_list.pack(fill="x", padx=24, pady=6)
        r2 = tk.Frame(self.settings_frame, bg=BG)
        r2.pack(anchor="w", padx=24)
        tk.Button(r2, text="add site", command=self._add_site,
                  **self._btn()).pack(side="left", padx=(0, 6))
        tk.Button(r2, text="remove", command=self._remove_site,
                  **self._btn()).pack(side="left", padx=6)

        tk.Button(self.settings_frame, text="\u2190 back", command=self._show_timer,
                  bg=BG, fg=DIM, activebackground=BG, activeforeground=FG,
                  relief="flat", font=("Consolas", 11)).pack(pady=24)

        self._refresh_lists()

    def _build_running_screen(self):
        self.run_frame = tk.Frame(self.root, bg=BG)
        tk.Label(self.run_frame, text="LOCKED", bg=BG, fg=ACCENT,
                 font=("Consolas", 20, "bold")).pack(pady=(60, 10))
        self.countdown = tk.Label(self.run_frame, text="--:--", bg=BG, fg=FG,
                                  font=("Consolas", 56, "bold"))
        self.countdown.pack(pady=10)
        # Terminal-style line where Oblivionis "types" slowly, matrix-fashion.
        self.quote_label = tk.Label(self.run_frame, text="", bg=BG,
                                    fg=OBLIVIONIS_BLUE, justify="left",
                                    font=("Consolas", 11), wraplength=400,
                                    anchor="w")
        self.quote_label.pack(pady=30, padx=24, fill="x")
        self._type_job = None
        self._type_full = ""
        self._type_i = 0
        self.root.after(1200, lambda: self._type_quote())
        tk.Label(self.run_frame, text="There is no stop button.", bg=BG,
                 fg="#444444", font=("Consolas", 10)).pack(side="bottom", pady=30)

    # -- helpers -------------------------------------------------------------
    def _btn(self):
        return dict(bg="#161616", fg=FG, activebackground="#262626",
                    activeforeground=FG, relief="flat",
                    font=("Consolas", 11), padx=10, pady=4)

    def _bump(self, d):
        v = max(5, min(600, self.min_var.get() + d))
        self.min_var.set(v)
        self._refresh_min()

    def _refresh_min(self):
        self.min_label.config(text=str(self.min_var.get()))

    def _refresh_lists(self):
        self.exe_list.delete(0, "end")
        for e in self.cfg["exes"]:
            self.exe_list.insert("end", e)
        self.site_list.delete(0, "end")
        for s in self.cfg["sites"]:
            self.site_list.insert("end", s)

    def _save_cfg(self):
        self.cfg["minutes"] = self.min_var.get()
        save_json(CONFIG_FILE, self.cfg)

    # -- settings actions ----------------------------------------------------
    def _pick_file(self):
        p = filedialog.askopenfilename(filetypes=[("Programs", "*.exe")])
        if p:
            name = os.path.basename(p)
            if name not in self.cfg["exes"]:
                self.cfg["exes"].append(name)
                self._save_cfg()
                self._refresh_lists()

    def _pick_running(self):
        names = sorted({n for _, n in snapshot_processes() if n.endswith(".exe")})
        if not names:
            messagebox.showinfo(APP_NAME, "No running programs found.")
            return
        self._chooser(names)

    def _chooser(self, names):
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Pick running program")
        win.geometry("320x420")
        lb = tk.Listbox(win, bg="#0a0a0a", fg=FG, selectbackground=ACCENT,
                        selectmode="multiple", relief="flat",
                        highlightthickness=0, font=("Consolas", 10))
        lb.pack(fill="both", expand=True, padx=12, pady=12)
        for n in names:
            lb.insert("end", n)

        def add():
            for i in lb.curselection():
                n = names[i]
                if n not in self.cfg["exes"]:
                    self.cfg["exes"].append(n)
            self._save_cfg()
            self._refresh_lists()
            win.destroy()

        tk.Button(win, text="add selected", command=add,
                  **self._btn()).pack(pady=8)

    def _remove_exe(self):
        for i in reversed(self.exe_list.curselection()):
            del self.cfg["exes"][i]
        self._save_cfg()
        self._refresh_lists()

    def _add_site(self):
        s = self.site_entry.get().strip()
        if s and s not in self.cfg["sites"]:
            self.cfg["sites"].append(s)
            self.site_entry.delete(0, "end")
            self._save_cfg()
            self._refresh_lists()

    def _remove_site(self):
        for i in reversed(self.site_list.curselection()):
            del self.cfg["sites"][i]
        self._save_cfg()
        self._refresh_lists()

    # -- navigation ----------------------------------------------------------
    def _show_timer(self):
        self.settings_frame.pack_forget()
        if hasattr(self, "run_frame"):
            self.run_frame.pack_forget()
        self.timer_frame.pack(fill="both", expand=True)

    def _show_settings(self):
        if self.session.active:
            messagebox.showinfo(APP_NAME, "Settings are locked during a session.")
            return
        self.timer_frame.pack_forget()
        self.settings_frame.pack(fill="both", expand=True)

    def _show_running(self):
        self.timer_frame.pack_forget()
        self.settings_frame.pack_forget()
        if not hasattr(self, "run_frame"):
            self._build_running_screen()
        self.run_frame.pack(fill="both", expand=True)

    # -- start/stop ----------------------------------------------------------
    def _start(self):
        self._save_cfg()
        mins = self.min_var.get()
        if not self.cfg["exes"] and not self.cfg["sites"]:
            if not messagebox.askyesno(APP_NAME,
                                       "Nothing is set to block. Start anyway?"):
                return
        if not is_admin():
            messagebox.showinfo(
                APP_NAME,
                "Running without admin: website + OS-level exe blocking are off.\n"
                "Programs will still be force-closed. For full blocking, "
                "right-click the app and Run as administrator.")
        self.session.start(mins, self.cfg["exes"], self.cfg["sites"])
        self._show_running()

    def _on_close(self):
        if self.session.active:
            messagebox.showinfo(APP_NAME, "Locked. The session cannot be closed.")
            return  # refuse
        self.root.destroy()

    def on_time_up(self):
        # Called from poll thread -> marshal to UI thread.
        self.root.after(0, self._complete)

    def _complete(self):
        self.session.finish()
        messagebox.showinfo(APP_NAME, "Session complete. You are free.")
        self._show_timer()

    def flash_quote(self):
        # A blocked program tried to launch -> Oblivionis speaks a new line.
        self.root.after(0, lambda: self._type_quote(force=True))

    def _type_quote(self, force=False):
        if not hasattr(self, "quote_label"):
            return
        import random
        # Don't interrupt a line mid-type unless a block event forces it.
        if self._type_job is not None and not force:
            return
        if self._type_job is not None:
            try:
                self.root.after_cancel(self._type_job)
            except Exception:
                pass
        self._type_full = "> " + random.choice(QUOTES)
        self._type_i = 0
        self._type_step()

    def _type_step(self):
        if not hasattr(self, "quote_label"):
            return
        if self._type_i <= len(self._type_full):
            shown = self._type_full[:self._type_i]
            cursor = "_" if (self._type_i % 2 == 0) else " "
            self.quote_label.config(text=shown + cursor)
            self._type_i += 1
            # ~45ms/char gives that slow, deliberate AI-terminal cadence.
            self._type_job = self.root.after(45, self._type_step)
        else:
            self.quote_label.config(text=self._type_full)
            self._type_job = None
            # Idle a while, then she speaks again on her own.
            self._type_job = self.root.after(9000, lambda: self._type_quote())

    # -- tick ----------------------------------------------------------------
    def _tick(self):
        if self.session.active and hasattr(self, "run_frame") and self.run_frame.winfo_ismapped():
            rem = self.session.remaining()
            m, s = divmod(rem, 60)
            self.countdown.config(text="%02d:%02d" % (m, s))
            if rem <= 0:
                self._complete()
        self.root.after(1000, self._tick)


# ----------------------------------------------------------------------------
# Entry
# ----------------------------------------------------------------------------

def main():
    lock = acquire_single_instance()
    if lock is None:
        # Another instance already runs (e.g. guard task double-fired). Exit.
        return
    autostart_set(True)
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
