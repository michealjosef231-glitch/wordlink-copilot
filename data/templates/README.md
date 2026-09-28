# Letter masks

The PNG files are small white-on-black A–Z glyph masks, normalized to 64×64 while preserving aspect ratio. The first filename character identifies the letter; remaining text identifies its font and weight. No font binaries are included.

`scripts/build_templates.py` generates these 442 candidates from the installed macOS `SFNS.ttf`, `SFCompact.ttf`, `SFNSRounded.ttf`, `SFCompactRounded.ttf` (weights 500, 600, 700, 800), and `Arial Rounded Bold.ttf` (one static weight). Runtime uses these local bitmaps and does not need the original fonts or an OCR service.

Templates contain complete synthetic alphabets, not extracted evaluation glyphs. Expected fixture labels and filenames are not used to choose predictions. Initial rounded fonts were generated before evaluation; normal SF fonts were added after inspecting the glyph terminals. The matcher ranks all 26 letters using a combination of pixel overlap and symmetric stroke distance. Its score is not calibrated accuracy or game confidence.

Recognition is currently intended for complete, light-colored 4×4 boards in this recording's style. Highlighted/partially obscured boards may be rejected. Glyphs with a small margin over another letter generate warnings. Different fonts, compression, extremely small tiles, perspective, or occlusion require separate validation.
