#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="smashah/ugreen-dxp-led-cli"
VERSION="${UGREEN_LED_VERSION:-latest}"
SOURCE_DIR="${UGREEN_LED_INSTALL_SOURCE_DIR:-}"
BACKEND_SOURCE="${UGREEN_LED_BACKEND_SOURCE:-}"
DESTDIR="${UGREEN_LED_DESTDIR:-}"
PREFIX="${UGREEN_LED_PREFIX:-/usr/local}"
CONFIG_PATH="${UGREEN_LED_CONFIG_PATH:-/etc/ugreen-led-cli.conf}"
SYSTEMD_DIR="${UGREEN_LED_SYSTEMD_DIR:-/etc/systemd/system}"
MODULES_DIR="${UGREEN_LED_MODULES_DIR:-/etc/modules-load.d}"
ENABLE=1
START=1
REPLACE_EXISTING=0
INTERFACE=""
VM_ID=""
HEALTH_URL=""
WITH_API=0
API_LISTEN="127.0.0.1"
API_PORT=9842
API_LISTEN_EXPLICIT=0
API_PORT_EXPLICIT=0
API_CONFIG_PATH="${UGREEN_LED_API_CONFIG_PATH:-/etc/ugreen-led-api.conf}"
API_TOKEN_PATH="${UGREEN_LED_API_TOKEN_PATH:-/etc/ugreen-led-api.token}"

usage() {
  cat <<'EOF'
Usage: install.sh [options]

  --interface NAME       Network interface used for the network-speed LED.
  --vm-id ID             Optional Proxmox VM whose running state affects power LED.
  --health-url URL       Optional HTTP(S) health check that affects power LED.
  --replace-existing     Disable known, conflicting UGREEN LED services.
  --with-api             Install the authenticated HTTP API service.
  --api-listen ADDRESS   API bind address (default: 127.0.0.1).
  --api-port PORT        API port (default: 9842).
  --no-enable            Do not enable the systemd service at boot.
  --no-start             Do not start the systemd service now.
  --version TAG          Install backend from a release tag instead of latest.
EOF
}

die() { printf 'install: %s\n' "$*" >&2; exit 1; }

while [ "$#" -gt 0 ]; do
  case "$1" in
    --interface) [ "$#" -ge 2 ] || die "--interface requires a value"; INTERFACE="$2"; shift 2 ;;
    --vm-id) [ "$#" -ge 2 ] || die "--vm-id requires a value"; VM_ID="$2"; shift 2 ;;
    --health-url) [ "$#" -ge 2 ] || die "--health-url requires a value"; HEALTH_URL="$2"; shift 2 ;;
    --replace-existing) REPLACE_EXISTING=1; shift ;;
    --with-api) WITH_API=1; shift ;;
    --api-listen) [ "$#" -ge 2 ] || die "--api-listen requires a value"; API_LISTEN="$2"; API_LISTEN_EXPLICIT=1; shift 2 ;;
    --api-port) [ "$#" -ge 2 ] || die "--api-port requires a value"; API_PORT="$2"; API_PORT_EXPLICIT=1; shift 2 ;;
    --no-enable) ENABLE=0; shift ;;
    --no-start) START=0; shift ;;
    --version) [ "$#" -ge 2 ] || die "--version requires a value"; VERSION="$2"; shift 2 ;;
    -h|--help) usage; exit ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ "$INTERFACE" =~ ^[a-zA-Z0-9_.:-]*$ ]] || die "invalid interface"
