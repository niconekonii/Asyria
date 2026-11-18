# Ave

A no-killswitch focus timer for Windows, watched over by Oblivionis.

## Get it (one step)

Download **Ave.exe** from the repo's **Releases** page, put it in a folder called `ave`,
then **right-click > Run as administrator**.
(Windows may warn that the app is unsigned: **More info > Run anyway**.)

If Defender complains, exclude **both** folders: your `ave` folder and `%LOCALAPPDATA%\Ave`
(Ave keeps a hidden spare copy of itself there).

## Use it

- Pick a preset (Deep / Pomodoro / Sprint) or use **- / +** to change the minutes.
- Click **Start** twice. After that there's no way out until the timer ends.
- Breaks unblock everything. The next round blocks it all again.
- **settings** (only before a session): Programs (Browse or Running), Websites, Presets.

Without admin, Ave still closes blocked programs, but it can't block websites or stop games from launching.

## Escape routes, sealed

| You try... | Ave does |
|---|---|
| Close the window / Alt+F4 | Refuses |
| End task in Task Manager | Comes back within ~1 minute. The timer keeps counting. |
| Delete `AveGuard` in Task Scheduler | Task Scheduler gets closed during focus, and `AveGuard` is recreated every ~90 s |
| Suspend Ave (Resource Monitor etc.) | Its heartbeat stops, and the guard replaces it within ~3 minutes |
| Edit hosts / registry blocks by hand | Regedit gets closed during focus; blocks are put back every 30 s |
| Rename or copy the game's .exe | The whole game folder is blocked, not just the name |
| Delete Ave.exe | Windows refuses while Ave runs. A hidden spare copy relaunches anyway. |
| Change the PC clock | Does nothing. The timer runs on Windows uptime. After a reboot it uses online time, or only counts uptime if offline. |
| Edit or delete Ave's save file | It's signed and stored twice. An edited copy gets ignored. |
| m.youtube.com, youtu.be, x.com... | Common alternate addresses are blocked too |

**Still open (on purpose or because it can't be closed):** Task Manager (you asked for it),
PowerShell/Command Prompt (blocking them breaks Windows), other devices,
a second Windows account, Safe Mode, and browser games on sites you didn't list.
Anti-cheat games may object to the registry launch block.

## If something stays blocked

That shouldn't happen. Ave removes every block when a session ends. If it ever does,
run `Ave.exe --cleanup` as administrator.

## Not tested yet

These parts have not been run on a real Windows PC yet: the auto-relaunch task,
the registry launch block, the hosts-file site block, and surviving a reboot.
Anti-cheat games may object to the registry launch block.
