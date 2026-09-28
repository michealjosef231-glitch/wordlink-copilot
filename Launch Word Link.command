#!/bin/zsh
cd -- "${0:A:h}"
exec .venv/bin/python -m wordlink.cli ui fixtures/boards/frame_010.000.png
