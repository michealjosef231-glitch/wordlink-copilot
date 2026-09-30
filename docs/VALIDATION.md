# Validation on this Mac

Verified locally on Intel macOS 12.7.6, Python 3.12.14. Commands and scripts below run against the source checkout. The original screenshot and recording baselines require neither hardware nor a runtime network service. Current live validation distinguishes native pixels, recording replay, and actual iPad input.

## Screenshot milestone

Four independently labeled crops from the supplied recording passed **64/64 letters and 64/64 dot values**, with no uncertainty warnings. Complete synthetic font alphabets and a generic shape metric provide recognition; no screenshot glyphs or test labels are fitted as templates.

The initial suite passed **66 tests** in 8.23 seconds. The current suite, including live controller, native-capture API, replay, and GUI helper regressions, passed **143 tests** with one opt-in native test skipped, in **10.39 seconds** on 2026-09-30. The opt-in real native color/orientation test then passed separately in 3.04 seconds:

```sh
.venv/bin/python -m pytest -q
```

Tests cover eight-neighbor search and tile reuse, vocabulary verdicts and common-word bands, recognition and dots, resized/rotated inputs, incomplete grids, settle detection, CLI output, and recovery from a bad recording frame. GUI helper tests are supplemented by the actual desktop smoke workflow.

## Pre-iPad audit

Two bounded agent reviews identified issues that were reproduced, fixed and reviewed again:

- Cache comparisons previously used the last capture, allowing several small shifts to accumulate without refreshing recognized path coordinates. The cache now compares against its recognized-frame signature. Regressions cover both cumulative geometry and glyph drift while retaining ranking reuse for an unchanged board.
- Some fractional replay starts returned the preceding frame because of clock subtraction precision. An elapsed-clock anchor and explicit first-frame bound fix opening and looping.
- Native capture now timestamps before pixel acquisition, so a slow native call cannot label older pixels fresh.
- Screenshot warnings now hold candidate words and show `REVIEW NEEDED` until an explicit manual solve. The real Tk workflow verifies both the held state and manual confirmation.
- Starting another live source, unreadable updates and stale expiry clear prior editable entries as well as suggestions. The launcher also checks that its staged entry point exists.

`scripts/smoke_cross_process.py` captures only a purpose-built fixture window in a **different process**, with standard Screen Recording consent. It matched all **64 letters and 64 dot values**, showed numbered paths, cleared suggestions and editable letters on a missing grid, recovered at a different source size, completed three stop/start cycles, and cleared results when minimized before recovering after restore and reconnect. The harness waits for WindowServer to apply the native minimize transition before asserting the disconnected state. No Tk callback errors occurred. Ready times were **2,335 ms** including dictionary loading, then **965, 977 and 1,004 ms** for changed boards. These checks exercise another application's pixel transport without claiming a QuickTime or physical iPad test.

Run the graphical checks separately from performance measurements:

```sh
PYTHONPATH=src .venv/bin/python scripts/smoke_ui.py
PYTHONPATH=src .venv/bin/python scripts/smoke_cross_process.py
WORDLINK_NATIVE_CAPTURE_TEST=1 .venv/bin/python -m pytest tests/test_macos_capture.py::test_native_own_tk_window_pixels_and_closed_window -q -s
```

The cross-process check requires normal Screen Recording permission. Test output stays in ignored `artifacts/cross_process_smoke.json`; it never captures the desktop, webcam or an arbitrary application.

The updated desktop runtime was restaged and all **477 code/data files** plus `launch.py` matched the checkout byte-for-byte. The real screenshot GUI smoke then passed using that staged Python, source and dictionary, with fixture paths supplied explicitly from the checkout. The Finder-launched app was restarted, its actual window captured and visually inspected, and its new startup log recorded Screen Recording preflight **true**. The desktop log was empty. This staged app was then used for the first physical iPad test below.

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

After the pre-iPad fixes, `scripts/validate_live_recording.py` completed the original 130.433 s recording in **130.56 s** of wall time through the same `LiveAssistant` controller used by the GUI. It recognized **13 distinct settled boards**, including all four independently labeled boards; their letters and dots matched **64/64 and 64/64**. It verified every ranked path's letters, neighboring steps, dot sum, and tile uniqueness, and asserted that non-ready updates carried no recommendations. The 271 ready updates had a median frame age of **203 ms** and maximum **615 ms**, below the configured 1.5 s freshness limit. Unique-board processing measured 193–606 ms, with the slowest result on the first board. The recording also produced 236 waiting, 198 reading, one review, and one ended update. These are measurements from this sample and Mac, not guarantees for a different iPad view or game version.

The previously over-sensitive pixel fingerprint was replaced with tolerant per-tile shape comparison and a semantic OCR check when tile ink changes. A genuinely changed letter or dot still clears old suggestions and waits for a quiet board. Selected-tile variation in the supplied compressed recording no longer prevents the labeled 90 s board from appearing. The real-time replay output is in ignored local `artifacts/live_recording_validation.json`.

## First physical iPad board test

On 2026-09-30, macOS USB enumeration detected an iPad (Apple product ID `0x12ab`) and QuickTime Player selected “iPad de pop’s” as its Camera source. The installed app had ordinary Screen Recording consent, with preflight **true**. Earlier, before that consent and a Finder-app restart, selecting another application's window correctly returned `CapturePermissionError`.

The initial QuickTime preview was black both in captured pixels and according to the user. After a fresh, unrecorded preview, the user reported that the picture was visible. This observed recovery does not establish why the initial preview was black.

CoreGraphics then captured the actual QuickTime window at **756 x 1080** pixels. Its board was independently labeled before comparison:

| Row | Letters | Dot counts |
| --- | --- | --- |
| 1 | P W R F | 3, 3, 1, 3 |
| 2 | I A S I | 2, 2, 1, 2 |
| 3 | T N G E | 1, 1, 3, 1 |
| 4 | A P E N | 2, 3, 1, 1 |

The Finder-launched installed app selected that QuickTime window through its GUI and reached **READY**. All **16 letters and 16 dot counts** matched, with no recognition warnings. It displayed **PAWING**, the one-based path **1 → 6 → 2 → 5 → 10 → 11**, and dot sum **14**. There were **310 ranked candidates**; their game acceptance remains unknown.

A separate live-controller check of the same physical source ran for **25.02 seconds**, producing **50 ready**, six waiting and two reading updates. Maximum frame age was **383.5 ms**, mean frame age **165.8 ms**, and maximum computation time **368.3 ms**. Sixteen compared pixel pairs differed, while the recognized board stayed unchanged. Every returned candidate path was legal. Only this **one board** was independently annotated; no real gameplay board transition, vocabulary acceptance or score gain was verified.

The USB connection later dropped. Both `system_profiler` and `ioreg` reported no iPad; QuickTime reported zero natural video dimensions and showed a black **350 x 240** preview. The installed app correctly showed **WAITING**, cleared recommendations and left editable letters empty. This verifies withholding recommendations when the source no longer contains a readable board. It does not establish successful device reconnection or a sustained physical session.

Device screenshots and diagnostics remain in ignored local `artifacts/`; no new private screenshots or fixtures were added to Git. The last verified physical state was disconnected. Pending: restore connectivity, verify sustained mirroring and reconnection, observe real gameplay board changes, annotate additional physical boards, and collect score/vocabulary evidence. Commonness and dot/gesture utility remain estimates; no recommendation is marked game-confirmed without evidence.
