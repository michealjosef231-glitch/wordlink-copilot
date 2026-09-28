# Local video fixture

The user's original MP4 is unchanged. `reference.mp4` is a local symlink to it and is ignored by Git. On another computer, put a recording here or pass its path to the commands; no full recording is uploaded with this project.

Extract reproducible raw frames into ignored local artifacts:

```sh
.venv/bin/python scripts/extract_frames.py fixtures/videos/reference.mp4
```

The four annotated board crops and their source crop rectangles are in `fixtures/boards/labels.json`. Original metadata: 130.433 seconds, 512 x 732 pixels, 30 fps.
