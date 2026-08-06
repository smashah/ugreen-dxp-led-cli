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

printf 'installer tests passed\n'