[ -z "$VM_ID" ] || [[ "$VM_ID" =~ ^[0-9]+$ ]] || die "VM ID must be numeric"
[ -z "$HEALTH_URL" ] || [[ "$HEALTH_URL" =~ ^https?:// ]] || die "health URL must use HTTP or HTTPS"
[[ "$API_LISTEN" =~ ^[a-zA-Z0-9_.:-]+$ ]] || die "invalid API listen address"
[[ "$API_PORT" =~ ^[0-9]+$ ]] && [ "$API_PORT" -ge 1 ] && [ "$API_PORT" -le 65535 ] ||
  die "API port must be from 1 to 65535"

if [ -z "$INTERFACE" ] && command -v ip >/dev/null 2>&1; then
  INTERFACE="$(ip route show default 2>/dev/null | awk 'NR == 1 {
    for (field = 1; field <= NF; field++) {
      if ($field == "dev") { print $(field + 1); exit }
    }
  }')"
fi

if [ -z "$DESTDIR" ] && [ "$(id -u)" -ne 0 ]; then
  die "run as root, for example: curl -fsSL https://raw.githubusercontent.com/$REPOSITORY/main/install.sh | sudo bash"
fi

install_rooted() {
  local mode="$1" source="$2" target="$3"
  mkdir -p "$(dirname "$DESTDIR$target")"
  install -m "$mode" "$source" "$DESTDIR$target"
}

download() {
  local url="$1" output="$2"
  command -v curl >/dev/null 2>&1 || die "curl is required"
  curl -fsSL --retry 3 "$url" -o "$output"
}

set_env_value() {
  local file="$1" key="$2" value="$3" temporary_config
  temporary_config="$(mktemp "$(dirname "$file")/.ugreen-led-api.conf.XXXXXX")"
  awk -F= -v key="$key" -v value="$value" '
    $1 == key { print key "=" value; found=1; next }
    { print }
    END { if (!found) print key "=" value }
  ' "$file" > "$temporary_config"
  chmod 0644 "$temporary_config"
  mv "$temporary_config" "$file"
}

temporary="$(mktemp -d "${TMPDIR:-/tmp}/ugreen-led-install.XXXXXX")"
trap 'rm -rf "$temporary"' EXIT

if [ -n "$SOURCE_DIR" ]; then
  cp "$SOURCE_DIR/led" "$temporary/led"
  cp "$SOURCE_DIR/systemd/ugreen-led-mode.service" "$temporary/ugreen-led-mode.service"
  if [ "$WITH_API" -eq 1 ]; then
    cp "$SOURCE_DIR/api/ugreen_led_api.py" "$temporary/ugreen_led_api.py"
    cp "$SOURCE_DIR/systemd/ugreen-led-api.service" "$temporary/ugreen-led-api.service"
  fi
else
  raw_base="https://raw.githubusercontent.com/$REPOSITORY/main"
  download "$raw_base/led" "$temporary/led"
  download "$raw_base/systemd/ugreen-led-mode.service" "$temporary/ugreen-led-mode.service"
  if [ "$WITH_API" -eq 1 ]; then
    download "$raw_base/api/ugreen_led_api.py" "$temporary/ugreen_led_api.py"
    download "$raw_base/systemd/ugreen-led-api.service" "$temporary/ugreen-led-api.service"
  fi
fi

if [ -n "$BACKEND_SOURCE" ]; then
  cp "$BACKEND_SOURCE" "$temporary/ugreen_leds_cli"
else
  case "$(uname -m)" in
    x86_64|amd64) asset_arch=amd64 ;;
    *) die "release binaries currently support x86_64 UGREEN NAS models only" ;;
  esac
  if [ "$VERSION" = "latest" ]; then
    release_base="https://github.com/$REPOSITORY/releases/latest/download"
  else
    release_base="https://github.com/$REPOSITORY/releases/download/$VERSION"
  fi
  asset="ugreen_leds_cli-linux-$asset_arch"
  download "$release_base/$asset" "$temporary/ugreen_leds_cli"
  download "$release_base/$asset.sha256" "$temporary/$asset.sha256"
  cp "$temporary/ugreen_leds_cli" "$temporary/$asset"
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$temporary" && sha256sum -c "$asset.sha256")
  elif command -v shasum >/dev/null 2>&1; then
    (cd "$temporary" && shasum -a 256 -c "$asset.sha256")
  else
    die "sha256sum or shasum is required to verify the backend"
  fi
