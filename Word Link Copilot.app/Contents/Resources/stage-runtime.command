#!/bin/zsh
set -e
umask 077
project_dir="${0:A:h:h:h:h}"
runtime_dir="$HOME/Library/Application Support/WordLinkCopilot"
if [[ ! -x "$project_dir/.venv/bin/python" ]]; then
    print -u2 -- "Create the project's local Python environment before staging the desktop app."
    exit 1
fi
mkdir -p "$runtime_dir/.venv" "$runtime_dir/src" "$runtime_dir/data"
/usr/bin/rsync -a --delete "$project_dir/.venv/" "$runtime_dir/.venv/"
/usr/bin/rsync -a --delete --exclude '__pycache__/' "$project_dir/src/" "$runtime_dir/src/"
/usr/bin/rsync -a --delete "$project_dir/data/" "$runtime_dir/data/"
/bin/cp "$project_dir/Word Link Copilot.app/Contents/Resources/launch.py" "$runtime_dir/launch.py"
print -r -- "Word Link Copilot desktop runtime staged in Application Support."
