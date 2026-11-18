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
- The update restart fix (PYINSTALLER_RESET_ENVIRONMENT): first real update from v4.0.12+ to a newer one

Also untested, from the next update onward: manual breaks, the manual program box,
the ±1 timer buttons, the new fonts and effects, the message bank shuffle, the typewriter speed.
Matte update: the matte colours and fonts on a real screen, the wordmark cursor, ending a break early
(blocks coming back on a real PC).

Testing rule: a change moves from here to "verified" only after a run on Windows, not by reading the code.
