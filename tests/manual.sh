#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
while IFS= read -r slug; do
  asset="$repository_root/docs/manual/$slug.webp"
  test -s "$asset"
  file "$asset" | grep -q 'Web/P'
  grep -q "docs/manual/$slug.webp" "$repository_root/README.md"
  grep -q "($slug.webp)" "$repository_root/docs/manual/README.md"
done < <(
  PYTHONPATH="$repository_root" python3 - <<'PY'
from docs.manual.generate_manual import CARDS
for card in CARDS:
    print(card["slug"])
PY
)

printf 'visual manual tests passed\n'
