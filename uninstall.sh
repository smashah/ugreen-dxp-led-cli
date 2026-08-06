#!/usr/bin/env bash
set -euo pipefail

PURGE=0
[ "${1:-}" != "--purge" ] || PURGE=1
if [ "$#" -gt 1 ] || { [ "$#" -eq 1 ] && [ "$PURGE" -ne 1 ]; }; then
  printf 'Usage: uninstall.sh [--purge]\n' >&2
  exit 2
fi
[ "$(id -u)" -eq 0 ] || { printf 'uninstall: run as root\n' >&2; exit 1; }

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now ugreen-led-api.service 2>/dev/null || true
  systemctl disable --now ugreen-led-mode.service 2>/dev/null || true
fi
rm -f /usr/local/bin/led /usr/local/libexec/ugreen_leds_cli /usr/local/libexec/ugreen_led_api.py
rm -f /etc/systemd/system/ugreen-led-mode.service /etc/systemd/system/ugreen-led-api.service
rm -f /etc/modules-load.d/ugreen-led-cli.conf
if [ "$PURGE" -eq 1 ]; then
  rm -f /etc/ugreen-led-cli.conf /etc/ugreen-led-api.conf /etc/ugreen-led-api.token
  rm -rf /var/lib/ugreen-led-cli
fi
if command -v systemctl >/dev/null 2>&1; then systemctl daemon-reload; fi
printf 'Removed UGREEN DXP LED CLI%s.\n' "$([ "$PURGE" -eq 1 ] && printf ' and its saved configuration' || true)"
