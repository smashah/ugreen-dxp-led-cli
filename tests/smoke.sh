#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
temporary="$(mktemp -d "${TMPDIR:-/tmp}/ugreen-led-test.XXXXXX")"
trap 'rm -rf "$temporary"' EXIT

export UGREEN_LED_ALLOW_NONROOT=1
export UGREEN_LED_SKIP_SYSTEMD=1
export UGREEN_LED_CONFIG="$temporary/config"
export UGREEN_LED_BACKEND="$repository_root/tests/fake-backend.sh"
export UGREEN_LED_MANUAL_FILE="$temporary/manual.tsv"
export UGREEN_LED_LOCK="$temporary/lock"
export UGREEN_LED_FAKE_STATE="$temporary/state.tsv"

cp "$repository_root/config.example" "$UGREEN_LED_CONFIG"

"$repository_root/led" status > "$temporary/status.txt"
grep -q '^power: status = off' "$temporary/status.txt"
"$repository_root/led" mode solid purple --brightness 111 >/dev/null
grep -q $'^power\ton\t111\t160\t32\t255$' "$UGREEN_LED_FAKE_STATE"

"$repository_root/led" set power,netdev '#00ffaa' --brightness 170 >/dev/null
grep -q $'^power\ton\t170\t0\t255\t170$' "$UGREEN_LED_FAKE_STATE"
grep -q '^MODE=manual$' "$UGREEN_LED_CONFIG"

cp "$UGREEN_LED_FAKE_STATE" "$temporary/before-trick.tsv"
UGREEN_LED_TRICK_STEPS=2 UGREEN_LED_TEST_NO_SLEEP=1 \
  "$repository_root/led" trick rainbow 15s >/dev/null
cmp "$temporary/before-trick.tsv" "$UGREEN_LED_FAKE_STATE"

UGREEN_LED_TEST_CPU_PCT=20 UGREEN_LED_TEST_MEMORY_PCT=55 \
UGREEN_LED_TEST_IOWAIT_PCT=80 UGREEN_LED_TEST_ROOT_PCT=91 \
UGREEN_LED_TEST_TEMP_C=70 UGREEN_LED_TEST_NETWORK_SPEED=2500 \
UGREEN_LED_TEST_GATEWAY=1 UGREEN_LED_TEST_HEALTH=1 UGREEN_LED_ONCE=1 \
  "$repository_root/led" mode resources >/dev/null
grep -q $'^power\ton\t160\t0\t255\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^netdev\ton\t160\t255\t255\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk2\ton\t140\t255\t200\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk3\ton\t140\t255\t96\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk4\ton\t140\t255\t0\t0$' "$UGREEN_LED_FAKE_STATE"

"$repository_root/led" off >/dev/null
grep -q $'^power\toff\t160\t0\t255\t0$' "$UGREEN_LED_FAKE_STATE"

printf 'smoke tests passed\n'
