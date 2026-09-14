#!/usr/bin/env bash
#
# Noctis machine bootstrap — everything that makes a machine able to run
# Noctis, as opposed to `make setup`, which installs this repo's own
# dependencies. The split is deliberate: setup.sh is about the checkout,
# this is about the machine (symlinks, launchd, config dirs, tooling).
#
# Idempotent. Safe to re-run. Nothing here silently overwrites: anything
# already correct is reported and skipped, anything present-but-different
# is reported and left alone unless --force is passed.
#
#   ./bootstrap/bootstrap.sh --dry-run    # report only, change nothing
#   ./bootstrap/bootstrap.sh              # do it
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DEFAULT="$(cd "$REPO_ROOT/.." && pwd)/second-brain"
VAULT_PATH="${VAULT_PATH:-$VAULT_DEFAULT}"
DRY_RUN=0
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
    -h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# ── output ────────────────────────────────────────────────────────────
BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
RED=$'\033[31m'; RESET=$'\033[0m'
ok()    { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
skip()  { printf "  ${DIM}·${RESET} ${DIM}%s${RESET}\n" "$1"; }
warn()  { printf "  ${YELLOW}!${RESET} %s\n" "$1"; }
fail()  { printf "  ${RED}✗${RESET} %s\n" "$1"; }
head_() { printf "\n${BOLD}%s${RESET}\n" "$1"; }
act()   { if [ "$DRY_RUN" = 1 ]; then printf "  ${DIM}would:${RESET} %s\n" "$1"; return 1; fi; return 0; }

PROBLEMS=0
note_problem() { PROBLEMS=$((PROBLEMS + 1)); }

[ "$DRY_RUN" = 1 ] && printf "${YELLOW}dry run — nothing will be changed${RESET}\n"
printf "${DIM}repo:  %s\nvault: %s${RESET}\n" "$REPO_ROOT" "$VAULT_PATH"

# ── 1. tooling ────────────────────────────────────────────────────────
head_ "1. Tooling"

check_tool() {  # name, why, install hint, required?
  local bin="$1" why="$2" hint="$3" required="$4"
  if command -v "$bin" >/dev/null 2>&1; then
    ok "$bin — $(("$bin" --version 2>&1 || echo '?') | head -1 | cut -c1-40)"
  elif [ "$required" = "required" ]; then
    fail "$bin missing — $why"; printf "      ${DIM}%s${RESET}\n" "$hint"; note_problem
  else
    warn "$bin missing — $why"; printf "      ${DIM}%s${RESET}\n" "$hint"
  fi
}

check_tool python3 "backend runtime"            "brew install python@3.13"                    required
check_tool node    "frontend build"             "brew install node"                           required
check_tool claude  "the engine — v2 drives it"  "npm i -g @anthropic-ai/claude-code"          required
check_tool git     "vault + repo version control" "xcode-select --install"                    required
check_tool cargo   "Tauri shell (Stage 2 item 4)" "curl https://sh.rustup.rs -sSf | sh"       optional
check_tool jq      "statusline script"          "brew install jq"                             optional

if python3 -c "import PyInstaller" 2>/dev/null; then
  ok "pyinstaller — python sidecar packaging"
else
  warn "pyinstaller missing — needed to bundle the Python sidecar (Stage 2 item 4)"
  printf "      ${DIM}pip install pyinstaller${RESET}\n"
fi

# FTS5 is not optional: all retrieval depends on it, and it is a compile-time
# flag in SQLite rather than something installable later.
if python3 - <<'PY' 2>/dev/null
import sqlite3, sys
c = sqlite3.connect(":memory:")
c.execute("CREATE VIRTUAL TABLE t USING fts5(b)")
c.execute("INSERT INTO t VALUES ('x')")
c.execute("SELECT bm25(t) FROM t WHERE t MATCH 'x'").fetchone()
PY
then ok "sqlite FTS5 + bm25() — retrieval backend"
else fail "sqlite lacks FTS5 — all retrieval depends on it"; note_problem
fi

# ── 2. vault ──────────────────────────────────────────────────────────
head_ "2. Vault"

if [ -d "$VAULT_PATH/.git" ]; then
  ok "vault present and version-controlled"
  if git -C "$VAULT_PATH" remote get-url origin >/dev/null 2>&1; then
    ok "vault has a remote — $(git -C "$VAULT_PATH" remote get-url origin)"
  else
    warn "vault has NO remote — it is the only copy on this machine"
    printf "      ${DIM}gh repo create second-brain --private --source=. --remote=origin --push${RESET}\n"
  fi
elif [ -d "$VAULT_PATH" ]; then
  fail "vault exists but is not a git repo — no history, no backup"; note_problem
else
  fail "vault not found at $VAULT_PATH (override with VAULT_PATH=…)"; note_problem
fi

# ── 3. the load-bearing symlink ───────────────────────────────────────
head_ "3. Symlinks"

# ~/.claude/CLAUDE.md is what makes every Claude Code session in every
# project read dev.md's methodology. Nothing else wires that up.
link_target="$VAULT_PATH/modes/dev/dev.md"
link_path="$HOME/.claude/CLAUDE.md"
if [ -L "$link_path" ] && [ "$(readlink "$link_path")" = "$link_target" ]; then
  skip "~/.claude/CLAUDE.md already points at modes/dev/dev.md"
elif [ -e "$link_path" ] && [ "$FORCE" != 1 ]; then
  warn "~/.claude/CLAUDE.md exists and differs — left alone (use --force to replace)"
  printf "      ${DIM}currently: %s${RESET}\n" "$(readlink "$link_path" 2>/dev/null || echo '(a real file)')"
elif act "symlink ~/.claude/CLAUDE.md -> $link_target"; then
  mkdir -p "$HOME/.claude"
  [ -e "$link_path" ] && mv "$link_path" "$link_path.bak-$(date +%Y%m%d%H%M%S)"
  ln -s "$link_target" "$link_path"
  ok "symlinked ~/.claude/CLAUDE.md"
fi

# ── 4. .env ───────────────────────────────────────────────────────────
head_ "4. Environment"

if [ -f "$REPO_ROOT/.env" ]; then
  skip ".env exists — not touched (it holds a real token)"
  grep -q "^NOCTIS_API_TOKEN=.\+" "$REPO_ROOT/.env" || { warn "NOCTIS_API_TOKEN is empty — every backend route will 401"; note_problem; }
elif act "create .env from .env.example, with a generated token"; then
  sed -e "s|^VAULT_PATH=.*|VAULT_PATH=$VAULT_PATH|" \
      -e "s|^NOCTIS_API_TOKEN=.*|NOCTIS_API_TOKEN=$(openssl rand -hex 32)|" \
      "$REPO_ROOT/.env.example" > "$REPO_ROOT/.env"
  chmod 600 "$REPO_ROOT/.env"
  ok ".env created with a generated token and the resolved vault path"
fi

# ── 5. launchd ────────────────────────────────────────────────────────
head_ "5. Scheduled jobs"

# launchd expands neither ~ nor environment variables in these paths, which
# is why the tracked file is a template and this step renders it.
tpl="$REPO_ROOT/launchd/com.noctis-os.nightshift.plist.template"
dst="$HOME/Library/LaunchAgents/com.noctis-os.nightshift.plist"
if [ ! -f "$tpl" ]; then
  fail "plist template missing at $tpl"; note_problem
else
  # The template carries a "do not load this directly" comment that stops
  # being true the moment it is rendered, so it is stripped rather than
  # shipped into ~/Library/LaunchAgents.
  rendered="$(sed "s|__REPO_ROOT__|$REPO_ROOT|g" "$tpl" | sed '/<!-- TEMPLATE\./,/-->/d')"
  if [ -f "$dst" ] && [ "$rendered" = "$(cat "$dst")" ]; then
    skip "nightshift plist already installed and current"
  elif act "render + install nightshift plist, then reload it"; then
    mkdir -p "$HOME/Library/LaunchAgents"
    printf '%s\n' "$rendered" > "$dst"
    plutil -lint "$dst" >/dev/null
    launchctl unload "$dst" 2>/dev/null || true
    launchctl load "$dst"
    ok "nightshift plist installed and loaded (nightly 03:00)"
  fi
fi

# ── summary ───────────────────────────────────────────────────────────
head_ "Summary"

if [ "$PROBLEMS" -gt 0 ]; then
  printf "\n${RED}%d problem(s) above need attention.${RESET}\n" "$PROBLEMS"
  exit 1
fi
printf "\n${GREEN}Machine is bootstrapped.${RESET}\n"
