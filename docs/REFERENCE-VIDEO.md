# Recording evidence

Source: the user's `ScreenRecording_09-28-2026 20-18-10_1(1).mp4`. Duration 130.433 seconds; 512 x 732 pixels; 30 fps. The original is unchanged. `fixtures/videos/reference.mp4` is a local symlink excluded from Git.

| Time | Directly observed |
| --- | --- |
| 2 s | Loading logo; no board |
| 10 s | Stable `NOAI / AERN / GLUT / GNOV`, score 0; 16 light tiles, black letters, 1–4 dots |
| 20 s | The L tile is selected and changes color; ordinary white-tile recognition must reject this incomplete idle grid |
| 40 s | `EETE / NLYO / GNNE / GOOV`, displayed score 1,115 |
| 60 s | `LEON / EVNE / UTGY / WROE`, displayed score 1,577; a notification is outside the board |
| 90 s | `IESV / HSNE / UTGY / WROE`, displayed score 2,164 |
| 110 s | Selected T/A/R cells and `TAR` input text; selection includes a diagonal step |
| 120 s | `WOTN / OTAY / GRUE / ISHS`, displayed score 2,374; green `SH` text does not by itself establish accepted score gain |

The four annotated test crops are from 10, 40, 60, and 90 seconds. The lead independently read letters and dots from the full frames before comparing predictions. Generated alphabet masks come from locally installed fonts, not from those labels. Crops exclude unrelated interface and notifications.

After the 2026-09-30 pre-iPad audit, the live controller again replayed the entire recording at normal speed and matched all four labeled board identities. That verification tests capture/settling/recognition, without establishing additional scoring or dictionary facts. See `VALIDATION.md` for measured timings and scope.

Not established: the game's full accepted dictionary, exact scoring formula, the minimum accepted word length, whether green input text guarantees acceptance, or precise acceptance/replacement timing. Add observations with frame times and before/after evidence before changing these facts.

For score calibration, record a stable board, exact selected path, dot values, displayed score before submission and after the animation, and any active multiplier. Do not infer a scoring formula from cumulative scores alone.

## Separate physical iPad observation, 2026-09-30

This observation is from a live QuickTime iPad preview, not a frame from the supplied recording. One independently labeled board was `PWRF / IASI / TNGE / APEN`, with dot rows `3,3,1,3 / 2,2,1,2 / 1,1,3,1 / 2,3,1,1`. The installed app matched all letters and dots without warnings and displayed PAWING on tiles `1 → 6 → 2 → 5 → 10 → 11`, totaling 14 dots. No submission or game acceptance was verified, and no score formula can be inferred from that suggestion.

The physical connection later dropped and the app withheld recommendations. USB enumeration and the QuickTime picture subsequently returned; after manually reselecting that preview, the revised Finder-installed app again reached `READY` on the same known board in Play view. Twenty GUI images over ten seconds showed unchanged word and board/path regions for that static board. Sustained connection, automatic recovery during another drop, and actual gameplay board changes remain unverified. Private device screenshots and diagnostics are excluded from Git. Full measurements and the last observed device state are in `VALIDATION.md`.

## Live session continuation, 2026-10-01

On 2026-10-01, QuickTime had replaced the selected preview with window 493. The running installed app (window 349) was manually refreshed and switched to that new selected source. It reached READY and displayed COPY with path 10 → 6 → 11 → 12 in Play view. A later GUI capture showed the game results menu; Copilot correctly changed to CHECKING and cleared the word and path because no 4x4 board was present. It was left actively watching the selected preview, ready for the player to open another round. This verifies manual source reselection and a board-to-menu transition; it does not add an independently annotated full board, establish game acceptance or score calibration, or prove automatic recovery after window replacement. Private captures remain ignored local artifacts.

## Preview latency update, 2026-10-02

Separated latest-frame capture (30 fps target) from recognition (10 fps target), retained confidence and stale-result clearing, optimized duplicate grid validation, and refreshed Tk pixels without recreating word/path widgets. Actual selected-QuickTime preview measured 19.25 fps and 56.18 ms median capture-to-paint age on a non-board screen. Full suite: 156 passed, one opt-in native test skipped; native probe and stable/fluid GUI checks passed. See `docs/VALIDATION.md` (or `VALIDATION.md` from this directory) for scope and limitations. Total iPad transport delay and accepted-word/score effects remain unmeasured.

Final installed-state check: the updated runtime was staged and relaunched with the selected QuickTime preview. At that point the physical iPad had disappeared from USB enumeration and QuickTime reported natural video dimensions 0×0. The device must be reconnected/unlocked before another physical-board test. This interruption is separate from the measured preview improvement.
