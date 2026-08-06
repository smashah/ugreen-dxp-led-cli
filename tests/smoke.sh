#!/usr/bin/env bash
set -euo pipefail
[ "${CI:-}" != "true" ] || set -x

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
grep -q $'^power\ton\t111\t160\t32\t255\t0\t0$' "$UGREEN_LED_FAKE_STATE"

"$repository_root/led" set power,netdev '#00ffaa' --brightness 170 >/dev/null
grep -q $'^power\ton\t170\t0\t255\t170\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q '^MODE=manual$' "$UGREEN_LED_CONFIG"

"$UGREEN_LED_BACKEND" disk1 -color 12 34 56 -brightness 77 -off
"$UGREEN_LED_BACKEND" disk2 -color 90 80 70 -brightness 66 -breath 400 800
cp "$UGREEN_LED_FAKE_STATE" "$temporary/before-trick.tsv"
UGREEN_LED_TRICK_STEPS=2 UGREEN_LED_TEST_NO_SLEEP=1 \
  "$repository_root/led" trick rainbow 15s >/dev/null
cmp "$temporary/before-trick.tsv" "$UGREEN_LED_FAKE_STATE"
UGREEN_LED_TRICK_STEPS=1 UGREEN_LED_TEST_NO_SLEEP=1 \
  "$repository_root/led" trick pulse forever red >/dev/null
cmp "$temporary/before-trick.tsv" "$UGREEN_LED_FAKE_STATE"

UGREEN_LED_TEST_CPU_PCT=20 UGREEN_LED_TEST_MEMORY_PCT=55 \
UGREEN_LED_TEST_IOWAIT_PCT=80 UGREEN_LED_TEST_ROOT_PCT=91 \
UGREEN_LED_TEST_TEMP_C=70 UGREEN_LED_TEST_NETWORK_SPEED=2500 \
UGREEN_LED_TEST_GATEWAY=1 UGREEN_LED_TEST_HEALTH=1 UGREEN_LED_ONCE=1 \
  "$repository_root/led" mode resources >/dev/null
grep -q $'^power\ton\t160\t0\t255\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^netdev\ton\t160\t255\t255\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk2\ton\t140\t255\t200\t0\t400\t800$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk3\ton\t140\t255\t96\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk4\ton\t140\t255\t0\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"

export UGREEN_LED_TELEMETRY_FILE="$temporary/telemetry.env"
telemetry_now="$(date +%s)"
cat > "$UGREEN_LED_TELEMETRY_FILE" <<EOF
UGREEN_TELEMETRY_RECEIVED_AT=$telemetry_now
UGREEN_TELEMETRY_ARRAY_STATE=STARTED
UGREEN_TELEMETRY_ARRAY_HEALTH=ONLINE
UGREEN_TELEMETRY_ARRAY_USAGE_PCT=61
UGREEN_TELEMETRY_DISK1_PRESENT=1
UGREEN_TELEMETRY_DISK1_TEMP_C=29
UGREEN_TELEMETRY_DISK1_STATUS=OK
UGREEN_TELEMETRY_DISK1_USAGE_PCT=10
UGREEN_TELEMETRY_DISK2_PRESENT=1
UGREEN_TELEMETRY_DISK2_TEMP_C=34
UGREEN_TELEMETRY_DISK2_STATUS=OK
UGREEN_TELEMETRY_DISK2_USAGE_PCT=50
UGREEN_TELEMETRY_DISK3_PRESENT=1
UGREEN_TELEMETRY_DISK3_TEMP_C=43
UGREEN_TELEMETRY_DISK3_STATUS=OK
UGREEN_TELEMETRY_DISK3_USAGE_PCT=80
UGREEN_TELEMETRY_DISK4_PRESENT=1
UGREEN_TELEMETRY_DISK4_TEMP_C=47
UGREEN_TELEMETRY_DISK4_STATUS=OK
UGREEN_TELEMETRY_DISK4_USAGE_PCT=100
EOF
UGREEN_LED_TEST_CPU_PCT=99 UGREEN_LED_TEST_MEMORY_PCT=99 \
UGREEN_LED_TEST_IOWAIT_PCT=99 UGREEN_LED_TEST_ROOT_PCT=99 \
UGREEN_LED_TEST_TEMP_C=70 UGREEN_LED_TEST_NETWORK_SPEED=2500 \
UGREEN_LED_TEST_GATEWAY=1 UGREEN_LED_TEST_HEALTH=1 UGREEN_LED_ONCE=1 \
  "$repository_root/led" mode resources >/dev/null
