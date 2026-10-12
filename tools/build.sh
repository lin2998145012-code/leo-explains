#!/usr/bin/env bash
# Full pipeline: voice-over → sound cues → soundtrack → portrait + landscape videos.
#
# Usage: tools/build.sh <models dir>
#   With voice/ref.wav + voice/ref.txt present, Leo speaks in the cloned voice
#   (needs sherpa-onnx-zipvoice-distill-int8-zh-en-emilia/, vocos_24khz.onnx and
#   sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/ in <models dir>);
#   otherwise the stock Kokoro voice (kokoro-multi-lang-v1_1/).
set -euo pipefail
cd "$(dirname "$0")/.."
M=${1:?usage: tools/build.sh <models dir>}
python3 tools/cutout.py
if [[ -f voice/ref.wav && -f voice/ref.txt ]]; then
  python3 tools/tts.py --model "$M/sherpa-onnx-zipvoice-distill-int8-zh-en-emilia" \
    --vocoder "$M/vocos_24khz.onnx" --ref voice/ref.wav --ref-text voice/ref.txt \
    --asr "$M/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
else
  python3 tools/tts.py --model "$M/kokoro-multi-lang-v1_1"
fi
node tools/render.mjs --cues
python3 tools/mix.py
node tools/render.mjs --layout portrait
node tools/render.mjs --layout landscape
