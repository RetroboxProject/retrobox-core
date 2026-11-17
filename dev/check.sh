#!/usr/bin/env bash
# Run the project's checks, the same way CI does.
#
#   dev/check.sh            everything
#   dev/check.sh tests      pytest (tests/)
#   dev/check.sh pylint     pylint: strict outside configgen, baseline inside it
#   dev/check.sh shell      bash -n and shellcheck on every shell script
#
# Needs the tools of dev/requirements-dev.txt (pytest, pylint) and shellcheck;
# the tests also need Retrobox's own Python dependencies (tools/deps/*.list or
# requirements.txt). Exits non-zero if any check fails.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd -P)"
cd "${ROOT}" || exit 1
PYTHON="${PYTHON:-python3}"
failed=()

# Every tracked shell script: *.sh, and files whose shebang names bash or sh.
shell_scripts() {
    local file
    while IFS= read -r -d '' file; do
        [[ -f "${file}" ]] || continue
        case "${file}" in
            lib/retrobox/_vendor/*) continue ;;
            *.sh) echo "${file}" ;;
            *) head -n1 "${file}" | grep -qE '^#!.*\b(ba)?sh\b' && echo "${file}" ;;
        esac
    done < <(git ls-files -z)
}

run_tests() {
    echo "== pytest"
    "${PYTHON}" -m pytest -q tests || failed+=(tests)
}

run_pylint() {
    echo "== pylint (strict: everything but configgen)"
    PYTHONPATH="${ROOT}/lib:${ROOT}/tests" "${PYTHON}" -m pylint --score=n \
        --ignore=_vendor,configgen lib/retrobox tests dev/pylint_baseline.py \
        || failed+=(pylint)
    echo "== pylint (configgen against dev/pylint-baseline.json)"
    "${PYTHON}" dev/pylint_baseline.py || failed+=(pylint-baseline)
}

run_shell() {
    local scripts=() script
    mapfile -t scripts < <(shell_scripts)
    echo "== bash -n (${#scripts[@]} scripts)"
    for script in "${scripts[@]}"; do
        bash -n "${script}" || failed+=("bash -n ${script}")
    done
    echo "== shellcheck"
    if ! command -v shellcheck >/dev/null 2>&1; then
        echo "shellcheck is not installed" >&2
        failed+=(shellcheck)
        return
    fi
    shellcheck --severity=warning --external-sources "${scripts[@]}" || failed+=(shellcheck)
}

case "${1:-all}" in
    tests) run_tests ;;
    pylint) run_pylint ;;
    shell) run_shell ;;
    all) run_tests; run_pylint; run_shell ;;
    -h | --help) sed -n '2,11p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown check: $1 (tests, pylint, shell or all)" >&2; exit 2 ;;
esac

if ((${#failed[@]})); then
    echo "FAILED: ${failed[*]}" >&2
    exit 1
fi
echo "All checks passed."
