# Word Link Copilot

Read PROJECT.md first. The user requests a lightweight offline Python desktop solver analyzing screenshots and the supplied 4x4 Word Link recording. This is the active project.

- Keep the agreed architecture: OpenCV and NumPy recognition, trie plus DFS, local dictionaries and ledger, Tkinter UI, pytest. No runtime model APIs, cloud, React, Electron, or premature C++.
- The lead agent coordinates bounded parallel tasks. Each task must have explicit owned paths; coordinate changes to shared contracts before editing another agent's files.
- Inspect the supplied recording and relevant fixtures before asserting game mechanics. Distinguish observations, external reports, implementation estimates, and measured results.
- Never report game score estimates as calibrated points. Confirmed/rejected dictionary entries require actual evidence; ordinary word lists are unknown to the game.
- Scope is offline recordings and screenshots. Live input is a future milestone; do not automate gameplay or interact with the recorded game.
- Add meaningful regression tests, run targeted checks, and report measured accuracy and timing with their fixture scope.
- Use src/wordlink/model.py for shared dataclasses. Keep implementation small and dependencies local to this project.
- Keep PROJECT.md, docs/TASKS.md, and docs/REFERENCE-VIDEO.md current so later chats can resume from files and Git.
- Commit one logical change after integration and verification. Do not alter unrelated workspace projects or the user's original video.
