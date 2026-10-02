# Live assistant setup on this Mac

## Connect the iPad

1. Connect the unlocked iPad to the iMac with a USB data cable. Accept **Trust This Computer** on the iPad if asked.
2. Open **QuickTime Player** and choose **File > New Movie Recording**.
3. Open the options menu next to the recording button. Under **Camera**, choose the connected iPad.
4. Open Word Link on the iPad and keep the mirrored board visible. A recording file is unnecessary; the assistant reads the preview window.
5. Open **Word Link Copilot.app**, choose **Refresh**, select the QuickTime window, and choose **Start live**.

QuickTime discovers the USB device. The assistant discovers Mac windows and reads the selected window's pixels; it does not directly pair with the iPad. Apple's [Monterey QuickTime guide](https://support.apple.com/en-ie/guide/quicktime-player/qtp356b55534/10.5/mac/12.0) documents the connected-device source menu. Actual device availability depends on the USB connection, device trust, and QuickTime support.

On 2026-09-30, the installed assistant successfully read one physical iPad board through the “iPad de pop’s” QuickTime source, matching all 16 letters and dot counts. The USB connection later dropped and the assistant cleared its results. USB and picture then returned; manual reselection of the QuickTime window in the revised installed app reached `READY` on the same known board. At the last check, the app was left live. Sustained connection, automatic recovery across a new drop, and real gameplay board changes remain pending; see [validation](VALIDATION.md) for the observed evidence. Check the picture and selected window again when starting a later session.

## Allow screen capture

Use **Capture help** in the assistant to request macOS Screen Recording access and open its settings. On Monterey, the route is **System Preferences > Security & Privacy > Privacy > Screen Recording**. Enable the application macOS names in the request, then quit and reopen it if macOS requires a restart. Running from an editor or a terminal can give that host application the permission identity instead of the launcher.

Screen Recording access permits the operating system to supply another application's pixels. The assistant requests only the selected window. It does not need microphone access, an API key, or game-control permission. Apple's [Monterey screen recording guide](https://support.apple.com/en-qa/guide/mac-help/mchld6aa7d23/12.0/mac/12.0) explains the privacy setting.

## Reading behavior

The assistant reads boards at up to 10 frames per second, independently captures preview frames at up to 30 fps, and waits for three quiet board frames before recognizing. A confident read updates the word candidates and numbered path. A single worker avoids building a queue of old frames. A briefly highlighted tile on an otherwise unchanged board can keep the last verified result visible while the assistant checks it again; this does not refresh the result's timestamp. True motion, changed letters or dots, an incomplete board, uncertainty, or stale input clears recommendations. The interface independently clears a displayed result if fresh input stops arriving for 1.5 seconds.

**Start live** opens the compact **Play view** automatically, showing a large board with the current word path and three alternatives. Choose **Review / details** for editable tile entries and diagnostics. Opening a screenshot switches to Review view. Same-board live updates keep the selected alternative and board picture steady; a different board resets the best suggestion. The assistant never performs the game gesture for you.

Choose **Stop** to pause reading. Opening a screenshot or editing a letter/dot count also stops live capture so a new frame cannot overwrite the correction. Choose **Start live** again to start a fresh selected-window session.

Dictionary acceptance is unknown unless observed and recorded; dot-weight and gesture utility remain uncalibrated ranking estimates. This version assists the player with suggestions and paths. The player performs the gestures.

## Test without a connected device

Choose **Replay recording** and select the original supplied MP4. Playback is paced in real time; if processing takes longer, the source skips to the current frame instead of accumulating old frames. The same settle/recognize/search/display loop runs for replay and native window capture.

For a replay starting at a known board:

```sh
.venv/bin/wordlink live --recording fixtures/videos/reference.mp4 --start 10
```

Replay validates the application pipeline. A native capture test validates the pixel transport. Neither proves the physical iPad has been connected successfully; see [validation](VALIDATION.md) for precisely what was tested.

## Troubleshooting

- **iPad absent from QuickTime:** use a data-capable cable, unlock and trust the computer, and reconnect. The assistant's window list cannot repair a missing USB device.
- **QuickTime preview is black:** first check the picture in QuickTime itself. During the first device test the user also saw a black preview; a fresh, unrecorded preview subsequently showed the picture. Check that the iPad is unlocked, trusted and still connected, then reselect its Camera source or reopen the preview. The observed recovery did not identify a root cause. Copilot needs visible game pixels before it can read a board.
- **QuickTime absent from the picker:** keep its preview window open and visible, then choose Refresh.
- **Permission needed:** use Capture help, allow Screen Recording for the named app, restart it, and refresh the list.
- **Waiting for board:** show the entire 4x4 grid at a readable size. Selected cells, animation, an unfamiliar font, or an incomplete grid may prevent a reliable read.
- **Review needed:** stop reading, correct the displayed letters and dots, and solve the edited board. Confidence scores are estimates.
- **Disconnected:** reopen/unminimize the selected mirror window and start a new session. Closing the source window invalidates its selection.
- **Waiting after a USB drop:** restore the physical connection and confirm the iPad picture in QuickTime. A preview window can remain open while its device has disappeared, so Copilot may show Waiting rather than Disconnected. Choose Refresh and deliberately select the current mirror window; start a fresh session if it stopped. This manual recovery worked with the known board on 2026-09-30. Recommendations and editable letters should remain cleared until a readable board returns.
