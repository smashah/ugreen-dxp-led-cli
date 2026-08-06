# UGREEN DXP LED CLI

Friendly LED control for UGREEN DXP NAS systems running Debian or Proxmox. It gives you persistent health/resource modes and temporary effects that restore the previous state when they finish or when you press Ctrl-C.

This project wraps and pins the hardware controller from [miskcoo/ugreen_leds_controller](https://github.com/miskcoo/ugreen_leds_controller). That project did the I2C reverse-engineering; this repository adds the user-facing command, safe temporary effects, configuration, tests, and boot service.

Tested on:

- UGREEN DXP4800 Plus
- Proxmox VE 8.x and 9.x
- The onboard I801 SMBus controller at address `0x3a`
- `power`, `netdev`, and `disk1` through `disk4`

## Install

Run this on the physical Proxmox or Debian host. The LED controller cannot be managed from a VM unless you pass its I2C controller through.

```sh
curl -fsSL https://raw.githubusercontent.com/smashah/ugreen-dxp-led-cli/main/install.sh | sudo bash
```

Resource mode can include a Proxmox VM and HTTP health check in the power LED:

```sh
curl -fsSL https://raw.githubusercontent.com/smashah/ugreen-dxp-led-cli/main/install.sh | \
  sudo bash -s -- --interface enp6s0 --vm-id 504 --health-url https://192.168.1.27/
```

The installer refuses to run alongside known UGREEN LED services. Once you have a rollback copy of their configuration, replace them explicitly:

```sh
sudo ./install.sh --replace-existing
```

## Usage

```sh
led status
led mode resources
led mode solid purple --brightness 140
led set power red
led set disk1,disk2 '#00ffaa'
led set all 255,0,255 --brightness 180
led mode manual
led mode off
```

Shortcuts are available for common mode changes:

```sh
led resources
led solid cyan
led off
```

Changes to `resources`, `solid`, `manual`, and `off` are saved in `/etc/ugreen-led-cli.conf` and applied again at boot.

## Temporary tricks

```sh
led trick rainbow 15s
led trick chase 15s cyan
led trick pulse 30s purple
led trick police 10s
led trick random 15s
led identify
```

Tricks run for 15 seconds by default and accept durations from 1 to 300 seconds. The command stops the persistent LED service, snapshots the current lights, runs the effect, restores the snapshot, and restarts the service if it was active. Ctrl-C follows the same restore path.

Colors can be named, `#RRGGBB`, or `R,G,B`. Run `led colors` for the built-in palette.

## Resource mode

The default six LEDs provide a compact host dashboard:

| LED | Meaning |
| --- | --- |
| `power` | Green when the optional VM/URL checks and CPU temperature are healthy; orange on temperature warning; red on a failed health check or critical temperature. |
| `netdev` | Link speed color when the default gateway answers; red when it does not. |
| `disk1` | CPU usage. |
| `disk2` | Memory usage. |
| `disk3` | CPU I/O wait. |
| `disk4` | Root filesystem usage. |

Resource colors progress from green below 50%, through yellow and orange, to red at 90%. Network colors are green at 100 Mbps, blue at 1 Gbps, yellow at 2.5 Gbps, and white at 10 Gbps.

## Configuration

Edit `/etc/ugreen-led-cli.conf`, then restart the service:

```sh
sudo systemctl restart ugreen-led-mode.service
```

The main settings are `MODE`, `BRIGHTNESS`, `REFRESH_SECONDS`, `INTERFACE`, `VM_ID`, `HEALTH_URL`, `TEMP_WARN_C`, and `TEMP_CRIT_C`. See [`config.example`](config.example) for the full file.

## Uninstall

Keep the saved configuration by default:

```sh
sudo ./uninstall.sh
```

Remove configuration and manual LED state too:

```sh
sudo ./uninstall.sh --purge
```

## Development

The smoke suite uses a stateful fake controller, so it exercises modes and exact trick restoration without touching hardware:

```sh
make test
```

Release builds compile the backend from the pinned source documented in [`VENDOR.md`](VENDOR.md).

## Credits

Hardware access comes from [miskcoo/ugreen_leds_controller](https://github.com/miskcoo/ugreen_leds_controller), used under the MIT License. Please credit that project for the controller work.
