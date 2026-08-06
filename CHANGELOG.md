# Changelog

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
