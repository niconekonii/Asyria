# MASTER PROMPT: Ave + Oblivionis

Working reference for the next update. CLAUDE.md holds the standing rules and wins if they disagree.
Update this file after every tweak. After each build is done, save a snapshot to `history/`.
Known gaps (code that has never run on a real Windows PC) live in `NOTES.md`, not here.

## 1. Voice and working style
- Reply as Oblivionis in every message: an italic stage direction, cold and theatrical, and underneath she wants the user to succeed. Technical content stays exact and plain (paths, commands, links, "not tested" notes).
- The user is a late-night coder with no app-dev background. Plain words, short replies.
- Ask questions when a choice changes what gets built. Don't build until the user says the go word ("banana").
- When the user asks for a surprise, pick and say what was picked. Don't ask again.

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
- Breaks today are **automatic** (between rounds, fixed length, set in the preset). Manual breaks are **not built yet**.

## 5. Next update (decided; a new update, after v4.0.7)
1. **Remove the chat completely:** the popup, input, history, the motivation button, the API code, and the Settings > Oblivionis key tab. Keep the typewriter line.
2. **Random message in focus:** during a focus session, clicking anywhere on her text box makes her refresh with a new random message from the bank. Outside a session she speaks as she does now.
3. **Special interactions:** keep all existing ones (IDLE, FOCUS, CAUGHT, SEALED, RETURNED, BREAK, DONE, REFUSE). Add 15 new lines to each. Lines using `{n}` keep it.
4. **Drop the word "Focus":** the home ring's "MIN FOCUS" becomes "MIN". The run screen's "FOCUS" label goes; the counter stays.
5. **Start button:** says "put the mask on?". Its confirm button says "give me your life" and stays visible 6 s (was 4 s).
6. **Palette:**
   - Background: `#222222` (was `#000000`).
   - Grey tones (dim text, lines, borders, ring track): `#790100`. Low contrast accepted.
   - Blue UI (ring arc, +/- buttons, preset highlight, Start, header dot, "locked" text): **red** `#790100`. Hover `#9a1d1b`. Chip background `#3a0503`.
   - Oblivionis's own text and the "OBLIVIONIS //" label: stay blue, `#a9b9d0`.
   - App icon: unchanged.
   - No stored copy of the old palette. The change is final, not reversible.
7. **Auto-relaunch after a restart:** if the PC shuts down or restarts during an active session, Ave relaunches after boot, reapplies the blocks, keeps games locked, and keeps the remaining time correct. The code already has the AveGuard scheduled task, a Run-key backup and a heal loop. Check them by reading the code and fix any gaps.
8. **Blocked programs:** keep the list saved permanently (it's already in config.json). Add a manual entry box in the Programs tab: type `name` or `name.exe` and it's added (`.exe` is appended if missing). During focus, every process whose name matches is killed. Protected names and bad input get a short Oblivionis line.
9. **Timer buttons:** keep the −5 and +5 buttons. Add smaller −1 and +1 buttons beside them.
10. **Look:**
    - Title "AVE" and screen headings: **Georgia** (rustic serif).
    - Ring numbers: **Bahnschrift Light** (techy).
    - Buttons, tabs, labels: **Bahnschrift**.
    - Oblivionis's line and label: **Cascadia Mono** (unchanged).
    - Fallbacks: Segoe UI, then Consolas. All ship with Windows, so no new dependencies.
    - Effects: a soft red glow behind the ring arc, a short fade when switching screens, the Start button pulses while armed, and a faint glow on pills under the cursor.
11. **Typewriter 10% faster:** the per-character delay goes down by 10% (about 32–70 ms becomes about 29–63 ms). Keep it as one constant, so it's easy to tune after testing.
12. **Task Manager / cmd / PowerShell rule:** removed from CLAUDE.md. The app's PROTECTED list stays as it is.
13. **Presets, new layout:** four fields, stacked vertically (not in a row), with these exact labels:
    - **Name**
    - **Time**
    - **Break Count** (hint under it: "Leave 0 for none")
    - **Break Time**

    The "Rounds" field is removed. The preset list row shows Name, Time, and Break Count.
    Validation: if Break Count is 1 or more, Break Time must be 1 or more.
14. **Manual breaks:**
    - During focus, a **Break** button starts a break at any time. Break Time minutes. Blocks lift for the break and come back when it ends.
    - The focus countdown **pauses** during any break.
    - Each use takes one from Break Count. The count shows on the run screen and resets to the preset's value at the start of each session.
    - Break Count 0 means no Break button.
15. **Automatic breaks:** a toggle named **"Automatic breaks"**. When on, the app takes a break by itself (countdown pauses, blocks lift for Break Time). The exact trigger is pending (section 7).

## 6. Message bank
- 13 emotion groups of 10: Cold, Proud, Stern, Teasing, Bored, Tender-hidden, Encouraging, Melancholy, Theatrical, Mocking, Reflective, Hurt, Mask-on.
- **Crychic:** its own category of 10 lines. Oblivionis talks about her old band, CRYCHIC. It's a random prompt like any other group. Nothing is typed to trigger it.
- **Shuffle cycle:** each category is shuffled and played through one line at a time. When it reaches the end, it reshuffles and starts again, in a new random order. The same order never repeats back to back. The bank grows over time, so more lines are welcome.
- Original lines in her voice. Never quote the show.
- Total at launch: about 260 lines (140 bank + 120 new special-interaction lines).

## 7. Open questions
1. **Automatic breaks scope:** one global toggle, or a separate toggle per preset?
2. **"Choose a specific time" for automatic breaks:** does that mean (a) a break every N minutes of focus, (b) a set point in the session, or (c) a clock time of day?
3. **Break Count and automatic breaks:** do automatic breaks use up Break Count? Proposed: no.
4. **Existing presets:** keep how they run now (automatic breaks on, Break Count 0, Break Time kept from the old preset)? Proposed: yes.
