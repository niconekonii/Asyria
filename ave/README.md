# Ave

A no-killswitch focus timer for Windows, watched over by Oblivionis.

## Get it (one step)

Download **Ave.exe** from the repo's **Releases** page and **right-click > Run as administrator**, once.
(Windows may warn that the app is unsigned: **More info > Run anyway**.)
Ave installs itself to `%LOCALAPPDATA%\Programs\Ave` and appears in **Start** as **Ave**.
Right-click it there > **Pin to taskbar** / **Pin to Start**. You can delete the downloaded file.

- **Tray:** Ave sits behind the taskbar's **^** arrow. Click it to open. Right-click > **quit** to close it
  (not offered during a session). With no session running, the window's **X** hides Ave to the tray.
- **Windows 11:** new tray icons hide behind the ^ arrow. To keep mine always visible: Settings >
  Personalization > Taskbar > Other system tray icons > Ave: On. If **Smart App Control** is on, Windows
  blocks unsigned apps like Ave with no "Run anyway" (Windows Security > App & browser control).
- **Uninstall:** Settings > Apps > Installed apps > Ave > Uninstall. Refused while a session runs.

If Defender complains, exclude **both** folders: `%LOCALAPPDATA%\Programs\Ave` and `%LOCALAPPDATA%\Ave`
(Ave keeps a hidden spare copy of itself there).

## Use it

- Pick a preset (Deep / Pomodoro / Sprint) or use **- / +** to change the minutes.
- Click **Start** twice. After that there's no way out until the timer ends.
- Breaks unblock everything until the break ends (or you end it early with "end break early", two clicks). Then it all blocks again.
- **settings** (only before a session): Programs (Browse or Running), Websites, Presets, Oblivionis.
- **Updates:** Ave updates itself between sessions (settings > About > Check for updates, or
  auto-update). It restarts with the same rights it had, so admin stays admin.
- **Talk to Oblivionis:** hover over her line at the bottom. Type to her on the home screen. During a
  session, press **motivation** for a line. To let her speak freely, paste an Anthropic API key in
  **settings > Oblivionis**. The key is encrypted for your Windows account. Without one she uses her
  canned lines.

Without admin, Ave still closes blocked programs, but it can't block websites or stop games from launching.

## Escape routes, sealed

| You try... | Ave does |
|---|---|
| Close the window / Alt+F4 | Refuses |
| Tray icon > quit | Not offered during a session |
| Uninstall from Installed apps | Refuses during a session |
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

That shouldn't happen: Ave removes every block the moment a session ends, and tidies up
on its own if it ever finds a session that died with blocks left. There is no `--cleanup`
command any more — the only way out of a running session is the in-app surrender ordeal.
If a block ever truly stays stuck, you clear it by hand (the hosts file and the IFEO
registry keys) or reinstall.

## Not tested yet

These parts have not been run on a real Windows PC yet: the auto-relaunch task,
the registry launch block, the hosts-file site block, and surviving a reboot.
Anti-cheat games may object to the registry launch block.
