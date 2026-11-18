# Ave

A no-killswitch focus timer for Windows, watched over by Oblivionis.

## Get it (one step)

Download **Ave.exe** from the repo's **Releases** page, put it in a folder called `ave`,
then **right-click > Run as administrator**.
(Windows may warn that the app is unsigned: **More info > Run anyway**.)

## Use it

- Pick a preset (Deep / Pomodoro / Sprint) or use **- / +** to change the minutes.
- Click **Start** twice. After that there's no way out until the timer ends.
- Breaks unblock everything. The next round blocks it all again.
- **settings** (only before a session): Programs (Browse or Running), Websites, Presets.

Without admin, Ave still closes blocked programs, but it can't block websites or stop games from launching.

## If something stays blocked

That shouldn't happen. Ave removes every block when a session ends. If it ever does,
run `Ave.exe --cleanup` as administrator.

## Not tested yet

These parts have not been run on a real Windows PC yet: the auto-relaunch task,
the registry launch block, the hosts-file site block, and surviving a reboot.
Anti-cheat games may object to the registry launch block.
