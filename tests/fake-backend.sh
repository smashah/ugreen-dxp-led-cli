#!/usr/bin/env bash
set -euo pipefail

state_file="${UGREEN_LED_FAKE_STATE:?UGREEN_LED_FAKE_STATE is required}"
leds="${UGREEN_LED_FAKE_LEDS:-power netdev disk1 disk2 disk3 disk4}"

initialize() {
  local led
  [ -s "$state_file" ] && return
  mkdir -p "$(dirname "$state_file")"
  : > "$state_file"
  for led in $leds; do
    printf '%s\toff\t0\t0\t0\t0\t0\t0\n' "$led" >> "$state_file"
  done
}

show_status() {
  local led state brightness red green blue time_on time_off
  [ "${UGREEN_LED_FAKE_FAIL_STATUS:-0}" != "1" ] || exit 42
  while IFS=$'\t' read -r led state brightness red green blue time_on time_off; do
    printf '%s: status = %s, brightness = %s, color = RGB(%s, %s, %s)' \
      "$led" "$state" "$brightness" "$red" "$green" "$blue"
    case "$state" in
      blink) printf ', blink_on = %s ms, blink_off = %s ms' "$time_on" "$time_off" ;;
      breath) printf ', breath_on = %s ms, breath_off = %s ms' "$time_on" "$time_off" ;;
    esac
    printf '\n'
  done < "$state_file"
}

update() {
  local target="$1" state="$2" brightness="$3" red="$4" green="$5" blue="$6"
  local time_on="$7" time_off="$8"
  local temporary
  temporary="$(mktemp "$(dirname "$state_file")/.fake-state.XXXXXX")"
  awk -F '\t' -v OFS='\t' -v target="$target" -v state="$state" \
    -v brightness="$brightness" -v red="$red" -v green="$green" -v blue="$blue" \
    -v time_on="$time_on" -v time_off="$time_off" '
      $1 == target {
        $2=state
        if (brightness != "") $3=brightness
        if (red != "") $4=red
        if (green != "") $5=green
        if (blue != "") $6=blue
        if (time_on != "") $7=time_on
        if (time_off != "") $8=time_off
      }
      { print }
    ' "$state_file" > "$temporary"
  mv "$temporary" "$state_file"
}

initialize
target="${1:-}"
shift || true

if [ "$target" = "all" ] && [ "${1:-}" = "-status" ]; then
  show_status
  exit
fi

brightness="" red="" green="" blue="" state=on time_on="" time_off=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -status) show_status; exit ;;
    -color) red="$2"; green="$3"; blue="$4"; shift 4 ;;
    -brightness) brightness="$2"; shift 2 ;;
    -on) state=on; shift ;;
    -off) state=off; shift ;;
    -blink|-breath)
      state="${1#-}"; time_on="$2"; time_off="$3"; shift 3
      ;;
    *) printf 'fake backend: unknown argument %s\n' "$1" >&2; exit 2 ;;
  esac
done

case " $leds " in
  *" $target "*) update "$target" "$state" "$brightness" "$red" "$green" "$blue" "$time_on" "$time_off" ;;
  *) printf 'fake backend: unknown LED %s\n' "$target" >&2; exit 2 ;;
esac