fi

if [ -z "$DESTDIR" ] && command -v systemctl >/dev/null 2>&1; then
  conflicts=""
  for unit in sre-ugreen-led-status.service ugreen-probe-leds.service ugreen-diskiomon.service ugreen-power-led.service; do
    if systemctl is-enabled "$unit" >/dev/null 2>&1 || systemctl is-active "$unit" >/dev/null 2>&1; then
      conflicts="${conflicts:+$conflicts }$unit"
    fi
  done
  if systemctl list-units --all --no-legend 'ugreen-netdevmon@*.service' 2>/dev/null | grep -q .; then
    while read -r unit _; do conflicts="${conflicts:+$conflicts }$unit"; done < <(
      systemctl list-units --all --no-legend 'ugreen-netdevmon@*.service'
    )
  fi
  if [ -n "$conflicts" ] && [ "$REPLACE_EXISTING" -ne 1 ]; then
    die "conflicting LED services found: $conflicts (rerun with --replace-existing after confirming rollback)"
  fi
  if [ -n "$conflicts" ]; then
    for unit in $conflicts; do systemctl disable --now "$unit"; done
  fi
fi

backup_dir=""
if [ -z "$DESTDIR" ] && { [ -e "$PREFIX/bin/led" ] || [ -e "$PREFIX/libexec/ugreen_leds_cli" ] || [ -e "$SYSTEMD_DIR/ugreen-led-mode.service" ] || [ -e "$PREFIX/libexec/ugreen_led_api.py" ]; }; then
  backup_dir="/var/backups/ugreen-led-cli/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$backup_dir"
  chmod 0700 "$backup_dir"
  for path in "$PREFIX/bin/led" "$PREFIX/libexec/ugreen_leds_cli" "$SYSTEMD_DIR/ugreen-led-mode.service" "$CONFIG_PATH" "$PREFIX/libexec/ugreen_led_api.py" "$SYSTEMD_DIR/ugreen-led-api.service" "$API_CONFIG_PATH" "$API_TOKEN_PATH"; do
    [ ! -e "$path" ] || cp -a "$path" "$backup_dir/"
  done
fi

install_rooted 0755 "$temporary/led" "$PREFIX/bin/led"
install_rooted 0755 "$temporary/ugreen_leds_cli" "$PREFIX/libexec/ugreen_leds_cli"
install_rooted 0644 "$temporary/ugreen-led-mode.service" "$SYSTEMD_DIR/ugreen-led-mode.service"
if [ "$WITH_API" -eq 1 ]; then
  command -v python3 >/dev/null 2>&1 || [ -n "$DESTDIR" ] || die "python3 is required for the API service"
  install_rooted 0755 "$temporary/ugreen_led_api.py" "$PREFIX/libexec/ugreen_led_api.py"
  install_rooted 0644 "$temporary/ugreen-led-api.service" "$SYSTEMD_DIR/ugreen-led-api.service"
fi
mkdir -p "$DESTDIR$(dirname "$CONFIG_PATH")" "$DESTDIR$MODULES_DIR" "$DESTDIR/var/lib/ugreen-led-cli"

if [ ! -e "$DESTDIR$CONFIG_PATH" ]; then
  {
    printf 'BACKEND=%q\n' "$PREFIX/libexec/ugreen_leds_cli"
    printf 'LEDS=%q\n' "power netdev disk1 disk2 disk3 disk4"
    printf 'MODE=resources\nBRIGHTNESS=140\nREFRESH_SECONDS=5\n'
    printf 'MANUAL_FILE=/var/lib/ugreen-led-cli/manual.tsv\n'
    printf 'SOLID_COLOR=%q\nSOLID_BRIGHTNESS=140\n' "160 32 255"
    printf 'INTERFACE=%q\nVM_ID=%q\nHEALTH_URL=%q\n' "$INTERFACE" "$VM_ID" "$HEALTH_URL"
    printf 'TEMP_WARN_C=80\nTEMP_CRIT_C=90\nROOT_PATH=/\n'
    printf 'TELEMETRY_FILE=/run/ugreen-led-cli/telemetry.env\n'
    printf 'TELEMETRY_TTL_SECONDS=90\n'
  } > "$DESTDIR$CONFIG_PATH"
  chmod 0644 "$DESTDIR$CONFIG_PATH"
