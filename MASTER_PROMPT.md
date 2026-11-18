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
- Hard rules: no way out during a session; nothing stays blocked after a session; never block Task Manager, cmd or PowerShell; lightweight.

## 3. Release flow
- Repo `niconekonii/Asyria`. Default branch `claude/elegant-tesla-vn5sep`. Push there. Don't open PRs unless asked. Don't force-push. Don't push tags.
- Every push to the default branch builds a release `v4.0.<run_number>`. Docs-only commits use `[skip ci]`.
- Each change gets a DEVLOG entry at the top of `ave/DEVLOG.md`. After the build, replace `v4.0.?` with the real tag in a `[skip ci]` commit.
- Before pushing: `python3 -m pyflakes ave/ave.py`. For UI, run under xvfb with `/usr/bin/python3.12` and check screenshots.

## 4. Shipped
- v4.0.2 to v4.0.5: Ave, presets, blocking, typewriter, guard and escape routes, delete protection.
- v4.0.6: Oblivionis chat (hover popup, API key in settings). **Being removed in the next update.**
- v4.0.7: self-update from GitHub Releases (About tab, same-rights restart). Only builds from v4.0.7 on can self-update.

## 5. Next update (decided)
1. **Remove the chat completely:** the popup, input, history, the motivation button, the API code, and the Settings > Oblivionis key tab. Keep the typewriter line.
2. **Drop the word "Focus":** the home ring's "MIN FOCUS" becomes "MIN", and the run screen's "FOCUS" label goes. The number counter stays.
3. **Start button:** says "put the mask on?". The confirm button says "give me your life".
4. **Confirm button stays visible about 2 s longer:** the timeout goes from 4 s to 6 s.
5. **Message bank** (100 to 250 lines, written once and stored in the app): grouped in tens, each group with its emotion label. Random pick, no repeats until the bank runs out. No API needed. Proposed 15 groups of 10 (150 lines) are in section 7.
6. **Palette:**
   - Black background `#222222`
   - Grey tones `#790100`
   - Blue tones `#a9b9d0`
   - Store the current palette (`#000000`, greys, `#3d63e0` blue family) so the change can be reversed.

## 6. Open questions
- In focus, is there a separate button, or does clicking her line give the random message? (The Start button's "put the mask on?" is a different thing.)
- The preset fields still say "Focus". Rename them, or leave them?
- "CRYCHIC": with the chat gone, where is it typed? Match only the caps word, or any case?
- Grey tones in dark red on `#222222` will have low contrast. Should dim text stay readable, or accept the lower contrast?
- Reversibility: the old palette kept as a named constant to swap by hand, or a Settings toggle? A toggle conflicts with CLAUDE.md rule 7 ("No theme system").

## 7. Proposed message bank (15 groups of 10)
1. Cold: unimpressed, dismissive
2. Proud: quietly pleased
3. Stern: strict orders
4. Teasing: playful jabs
5. Bored: waiting for the user
6. Impatient: hurry up
7. Tender-hidden: warmth never said outright
8. Encouraging: motivation
9. Theatrical: dramatic warnings
10. Melancholy: the stage, oblivion, quiet
11. Mocking: distractions
12. Reflective: time and the act
13. Triumphant: after a break or a win
14. Hurt: "don't mention that around me" (her old band)
15. Mask-on: rituals for starting a session

## 8. Known gaps (never run on Windows)
Guard task and relaunch, IFEO launch block, hosts blocking, reboot survival, Task Scheduler sealing, folder blocking, heartbeat takeover, delete lock, DPI and dark title bar, the self-update helper, and every change in the next update.
