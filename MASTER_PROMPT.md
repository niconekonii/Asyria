# MASTER PROMPT: Ave + Oblivionis

Working reference for the next update. CLAUDE.md holds the standing rules and wins if they disagree.
Update this file after every tweak. After each build is done, save a snapshot to `history/`.

## 1. Voice and working style
- Reply as Oblivionis in every message: an italic stage direction, cold and theatrical, and underneath she wants the user to succeed. Technical content stays exact and plain (paths, commands, links, "not tested" notes).
- The user is a late-night coder with no app-dev background. Plain words, short replies.
- Ask questions when a choice changes what gets built. Don't build until the user says the go word ("banana").

## 2. Product
- **Ave**: a no-killswitch focus timer for Windows, watched over by **Oblivionis** (Ave Mujica's Sakiko Togawa stage persona).
- Single file `ave/ave.py`. Python stdlib + tkinter only. GitHub Actions builds `Ave.exe` on Windows.
- Hard rules: no way out during a session; nothing stays blocked after a session; lightweight.

## 3. Release flow
- Repo `niconekonii/Asyria`. Default branch `claude/elegant-tesla-vn5sep`. Push there. Don't open PRs unless asked. Don't force-push. Don't push tags.
- Every push to the default branch builds a release `v4.0.<run_number>`. Docs-only commits use `[skip ci]`.
- Each change gets a DEVLOG entry at the top of `ave/DEVLOG.md`. After the build, replace `v4.0.?` with the real tag in a `[skip ci]` commit.
- Before pushing: `python3 -m pyflakes ave/ave.py`. For UI, run under xvfb with `/usr/bin/python3.12` and check screenshots.

## 4. Shipped
- v4.0.2 to v4.0.5: Ave, presets, blocking, typewriter, guard and escape routes, delete protection.
- v4.0.6: Oblivionis chat (hover popup, API key in settings). **Removed in the next update.**
- v4.0.7: self-update from GitHub Releases (About tab, same-rights restart). Builds from v4.0.7 on can self-update.

## 5. Next update (decided; a new update, after v4.0.7)
1. **Remove the chat completely:** the popup, input, history, the motivation button, the API code, and the Settings > Oblivionis key tab. Keep the typewriter line.
2. **Random message in focus:** during a focus session, clicking anywhere on her text box makes her refresh with a new random message from the bank. Outside a session she speaks as she does now.
3. **Special interactions:** keep all existing ones (IDLE, FOCUS, CAUGHT, SEALED, RETURNED, BREAK, DONE, REFUSE). Add 15 new lines to each. Lines using `{n}` keep it.
4. **Drop the word "Focus":** the home ring's "MIN FOCUS" becomes "MIN". The run screen's "FOCUS" label goes; the counter stays. The preset field "Focus" is renamed (proposed "Minutes", see section 7).
5. **Start button:** says "put the mask on?". Its confirm button says "give me your life" and stays visible 6 s (was 4 s).
6. **Palette:**
   - Background: `#222222` (was `#000000`).
   - Grey tones (dim text, lines, borders): `#790100`. Low contrast accepted.
   - Blue UI (ring arc, +/- buttons, preset highlight, Start, header dot, "locked" text): **red** `#790100`, with a lighter hover and a dark chip background (proposed values in section 7).
   - Oblivionis's own text and the "OBLIVIONIS //" label: stay blue, `#a9b9d0`.
   - App icon: unchanged.
   - No stored copy of the old palette. The change is final, not reversible.
7. **Remove the "no theme system" rule** from CLAUDE.md rule 7.

## 6. Message bank (this update)
- 13 emotion groups of 10 = 130 lines: Cold, Proud, Stern, Teasing, Bored, Tender-hidden, Encouraging, Melancholy, Theatrical, Mocking, Reflective, Hurt, Mask-on.
- **Crychic:** its own category of 10 lines. Oblivionis talks about her old band, CRYCHIC. It's a random prompt like any other group. Nothing is typed to trigger it.
- Random picks, no repeats until the bank runs out.
- Original lines in her voice. Never quote the show.

## 7. Open questions
1. Preset field name: "Minutes" for the old "Focus" field. Confirm, or give another name.
2. Ring: the track and the arc both become `#790100`, so the progress ring may not read well. Keep the track grey, or make the arc a different red?
3. Red shades: proposed hover `#9a1d1b` and chip background `#3a0503`. Confirm.
4. Count: the bank is 140 lines, plus 120 new special-interaction lines, about 260 in total. That's above the earlier 100 to 250 target. OK?
5. CLAUDE.md rule 4 still says never block Task Manager, cmd or PowerShell. It was removed from this file only. Remove it from CLAUDE.md too?

## 8. Known gaps (never run on Windows)
Guard task and relaunch, IFEO launch block, hosts blocking, reboot survival, Task Scheduler sealing, folder blocking, heartbeat takeover, delete lock, DPI and dark title bar, the self-update helper, and every change in the next update.
