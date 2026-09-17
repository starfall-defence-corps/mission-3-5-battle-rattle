#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
TEST_DIR="$ROOT_DIR/molecule/default/tests"

GREEN='\033[32m'
RED='\033[31m'
CYAN='\033[36m'
BOLD='\033[1m'
DIM='\033[2m'
RESET='\033[0m'

echo ""
echo -e "  ${CYAN}${BOLD}=============================================="
echo -e "  ARIA — Automated Review & Intelligence Analyst"
echo -e "  MOS 5: Battle Rattle"
echo -e "  ==============================================${RESET}"

cd "$ROOT_DIR"

if [ -f "$ROOT_DIR/venv/bin/activate" ]; then
    source "$ROOT_DIR/venv/bin/activate"
fi

# Run the phased verification. conftest.py renders the ARIA report to stderr;
# discard pytest's stdout and its stderr noise, keeping only our ARIA lines.
ARIA_COLOR=1 python3 -m pytest "$TEST_DIR" -p no:cacheprovider --tb=no --no-header -q 2>&1 1>/dev/null \
    | grep -vE '^(assert |FAILED| *\+  where|  *\+  |[0-9]+ (passed|failed|skipped))' || true
EXIT_CODE=${PIPESTATUS[0]}

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}=============================================="
    echo -e "  ARIA: All objectives verified."
    echo -e "  MOS 5 status: COMPLETE"
    echo -e ""
    echo -e "  Lieutenant Commander, your battle rattle holds. Every runbook you"
    echo -e "  wrote worked against an indicator you had never seen —"
    echo -e "  because you parameterised, not memorised. The Hydra"
    echo -e "  changed shape and your response never blinked. These"
    echo -e "  are the tools you carry into every incident from here."
    echo -e "  The Starfall Defence Corps salutes you."
    echo -e "  ==============================================${RESET}"
else
    echo -e "  ${RED}${BOLD}=============================================="
    echo -e "  ARIA: Deficiencies detected."
    echo -e "  A runbook that only works on the indicator you"
    echo -e "  memorised is not a battle rattle. Review the findings"
    echo -e "  above and make your response work for ANY scenario."
    echo -e ""
    echo -e "  If every check was skipped, the range is not armed —"
    echo -e "  run 'make reset', then 'make test' again."
    echo -e "  ==============================================${RESET}"
fi

echo ""
exit $EXIT_CODE
