#!/bin/bash
#
# Local Bonsai Image 4B (ternary-mlx) wrapper for the blog agent.
# Used as a local fallback for blog cover, body, Threads, IG cards, etc.
#
# Usage:
#   ./scripts/generate_bonsai.sh "masterful hand-drawn ink illustration, ... full prompt" "output/my-image.png" [seed]
#
# Uses the official Bonsai Image Demo wrapper, which carries the Prism-patched
# runtime needed for the ternary MLX model.
# The agent must put the full style prefix + scene description in the first argument.

set -e

cd "$(dirname "$0")/.."

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 \"PROMPT\" \"output/path.png\" [SEED]"
  echo "Example: $0 \"masterful hand-drawn ... a serene bonsai\" \"output/test-cover.png\" 42"
  exit 1
fi

PROMPT="$1"
OUT_PATH="$2"
SEED="${3:-42}"
SIZE="${BONSAI_SIZE:-1024x1024}"

DEMO_DIR="${BONSAI_DEMO_DIR:-$HOME/.openclaw/Bonsai-Image-Demo}"
DEMO_GENERATE="$DEMO_DIR/scripts/generate.sh"

if [ ! -x "$DEMO_GENERATE" ]; then
  echo "ERROR: Bonsai demo generator not found or not executable: $DEMO_GENERATE" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT_PATH")"
case "$OUT_PATH" in
  /*) ABS_OUT="$OUT_PATH" ;;
  *) ABS_OUT="$PWD/$OUT_PATH" ;;
esac

echo "Generating with Bonsai Image 4B via Bonsai-Image-Demo..."
"$DEMO_GENERATE" \
  --model ternary-mlx \
  --prompt "$PROMPT" \
  --size "$SIZE" \
  --steps 4 \
  --seed "$SEED" \
  --output "$ABS_OUT"

echo "Done: $OUT_PATH"
ls -l "$OUT_PATH"
