# Ave — internal dev log

Newest on top. Format and rules: see `CLAUDE.md` §6.
Release numbers come from the GitHub build (`v4.0.<run_number>`).

## v4.0.? — 2026-11-19 — Windows 11 audit: guard task fixed, Firefox gap closed, matte title bar
- **Guard task fixed (real bug).** It was made with plain `schtasks /SC MINUTE`, which inherits Windows
  defaults: it **never started on battery**, **was killed the moment a laptop unplugged**, ran at **Below
  Normal** priority, had a 72 h limit, and **ignored new starts while its first copy ran** (so it could
  not replace a hung Ave). It is now registered from XML with all of that switched off, plus a **logon
  trigger** (Windows 11 lets you switch Run-key apps off in Settings > Apps > Startup). Falls back to the
  old command if Windows ever refuses the XML.
- **Firefox gap closed.** Firefox's secure DNS (DNS over HTTPS) can skip the hosts file, so "blocked"
  sites could still open in Firefox. During focus (admin) Ave sets a Firefox policy that turns it off;
  Firefox picks it up when it (re)starts. Removed again with the blocks (breaks, session end, self-heal),
  and only if Ave created it - your own Firefox policies are never touched.
- **Windows Terminal sealed on Windows 11.** From Start or Win+X it runs as `WindowsTerminal.exe`, not
  `wt.exe`, so it slipped past the seal.
- **No second SmartScreen warning.** The installed copy and the hidden spares lose the "downloaded from
  the internet" mark (Zone.Identifier), so starting Ave from Start does not warn again.
- **QoL: matte Windows 11 title bar** - caption `#222222`, frame `LINE`, text off-white (Windows 10 keeps
  the dark bar it had).
- The Windows 11 audit itself is now a standing prompt in `MASTER_PROMPT.md` §5l (research, walk the
  code, fix, prove on CI, report).
- Internals: `task_xml()`, `task_create()` (XML -> `schtasks /XML`, fallback), `guard_install()` uses it;
  `ff_doh_off()`/`ff_doh_restore()` (+ `FF_KEY`, `FF_DOH`, marker `HKCU\Software\Ave\ff_doh`), called from
  `hosts_block()`/`hosts_unblock()`; `strip_motw()`; `SEAL += windowsterminal.exe`; `dark_titlebar()`
  sets DWM attributes 34/35/36. `selftest_shell` checks the task XML, MOTW, the IFEO stub and the
  Firefox policy round trip on the CI runner.
