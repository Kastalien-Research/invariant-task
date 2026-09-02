#!/usr/bin/env bash
# Build an isolated CODEX_HOME for task runs: auth plus model config only.
# No AGENTS.md, no MCP servers, no skills from the operator's real home.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/.codex-home"
cp "$HOME/.codex/auth.json" "$ROOT/.codex-home/"
grep -E '^(model|model_reasoning_effort|model_reasoning_summary) ' "$HOME/.codex/config.toml" > "$ROOT/.codex-home/config.toml"
echo "isolated CODEX_HOME at $ROOT/.codex-home:"; cat "$ROOT/.codex-home/config.toml"
