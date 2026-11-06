#!/usr/bin/env bash
# Build a Model 1-only MAME plus the unidasm disassembler from source, into build/mame (git-ignored).
# Idempotent: clones once, checks out the pinned tag, rebuilds only what changed.
set -euo pipefail
TAG="${MAME_TAG:-mame0289}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIR="$ROOT/build/mame"
command -v brew >/dev/null || { echo "Homebrew required"; exit 1; }
for dep in sdl3 pkgconf; do
  brew list --formula "$dep" >/dev/null 2>&1 || { echo "missing: brew install $dep"; exit 1; }
done
mkdir -p "$ROOT/build"
if [ ! -d "$DIR/.git" ]; then
  git clone --depth 1 --branch "$TAG" https://github.com/mamedev/mame.git "$DIR"
fi
cd "$DIR"
git fetch --depth 1 origin "refs/tags/$TAG:refs/tags/$TAG" 2>/dev/null || true
git checkout -q "$TAG"
make -j"$(sysctl -n hw.ncpu)" SUBTARGET=model1 SOURCES=src/mame/sega/model1.cpp TOOLS=1 REGENIE=1 NOWERROR=1
ls -la "$DIR/model1" "$DIR/unidasm"
