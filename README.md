# Word Link Copilot

An offline Python screenshot and recording analyzer for the 4 x 4 board in the supplied Word Link video. It reads letters and dots, searches local word lists, and draws numbered paths. It runs on this Intel macOS Monterey computer.

## Start

The project uses Python 3.12 and `uv`. From this folder:

```sh
uv sync --extra dev
.venv/bin/wordlink ui fixtures/boards/frame_010.000.png
```

For the desktop app, choose **Open screenshot**, review the 16 detected letters and dots, and select a suggested word to see its path. Edit a tile and choose **Solve edited board** to correct a read. The interface shows a few alternatives and local timing. Initial dictionary loading is slower than subsequent board solves.

On this Mac you can also double-click `Launch Word Link.command` to open the app with the first recorded board.

## Screenshot and recording commands

```sh
.venv/bin/wordlink screenshot fixtures/boards/frame_010.000.png \
  --json artifacts/first_board.json --overlay artifacts/best_path.png

.venv/bin/wordlink video fixtures/videos/reference.mp4 \
  --json artifacts/video_analysis.json --overlays artifacts/video_boards

.venv/bin/python -m pytest -q
```

The screenshot command requires review when recognition raises a warning; `--allow-uncertain` permits an explicitly flagged offline inspection. Recording analysis samples consecutive frames and waits for an unchanged board region before recognizing. Highlighted/incomplete grids are skipped; sampled recognition is not proof that every animation or short-lived board was captured.

## What the results mean

Search retains all legal eight-neighbor paths without tile reuse. Recommendations favor recorded accepted words, then common words, then less common dictionary candidates. All ordinary dictionary words have **unknown game acceptance** until recorded in the ledger.

Dot-weight and gesture utility are ranking proxies. They are **not calibrated game points**. Exact scoring and accepted vocabulary need evidence from the game. See [validation](docs/VALIDATION.md) for measured fixture accuracy and timing; [tasks](docs/TASKS.md) records remaining work.

## Project context

Read [PROJECT.md](PROJECT.md) and [AGENTS.md](AGENTS.md) before a new coding task. [Recording evidence](docs/REFERENCE-VIDEO.md) separates observations from assumptions. [Data provenance](data/README.md) explains the offline word lists and templates. The recording and full extracted frames stay local; only board crops are fixtures.

There are no runtime AI services, API keys, cloud services, or gameplay automation. This application currently analyzes screenshots and recordings. Live input is a future milestone. GitHub connection status is recorded in `docs/TASKS.md`.
