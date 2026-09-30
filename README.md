# Word Link Copilot

A local desktop live assistant for the 4 x 4 board in the supplied Word Link video. It automatically reads a selected mirror window, searches local word lists, and draws numbered paths. Screenshot review and recording replay are also available. It runs on this Intel macOS Monterey computer.

## Start

The project uses Python 3.12 and `uv`. From this folder:

```sh
uv sync --extra dev
'Word Link Copilot.app/Contents/Resources/stage-runtime.command'
.venv/bin/wordlink ui
```

After the one-time runtime staging command above, double-click **Word Link Copilot.app** to open the desktop assistant without a terminal. Staging copies only the local Python environment, code, and word data to Application Support because macOS blocks this Finder-launched app from reading its runtime inside Documents. Re-run staging after a source update. Select a mirrored game window and choose **Start live**. The app waits for a settled board, reads letters and dots, and updates suggested words and paths. Suggestions clear during movement, uncertainty, or lost input. Initial dictionary loading is slower than subsequent solves.

To connect an iPad, use a USB cable and QuickTime Player's **File > New Movie Recording**, then choose the iPad as the camera source. Select that QuickTime window in the assistant. See [live setup](docs/LIVE-SETUP.md) for permission and troubleshooting steps. You can choose **Replay recording** to exercise automatic reading without a device.

Choose **Open screenshot** to review a saved image. Edit a tile and choose **Solve edited board** to correct a read; editing pauses live capture. The interface shows alternatives, unknown game acceptance, and local timing. `Launch Word Link.command` remains an alternative launcher.

## Screenshot and recording commands

```sh
.venv/bin/wordlink screenshot fixtures/boards/frame_010.000.png \
  --json artifacts/first_board.json --overlay artifacts/best_path.png

.venv/bin/wordlink video fixtures/videos/reference.mp4 \
  --json artifacts/video_analysis.json --overlays artifacts/video_boards

.venv/bin/wordlink live --recording fixtures/videos/reference.mp4 --start 10

.venv/bin/wordlink windows
# Pass a listed window ID to open it directly:
.venv/bin/wordlink live --window-id 123

.venv/bin/python -m pytest -q
```

The screenshot command requires review when recognition raises a warning; `--allow-uncertain` permits an explicitly flagged offline inspection. Recording analysis samples consecutive frames and waits for an unchanged board region before recognizing. Highlighted/incomplete grids are skipped; sampled recognition is not proof that every animation or short-lived board was captured.

## What the results mean

Search retains all legal eight-neighbor paths without tile reuse. Recommendations favor recorded accepted words, then common words, then less common dictionary candidates. All ordinary dictionary words have **unknown game acceptance** until recorded in the ledger.

Dot-weight and gesture utility are ranking proxies. They are **not calibrated game points**. Exact scoring and accepted vocabulary need evidence from the game. See [validation](docs/VALIDATION.md) for measured fixture accuracy and timing; [tasks](docs/TASKS.md) records remaining work.

## Project context

Read [PROJECT.md](PROJECT.md) and [AGENTS.md](AGENTS.md) before a new coding task. [Recording evidence](docs/REFERENCE-VIDEO.md) separates observations from assumptions. [Data provenance](data/README.md) explains the offline word lists and templates. The recording and full extracted frames stay local; only board crops are fixtures.

There are no runtime AI services, API keys, cloud services, or automated game gestures. Capture reads only the selected window and retains no live screenshot history on disk. The iPad must first be mirrored through QuickTime or another working mirror app. Physical-device validation and exact game scoring are still separate tasks. GitHub connection status is recorded in `docs/TASKS.md`.
