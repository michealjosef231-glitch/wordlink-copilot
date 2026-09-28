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

Not established: the game's full accepted dictionary, exact scoring formula, the minimum accepted word length, whether green input text guarantees acceptance, or precise acceptance/replacement timing. Add observations with frame times and before/after evidence before changing these facts.

For score calibration, record a stable board, exact selected path, dot values, displayed score before submission and after the animation, and any active multiplier. Do not infer a scoring formula from cumulative scores alone.
