# Ave — internal dev log

Newest on top. Format and rules: see `CLAUDE.md` §6.
Release numbers come from the GitHub build (`v4.0.<run_number>`).

## v4.0.? — 2026-11-18 — Oblivionis chat
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
