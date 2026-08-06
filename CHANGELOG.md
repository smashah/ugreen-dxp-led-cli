# Changelog

## 0.3.1 - 2026-08-06

- Make the Linux priority integration harness model systemd `Type=simple` service starts asynchronously, avoiding a test-only lock deadlock.

## 0.3.0 - 2026-08-06

- Add authenticated `POST`/`GET /v1/telemetry` endpoints for Unraid array and disk data.
- Render four bay temperatures and disk health in resource mode, with usage-based brightness.
- Mark stale telemetry visibly and retain the previous host-metric display before telemetry arrives.
- Keep notifications and temporary effects above telemetry in the display priority order.

## 0.2.0 - 2026-08-06

- Add an optional token-authenticated HTTP API and hardened systemd service.
- Add asynchronous effects, cancellation, notifications, and persistent mode endpoints.
- Add `forever` effects for alerts that remain active until explicitly cleared.
- Add installer support for secure token generation and explicit API binding.
- Add real HTTP integration tests backed by a fake `led` command.

## 0.1.0 - 2026-08-06

- Add persistent resource, solid, manual, and off modes.
- Add temporary rainbow, chase, pulse, police, random, and identify effects.
- Restore the exact prior LED state after temporary effects, including Ctrl-C.
- Add a systemd installer with conflicting UGREEN LED service detection.
- Vendor and pin the low-level UGREEN I2C controller backend.