fi
printf 'i2c-dev\n' > "$DESTDIR$MODULES_DIR/ugreen-led-cli.conf"

if [ "$WITH_API" -eq 1 ]; then
  if [ ! -e "$DESTDIR$API_CONFIG_PATH" ]; then
    mkdir -p "$DESTDIR$(dirname "$API_CONFIG_PATH")"
    {
      printf 'UGREEN_LED_API_LISTEN=%q\n' "$API_LISTEN"
      printf 'UGREEN_LED_API_PORT=%s\n' "$API_PORT"
      printf 'UGREEN_LED_API_TOKEN_FILE=%q\n' "$API_TOKEN_PATH"
      printf 'UGREEN_LED_COMMAND=%q\n' "$PREFIX/bin/led"
      printf 'UGREEN_LED_TELEMETRY_FILE=/run/ugreen-led-cli/telemetry.env\n'
      printf 'UGREEN_LED_CONFIG=%q\n' "$CONFIG_PATH"
    } > "$DESTDIR$API_CONFIG_PATH"
    chmod 0644 "$DESTDIR$API_CONFIG_PATH"
  else
    [ "$API_LISTEN_EXPLICIT" -eq 0 ] ||
      set_env_value "$DESTDIR$API_CONFIG_PATH" UGREEN_LED_API_LISTEN "$API_LISTEN"
    [ "$API_PORT_EXPLICIT" -eq 0 ] ||
      set_env_value "$DESTDIR$API_CONFIG_PATH" UGREEN_LED_API_PORT "$API_PORT"
  fi
  if [ ! -e "$DESTDIR$API_TOKEN_PATH" ]; then
    mkdir -p "$DESTDIR$(dirname "$API_TOKEN_PATH")"
    if command -v openssl >/dev/null 2>&1; then
      openssl rand -hex 32 > "$DESTDIR$API_TOKEN_PATH"
    else
      od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > "$DESTDIR$API_TOKEN_PATH"
      printf '\n' >> "$DESTDIR$API_TOKEN_PATH"
    fi
    chmod 0600 "$DESTDIR$API_TOKEN_PATH"
  fi
fi

if [ -z "$DESTDIR" ] && command -v systemctl >/dev/null 2>&1; then
  modprobe i2c-dev
  systemctl daemon-reload
  [ "$ENABLE" -eq 0 ] || systemctl enable ugreen-led-mode.service
  [ "$START" -eq 0 ] || systemctl restart ugreen-led-mode.service
  if [ "$WITH_API" -eq 1 ]; then
    [ "$ENABLE" -eq 0 ] || systemctl enable ugreen-led-api.service
    [ "$START" -eq 0 ] || systemctl restart ugreen-led-api.service
  fi
fi

printf 'Installed led to %s\n' "$PREFIX/bin/led"
[ -z "$backup_dir" ] || printf 'Previous files backed up to %s\n' "$backup_dir"
printf 'Run: sudo led status\n'
if [ "$WITH_API" -eq 1 ]; then
  API_LISTEN="$(awk -F= '$1 == "UGREEN_LED_API_LISTEN" { print $2; exit }' "$DESTDIR$API_CONFIG_PATH")"
  API_PORT="$(awk -F= '$1 == "UGREEN_LED_API_PORT" { print $2; exit }' "$DESTDIR$API_CONFIG_PATH")"
  printf 'API configured at http://%s:%s\n' "$API_LISTEN" "$API_PORT"
  printf 'Read the bearer token with: sudo cat %s\n' "$API_TOKEN_PATH"
fi
