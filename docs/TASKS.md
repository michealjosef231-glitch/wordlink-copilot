# Project tasks

| Status | Task | Evidence / next dependency |
| --- | --- | --- |
| Done | Create the Python project and local environment | `pyproject.toml`, `uv.lock`; Monterey-compatible OpenCV wheel |
| Done | Record project instructions and video evidence | `PROJECT.md`, `AGENTS.md`, reference notes, four independently annotated board crops |
| Done | Milestone 1: screenshot solver | 16/16 letters and dots on all four fixtures; legal paths, CLI JSON and inspected numbered overlay |
| Done | Search and ranking foundation | All 600 fixture paths legal; deterministic trie/DFS; reusable local dictionary |
| Initial version verified | Milestone 2: video solver | Whole recording examined; 13 unique settled reads. Other reads and short-lived states need further accuracy validation |
| Foundation done | Milestone 3: vocabulary engine | ENABLE and common-word subset, evidence-ledger policy, A/B/C bands. Confirmed/rejected ledgers remain empty |
| Waiting for observations | Milestone 4: score model | Proxy ranking exists; exact scoring requires before/after score observations and selected paths |
| Initial version verified | Milestone 5: desktop interface | Real Tk window smokes passed: screenshots, corrections, numbered paths, alternatives, compact Play view, Review / details, and shutdown |
| Done; hardware test remains separate | Pre-iPad quality audit | Current suite: 147 passed, one opt-in native test skipped. Native color/orientation and separate-process mirror smokes passed; the latter matched 64 letters/dots and exercised resize, missing-grid clearing, restarts, minimize/restore/reconnect, and zero Tk errors. Cache drift, replay timing, stale timestamps, uncertainty handling and stale editable entries have regressions. |
| Done for prototype | Stable live display | Same-board ink recheck holds the last still-fresh result without flashing READING/blank; true changes and stale/uncertain input clear it. Real Tk smoke at 1240 x 760 passed 20 ready heartbeats without replacing the photo, canvas items, alternative buttons or entry values; it retained the chosen alternative, ignored up to 3 px geometry jitter, repainted after a 4 px cumulative shift, and verified waiting/expiry clearing and zero callback errors. |
| Revised app READY on one physical board; transitions pending | Milestone 6: live input | Native capture and earlier 130.56 s recording replay passed. The installed Finder app read one actual QuickTime iPad board with 16/16 letters and dots, no warnings and a PAWING path; a separate 25.02 s check produced 50 ready updates with maximum age 383.5 ms. USB later dropped and the app correctly cleared recommendations. After USB and picture returned, the revised installed app selected QuickTime window 292 and again reached READY on the known board in Play view. Twenty GUI images over ten seconds showed unchanged word and board/path regions. Sustained connection, automatic recovery and real gameplay transitions remain unverified. |
| Done | Local source control | Project repository initialized; verified implementation and documentation committed together |
| Done | GitHub upload and project write access | Published to [michealjosef231-glitch/wordlink-copilot](https://github.com/michealjosef231-glitch/wordlink-copilot). This Mac uses a dedicated read/write deploy key with repository-local SSH configuration; SSH authentication and `git push -u origin main` succeeded. The original video, local environment, and private key are excluded from Git. |

## Continue in a new chat

Read `PROJECT.md` and `AGENTS.md`. Choose one small task, state the owned paths, inspect relevant fixtures, run targeted tests, and update this table with measured results. The lead coordinates agents and integrates their work.

At this update, the revised installed app was left live and showing the known board. Next, observe a real gameplay board change and independently annotate more boards. Verify sustained physical mirroring and what the app does during and after another disconnect; manual reselection after the prior USB drop succeeded, but automatic recovery has not been tested. Collect explicit score changes and vocabulary verdicts from permitted recording/practice evidence. Keep the scoring profile uncalibrated until that evidence exists.

## Team work completed

The vision agent owned detection, glyph/dot recognition and template tests; the solver agent owned trie/DFS, ranking and vocabulary; the interface agent owned Tkinter and UI helpers. Later agents implemented native selected-window capture, the live controller, and GUI controls while the lead integrated replay, CLI, fixtures, validation, source control and documentation. The superseded letter-circle prototype is archived outside the active workspace.

## Live session continuation, 2026-10-01

On 2026-10-01, QuickTime had replaced the selected preview with window 493. The running installed app (window 349) was manually refreshed and switched to that new selected source. It reached READY and displayed COPY with path 10 → 6 → 11 → 12 in Play view. A later GUI capture showed the game results menu; Copilot correctly changed to CHECKING and cleared the word and path because no 4x4 board was present. It was left actively watching the selected preview, ready for the player to open another round. This verifies manual source reselection and a board-to-menu transition; it does not add an independently annotated full board, establish game acceptance or score calibration, or prove automatic recovery after window replacement. Private captures remain ignored local artifacts.
