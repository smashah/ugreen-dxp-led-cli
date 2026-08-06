# Visual command manual

These cards explain every primary `led` command family, shortcut, and lifecycle
action on the UGREEN DXP4800 Plus. Mutating commands use `sudo`; it can be
omitted when the shell is already root. The illustration layer was generated with
[Gemini 3.1 Flash Image](https://ai.google.dev/gemini-api/docs/image-generation)
from an [official UGREEN product image](https://www.lulian.cn/product/1126.html),
then the exact titles and commands were added deterministically so they remain
accurate and readable.

## Color map

![LED temperature, health, notification, and network color meanings](00-color-map.webp)

## Setup and inspection

### 01 — Install

```sh
curl -fsSL https://raw.githubusercontent.com/smashah/ugreen-dxp-led-cli/main/install.sh | \
  sudo bash
```

![Install the LED CLI on the physical host](01-install.webp)

### 02 — Status

```sh
led
led status
```

![Read the current mode and every LED](02-status.webp)

### 03 — Colors

```sh
led colors
```

![Print the named color palette](03-colors.webp)

## Persistent modes

### 04 — Current mode

```sh
led mode
```

![Show the saved persistent mode](04-mode.webp)

### 05 — Resources

```sh
sudo led mode resources
sudo led resources
```

![Use array, network, and bay telemetry](05-resources.webp)

### 06 — Solid

```sh
sudo led mode solid purple --brightness 140
sudo led solid cyan
```

![Save one color for every LED](06-solid.webp)

### 07 — Manual

```sh
sudo led mode manual
```

![Keep individually assigned LED colors](07-manual.webp)

### 08 — Off

```sh
sudo led mode off
sudo led off
```

![Turn every LED off persistently](08-off.webp)

### 09 — Set LEDs

```sh
sudo led set power red
sudo led set disk1,disk2 '#00ffaa'
sudo led set all 255,0,255 --brightness 180
```

![Set one LED or a comma-separated group](09-set.webp)

## Temporary tricks

### 10 — Rainbow

```sh
sudo led trick rainbow 15s
```

![Sweep the spectrum across the LEDs](10-rainbow.webp)

### 11 — Chase

```sh
sudo led trick chase 15s cyan
```

![Chase one colored light across the LEDs](11-chase.webp)

### 12 — Pulse

```sh
sudo led trick pulse 30s purple
sudo led trick pulse forever red
```

![Pulse temporarily or until cancelled](12-pulse.webp)

### 13 — Police

```sh
sudo led trick police 10s
```

![Alternate red and blue](13-police.webp)

### 14 — Random

```sh
sudo led trick random 15s
```

![Generate changing random colors](14-random.webp)

### 15 — Identify

```sh
sudo led identify
sudo led trick identify
```

![Scan the front LEDs white to locate the NAS](15-identify.webp)

### 16 — Help

```sh
led --help
```

![Show every command and shortcut](16-help.webp)

### 17 — Uninstall

Keep configuration and manual LED state:

```sh
curl -fsSL https://github.com/smashah/ugreen-dxp-led-cli/releases/latest/download/uninstall.sh | \
  sudo bash
```

Remove saved configuration and state too:

```sh
curl -fsSL https://github.com/smashah/ugreen-dxp-led-cli/releases/latest/download/uninstall.sh | \
  sudo bash -s -- --purge
```

![Remove the service and optionally purge saved state](17-uninstall.webp)

## Regenerate the artwork

The official reference image is deliberately not copied into this repository.
Download it, export a Gemini API key in your shell, and run the generator:

```sh
curl -fsSL https://images.lulian.cn/upload/202408/1724924604.jpg \
  -o /tmp/dxp4800-plus-reference.jpg
read -s GEMINI_KEY
export GEMINI_KEY
python3 docs/manual/generate_manual.py \
  --reference /tmp/dxp4800-plus-reference.jpg \
  --output docs/manual \
  --jobs 3
```

The generator sends the reference image and a wordless scene description to
Gemini. ImageMagick then adds the version-controlled headings and commands.
The API key is passed to `curl` through standard input, so it does not appear
in the process list or generated files. Gemini-generated images include
Google's SynthID watermark.
