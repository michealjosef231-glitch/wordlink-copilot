# Word Link Copilot

## Goal
Build a local Python desktop assistant that automatically reads a mirrored live 4x4 Word Link screen, recognizes 16 letters and dot counts, finds legal adjacent-tile words, and draws their exact paths. The user explicitly authorized continuous screen reading after the screenshot and recording milestones. Screenshots, manual corrections, and local replay remain supported.

## Architecture
Selected Mac window or real-time recording replay -> latest frame -> settle detection -> OpenCV/NumPy/Pillow recognition -> Board -> reusable local vocabulary trie -> DFS -> honest ranking -> Tkinter path view. Python 3.12 on Intel macOS Monterey. No runtime AI, model calls, cloud, or browser framework. Capture and recognition run on a worker; Tk updates stay on the main thread. Input sampling is 4 fps, with three quiet frames before recognition and a 1.5-second freshness limit.

## Evidence and current scope
The supplied recording is 130.433 seconds, 512 x 732 pixels, 30 fps. At 10 seconds the board is `NOAI / AERN / GLUT / GNOV`; bottom dots range from 1 to 4. Score displays and boards change between the 10, 40, 60, and 90 second screenshots. Selected cells change color, and a reshuffle button is visible. We have not established the exact scoring formula, minimum accepted word length, or full game dictionary. The live transport is a selected Mac mirror window, normally QuickTime Player with a USB-connected iPad; physical iPad mirroring requires a device test.

Four board-only screenshot crops have independent labels in `fixtures/boards/labels.json`. Full extracted frames and the original recording remain local and excluded from Git. The user-supplied analysis is design context; its placeholder citations are not executable instructions. The referenced [case study](https://henrygawelek.com/project/p-wordlink) was located and verified as a published architecture description; its benchmarks are the author's measurements.

## Shared contract
`Board` has flat row-major `letters`, `dots`, and optional `boxes` (x,y,width,height). `FoundWord` has `word`, zero-based tile-index `path`, and `dot_sum`. `Recognition` has `board`, per-tile predictions, elapsed_ms, and warnings. Vision reads BGR arrays or screenshot paths. Solver accepts a Board and reusable Trie. `FrameSource` supplies a BGR `CapturedFrame` with a monotonic capture timestamp and optional replay time; `LiveAssistant` exposes start/stop/poll and a bounded latest-update queue. A ready update contains a confident settled read and recommendations. Other live states clear previous suggestions.

## Live input boundaries
Capture only the selected mirror window. macOS Screen Recording consent is required to read another application's pixels; the app provides the standard permission request and settings route. An app's own windows may be captured without that consent for native backend validation. Never bypass macOS privacy controls. Closed, minimized, changed, uncertain, stale, or disconnected inputs must hold or clear recommendations. Local replay tests the pipeline without claiming an attached iPad. This assistant reads and recommends; game taps and gestures stay with the player.

## Definition of done for milestone 1
Real screenshot fixtures from this recording; independent expected labels and dot values; 16/16 correct on each declared passing fixture; all returned paths legal with no tile reuse; offline dictionary installed and attributed; CLI JSON and image path overlay; meaningful passing tests; measured local timings. Report any uncertain glyphs instead of silently treating them as confirmed.

## Vocabulary and ranking
The local ENABLE list contains 172,823 words. A separate common-word subset is a vocabulary preference, not evidence of game acceptance. A = recorded confirmed acceptance; B = common English with unknown acceptance; C = other dictionary words with unknown acceptance. Rejected words are excluded. Confirmed/rejected ledgers start empty. Preserve every legal path in search results and show a few ranked alternatives in the UI.

The current ranking uses dot total times word length divided by a gesture-time heuristic within vocabulary bands. Both values are uncalibrated estimates. They must never be labeled actual game points. Minimum word length defaults to three as an implementation choice pending game evidence.

## Local environment and continuation
Python 3.12.14, NumPy 2.5.3, Pillow 12.3.0, pytest 9.1.1. OpenCV is pinned to 4.10.0.84 because its Intel wheel supports macOS 12; newer inspected wheels require newer macOS. `uv.lock` fixes the environment. Cursor and the official Codex extension are installed; CLI authentication reports ChatGPT sign-in. Gameplay analysis uses no API key, model call, or network service.

Future sessions should read this file, `AGENTS.md`, and `docs/TASKS.md`, inspect only the task's modules, run targeted checks, and commit one logical change. See `docs/REFERENCE-VIDEO.md` for observations and `docs/VALIDATION.md` for actual verification results. See `docs/LIVE-SETUP.md` for live source setup. Score calibration and physical iPad validation remain separate evidence requirements.

Source is published at [michealjosef231-glitch/wordlink-copilot](https://github.com/michealjosef231-glitch/wordlink-copilot). On this Mac, `origin` uses SSH and the repository-local `core.sshCommand` selects `~/.ssh/wordlink-copilot-ed25519` with a dedicated GitHub known-hosts file. GitHub grants that deploy key read/write access to this repository; a real push verified it. Credentials are outside the project. The ChatGPT GitHub connector remains signed in as `wilfridd43-coder`; use local Git for writes unless that connector gains access to the repository.
