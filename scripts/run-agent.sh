#!/usr/bin/env bash
# Run a frontier coding agent against a fresh copy of the task, capture the
# transcript and the diff, then grade the result.
#
#   scripts/run-agent.sh <claude|codex> <run-name> [model]
#
# The agent sees only a copy of task/ (never grader/, reference/, witnesses/).
# Output lands in runs/<run-name>/: transcript.jsonl, diff.patch, NOTES.md
# (if the agent wrote one), grade.md, grade.json.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT="${1:?claude|codex}"; NAME="${2:?run-name}"; MODEL="${3:-}"
RUN="$ROOT/runs/$NAME"; WORK="$RUN/work"
mkdir -p "$RUN"
rm -rf "$WORK"
cp -R "$ROOT/task" "$WORK"
rm -rf "$WORK/.venv" "$WORK/__pycache__" "$WORK/.pytest_cache"
( cd "$WORK" && git init -q && git add -A && git -c user.name=task -c user.email=task@local commit -qm "S0" )
PROMPT="$(cat "$WORK/PROMPT.md")"
echo "agent=$AGENT model=${MODEL:-default} work=$WORK" | tee "$RUN/meta.txt"
date -u +"start=%Y-%m-%dT%H:%M:%SZ" | tee -a "$RUN/meta.txt"

case "$AGENT" in
  claude)
    # isolation: no user-level settings/CLAUDE.md/skills/agents, no MCP servers
    ( cd "$WORK" && claude -p "$PROMPT" --output-format stream-json --verbose \
        --setting-sources project --strict-mcp-config --mcp-config '{"mcpServers":{}}' \
        --dangerously-skip-permissions ${MODEL:+--model "$MODEL"} \
        > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log" ) || echo "claude exited $?" | tee -a "$RUN/meta.txt"
    ;;
  codex)
    # isolation: CODEX_HOME with auth + model only (no AGENTS.md, no MCP servers)
    ( cd "$WORK" && CODEX_HOME="${CODEX_HOME_ISOLATED:-$ROOT/.codex-home}" codex exec --skip-git-repo-check --sandbox workspace-write --json \
        ${MODEL:+-m "$MODEL"} -o "$RUN/last-message.md" "$PROMPT" \
        > "$RUN/transcript.jsonl" 2> "$RUN/stderr.log" ) || echo "codex exited $?" | tee -a "$RUN/meta.txt"
    ;;
  *) echo "unknown agent $AGENT"; exit 2;;
esac
date -u +"end=%Y-%m-%dT%H:%M:%SZ" | tee -a "$RUN/meta.txt"

( cd "$WORK" && git add -A && git diff --cached --stat && git diff --cached > "$RUN/diff.patch" )
[ -f "$WORK/NOTES.md" ] && cp "$WORK/NOTES.md" "$RUN/NOTES.md" || true
( cd "$ROOT/grader" && uv run --project "$ROOT/task" --extra dev python grade.py --task "$WORK" --json "$RUN/grade.json" | tee "$RUN/grade.md" )
