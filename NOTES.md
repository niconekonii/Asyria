# Notes: known gaps

Code that exists but has never been run on a real Windows PC. We can't yet say it works.
Each item needs a real Windows test before it's called done.

- Auto-relaunch after a restart (AveGuard scheduled task, Run-key backup, heal loop). Read through in v4.0.8: a break in progress survives a reboot in the code, but it has never run on Windows.
- Guard task and relaunch
- IFEO launch block (games refused at launch, needs admin)
- Hosts-file website blocking
- Reboot survival of a session
- Task Scheduler sealing (mmc, schtasks, regedit closed during focus)
- Folder blocking (renamed copies caught)
- Heartbeat takeover (a suspended or hung Ave gets replaced)
- Delete lock and the hidden spare copy
- DPI scaling and the dark title bar
- The self-update helper (swap, restart with the same rights)
- The update restart fix (PYINSTALLER_RESET_ENVIRONMENT): first real update from v4.0.13 to a newer one
- The watchdog pair: kill-and-relaunch timing, one-watcher mutex, admin inheritance, both-killed fallback
- The exit sealing: cmd/PowerShell/Task Manager/taskkill killed on sight during focus; the two-name
  (Ave.exe + AveGuard.exe) taskkill resistance; the suspend relaunch
- The surrender ordeal: 10 clicks to summon, the 60 s wait, typing the 40-char phrase, and that committing
  it truly ends the session and lifts every block on a real PC
- That `--cleanup` is now inert on Windows and that blocks still lift on a normal session end without it

Also untested, from the next update onward: manual breaks, the manual program box,
the ±1 timer buttons, the new fonts and effects, the message bank shuffle, the typewriter speed.
Typed minutes in the ring, the new start/end sounds.
Matte update: the matte colours and fonts on a real screen, the wordmark cursor, ending a break early
(blocks coming back on a real PC).
Restart fix: that a mid-session restart brings back the current version (newest-copy relaunch, versioned
spares, stale hand-off), and the hand-off from an old download.
the first-run self-install and hand-off to the installed copy, the Start menu entry and
pinning, taskbar grouping of relaunched copies (one app id), the tray icon/menu/hover text with a real Explorer
(also as admin), X hiding to the tray, the one-time notice, uninstall from Installed apps (and its refusal during
a session), and the old-folder v4.0.34 auto-update ending up installed. (The CI runner exercises the shortcut,
icon load and tray window code, but has no real taskbar.)

Testing rule: a change moves from here to "verified" only after a run on Windows, not by reading the code.
