#!/bin/zsh
set -e
cd "$(dirname "$0")"
python3 -m pip install --user -q -U "youtube-transcript-api>=1.2,<2" "yt-dlp>=2026.8.19" "faster-whisper>=1.2,<2"
python3 local_transcribe.py
