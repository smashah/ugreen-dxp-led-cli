#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "$0")/.." && pwd)"
temporary="$(mktemp -d "${TMPDIR:-/tmp}/ugreen-led-install-test.XXXXXX")"
trap 'rm -rf "$temporary"' EXIT

UGREEN_LED_INSTALL_SOURCE_DIR="$repository_root" \
UGREEN_LED_BACKEND_SOURCE="$repository_root/tests/fake-backend.sh" \
UGREEN_LED_DESTDIR="$temporary/root" \
  "$repository_root/install.sh" --interface enp6s0 --vm-id 504 \
  --health-url https://192.0.2.1/ --no-start --no-enable >/dev/null

test -x "$temporary/root/usr/local/bin/led"
test -x "$temporary/root/usr/local/libexec/ugreen_leds_cli"
grep -q '^INTERFACE=enp6s0$' "$temporary/root/etc/ugreen-led-cli.conf"
grep -q '^VM_ID=504$' "$temporary/root/etc/ugreen-led-cli.conf"
grep -q '^i2c-dev$' "$temporary/root/etc/modules-load.d/ugreen-led-cli.conf"
grep -q '^ExecStart=/usr/local/bin/led daemon$' \
  "$temporary/root/etc/systemd/system/ugreen-led-mode.service"

mkdir -p "$temporary/bin"
cat > "$temporary/bin/ip" <<'EOF'
#!/usr/bin/env bash
printf 'default via 192.0.2.1 dev eno1 proto dhcp\n'
EOF
chmod +x "$temporary/bin/ip"
PATH="$temporary/bin:$PATH" \
UGREEN_LED_INSTALL_SOURCE_DIR="$repository_root" \
UGREEN_LED_BACKEND_SOURCE="$repository_root/tests/fake-backend.sh" \
UGREEN_LED_DESTDIR="$temporary/autodetect-root" \
  "$repository_root/install.sh" --no-start --no-enable >/dev/null
grep -q '^INTERFACE=eno1$' "$temporary/autodetect-root/etc/ugreen-led-cli.conf"

UGREEN_LED_INSTALL_SOURCE_DIR="$repository_root" \
UGREEN_LED_BACKEND_SOURCE="$repository_root/tests/fake-backend.sh" \
UGREEN_LED_DESTDIR="$temporary/api-root" \
  "$repository_root/install.sh" --with-api --api-listen 192.0.2.10 \
  --api-port 9842 --no-start --no-enable >/dev/null
test -x "$temporary/api-root/usr/local/libexec/ugreen_led_api.py"
test -f "$temporary/api-root/etc/systemd/system/ugreen-led-api.service"
grep -q '^UGREEN_LED_API_LISTEN=192.0.2.10$' \
  "$temporary/api-root/etc/ugreen-led-api.conf"
grep -q '^UGREEN_LED_API_PORT=9842$' \
  "$temporary/api-root/etc/ugreen-led-api.conf"
grep -q '^UGREEN_LED_TELEMETRY_FILE=/run/ugreen-led-cli/telemetry.env$' \
  "$temporary/api-root/etc/ugreen-led-api.conf"
grep -q '^UGREEN_LED_CONFIG=/etc/ugreen-led-cli.conf$' \
  "$temporary/api-root/etc/ugreen-led-api.conf"
grep -q '^TELEMETRY_TTL_SECONDS=90$' \
  "$temporary/api-root/etc/ugreen-led-cli.conf"
test "$(stat -c '%a' "$temporary/api-root/etc/ugreen-led-api.token" 2>/dev/null || \
  stat -f '%Lp' "$temporary/api-root/etc/ugreen-led-api.token")" = 600
test "$(wc -c < "$temporary/api-root/etc/ugreen-led-api.token" | tr -d ' ')" -ge 33

UGREEN_LED_INSTALL_SOURCE_DIR="$repository_root" \
UGREEN_LED_BACKEND_SOURCE="$repository_root/tests/fake-backend.sh" \
UGREEN_LED_DESTDIR="$temporary/api-root" \
  "$repository_root/install.sh" --with-api --api-listen 192.0.2.11 \
  --api-port 9988 --no-start --no-enable >/dev/null
grep -q '^UGREEN_LED_API_LISTEN=192.0.2.11$' \
  "$temporary/api-root/etc/ugreen-led-api.conf"
grep -q '^UGREEN_LED_API_PORT=9988$' \
  "$temporary/api-root/etc/ugreen-led-api.conf"

printf 'installer tests passed\n'
