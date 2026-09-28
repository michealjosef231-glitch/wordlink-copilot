# Validation on this Mac

Verified locally on Intel macOS 12.7.6, Python 3.12.14. Commands and scripts below run against the source checkout; no hardware connection or runtime network is required.

## Screenshot milestone

Four independently labeled crops from the supplied recording passed **64/64 letters and 64/64 dot values**, with no uncertainty warnings. Complete synthetic font alphabets and a generic shape metric provide recognition; no screenshot glyphs or test labels are fitted as templates.

The integrated suite passed **66 tests** in 8.23 seconds:

```sh
.venv/bin/python -m pytest -q
```

Tests cover eight-neighbor search and tile reuse, vocabulary verdicts and common-word bands, recognition and dots, resized/rotated inputs, incomplete grids, settle detection, CLI output, and recovery from a bad recording frame. GUI helper tests are supplemented by the actual desktop smoke workflow.

## Measured performance

`scripts/validate.py` loads the 172,823-word dictionary once, then measures five warm end-to-end repetitions per fixture. The timings include screenshot loading, recognition, search, and ranking, without display rendering or live transport.

| Recording frame | Letters / dots | Words / legal paths | Median complete pipeline |
| --- | --- | --- | --- |
| 10 s | 16/16 + 16/16 | 172 / 203 | 154.7 ms |
| 40 s | 16/16 + 16/16 | 59 / 120 | 144.7 ms |
| 60 s | 16/16 + 16/16 | 75 / 112 | 153.8 ms |
| 90 s | 16/16 + 16/16 | 127 / 165 | 152.4 ms |

All **600** returned paths were checked for bounds, correct letters, neighboring steps, no tile reuse, dot totals, and dictionary membership. Separate solver benchmarks used 25 warm repetitions per board and verified deterministic output. Word search was about 0.8–2.8 ms; ranking about 0.8–2.7 ms in those runs.

Initial dictionary construction took about 1.6 seconds in the end-to-end run; the first recognition call took 325 ms. Cold startup can be slower, especially during macOS's first native-library checks. Warm timings are measurements on these fixtures, not a guarantee across fonts, resolutions, or live streams. The aspirational 100 ms compute target has not been reached.

## Recording processing

The complete 130.433-second recording was processed at 4 sampled frames/second. The initial run examined **522 frames**, emitted **13 unique settled boards**, and skipped incomplete/highlighted grids. It also deduplicated 40 repeated settled reads. None of its 13 reads raised recognition warnings. End-to-end batch processing took 101.6 seconds, including video seeking and decoding.

Only the four annotated crops establish independently measured recognition accuracy; the other recording reads remain unverified. Sampling can miss brief board states. This is an initial video analyzer, not proof that every stable state was captured.

## Desktop and artifacts

`scripts/smoke_ui.py` exercised the real Tk window, asynchronous screenshot work, numbered paths, candidate selection, full/cropped view, invalid corrections, manual solving, a second screenshot, and shutdown. It passed without Tk callback errors. The first-board JSON and overlay were produced through the actual CLI; the overlay was visually inspected.

Local artifacts are ignored by Git: `artifacts/validation.json`, `solver_benchmark.json`, `ui_smoke.json`, `first_board.json`, `best_path.png`, `video_analysis.json`, and `video_boards/`.

Still unresolved: actual game score calibration, accepted/rejected vocabulary evidence, fonts or recordings beyond this sample, and live input. Commonness and dot/gesture utility are estimates; no recommendation is falsely marked game-confirmed.
