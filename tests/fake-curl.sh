#!/usr/bin/env bash
set -euo pipefail

url=""
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    http*) url="$1"; shift ;;
    *) shift ;;
  esac
done

printf '%s\n' "$url" >> "$UGREEN_LED_TEST_CURL_LOG"
case "$url" in
  */led) source="$UGREEN_LED_TEST_REPOSITORY_ROOT/led" ;;
  */ugreen-led-mode.service) source="$UGREEN_LED_TEST_REPOSITORY_ROOT/systemd/ugreen-led-mode.service" ;;
  */ugreen_led_api.py) source="$UGREEN_LED_TEST_REPOSITORY_ROOT/api/ugreen_led_api.py" ;;
  */ugreen-led-api.service) source="$UGREEN_LED_TEST_REPOSITORY_ROOT/systemd/ugreen-led-api.service" ;;
  *) printf 'unexpected URL: %s\n' "$url" >&2; exit 1 ;;
esac
cp "$source" "$output"
