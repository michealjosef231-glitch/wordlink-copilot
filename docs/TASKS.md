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
| Initial version verified | Milestone 5: desktop interface | Real Tk window smoke passed: screenshots, corrections, numbered paths, alternatives, timing, shutdown |
| Deferred | Milestone 6: live input | Needs a working mirror/capture source and separate latency/accuracy validation |
| Done | Local source control | Project repository initialized; verified implementation and documentation committed together |
| Done | GitHub upload and project write access | Published to [michealjosef231-glitch/wordlink-copilot](https://github.com/michealjosef231-glitch/wordlink-copilot). This Mac uses a dedicated read/write deploy key with repository-local SSH configuration; SSH authentication and `git push -u origin main` succeeded. The original video, local environment, and private key are excluded from Git. |

## Continue in a new chat

Read `PROJECT.md` and `AGENTS.md`. Choose one small task, state the owned paths, inspect relevant fixtures, run targeted tests, and update this table with measured results. The lead coordinates agents and integrates their work.

Suggested next engineering task: annotate additional held-out settled frames and compare their full letter/dot arrays against video output. Then collect explicit score changes and vocabulary verdicts from permitted recording/practice evidence. Keep the scoring profile uncalibrated until that evidence exists.

## Team work completed

The vision agent owned detection, glyph/dot recognition and template tests; the solver agent owned trie/DFS, ranking and vocabulary; the interface agent owned Tkinter and UI helpers. The lead integrated recording processing, CLI, fixtures, validation, source control and documentation. The superseded letter-circle prototype is archived outside the active workspace.
