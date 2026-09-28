"""Extract reproducible screenshots from a local recording without changing it."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from wordlink.capture.video import read_frame, video_info
from wordlink.paths import ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--times", type=float, nargs="+", default=[2, 10, 20, 40, 60, 90, 110, 120])
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/frames")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    info = video_info(args.video)
    print(json.dumps({**asdict(info), "duration": info.duration}), flush=True)
    thumbs = []
    for seconds in args.times:
        frame = read_frame(args.video, seconds)
        destination = args.output / f"frame_{seconds:07.3f}.png"
        if not cv2.imwrite(str(destination), frame):
            raise ValueError(f"Cannot write {destination}")
        im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        im.thumbnail((300, 640))
        thumb = Image.new("RGB", (320, 680), "#17202b")
        thumb.paste(im, ((320 - im.width) // 2, 30))
        ImageDraw.Draw(thumb).text((10, 8), f"{seconds:.3f} seconds", fill="white")
        thumbs.append(thumb)
        print(str(destination), flush=True)
    sheet = Image.new("RGB", (320 * 4, 680 * ((len(thumbs) + 3) // 4)), "#17202b")
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % 4) * 320, (index // 4) * 680))
    sheet.save(args.output / "contact_sheet.jpg")


if __name__ == "__main__":
    main()
