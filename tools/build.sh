#!/usr/bin/env bash
# Full pipeline: voice-over → sound cues → soundtrack → video.
# Usage: tools/build.sh <path to kokoro-multi-lang-v1_1>
set -euo pipefail
cd "$(dirname "$0")/.."
MODEL=${1:?usage: tools/build.sh <kokoro-multi-lang-v1_1 dir>}
python3 tools/cutout.py
python3 tools/tts.py --model "$MODEL"
node tools/render.mjs --cues
python3 tools/mix.py
node tools/render.mjs