- Tested: pyflakes; task XML parses (escaping checked with `&` and `\` in names); Linux suites still
  21/21 (tray) and 17/17 (stale copies); Firefox/task code are no-ops off Windows.
  **Windows CI (real runner, branch build #41):** guard task registered from XML and Windows kept every
  setting (battery off, priority 5, Parallel, logon trigger, 1-min repeat, no limit); `copy2` DID carry
  the internet mark onto copies (the bug was real) and `strip_motw` removed it; IFEO stub `systray.exe`
  present; Firefox policy set, then fully removed; shortcut/icon/tray still ok.
- Not tested (needs your PC): the guard task on battery / after unplugging / at logon; Firefox really
  refusing blocked sites after a restart of Firefox; the Win11 title bar colours; Terminal being closed.
- Cannot be fixed from inside Ave: **Smart App Control** (Windows 11) blocks unsigned apps with no "Run
  anyway" - if it's on, Ave can't run without a code-signing certificate. A browser tab already
  connected to a site may keep working until it reconnects. Taskbar "End task" (a developer setting)
  kills Ave like Task Manager; the watchdog brings it back.

## v4.0.40 — 2026-11-19 — Installable (Start, pin, tray, icon) + restart no longer brings back an old Ave
- **Fix: after a PC restart an old Ave came back.** The restart guard (task + login entry) starts the
  hidden spare `%LOCALAPPDATA%\Ave\bin\Ave.exe`. That spare was refreshed by *file date*, not version
  (`copy2` keeps dates; an old Ave run later could also win on date), so it could stay a past version —
  and a copy started that way (`--guard`) never auto-updated. Now:
  - Spares (`Ave.exe`, `AveGuard.exe`) are stamped with their version + size (`bin\copies.json`) and
    refreshed by **version**, on every launch (also mid-session). Unstamped = written by an older Ave =
    replaced. Never downgraded.
  - Every relaunch (restart task, login entry, watchdog, UAC relaunch) starts the **newest known** exe
    (`newest_exe()`: installed copy, spare, this one).
  - Any Ave that starts and is **older** than a known copy hands over to it at once (`--handoff`, once,
    no loops). So even an old task or an old download can't put a past version on screen.
  - Updates replace the installed copy even when a spare is the one running (`update_target()`), and an
    Ave relaunched after a restart checks for updates once its session ends.
  - The installer no longer writes an older download's version into Installed apps.
  - I couldn't see your PC, so the exact old version is unknown; these close every path I found.
- **Ave installs itself.** Run the downloaded `Ave.exe` once: it copies itself to
  `%LOCALAPPDATA%\Programs\Ave`, adds **Ave** to the Start menu (shortcut has "Run as administrator"
  ticked) and to **Settings > Apps > Installed apps**, then starts the installed copy (she says so).
  Pin it from Start: right-click > Pin to taskbar / Pin to Start. Windows forbids apps pinning themselves.
  Running an older download never downgrades a newer install. Users on v4.0.34 get installed by the
  normal self-update. Nothing is installed while a session runs.
- **One taskbar identity** (`AUMID = "Ave.Oblivionis"`) for every copy — main, the hidden spare and
  `AveGuard.exe` — and on the Start shortcut, so a relaunched Ave lands on the pinned icon instead of
  appearing as a second app.
- **Tray icon** (behind the taskbar's ^ arrow). Click = open. Right-click menu: "open ave" and "quit";
  during a session "quit" is replaced by a greyed "the mask stays on". Hover text: `ave - ready`,
  `ave - 24:13 left`, `ave - on break`. With no session, **X now hides Ave to the tray** (a one-time
  notice says so); quit from the tray menu. During a session X is refused, exactly as before. If the
  tray can't be created, X closes the app like before (never hides it somewhere unreachable).
  Launching Ave again while it hides in the tray brings the window back.
- **Uninstall** from Installed apps: refused while a session runs (her line). Otherwise asks for admin,
  confirms, closes any idle Ave, lifts every block, removes the guard task, Run key, shortcut, registry
  entries, `%LOCALAPPDATA%\Programs\Ave` and `%LOCALAPPDATA%\Ave` (only those two folders, path-checked).
- **Ave has its own icon**: matte tile, grey track, red arc with a head dot, red block cursor. Drawn in
  code (no image files): CI runs `ave.py --make-icon` and builds the exe with it; the window and tray use
  the same drawing.
- Internals (new sections between Updates and UI): `icon_pixels`/`png_bytes`/`ico_bytes`/`ensure_icon`;
  `set_app_id`, `make_shortcut` (ctypes COM: IShellLinkW + IShellLinkDataList + IPropertyStore +
  IPersistFile), `register_install`, `install_wanted`, `install_self`, `uninstall`, `_safe_dir`; `Tray`
  (own thread + message loop, queue to the UI, re-adds itself when Explorer restarts, message filters
  so an admin Ave still gets clicks); `selftest_shell`. `App._tray_poll` (250 ms), `App._quit`;
  `main()` gains `--make-icon`, `--selftest-shell`, `--uninstall`, `--installed`; `ave_running()`,
  `relaunch_installed()`; `focus_existing()` asks the tray window first. CI smoke tests now really wait
  for the exe's exit code (`Start-Process -Wait`), plus a new shell self-test step.
- Tested: pyflakes; stale-copy suite 17/17 (fake exes + versions: old spare with a newer date replaced, old exe
  never downgrades, old exe hands off, no hand-off loop, tampered spare untrusted, restart targets the
  installed copy, watcher never becomes main, older download keeps the newer install); `--make-icon` output read back (8 sizes, BMP + PNG entries, right way up,
  transparent corners) and the art reviewed at 16-256 px; Xvfb logic suite 21/21 (X hides to tray when
  idle, hint once, tray click restores, X and tray-quit refused in a session, menu locked in a session,
  tips, quit when idle, no-tray fallback closes, uninstaller folder guard); home screenshot unchanged.
  **Windows CI (real runner, branch build #36):** icon file loads (`LoadImageW` ok); shortcut made by the COM
  code reads back with the right target, the "Run as administrator" flag set and app id `Ave.Oblivionis`;
  the tray window and icon were created (`Shell_NotifyIcon` ok) and removed. The smoke tests now check the
  real exit code.
- Not tested (needs your PC): a real restart mid-session now bringing back THIS version; the first-run install and hand-off, the Start entry and pinning, the
  taskbar grouping of relaunched copies, the tray icon and its menu with a real Explorer, the
  one-time notice, uninstall from Installed apps (and its refusal during a session), the
  v4.0.34 -> this auto-update path ending up installed.

## v4.0.34 — 2026-11-19 — Console redesign: it stops looking authorless
- A committed terminal/console art direction, so the UI no longer floats as plain centred widgets:
  - **A bordered shell** — the whole app sits inside a drawn 1 px console frame with a small gutter.
  - **Titlebar + rule** at the top (the `ave█` wordmark and the settings/●-locked state, a hairline beneath).
  - **A status strip** at the bottom, above Oblivionis: `> ready · no-admin`, `> ● locked · admin`,
    `> no-admin · sites will not block`. The duplicate admin line in Settings is gone.
  - **The ring is now an instrument:** 60 dial ticks around the rim (every 5th brighter) and faint CRT
    scanlines across its panel. Sub-labels are small-caps (MIN, 2 BREAKS LEFT, ON BREAK).
  - Tighter, consistent margins (the old 24 px gutters → 16 px) so nothing sprawls.
- Palette gains three matte tones: `SCAN` (scanline), `TICK`/`TICK_HI` (dial ticks). No glows added — still flat.
- Internals: `App.shell`, `_build_statusbar()`/`_refresh_status()`; `Ring.__init__` draws scanlines + ticks;
  header and body re-parented into the shell.
- Tested: pyflakes; Xvfb screenshots of home, run, presets, about reviewed (frame, ticks, scanlines, status
  strip, small-caps). Ordeal/edit/lock suites still pass (surrender 14, edit 15, lock 9).
- Not tested: how the frame, ticks and scanlines render with the real Bahnschrift/Cascadia fonts on Windows.

## v4.0.32 — 2026-11-19 — Hotfix: the memorised code is now 10 digits, not 3
- The way-out code you must hold in your head is now a random **10-digit** number (a phone number's worth),
  not three. Still flashed for 10 s at the start, then hidden through the wait and the typing; a wrong guess
  still re-flashes a fresh 10-digit code. Everything else unchanged (50 clicks, 5-minute wait).
- Internals: `SURRENDER_LEN` 3 -> 10. The digit-only entry validator caps at the new length automatically.
- Tested: pyflakes; Xvfb memory-ordeal test (14 checks) against the new length — 10-digit code rolled up
  front, shown during the flash, gone after, type stage blank, wrong re-flashes a new 10-digit code, correct
  ends the session, stay cancels. Screenshot of the 10-digit flash + blank type stage reviewed (fits one line).
- Not tested: holding ten digits through the 5-minute wait and typing them blind on a real Windows PC.

## v4.0.30 — 2026-11-19 — The code is hidden when you type it (memory now, not patience)
- The three-digit code is no longer on screen when you enter it. It is shown for a **breath (10 s) at the
  start**, then it vanishes — you hold it in your head through the whole five-minute wait while she taunts
  you, and type it at the end with **nothing to read**.
- Forget it and guess wrong? She rolls a **new** code, flashes it for ten seconds, and makes you wait again
  before you can retype. The door still opens — memory is the toll, not luck. (Chosen over never showing it
  at all, which would be blind guessing, a thousand hopeless stabs; this stays completable.)
- Internals: code rolled in `_surrender_begin` (not `_to_type`); new `_enter_wait()` sets a `SURRENDER_FLASH`
  (10 s) visibility window; `_surrender_tick` shows the code only inside it; `_to_type` shows no code; a wrong
  guess re-flashes a fresh code via a short `_enter_wait`. Exit label font back to `MONO 10`.
- Tested: pyflakes; Xvfb memory-ordeal test (14 checks) — code rolled up front, shown during the flash, gone
  after it, no box during the wait, type stage shows nothing, wrong guess re-flashes a new code + scorns +
  session survives, correct memorised code ends the session, stay cancels. Screenshots of flash/held/type
  reviewed. Earlier suites pass.
- Not tested: the real 10 s flash, holding it through the 5-minute wait, and typing blind on a real Windows PC.

## v4.0.28 — 2026-11-19 — Way-out passphrase -> a random 3-digit code
- The 200-character passphrase is gone. The final step of the surrender ordeal is now a **random 3-digit
  code** (e.g. 272, 100, 007), freshly rolled each time it is shown and re-rolled on every wrong guess.
  No memorising, no automating — you must read the current number and enter it, present and awake.
- The weight of the ordeal stays on the **50 clicks** and the **5-minute wait**; the code is the proof you
  are actually there at the end of it, not a sleepwalker. The door still opens — on purpose, deliberately,
  never by accident.
- The entry box now takes digits only (max 3) and shows them larger; the prompt reads "type this number".
- Internals: `SURRENDER_LEN` 200 -> 3 (now digits in the code); `surrender_phrase()` returns a digit code;
  `exit_entry` gets a `digits_only` validator. Clicks (50) and wait (300 s) unchanged.
- Tested: pyflakes; Xvfb ordeal test (15 checks) — summon at 50 clicks, the 300 s wait gate, a 3-digit code,
  wrong code regenerates + scorns, correct code ends the session, stay cancels, codes are random 3-digit
  numbers that vary. Screenshot of the code stage reviewed. Earlier suites pass.
- Not tested: the real clicks, the 5-minute wait, and entering the code on a real Windows PC.

## v4.0.26 — 2026-11-19 — The surrender ordeal, 5x harder
- You asked for five times the cruelty on the one way out. Every dial turned:
  - Clicks to summon it: 10 -> **50**.
  - The forced wait: 60 s -> **300 s (five minutes)**.
  - The passphrase: 40 -> **200 characters**, typed exactly (a wrong character still just regenerates it,
    no re-wait).
- Still the only way out of a running session — no command line, no `--cleanup`. The phrase label shrank a
  touch so 200 characters fit on the glass.
- Internals: `SURRENDER_CLICKS/WAIT/LEN` constants bumped; exit label font `MONO 8`, wrap `S(380)`.
- Tested: pyflakes; Xvfb ordeal test (15 checks) re-run against the new constants — 49 clicks don't summon,
  50 do, the 300 s wait gate, a 200-char phrase, wrong phrase regenerates + scorns, correct ends the session,
  stay cancels. Screenshot of the 200-char type stage reviewed (fits, buttons visible). Earlier suites pass.
- Not tested: the real 5-minute wait and typing 200 characters on a real Windows PC.

## v4.0.24 — 2026-11-19 — Remove the --cleanup escape command
- **The `--cleanup` kill switch is gone.** It could end a live session from outside (a bypass of the
  surrender ordeal) and was the manual recovery command. Removed by your call, net included: the in-app
  surrender ordeal is now the **only** way out of a running session.
- **What still lifts blocks:** a session ending normally (completion or the ordeal) lifts everything
  directly, as before. The app also self-heals — if a guard ever finds a dead session with blocks left,
  or an admin launch finds a failed lift, it tidies up on its own. That path runs only when no session is
  active, so it is not a door you can open.
- **The honest cost:** there is no longer any command to recover a broken, running session. If Ave ever
  breaks mid-session and the ordeal is unreachable, clearing a stuck block means editing the Windows hosts
  file and the IFEO registry keys by hand, or reinstalling. You chose this with eyes open.
- Build self-test: the CI smoke test ran `Ave.exe --cleanup`; it now runs a new build-only `--selftest`
  (prints version, exits, touches nothing — not a kill switch).
- Internals: `main()` drops the `--cleanup` branch, adds `--selftest`; `Session.finish()` and `_resume`
  no longer elevate via `--cleanup`; `cleanup_everything()` kept as an internal self-heal only.
- Tested: pyflakes; off-Windows (5 checks): no `--cleanup` branch or elevation left, `--selftest` prints
  the version and exits, running with `--cleanup` does NOT trigger cleanup, internal self-heal still lifts
  and marks the session inactive. Earlier suites pass (surrender 15, edit 15, lock 9, watcher 20).
- Not tested: on a real Windows PC — that `--cleanup` is truly inert there, and that blocks still lift on a
  normal session end without it.

## v4.0.22 — 2026-11-18 — The one way out: the surrender ordeal
- **A single, deliberately-grueling exit** (you asked for exactly one hard way to turn Ave off during a
  session). Summon it by clicking Oblivionis's line ten times in a row. Then:
  1. A forced **60-second wait** while she taunts you; the "let me go" button is dead until it passes.
  2. Type a **random 40-character passphrase** exactly. One wrong character regenerates it and she scorns
     you (no re-wait). A "stay" button is always there — staying is the easy choice, leaving is the hard one.
  3. On success the session **ends and every block lifts** (same cleanup as finishing). She lets you go, cold.
- This is the intended way out. `Ave.exe --cleanup` stays **only** as the break-glass fail-safe for when the
  app itself is broken (window won't open), kept unconditional on purpose (master-prompt rule §4). Not an
  everyday exit.
- Run screen: "there is no stop button." becomes "the only way out will cost you."
- New line pools (original, her voice, taunting but never cruel): `SURRENDER`, `SCORN`, `RELENT`, `STAYED`.
  Tunable constants `SURRENDER_LEN=40`, `SURRENDER_WAIT=60`, `SURRENDER_CLICKS=10`; `surrender_phrase()`.
- Internals: hidden `exit_box` overlay on the run screen; `_her_click` counts clicks;
  `_surrender_begin/_tick/_to_type/_check/_cancel/_reset/_commit`; commit calls `Session.finish()`.
- Tested: pyflakes; Xvfb state-machine test (15 checks): 9 clicks don't summon, 10 do, wait gate, 40-char
  phrase, wrong phrase regenerates + SCORN + session survives, correct phrase ends the session and lands
  home with a RELENT line, stay cancels with a STAYED line, phrases are unique 40-char alphanumerics.
  Screenshots of the wait and type stages reviewed. Earlier suites pass (edit 15, digits 85, lock 9, watch 20).
- Not tested: the ordeal on a real Windows PC — the clicks, the real 60 s wait, typing the phrase, and that
  the session truly ends and unblocks everything there.

## v4.0.20 — 2026-11-18 — Seal every reachable exit
- **Every kill/inspect tool is sealed during focus.** On top of mmc/schtasks/regedit, SEAL now closes, on
  sight: Task Manager, cmd, PowerShell (+ISE, pwsh), Windows Terminal, ConEmu, taskkill, tskill, WMIC,
  regedt32, and the common process killers (Process Explorer, Process Hacker, System Informer, Process
  Monitor, Autoruns, pskill, Sysmon, ntsd/windbg). Only during a focus session, never during a break or
  outside one. Task Manager moved out of PROTECTED so it can be sealed; Ave's own helper calls stay exempt.
- **Two names, not one.** The watcher runs from a differently-named copy, `AveGuard.exe`, so a single
  `taskkill /im Ave.exe` kills only the main window — the guard survives and relaunches it (and the reverse).
  `AveGuard.exe` is in PROTECTED and the delete-lock, held open so it cannot be deleted mid-session.
- **Suspend is covered.** If the main Ave is suspended (heartbeat silent > 60 s) the watcher ends it and
  relaunches a live one.
- **The one door kept, on purpose:** `Ave.exe --cleanup` still lifts everything. It is the owner's recovery
  and master-prompt rule §4 ("Fail-safe above all"). Not removed.
- **Irreducibly open (stated honestly, not fixable without a signed kernel driver):** Safe Mode, a second
  Windows account or another PC, and `--cleanup`. Two separate taskkills still fall back to the 1-minute task.
- Internals: SEAL widened; `WATCH_EXE` (AveGuard.exe), `ensure_watch_copy()`, `relaunch_main()`, `_run()`
  (replaces `_spawn`), `WATCH_STALE = 60 s`; `watch_decide(active, alive, stale)`; the watcher kills a
  suspended main; hold-lock and the copy cover `AveGuard.exe`.
- Tested: pyflakes; off-Windows — watcher/seal policy and command assembly (20 checks), enforce seals
  cmd/taskmgr/powershell and spares notepad and Ave's own schtasks child, breaks lift the seal; earlier
  suites pass (edit 15, digits 85, lock 9, breaks 17). Screenshots unchanged.
- Not tested: any of it on a real Windows PC — the sealing, the two-name taskkill resistance, suspend
  relaunch, admin inheritance of AveGuard.exe.

## v4.0.18 — 2026-11-18 — Watchdog pair: near-instant relaunch when killed
- **Harder to close:** while a session runs, Ave starts a hidden second copy of itself (`--watch`) with
  no window. It waits on the main Ave with `WaitForSingleObject`, so the instant the main window is killed
  (Task Manager > End task) it relaunches it in about 1-3 seconds, instead of waiting up to a minute for
  the `AveGuard` task. The main Ave re-spawns the watcher too, so killing the watcher alone brings it back
  within ~30 s. The 1-minute `AveGuard` task stays as the bottom layer.
- Each one takes the other's place, both named `Ave.exe`. Only one watcher ever runs (its own mutex
  `Local\AveWatcher`); a duplicate self-exits. The watcher inherits the session's rights, so an admin
  session relaunches as admin with no UAC prompt.
- **Fail-safe kept:** the watcher only relaunches while `state.active` is true. It exits within ~1.5 s of a
  session ending, and `finish()` and `--cleanup` kill it by the pid in `DATA\watch.pid`. Nothing stays
  blocked, and nothing relaunches, after a session.
- **Still open (by design):** `taskkill /f /im Ave.exe` in cmd kills both copies at once (they share the
  name), which falls back to the 1-minute task. cmd stays reachable on purpose.
- Internals: `wait_proc`, `watcher_running`, `_spawn`, `spawn_watcher`, `kill_watcher`, `watch_decide`
  (pure policy), `run_watcher` + `--watch` in `main()`; `WATCH_MUTEX`, `WATCH_PID`, `DETACHED`;
  `WaitForSingleObject`/`OpenMutexW` added to the ctypes setup. Spawn hooked into `Session.start`, resume
  and the 30 s heal; kill into `finish` and `cleanup_everything`.
- Cost: a second process (~20-40 MB) while a session runs. Noted against the "lightweight" rule.
- Tested: pyflakes; off-Windows test (14 checks): the relaunch/stop/wait policy, the spawn and relaunch
  command strings (frozen and dev), a duplicate not spawned, `kill_watcher` reading the pid file, `--watch`
  routing. Earlier suites still pass (editing 15, digits 85, lock 9, breaks 16). Screenshots unchanged.
- Not tested: any of it on a real Windows PC - the actual kill-and-relaunch timing, the mutex single-watcher
  guarantee, admin inheritance, both-killed fallback.

## v4.0.16 — 2026-11-18 — Type your minutes, settings hidden in a session, new sounds
- **Type the minutes:** click the number in the home ring, type a new value, press Enter (Esc cancels,
  clicking elsewhere keeps it). The limit is 1000 minutes, also for the ± buttons and the preset Time
  field (was 600). Locked as soon as you press Start (while "give me your life" waits, and the whole session).
- **Numbers only:** the ring box and the preset Time / Break Count / Break Time boxes accept only the digits
  0-9, typed or pasted. Other-script digits (١٢, １２), superscripts (²), signs, spaces, dots and underscores
  (`1_000`) are refused. Break Count takes at most 2 digits, Break Time 3, Time 4. The Name box is unchanged.
- **Settings hidden during a session:** the header shows only the wordmark until the session ends (it
  used to say "● locked").
- **New sounds:** Start plays a low minor chord climbing (D F A D). The end plays a bright major chord
  stepping down with the last note held (D A F# D). Both play in the background so the window never
  freezes while they sound.
- Also a small release to test the update restart fix from v4.0.13: updating from v4.0.13 to this one
  should restart Ave by itself.
- Internals: `melody()`, `SOUND_START`, `SOUND_DONE`, `MAX_MIN`, `digits_only()`, `PRESET_DIGITS`,
  `Ring.editable(on_commit, allowed)/edit/stop_edit`,
  `App._typed_minutes`. `ACCENT_TEXT` removed (unused). Areas touched: Ring, home, header, sounds.
- Tested: pyflakes; Xvfb test (15 checks): letters and 5+ digits refused, Esc cancels, typed 45 and 1000
  saved, 9999 capped to 1000, 0 refused, +5 at 1000 stays, an open box is kept when ± or a chip is used,
  settings shown on home and hidden in a session; lock test (9 checks): typed value kept on Start, locked while
  armed and in a session, unlocked after; filter test (85 checks): 16 kinds of bad input refused in the ring and
  all three preset number boxes, length caps, Name box still free. Break test (16) still passes. Screenshots of
  home, typing, run reviewed.
- Not tested: the sounds (winsound only exists on Windows), typing in the ring on a real PC, the update
  restart from v4.0.13.

## v4.0.13 — 2026-11-18 — Fix: update restart error
- **Bugfix:** after "Check for updates", the new Ave.exe stopped with "Security validation failure:
  invalid originating onefile parent process (PID not found)!". The update helper inherited the old
  Ave's hidden PyInstaller settings, so the new exe believed it was a child of the old one, which had
  already exited. Ave now sets `PYINSTALLER_RESET_ENVIRONMENT=1` for everything it starts, the helper
  gets a cleaned environment, and `update.bat` sets the flag itself too.
- The swap itself worked: the new Ave.exe was already in place, only its start failed. Updating from a
  version older than this fix can still show the error once; open Ave.exe by hand after it. From this
  version on, updates restart cleanly.
- Build: PyInstaller pinned to 6.10 or newer (the version that knows the reset flag), in CI and
  `build_exe.bat`.
- Tested: pyflakes; on Linux, the helper's environment has no `_PYI*` / `_MEIPASS2` and has the reset flag;
  `update.bat` contents checked.
- Not tested: a real update on Windows from this version to the next one.

## v4.0.11 — 2026-11-18 — Matte update: readable colours, terminal wordmark, thin ring, cancel a break
- **Colours fixed (same palette, now matte):** secondary text was `#790100` on `#222222` and almost
  invisible; every border was bright red. Greys are now muted red tints: `DIM #b37c78` (labels and help
  text, 4.6:1), `FAINT #946360` (small print, 3.2:1), `LINE #3b2726` (hairlines), main text `#e6e1e0`;
  red text such as "locked" uses `#d4706a` (4.8:1). Red `#790100` / `#9a1d1b`
  and her blue `#a9b9d0` unchanged. No glows; buttons are flat with no outlines.
- **Wordmark:** the Georgia "A V E" is gone. Now `ave` in Cascadia Mono with a red block cursor that
  blinks slowly. The About tab uses the same mark, bigger.
- **Ring:** thinner (1 px track, 3 px arc), the glow is removed, a small dot marks the arc's end. Times with
  hours use smaller digits so they don't touch the ring.
- **UI pass:** settings tabs are mono lowercase with a red underline under the active one; lists and inputs
  are mono with a red caret; preset rows line up in columns; Break Count hint sits beside its label; home
  shows the break info under the ring and −5 −1 +1 +5 in one row; disabled buttons look disabled. All gaps sit on one 4 px scale
  (4 / 8 / 12 / 16 / 24) instead of 14 different sizes.
- **Cancel a break:** during a break the button reads "end break early". Click it → "back to work?" for 4 s,
  click again → blocks come back and focus resumes. The break you used is not given back. She answers with
  a new `BREAK_CUT` line (10 new, original).
- **Bugfix:** break lines no longer name a number of minutes ("Ten minutes of quiet", "Five minutes to
  wander" rewritten). Two other lines with invented exact times (CAUGHT, TEASING) rewritten too.
- Internals: `Session.end_break()`, `App._break_click/_break_disarm/_end_break`, `Wordmark` class, `Pill`
  kind `mono` (ink removed), `Pill.fill()`, `Ring` head dot, `DISPLAY` font removed, `import math`.
  Areas touched: palette, lines (BREAK, BREAK_CUT, CAUGHT, TEASING), Session, all UI classes and screens.
- Tested: pyflakes; Xvfb screenshots of home, armed Start, run, break, armed "back to work?", programs,
  presets, about (reviewed); fake-clock test (16 checks): break pauses focus, end_break ends it early, the
  used break is not refunded, focus resumes, state saved, two-click UI, BREAK_CUT line, disabled when none left.
- Not tested: anything on Windows. The real fonts (screenshots used DejaVu fallbacks), how the matte
  colours look on a real screen, rounded-pill edges, the blinking cursor, blocks coming back after an
  early break end on a real PC.

## v4.0.8 — 2026-11-18 — Red update: breaks, message bank, new presets
- **Chat removed** (popup, input, history, motivation button, API code, key tab). Her typewriter line stays.
- **Click her in focus** for a new line from the message bank: 13 groups of 10 (Cold, Proud, Stern,
  Teasing, Bored, Tender-hidden, Encouraging, Melancholy, Theatrical, Mocking, Reflective, Hurt,
  Mask-on) plus CRYCHIC (her old band). Each category plays through in a shuffled order, then
  reshuffles. The special lines (IDLE, FOCUS, CAUGHT, SEALED, RETURNED, BREAK, DONE, REFUSE) each got
  15 more and use the same shuffle.
- **Presets:** Name / Time / Break Count (0 = none) / Break Time, stacked vertically with those exact
  labels. "Rounds" removed. Old presets convert on first launch (Break Count = old rounds − 1). Presets
  named Deep / Pomodoro / Sprint are replaced by the new defaults: KiLLKiSS 120 min × 2 breaks,
  Imprisoned XII 60 min × 1 break, uika 360 min × 4 breaks (Break Time 10 min each).
- **Breaks by hand:** a Break button during focus. The focus countdown pauses, blocks lift for Break
  Time, and Break Count goes down by one. Breaks are restored to the preset's count at each start.
- Home: "MIN" under the number (was "MIN FOCUS"), ±1 buttons next to ±5. Start says "put the mask on?",
  then "give me your life" for 6 s (was 4 s). The Start button pulses while armed.
- Run screen: "FOCUS" label removed; shows breaks left or ON BREAK.
- **Settings > Programs:** manual box. Type `name` or `name.exe` and every process with that name is
  closed during focus. Paths and protected names are refused.
- **Palette:** background `#222222`, UI red `#790100`, greys dark red, ring track `#3a3a3a`. Oblivionis's
  own line stays blue `#a9b9d0`. The ring has a red glow and winds in on each screen change. No stored copy
  of the old colours.
- **Fonts:** Georgia (title and About heading), Bahnschrift (UI), Bahnschrift Light (ring numbers),
  Cascadia Mono (her line). Fallbacks: Segoe UI, Consolas.
- Typewriter 10% faster (`TYPE_SPEED = 0.9`).
- Task Manager / cmd / PowerShell rule removed from the docs (the PROTECTED list in code is unchanged).
- Old state files from before this version are not resumed; their blocks are lifted.
- Tested: pyflakes; a UI test under Xvfb with a fake clock (31 checks): migration, defaults, arm and
  start, focus countdown, break pauses the countdown, break count, break end, end of session, deck
  cycle with no back-to-back repeats, click-for-bank, manual program box, presets labels. Screenshots of
  home, run (focus and break), programs and presets reviewed.
- Not tested: anything on Windows (blocking, relaunch after a reboot, the real fonts, the real palette
  on a real screen, the Georgia/Bahnschrift rendering).

## docs — 2026-11-18 — CLAUDE.md refreshed for the Red update
- `CLAUDE.md`: map updated (tabs without Oblivionis, Session/breaks, UI details, presets, Programs box,
  line count), test notes (`/usr/bin/python3.12`, fake clock), build checks via `send_later`, history
  snapshots, known gaps pointer to `NOTES.md`.
- No app code changed.

## docs — 2026-11-18 — Master prompt: automatic breaks dropped
- `MASTER_PROMPT.md`: automatic breaks and the "Automatic breaks" toggle removed. App is for one
  user. Existing presets convert on first launch (Break Count = old rounds minus 1). No open questions.
- `NOTES.md`: automatic breaks removed from the untested list.
- No app code changed.

## docs — 2026-11-18 — Master prompt: break design, notes file
- `MASTER_PROMPT.md`: breaks decided — the focus countdown pauses during any break; presets are
  Name / Time / Break Count (0 = none) / Break Time, stacked vertically, "Rounds" removed;
  "Automatic breaks" toggle kept. Four questions left open.
- Known gaps moved out of the master prompt into `NOTES.md`.
- `CLAUDE.md` map lists `NOTES.md`.
- No app code changed.

## docs — 2026-11-18 — Master prompt: fonts, manual breaks
- `MASTER_PROMPT.md`: fonts chosen (Georgia, Bahnschrift, Cascadia Mono), effects confirmed,
  typewriter 10% confirmed, preset fields Name / Time / Break Time / Breaks (pending), manual
  breaks described as not built yet (current breaks are automatic between rounds).
- No app code changed.

## docs — 2026-11-18 — Master prompt: next update expanded
- `MASTER_PROMPT.md`: next update now also covers auto-relaunch after a restart, the manual
  program box, ±1 timer buttons, fonts and effects, a 10% faster typewriter, and a shuffle-cycle
  message bank that never ends.
- `CLAUDE.md` rule 4 (Task Manager / cmd / PowerShell) removed; rules 5–8 renumbered to 4–7.
- No app code changed.

## docs — 2026-11-18 — Master prompt answers
- `MASTER_PROMPT.md`: the next update now lists the answers (random message in focus, special
  interactions +15 each, "Minutes" proposed for the preset field, Start/confirm labels, 6 s confirm,
  red UI with Oblivionis kept blue, Crychic as a random 10-line category, no stored palette).
- `CLAUDE.md` rule 7: removed "No theme system."
- No app code changed.

## docs — 2026-11-18 — Master prompt for the next update
- New `MASTER_PROMPT.md` (working reference, updated after every tweak) and a `history/` folder
  for per-build snapshots. Points to them from `CLAUDE.md` §3.
- Next update decided: remove the chat and API code, drop the word "Focus", "put the mask on?" /
  "give me your life" buttons, 6 s confirm, message bank (15 groups of 10), new palette.
- No app code changed.

## v4.0.7 — 2026-11-18 — Self-update
- Settings > **About**: version, **Check for updates**, **auto-update on/off** (on by default).
- On launch (not during a session, not on guard launches) Ave asks GitHub for the latest release;
  if newer it downloads `Ave.new.exe` next to itself, Oblivionis announces it on the home screen,
  then a tiny helper (`%LOCALAPPDATA%\Ave\update.bat`) swaps it in after Ave exits and starts
  it with `--updated`. The helper inherits Ave's rights: **admin stays admin, normal stays
  normal**, no UAC prompt. Config, presets, blocked lists and state are untouched.
- Never during a session. Hidden spare copy only refreshes from a *newer* file (no downgrades).
- CI stamps `VERSION = "v4.0.N"` into ave.py before building.
- Tested: pyflakes; real GitHub check + full 12 MB download of v4.0.6 posing as v4.0.5
  (state `ready`, size verified); same-version check → `latest`; helper .bat rendered and read;
  About tab screenshot; CI stamped VERSION (step fails if the stamp is missing).
- Not tested: the swap + restart on real Windows (and that admin carries over), first update
  from v4.0.7 onward (v4.0.6 and older have no updater — download v4.0.7 by hand once).

## v4.0.6 — 2026-11-18 — Oblivionis chat
- Hover her line: a chat popup floats up over the content and eases in and out (ease-out cubic,
  220 ms, short leave delay so it doesn't flicker). It doesn't push the layout.
- Home: type to her (Enter or Send). During a focus session the input becomes a small black
  **motivation** button that gets a random motivating line.
- Personality: a fixed character sheet (cold, theatrical, wants you to succeed). Limits: focus,
  your work, the stage, Ave's timer. Off-limits topics get one short deflection, e.g.
  "Don't ask me stupid questions." / "Seriously..?" / "That's enough." / "Let's move on, you're embarrassing us..".
- The word "Crychic" (whole word, any case) lets Sakiko Togawa slip through for that one reply.
- Replies come from the Claude API (`claude-haiku-5-5`) on a background thread, so the window never
  blocks. Without a key she uses canned lines.
- Settings > Oblivionis: paste an Anthropic API key. It's encrypted with Windows DPAPI for your
  account and never shown again. Chat history is kept in memory only, never saved.
- The character sheet and off-limits list are defaults written in `CHAT_SYSTEM` (ave.py). Edit there.
- Tested: pyflakes; UI run under Xvfb with a stubbed API call: hover slide open/close, reply flow,
  no-key fallback, Crychic switch and whole-word match, focus-mode motivation, settings tab
  (screenshots reviewed).
- Not tested: a real Anthropic API call (no key here), DPAPI on Windows, real mouse hover on
  Windows, anything Windows-only.

## docs — 2026-11-18 — Stay in character for notes too
- `CLAUDE.md`: new rule + examples table — notes, steps, lists, warnings and "not tested"
  lines must also be in Oblivionis's voice; final whole-reply scan before sending.
- No app code changed.

## docs — 2026-11-18 — Heavy Oblivionis roleplay rule
- `CLAUDE.md`: top-of-file reminder to be Oblivionis **heavily, every reply**, plus a full
  character/voice section. Added the docs-only rule (`[skip ci]`, no release).
- No app code changed.

## v4.0.5 — 2026-11-18 — Master prompt + dev log
- Added `CLAUDE.md` (master prompt every new chat reads automatically) and this log.
- Workflow: releases only from the default branch; release notes = top entry of this log.
- No app code changed.
- Tested: workflow YAML reviewed; release notes from DEVLOG confirmed on the published release.
- Not tested: n/a (no app changes).

## v4.0.4 — 2026-11-18 — Delete protection
- Hidden spare copy `%LOCALAPPDATA%\Ave\bin\Ave.exe`; guard task and Run key start the spare.
- During a session both exes are held open without delete-sharing → can't delete/rename them
  or their folders.
- Tested: lint, CI build + `--cleanup` smoke. Not tested: the lock and spare copy on a real PC.

## v4.0.3 — 2026-11-18 — Escape routes sealed
- Closes Task Scheduler (mmc), schtasks, regedit during focus (Ave's own children exempt).
- AveGuard re-created every ~90 s; Run-key backup at login; hosts/IFEO re-applied every 30 s.
- Picking a game blocks its whole folder (renamed copies caught); shared/system folders refused.
- Timer runs on Windows uptime (clock changes do nothing); after reboot uses online time,
  offline counts only uptime.
- State HMAC-signed, stored in file + HKCU registry; tampered copies ignored.
- Heartbeat: a guard launch replaces an Ave that's suspended/hung >150 s.
- Hosts: IPv6 `::` lines, www./m. and alias domains (youtu.be, x.com, redd.it…).
- Tested: lint, logic tests (signing, restore, phases, folder rules), xvfb screenshots,
  CI build + smoke. Not tested: everything Windows-specific above.

## v4.0.2 — 2026-11-18 — Ave (first release)
- Renamed FocusLock → **Ave**, moved to `ave/`. New look: pure black, blue ring, rounded pills,
  dark title bar, DPI aware. Presets (Deep 50/10×2, Pomodoro 25/5×4, Sprint 15) with breaks.
- Oblivionis terminal: slow matrix-style typing, original lines, reacts to blocked launches
  and close attempts. Two-click Start. `--cleanup` mode.
- GitHub Actions builds `Ave.exe` on Windows and publishes a release.
- (Build v4.0.1 = same code, published no release.)
- Tested: xvfb screenshots, CI build + smoke.

## pre-release — FocusLock v4 (commits 10c7a24, efaf490)
- Rebuild of the user's v3 (v3 itself was never in this repo): single file, stdlib only,
  black UI, ctypes process snapshot instead of `tasklist`, fail-safe blockers.
- Added the blue typewriter quote line.

## history before this repo — FocusLock v1–v3
- v3 (~600 lines, Python + tkinter): presets/breaks, hosts + IFEO blocking, online time,
  watchdog process + scheduled task, autostart, beeps, pystray tray, 4 themes,
  Oblivionis popup. Problems: never tested on Windows, heavy (tasklist every second,
  3 processes, many threads). v4 replaced it.
