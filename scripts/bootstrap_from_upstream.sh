#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REPO="https://github.com/fastapi/full-stack-fastapi-template.git"
UPSTREAM_SHA="cb740b656d7a0a6c5e12c7bf8e50343ec94ee9c7"
DEST="${1:-../_upstream_fastapi_template}"

git clone "$UPSTREAM_REPO" "$DEST"
git -C "$DEST" checkout "$UPSTREAM_SHA"

echo "Pinned upstream checked out at: $DEST"
echo "Comparison/reference only. Integrate changes intentionally via ADR/PR."