grep -q $'^power\ton\t160\t0\t255\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk1\ton\t115\t0\t96\t255\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk2\ton\t177\t0\t255\t51\t400\t800$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk3\ton\t224\t255\t145\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk4\ton\t255\t255\t58\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"

sed -e 's/^UGREEN_TELEMETRY_DISK1_TEMP_C=.*/UGREEN_TELEMETRY_DISK1_TEMP_C=55/' \
  -e 's/^UGREEN_TELEMETRY_DISK1_STATUS=.*/UGREEN_TELEMETRY_DISK1_STATUS=WARNING/' \
  "$UGREEN_LED_TELEMETRY_FILE" > "$temporary/critical-telemetry.env"
mv "$temporary/critical-telemetry.env" "$UGREEN_LED_TELEMETRY_FILE"
UGREEN_LED_TEST_CPU_PCT=20 UGREEN_LED_TEST_MEMORY_PCT=20 \
UGREEN_LED_TEST_IOWAIT_PCT=20 UGREEN_LED_TEST_ROOT_PCT=20 \
UGREEN_LED_TEST_TEMP_C=70 UGREEN_LED_TEST_NETWORK_SPEED=2500 \
UGREEN_LED_TEST_GATEWAY=1 UGREEN_LED_TEST_HEALTH=1 UGREEN_LED_ONCE=1 \
  "$repository_root/led" mode resources >/dev/null
grep -q $'^disk1\ton\t115\t255\t0\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"

sed "s/^UGREEN_TELEMETRY_RECEIVED_AT=.*/UGREEN_TELEMETRY_RECEIVED_AT=$((telemetry_now - 91))/" \
  "$UGREEN_LED_TELEMETRY_FILE" > "$temporary/stale-telemetry.env"
mv "$temporary/stale-telemetry.env" "$UGREEN_LED_TELEMETRY_FILE"
UGREEN_LED_TEST_CPU_PCT=20 UGREEN_LED_TEST_MEMORY_PCT=20 \
UGREEN_LED_TEST_IOWAIT_PCT=20 UGREEN_LED_TEST_ROOT_PCT=20 \
UGREEN_LED_TEST_TEMP_C=70 UGREEN_LED_TEST_NETWORK_SPEED=2500 \
UGREEN_LED_TEST_GATEWAY=1 UGREEN_LED_TEST_HEALTH=1 UGREEN_LED_ONCE=1 \
  "$repository_root/led" mode resources >/dev/null
grep -q $'^power\ton\t220\t255\t96\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"
grep -q $'^disk1\ton\t60\t0\t96\t255\t0\t0$' "$UGREEN_LED_FAKE_STATE"

"$repository_root/led" off >/dev/null
grep -q $'^power\toff\t220\t255\t96\t0\t0\t0$' "$UGREEN_LED_FAKE_STATE"

mkdir -p "$temporary/bin"
cat > "$temporary/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  is-active) [ "$(cat "$UGREEN_LED_FAKE_SERVICE_STATE")" = active ] ;;
  stop) printf 'inactive\n' > "$UGREEN_LED_FAKE_SERVICE_STATE" ;;
  start|restart) printf 'active\n' > "$UGREEN_LED_FAKE_SERVICE_STATE" ;;
  *) exit 2 ;;
esac
EOF
chmod +x "$temporary/bin/systemctl"
export UGREEN_LED_FAKE_SERVICE_STATE="$temporary/service-state"
printf 'active\n' > "$UGREEN_LED_FAKE_SERVICE_STATE"
cp "$UGREEN_LED_FAKE_STATE" "$temporary/before-active-trick.tsv"
PATH="$temporary/bin:$PATH" UGREEN_LED_SKIP_SYSTEMD=0 \
UGREEN_LED_TRICK_STEPS=1 UGREEN_LED_TEST_NO_SLEEP=1 \
  "$repository_root/led" trick police 15s >/dev/null
grep -q '^active$' "$UGREEN_LED_FAKE_SERVICE_STATE"
cmp "$temporary/before-active-trick.tsv" "$UGREEN_LED_FAKE_STATE"

if PATH="$temporary/bin:$PATH" UGREEN_LED_SKIP_SYSTEMD=0 UGREEN_LED_FAKE_FAIL_STATUS=1 \
  "$repository_root/led" trick rainbow 15s >/dev/null 2>&1; then
  printf 'expected failed snapshot to fail the trick\n' >&2
  exit 1
fi
grep -q '^active$' "$UGREEN_LED_FAKE_SERVICE_STATE"

printf 'smoke tests passed\n'
