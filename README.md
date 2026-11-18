# FocusLock

A no-killswitch focus timer for Windows. Pick a time, press Start, and the
programs/websites you chose stay blocked until the clock runs out. No cancel,
no close button, survives reboot.

## Run it (one step)

1. Right-click `focuslock.py` → **Run as administrator** (or double-click it if
   Python is installed — admin just unlocks website + OS-level blocking).

That's it. First screen is the timer: adjust minutes, hit **START**.

Open **settings** (only before a session) to choose which `.exe` files and
websites to block. "pick running" lists programs open right now.

## Make a .exe (optional)

Run `build_exe.bat`. Needs `pip install pyinstaller`. Result: `dist\FocusLock.exe`.

## What's safe if something fails

- **No admin?** Website + registry blocking turn off automatically; the app
  just force-closes the chosen programs instead. It tells you.
- Every block (hosts file, registry, scheduled task) is **always removed** when
  the session ends — it never leaves your games or sites stuck blocked.

## Could not test

I have no Windows machine here, so this is **untested on real Windows**. The
risky pieces are: the scheduled-task relaunch guard, the IFEO registry block,
and the countdown surviving a reboot. If anything misbehaves, tell me which
screen and what happened.
