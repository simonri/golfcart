#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Exporting OpenAPI spec…"
(
  cd "$ROOT/packages/api"
  uv run python export_openapi.py
)

echo "Generating TypeScript client…"
(
  cd "$ROOT/packages/client"
  pnpm generate-openapi
)

echo "Done."
