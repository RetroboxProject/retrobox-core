#!/usr/bin/env bash
# Apply the retrobox-core cleanup on top of commit 8f9577d (run from the repo root).
#   bash apply-cleanup.sh            # stages everything, does not commit
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)"
git rev-parse --show-toplevel >/dev/null
git apply --index --whitespace=nowarn "${HERE}/retrobox-core-cleanup.patch"
xargs -a "${HERE}/deleted.txt" -d '\n' git rm -q --ignore-unmatch --
echo "Cleanup staged: $(git diff --cached --shortstat)"
