#!/usr/bin/env python3
"""Generate the visual command manual with Gemini, then add exact SVG text.

Requires GEMINI_KEY (or GEMINI_API_KEY), ImageMagick, and a DXP4800 Plus
reference image. The API key is read only from the environment and is never
written to requests, output files, logs, or repository configuration.
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODEL = "gemini-3.1-flash-image"
WIDTH = 2048
HEIGHT = 1152

CARDS = [
    {
        "slug": "00-color-map",
        "title": "LED COLOR MAP",
        "subtitle": "Read temperature, health, network, and alert state",
        "commands": (),
        "kind": "legend",
        "scene": "A large DXP4800 Plus with four bay LEDs arranged as a blue cyan green yellow orange red temperature scale, plus small power, network, disk-health, and alert pictograms.",
    },
    {
        "slug": "01-install",
        "title": "INSTALL",
        "subtitle": "Install the boot service on the physical host",
        "commands": (
            "curl -fsSL https://raw.githubusercontent.com/smashah/ugreen-dxp-led-cli/main/install.sh | \\",
            "  sudo bash",
        ),
        "command_size": 27,
        "scene": "A download arrow enters a small host computer beside the NAS; a service gear clicks into place.",
    },
    {
        "slug": "02-status",
        "title": "STATUS",
        "subtitle": "Read the saved mode and every physical LED",
        "commands": ("led", "led status"),
        "scene": "A magnifying glass inspects the six front status lights; show a simple checklist with check marks but no writing.",
    },
    {
        "slug": "03-colors",
        "title": "COLORS",
        "subtitle": "Print the built-in named color palette",
        "commands": ("led colors",),
        "scene": "A compact fan of eight colored swatches points toward the NAS LEDs.",
    },
    {
        "slug": "04-mode",
        "title": "CURRENT MODE",
        "subtitle": "Show which persistent mode is saved",
        "commands": ("led mode",),
        "scene": "Four miniature NAS states sit in a selector: telemetry colors, one solid color, individually colored LEDs, and lights off.",
    },
    {
        "slug": "05-resources",
        "title": "RESOURCE MODE",
        "subtitle": "Array, network, and bay health at a glance",
        "commands": ("sudo led mode resources", "sudo led resources"),
        "scene": "Four drive LEDs form a cool-to-hot blue cyan green yellow orange red temperature gradient; power is green and network is yellow. Add small thermometer, disk, and network pictograms.",
    },
    {
        "slug": "06-solid",
        "title": "SOLID MODE",
        "subtitle": "Save one color for every configured LED",
        "commands": (
            "sudo led mode solid purple --brightness 140",
            "sudo led solid cyan",
        ),
        "command_size": 30,
        "scene": "All six front LEDs glow the same purple; one brightness dial points near its middle.",
    },
    {
        "slug": "07-manual",
        "title": "MANUAL MODE",
        "subtitle": "Keep the individual colors created by led set",
        "commands": ("sudo led mode manual",),
        "scene": "A hand adjusts six separate color controls connected by arrows to six differently colored front LEDs.",
    },
    {
        "slug": "08-off",
        "title": "OFF MODE",
        "subtitle": "Turn every LED off and remember it across reboot",
        "commands": ("sudo led mode off", "sudo led off"),
        "scene": "The NAS remains powered but every front LED is dark; show a simple crossed-out light bulb pictogram.",
    },
    {
        "slug": "09-set",
        "title": "SET LEDS",
        "subtitle": "Set one LED or a comma-separated group",
        "commands": (
            "sudo led set power red",
            "sudo led set disk1,disk2 '#00ffaa'",
            "sudo led set all 255,0,255 --brightness 180",
        ),
        "command_size": 28,
        "scene": "The power LED is red and the first two disk LEDs are bright cyan; arrows isolate exactly those targets.",
    },
    {
        "slug": "10-rainbow",
        "title": "RAINBOW",
        "subtitle": "Sweep the spectrum, then restore the prior mode",
        "commands": ("sudo led trick rainbow 15s",),
        "scene": "A smooth rainbow ribbon travels across all six LEDs from left to right with a clear motion arrow.",
    },
    {
        "slug": "11-chase",
        "title": "CHASE",
        "subtitle": "Run one colored light across the front panel",
        "commands": ("sudo led trick chase 15s cyan",),
        "scene": "One cyan light moves sequentially across six LED positions; use six ghosted frames and one directional arrow.",
    },
    {
        "slug": "12-pulse",
        "title": "PULSE",
        "subtitle": "Breathe one color temporarily or until cancelled",
        "commands": ("sudo led trick pulse 30s purple", "sudo led trick pulse forever red"),
        "scene": "Purple LEDs breathe from dim to bright in three frames, with a separate small red alert beacon marked by an infinity symbol.",
    },
    {
        "slug": "13-police",
        "title": "POLICE",
        "subtitle": "Alternate red and blue, then restore",
        "commands": ("sudo led trick police 10s",),
        "scene": "The LEDs alternate red and blue in two frames with swapping arrows; keep the mood instructional, not dramatic.",
    },
    {
        "slug": "14-random",
        "title": "RANDOM",
        "subtitle": "Generate changing colors for a short interval",
        "commands": ("sudo led trick random 15s",),
        "scene": "Six LEDs display varied bright colors with shuffle arrows and a small dice pictogram.",
    },
    {
        "slug": "15-identify",
        "title": "IDENTIFY",
        "subtitle": "Run the quick white scanner to locate this NAS",
        "commands": ("sudo led identify", "sudo led trick identify"),
        "scene": "Front view only: preserve all four front drive doors and the six physical bottom status LEDs. Depict those six LEDs illuminating white one after another from left to right. Use only white or pale gray for the scanner and beams: absolutely no red, orange, green, or blue light. Include a small eye and location-marker pictogram. Never show the rear panel or rear ports.",
    },
    {
        "slug": "16-help",
        "title": "HELP",
        "subtitle": "Show primary syntax, modes, options, and tricks",
        "commands": ("led --help",),
        "scene": "The DXP4800 Plus sits beside an open instruction booklet with simple command-line and question-mark pictograms but no writing.",
    },
    {
        "slug": "17-uninstall",
        "title": "UNINSTALL",
        "subtitle": "Remove the service; optionally purge saved state",
        "commands": (
            "curl -fsSL https://github.com/smashah/ugreen-dxp-led-cli/releases/latest/download/uninstall.sh | sudo bash",
            "curl -fsSL https://github.com/smashah/ugreen-dxp-led-cli/releases/latest/download/uninstall.sh | sudo bash -s -- --purge",
        ),
        "command_size": 20,
        "scene": "A service gear is lifted cleanly away from the DXP4800 Plus. Show one protected configuration box that remains and a second crossed-out box for purge, using no words.",
    },
]


BASE_PROMPT = """Use case: infographic-diagram
Asset type: illustration layer for an open-source CLI command card
Input image: exact UGREEN DXP4800 Plus chassis reference; preserve its four-bay geometry and front-panel LED placement
Primary request: Create one wordless Scandinavian flat-pack instruction-manual illustration for this scene: {scene}
Style: warm off-white paper, crisp black technical line art, friendly simplified pictograms, sparse arrows, restrained saturated color only where the LEDs or action require it
Composition: 16:9 landscape; the NAS and instructional diagram must be large, bold, and clearly visible across the central 55 percent of the canvas; keep only the top 25 percent and bottom 18 percent empty for later labels
Constraints: no words, no letters, no numbers, no logos, no command text, no captions, no border, no photorealism, no people except a simple instructional hand when requested
Avoid: dark background, gradients in the paper, illegible pseudo-text, extra drive bays, extra LEDs, cables crossing the front panel, decorative clutter
"""


def api_key() -> str:
    value = os.environ.get("GEMINI_KEY") or os.environ.get("GEMINI_API_KEY")
    if not value:
        raise SystemExit("GEMINI_KEY or GEMINI_API_KEY is required")
    return value


def generate_art(reference: Path, scene: str, output: Path) -> None:
    payload = {
        "model": MODEL,
        "input": [
            {"type": "text", "text": BASE_PROMPT.format(scene=scene)},
            {
                "type": "image",
                "mime_type": "image/jpeg",
                "data": base64.b64encode(reference.read_bytes()).decode("ascii"),
            },
        ],
        "response_format": {
            "type": "image",
            "mime_type": "image/jpeg",
            "aspect_ratio": "16:9",
            "image_size": "2K",
        },
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8") as body:
        json.dump(payload, body)
        body.flush()
        curl_config = "\n".join(
            (
                f'url = "{API_URL}"',
                'request = "POST"',
                'header = "Content-Type: application/json"',
                f'header = "x-goog-api-key: {api_key()}"',
                f'data-binary = "@{body.name}"',
                "silent",
                "show-error",
                "fail-with-body",
                "max-time = 180",
            )
        )
        response = subprocess.run(
            ["curl", "--config", "-"],
            input=curl_config,
            text=True,
            capture_output=True,
            check=False,
        )
    if response.returncode != 0:
        detail = (response.stdout or response.stderr).strip()
        raise RuntimeError(f"Gemini request failed: {detail[:500]}")
    result = json.loads(response.stdout)

    for step in result.get("steps", []):
        if step.get("type") != "model_output":
            continue
        for block in step.get("content", []):
            if block.get("type") == "image" and block.get("data"):
                output.write_bytes(base64.b64decode(block["data"]))
                return
    raise RuntimeError("Gemini response did not contain an image")


def svg_text(value: str) -> str:
    return html.escape(value, quote=True)


def overlay_svg(card: dict[str, object]) -> str:
    commands = tuple(card["commands"])
    command_y = 1034 if len(commands) == 1 else 1006
    command_lines = "\n".join(
        f'<text x="164" y="{command_y + index * 54}" class="command">{svg_text(command)}</text>'
        for index, command in enumerate(commands)
    )
    number = str(card["slug"]).split("-", 1)[0]
    command_size = int(card.get("command_size", 34))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">
  <style>
    .number {{ font-family: Helvetica, Arial, sans-serif; font-size: 48px; font-weight: 700; fill: #111111; }}
    .title {{ font-family: Helvetica, Arial, sans-serif; font-size: 82px; font-weight: 700; letter-spacing: 2px; fill: #111111; }}
    .subtitle {{ font-family: Helvetica, Arial, sans-serif; font-size: 34px; fill: #333333; }}
    .run {{ font-family: Helvetica, Arial, sans-serif; font-size: 24px; font-weight: 700; letter-spacing: 3px; fill: #ffd800; }}
    .command {{ font-family: Courier, monospace; font-size: {command_size}px; font-weight: 700; fill: #ffffff; }}
  </style>
  <rect width="2048" height="280" fill="#f7f2e7" fill-opacity="0.96"/>
  <rect x="72" y="70" width="112" height="112" rx="4" fill="#ffd800"/>
  <text x="128" y="144" text-anchor="middle" dominant-baseline="middle" class="number">{number}</text>
  <text x="224" y="127" class="title">{svg_text(str(card['title']))}</text>
  <text x="228" y="185" class="subtitle">{svg_text(str(card['subtitle']))}</text>
  <rect y="922" width="2048" height="230" fill="#111111"/>
  <rect x="72" y="976" width="62" height="62" rx="31" fill="#ffd800"/>
  <path d="M94 1007h18m-8-9 9 9-9 9" fill="none" stroke="#111" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="164" y="970" class="run">RUN</text>
  {command_lines}
</svg>'''


def legend_overlay_svg(card: dict[str, object]) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}">
  <style>
    .title {{ font-family: Helvetica, Arial, sans-serif; font-size: 82px; font-weight: 700; letter-spacing: 2px; fill: #111111; }}
    .subtitle {{ font-family: Helvetica, Arial, sans-serif; font-size: 34px; fill: #333333; }}
    .section {{ font-family: Helvetica, Arial, sans-serif; font-size: 26px; font-weight: 700; letter-spacing: 2px; fill: #111111; }}
    .label {{ font-family: Helvetica, Arial, sans-serif; font-size: 25px; font-weight: 700; fill: #111111; }}
    .note {{ font-family: Helvetica, Arial, sans-serif; font-size: 21px; fill: #333333; }}
    .inverse {{ fill: #ffffff; }}
    .accent {{ fill: #ffd800; }}
  </style>
  <rect width="2048" height="1152" fill="#f7f2e7" fill-opacity="0.91"/>
  <rect x="72" y="70" width="112" height="112" rx="4" fill="#ffd800"/>
  <circle cx="128" cy="126" r="24" fill="#0077ff"/><circle cx="128" cy="126" r="15" fill="#00e5ff"/><circle cx="128" cy="126" r="7" fill="#ff5a2a"/>
  <text x="224" y="127" class="title">{svg_text(str(card['title']))}</text>
  <text x="228" y="185" class="subtitle">{svg_text(str(card['subtitle']))}</text>

  <rect x="72" y="276" width="925" height="304" rx="18" fill="#ffffff" fill-opacity="0.88" stroke="#111" stroke-width="3"/>
  <text x="112" y="326" class="section">BAY TEMPERATURE</text>
  <circle cx="150" cy="395" r="25" fill="#0060ff"/><text x="150" y="448" text-anchor="middle" class="label">&lt;30°</text>
  <circle cx="285" cy="395" r="25" fill="#00e5ff"/><text x="285" y="448" text-anchor="middle" class="label">30°</text>
  <circle cx="420" cy="395" r="25" fill="#00d94f"/><text x="420" y="448" text-anchor="middle" class="label">35°</text>
  <circle cx="555" cy="395" r="25" fill="#ffd800"/><text x="555" y="448" text-anchor="middle" class="label">40°</text>
  <circle cx="690" cy="395" r="25" fill="#ff7a00"/><text x="690" y="448" text-anchor="middle" class="label">45°</text>
  <circle cx="825" cy="395" r="25" fill="#e51919"/><text x="825" y="448" text-anchor="middle" class="label">50°+</text>
  <text x="112" y="522" class="note">Continuous gradient between markers • brighter = more array usage</text>

  <rect x="1051" y="276" width="925" height="304" rx="18" fill="#ffffff" fill-opacity="0.88" stroke="#111" stroke-width="3"/>
  <text x="1091" y="326" class="section">POWER / ARRAY</text>
  <circle cx="1120" cy="390" r="22" fill="#00c853"/><text x="1160" y="399" class="label">STARTED + ONLINE</text>
  <circle cx="1120" cy="456" r="22" fill="#ff7a00"/><text x="1160" y="465" class="label">DEGRADED OR STALE</text>
  <circle cx="1120" cy="522" r="22" fill="#e51919"/><text x="1160" y="531" class="label">STOPPED / FAULT / VM-URL / HOST HOT</text>

  <rect x="72" y="620" width="925" height="250" rx="18" fill="#ffffff" fill-opacity="0.88" stroke="#111" stroke-width="3"/>
  <text x="112" y="670" class="section">DISK HEALTH</text>
  <circle cx="120" cy="731" r="20" fill="#e51919"/><text x="154" y="739" class="label">FAILED / MISSING</text>
  <circle cx="485" cy="731" r="20" fill="#a020f0"/><text x="519" y="739" class="label">UNKNOWN</text>
  <circle cx="720" cy="731" r="20" fill="#00e5ff"/><text x="754" y="739" class="label">NO TEMP</text>
  <circle cx="120" cy="791" r="20" fill="#3f70a8"/><text x="154" y="799" class="label">DIM BLUE = STALE</text>
  <text x="112" y="827" class="note">Before telemetry: DISK1 CPU • DISK2 MEMORY • DISK3 I/O WAIT • DISK4 ROOT</text>
  <text x="112" y="857" class="note">Load: green &lt;50% • yellow 50–74% • orange 75–89% • red ≥90%</text>

  <rect x="1051" y="620" width="925" height="250" rx="18" fill="#ffffff" fill-opacity="0.88" stroke="#111" stroke-width="3"/>
  <text x="1091" y="670" class="section">NOTIFICATIONS</text>
  <circle cx="1118" cy="731" r="20" fill="#168cff"/><text x="1152" y="739" class="label">INFO</text>
  <circle cx="1325" cy="731" r="20" fill="#ff7a00"/><text x="1359" y="739" class="label">WARNING</text>
  <circle cx="1600" cy="731" r="20" fill="#e51919"/><text x="1634" y="739" class="label">CRITICAL</text>
  <circle cx="1118" cy="791" r="20" fill="#00c853"/><text x="1152" y="799" class="label">RESOLVED</text>

  <rect x="72" y="900" width="1904" height="170" rx="18" fill="#111111"/>
  <text x="112" y="948" class="section accent">NETWORK SPEED</text>
  <circle cx="130" cy="1015" r="21" fill="#00c853"/><text x="164" y="1023" class="label inverse">100 Mbps</text>
  <circle cx="450" cy="1015" r="21" fill="#168cff"/><text x="484" y="1023" class="label inverse">1 Gbps</text>
  <circle cx="745" cy="1015" r="21" fill="#ffd800"/><text x="779" y="1023" class="label inverse">2.5 Gbps</text>
  <circle cx="1080" cy="1015" r="21" fill="#fff" stroke="#777"/><text x="1114" y="1023" class="label inverse">10 Gbps</text>
  <circle cx="1400" cy="1015" r="21" fill="#e51919"/><text x="1434" y="1023" class="label inverse">UNREACHABLE</text>
  <circle cx="1740" cy="1015" r="21" fill="#ff7a00"/><text x="1774" y="1023" class="label inverse">UNKNOWN</text>
</svg>'''


def compose(art: Path, card: dict[str, object], output: Path, temporary: Path) -> None:
    overlay = temporary / "overlay.svg"
    if card.get("kind") == "legend":
        overlay.write_text(legend_overlay_svg(card), encoding="utf-8")
    else:
        overlay.write_text(overlay_svg(card), encoding="utf-8")
    subprocess.run(
        [
            "magick",
            str(art),
            "-auto-orient",
            "-resize",
            f"{WIDTH}x{HEIGHT}^",
            "-gravity",
            "center",
            "-extent",
            f"{WIDTH}x{HEIGHT}",
            "-background",
            "none",
            str(overlay),
            "-composite",
            "-strip",
            "-quality",
            "92",
            str(output),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", default=Path(__file__).parent, type=Path)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--keep-art", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()

    if shutil.which("magick") is None:
        raise SystemExit("ImageMagick 'magick' is required")
    if shutil.which("curl") is None:
        raise SystemExit("curl is required")
    args.output.mkdir(parents=True, exist_ok=True)
    selected = [card for card in CARDS if not args.only or card["slug"] in args.only]
    if not selected:
        raise SystemExit("no matching cards")

    with tempfile.TemporaryDirectory(prefix="ugreen-led-manual-") as directory:
        temporary = Path(directory)
        def build(card: dict[str, object]) -> Path:
            slug = str(card["slug"])
            card_temporary = temporary / slug
            card_temporary.mkdir()
            print(f"generating {slug}", flush=True)
            art = card_temporary / f"{slug}-art.jpg"
            generate_art(args.reference, str(card["scene"]), art)
            if args.keep_art:
                shutil.copy2(art, args.output / f"{slug}-art.jpg")
            output = args.output / f"{slug}.webp"
            compose(art, card, output, card_temporary)
            print(f"wrote {output}", flush=True)
            return output

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as executor:
            futures = [executor.submit(build, card) for card in selected]
            for future in concurrent.futures.as_completed(futures):
                future.result()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
