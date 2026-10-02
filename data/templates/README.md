# Letter masks

The PNG files are small white-on-black A–Z and Qu glyph masks, normalized to 64×64 while preserving aspect ratio. The filename prefix before the first hyphen identifies the tile token; remaining text identifies its font and weight. No font binaries are included.

`scripts/build_templates.py` generates these 459 candidates (442 single letters and 17 Qu glyphs) from the installed macOS `SFNS.ttf`, `SFCompact.ttf`, `SFNSRounded.ttf`, `SFCompactRounded.ttf` (weights 500, 600, 700, 800), and `Arial Rounded Bold.ttf` (one static weight). Runtime uses these local bitmaps and does not need the original fonts or an OCR service.

Templates contain complete synthetic alphabets, not extracted evaluation glyphs. Expected fixture labels and filenames are not used to choose predictions. Initial rounded fonts were generated before evaluation; normal SF fonts were added after inspecting the glyph terminals. The matcher ranks all 26 letters plus the QU tile token using a combination of pixel overlap and symmetric stroke distance. Its score is not calibrated accuracy or game confidence.

Recognition is currently intended for complete, light-colored 4×4 boards in this recording's style. Highlighted/partially obscured boards may be rejected. Glyphs with a small margin over another letter generate warnings. Different fonts, compression, extremely small tiles, perspective, or occlusion require separate validation.

The generator also writes `glyphs.npz`, a packed copy of the normalized runtime masks. Runtime loads this single archive with pickle disabled; malformed bundles fall back to the PNG originals. A regression compares every bundled mask and token with the original PNG loader. Regenerate the bundle after editing template PNGs.
