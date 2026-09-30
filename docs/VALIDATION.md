# Validation on this Mac

Verified locally on Intel macOS 12.7.6, Python 3.12.14. Commands and scripts below run against the source checkout. The original screenshot and recording baselines require neither hardware nor a runtime network service. Current live validation distinguishes native pixels, recording replay, and actual iPad input.

## Screenshot milestone

Four independently labeled crops from the supplied recording passed **64/64 letters and 64/64 dot values**, with no uncertainty warnings. Complete synthetic font alphabets and a generic shape metric provide recognition; no screenshot glyphs or test labels are fitted as templates.

The initial suite passed **66 tests** in 8.23 seconds. The current suite, including live controller, native-capture API, replay, and GUI helper regressions, passed **136 tests** with one opt-in native test skipped, in 61.44 seconds while the graphical smoke ran concurrently:

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

## Live selected-window validation

`scripts/smoke_live.py` displayed each labeled board in a real Tk validation window. The application captured only that window through CoreGraphics, recognized letters and dots, and showed a numbered word path. Each board transition cleared the prior word/path before showing the next. Closing the mirror window produced `disconnected` and cleared recommendations. The source ended state likewise cleared suggestions. The real Tk callback queue remained free of errors through these checks.

| Native validation board | Letters + dots | New ready result after display |
| --- | --- | ---: |
| 10 s labeled crop | 16/16 + 16/16 | 5,287 ms including first dictionary load |
| 40 s labeled crop | 16/16 + 16/16 | 1,181 ms |
| 60 s labeled crop | 16/16 + 16/16 | 1,103 ms |
| 90 s labeled crop | 16/16 + 16/16 | 1,154 ms |

The native source also passed a real color/orientation check on a 208 x 220 own-process Tk window: BGR red `[0, 0, 255]`, BGR blue `[255, 0, 0]`, upright rows/columns, about 12 ms for that small capture. macOS allows an application to capture its own window while global Screen Recording preflight is false; this proves the pixel path, not permission or image quality for QuickTime.

The latest native GUI smoke also passed recording replay from a known board, replay end, manual-edit pause, and shutdown with zero Tk callback errors. It verified that refreshing the picker does not silently select another app. The real screenshot UI was visually inspected after correcting a macOS button-contrast issue.

## Complete normal-speed recording replay

`scripts/validate_live_recording.py` completed the original 130.433 s recording in **130.67 s** of wall time through the same `LiveAssistant` controller used by the GUI. It recognized **13 distinct settled boards**, including all four independently labeled boards; their letters and dots matched **64/64 and 64/64**. It verified every ranked path's letters, dot sum, and tile uniqueness, and asserted that non-ready updates carried no recommendations. The 248 ready updates had a median frame age of **202 ms** and maximum **1,015 ms**, below the configured 1.5 s freshness limit. Unique-board processing measured 198–1,009 ms, with the slowest result on the first board. The recording also produced 244 waiting, 193 reading, six review, and one ended update. These are measurements from this sample and Mac, not guarantees for a different iPad view or game version.

The previously over-sensitive pixel fingerprint was replaced with tolerant per-tile shape comparison and a semantic OCR check when tile ink changes. A genuinely changed letter or dot still clears old suggestions and waits for a quiet board. Selected-tile variation in the supplied compressed recording no longer prevents the labeled 90 s board from appearing. The real-time replay output is in ignored local `artifacts/live_recording_validation.json`.

## Physical iPad boundary

On 2026-09-30, macOS USB enumeration briefly detected an iPad (Apple product ID `0x12ab`). QuickTime Player's Camera menu listed and selected “iPad de pop’s”; its preview became portrait at 1200 x 1718 native video dimensions, with no recording started. Initially Screen Recording preflight was **false** for the app, its standard permission request returned false, and selecting QuickTime correctly returned `CapturePermissionError`. After standard macOS consent and a Finder-app restart, the app's own preflight logged **true**. A later USB check showed **no connected iPad** and the QuickTime preview had shrunk. No real iPad pixels or game board have yet been validated through Copilot.

Still unresolved: actual game score calibration, accepted/rejected vocabulary evidence, fonts or recordings beyond this sample, and real iPad input verification. Commonness and dot/gesture utility are estimates; no recommendation is falsely marked game-confirmed.
