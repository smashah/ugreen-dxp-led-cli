#!/usr/bin/env python3
import hmac
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


EFFECTS = {"rainbow", "chase", "pulse", "police", "random", "identify"}
COLOR_EFFECTS = {"chase", "pulse"}
NAMED_COLORS = {
    "red",
    "orange",
    "yellow",
    "green",
    "cyan",
    "blue",
    "purple",
    "magenta",
    "pink",
    "white",
    "warmwhite",
    "warm-white",
    "black",
}
NOTIFICATION_COLORS = {
    "info": "blue",
    "warning": "orange",
    "critical": "red",
    "resolved": "green",
}
ARRAY_STATES = {"STARTED", "STOPPED", "STARTING", "STOPPING", "UNKNOWN"}
ARRAY_HEALTH = {"ONLINE", "DEGRADED", "FAULTED", "OFFLINE", "UNKNOWN"}
DISK_STATUS = {"OK", "WARNING", "FAILED", "MISSING", "STANDBY", "UNKNOWN"}


class EffectRestoreError(RuntimeError):
    pass


class LedApiServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 16

    def __init__(
        self,
        address,
        token,
        led_command,
        max_request_workers=16,
        request_read_timeout=5,
        effect_stop_timeout=15,
        telemetry_file="/run/ugreen-led-cli/telemetry.env",
        telemetry_ttl_seconds=90,
    ):
        self.api_token = token
        self.led_command = led_command
        self.operation_lock = threading.RLock()
        self.request_slots = threading.BoundedSemaphore(max_request_workers)
        self.request_read_timeout = request_read_timeout
        self.effect_stop_timeout = effect_stop_timeout
        self.effect_process = None
        self.effect_description = None
        self.telemetry_file = os.path.abspath(telemetry_file)
        self.telemetry_ttl_seconds = telemetry_ttl_seconds
        self.telemetry_lock = threading.Lock()
        self.telemetry = self._load_telemetry()
        super().__init__(address, LedApiHandler)

    def _load_telemetry(self):
        try:
            with open(self.telemetry_file, encoding="utf-8") as handle:
                first_line = handle.readline().rstrip("\n")
            prefix = "# UGREEN_TELEMETRY_JSON="
            if not first_line.startswith(prefix):
                return None
            telemetry = json.loads(first_line.removeprefix(prefix))
        except (OSError, ValueError, TypeError):
            return None
        if (
            not isinstance(telemetry, dict)
            or telemetry.get("source") != "unraid"
            or isinstance(telemetry.get("received_at"), bool)
            or not isinstance(telemetry.get("received_at"), int)
            or not isinstance(telemetry.get("array"), dict)
            or not isinstance(telemetry.get("disks"), list)
        ):
            return None
        return telemetry

    @staticmethod
    def _atomic_write(path, content):
        directory = os.path.dirname(path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".telemetry.", dir=directory, text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        except BaseException:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
            raise

    def store_telemetry(self, telemetry):
        environment = telemetry_environment(telemetry)
        with self.telemetry_lock:
            self._atomic_write(self.telemetry_file, environment)
            self.telemetry = telemetry

    def telemetry_status(self):
        with self.telemetry_lock:
            telemetry = None if self.telemetry is None else dict(self.telemetry)
        if telemetry is None:
            return {"fresh": False, "age_seconds": None, "telemetry": None}
        age = int(time.time()) - telemetry["received_at"]
        return {
            "fresh": 0 <= age <= self.telemetry_ttl_seconds,
            "age_seconds": age,
            "telemetry": telemetry,
        }

    def process_request(self, request, client_address):
        request.settimeout(self.request_read_timeout)
        if not self.request_slots.acquire(blocking=False):
            payload = b'{"error":"server_busy"}'
            response = (
                b"HTTP/1.0 503 Service Unavailable\r\n"
                b"Content-Type: application/json\r\n"
                + f"Content-Length: {len(payload)}\r\n".encode()
                + b"Connection: close\r\n\r\n"
                + payload
            )
            try:
                request.sendall(response)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.request_slots.release()

    def active_effect(self):
        with self.operation_lock:
            if self.effect_process is None:
                return None
            return dict(self.effect_description)

    def start_effect(self, arguments, description):
        with self.operation_lock:
            if self.effect_process is not None:
                return False
            process = subprocess.Popen(
                [self.led_command, *arguments],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            self.effect_process = process
            self.effect_description = dict(description)
        threading.Thread(
            target=self._wait_for_effect,
            args=(process,),
            daemon=True,
        ).start()
        return True

    def _wait_for_effect(self, process):
        _, stderr = process.communicate()
        if process.returncode not in (0, 130, -signal.SIGTERM):
            print(
                f"led effect exited with status {process.returncode}: {stderr.strip()}",
                flush=True,
            )
        with self.operation_lock:
            if self.effect_process is process:
                self.effect_process = None
                self.effect_description = None

    def stop_active_effect(self):
        with self.operation_lock:
            process = self.effect_process
            if process is None:
                return False
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            forced_kill = False
            try:
                process.wait(timeout=self.effect_stop_timeout)
            except subprocess.TimeoutExpired:
                forced_kill = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=2)
            if self.effect_process is process:
                self.effect_process = None
                self.effect_description = None
            if forced_kill or process.returncode not in (0, 130, -signal.SIGTERM):
                raise EffectRestoreError(
                    f"effect process exited without confirmed restoration: {process.returncode}"
                )
            return True


class LedApiHandler(BaseHTTPRequestHandler):
    server_version = "ugreen-led-api/0.3"

    def log_message(self, message, *args):
        return

    def send_json(self, status, body):
        payload = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authenticated(self):
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.server.api_token}"
        return hmac.compare_digest(supplied, expected)

    def require_authentication(self):
        if self.authenticated():
            return True
        self.send_json(401, {"error": "unauthorized"})
        return False

    def read_json(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid_content_length") from error
        if content_length < 1 or content_length > 4096:
            raise ValueError("invalid_body_size")
        try:
            body = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError("invalid_json") from error
        if not isinstance(body, dict):
            raise ValueError("json_body_must_be_an_object")
        return body

    def do_GET(self):
        if self.path == "/v1/health":
            self.send_json(200, {"status": "ok"})
            return
        if self.path in {"/v1/status", "/v1/telemetry"}:
            if not self.authenticated():
                self.send_json(401, {"error": "unauthorized"})
                return
            if self.path == "/v1/telemetry":
                self.send_json(200, self.server.telemetry_status())
                return
            try:
                result = subprocess.run(
                    [self.server.led_command, "status"],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            except (OSError, subprocess.SubprocessError):
                self.send_json(502, {"error": "led_command_failed"})
                return
            self.send_json(
                200,
                {
                    "led_status": result.stdout,
                    "active_effect": self.server.active_effect(),
                    "telemetry": self.server.telemetry_status(),
                },
            )
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self):
        if not self.require_authentication():
            return
        if self.path not in {
            "/v1/effects",
            "/v1/notifications",
            "/v1/mode",
            "/v1/telemetry",
        }:
            self.send_json(404, {"error": "not_found"})
            return
        try:
            body = self.read_json()
            if self.path == "/v1/telemetry":
                telemetry = normalized_telemetry(body)
            elif self.path == "/v1/effects":
                arguments, description = effect_command(body)
            elif self.path == "/v1/notifications":
                arguments, description = notification_command(body)
            else:
                arguments, description = mode_command(body)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        if self.path == "/v1/telemetry":
            try:
                self.server.store_telemetry(telemetry)
            except OSError:
                self.send_json(500, {"error": "telemetry_persistence_failed"})
                return
            self.send_json(202, {"accepted": True, "telemetry": telemetry})
            return
        if self.path == "/v1/mode":
            with self.server.operation_lock:
                if self.server.active_effect() is not None:
                    self.send_json(409, {"error": "effect_already_active"})
                    return
                try:
                    subprocess.run(
                        [self.server.led_command, *arguments],
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                except (OSError, subprocess.SubprocessError):
                    self.send_json(502, {"error": "led_command_failed"})
                    return
            self.send_json(200, {"mode": description["mode"], "applied": True})
            return
        if self.path == "/v1/notifications":
            with self.server.operation_lock:
                try:
                    self.server.stop_active_effect()
                except EffectRestoreError:
                    self.send_json(503, {"error": "effect_restore_failed"})
                    return
                notification = description["notification"]
                print(
                    f"LED notification: {json.dumps(notification, ensure_ascii=True)}",
                    flush=True,
                )
                try:
                    started = self.server.start_effect(arguments, description)
                except OSError:
                    self.send_json(502, {"error": "led_command_failed"})
                    return
        else:
            try:
                started = self.server.start_effect(arguments, description)
            except OSError:
                self.send_json(502, {"error": "led_command_failed"})
                return
        if not started:
            self.send_json(409, {"error": "effect_already_active"})
            return
        self.send_json(202, {"active_effect": description})

    def do_DELETE(self):
        if not self.require_authentication():
            return
        if self.path != "/v1/effects/current":
            self.send_json(404, {"error": "not_found"})
            return
        try:
            cancelled = self.server.stop_active_effect()
        except EffectRestoreError:
            self.send_json(503, {"error": "effect_restore_failed"})
            return
        self.send_json(200, {"cancelled": cancelled})


def normalized_duration(value):
    duration = str(value if value is not None else "15s").lower()
    if duration == "forever":
        return duration
    match = re.fullmatch(r"([1-9][0-9]{0,2})s?", duration)
    if not match or int(match.group(1)) > 300:
        raise ValueError("duration_must_be_1_to_300_seconds_or_forever")
    return f"{int(match.group(1))}s"


def valid_color(value):
    color = str(value).lower()
    if color in NAMED_COLORS:
        return color
    if re.fullmatch(r"#[0-9a-f]{6}", color):
        return color
    if re.fullmatch(r"(?:[0-9]{1,3},){2}[0-9]{1,3}", color):
        components = [int(component) for component in color.split(",")]
        if all(component <= 255 for component in components):
            return color
    raise ValueError("invalid_color")


def effect_command(body):
    effect = str(body.get("effect", "")).lower()
    if effect not in EFFECTS:
        raise ValueError("invalid_effect")
    if effect == "identify":
        return ["trick", "identify"], {"effect": "identify"}
    duration = normalized_duration(body.get("duration"))
    arguments = ["trick", effect, duration]
    description = {"effect": effect, "duration": duration}
    if effect in COLOR_EFFECTS:
        color = valid_color(body.get("color", "purple"))
        arguments.append(color)
        description["color"] = color
    elif "color" in body:
        raise ValueError("effect_does_not_accept_color")
    return arguments, description


def notification_command(body):
    level = str(body.get("level", "")).lower()
    if level not in NOTIFICATION_COLORS:
        raise ValueError("invalid_notification_level")
    message = str(body.get("message", "")).strip()
    if not message or len(message) > 256:
        raise ValueError("notification_message_must_be_1_to_256_characters")
    if re.search(r"[\x00-\x1f\x7f]", message):
        raise ValueError("notification_message_contains_control_characters")
    duration = normalized_duration(body.get("duration", "15s"))
    color = NOTIFICATION_COLORS[level]
    return (
        ["trick", "pulse", duration, color],
        {
            "effect": "pulse",
            "duration": duration,
            "color": color,
            "notification": {"level": level, "message": message},
        },
    )


def mode_command(body):
    mode = str(body.get("mode", "")).lower()
    if mode in {"resources", "manual", "off"}:
        return ["mode", mode], {"mode": mode}
    if mode != "solid":
        raise ValueError("invalid_mode")
    color = valid_color(body.get("color", ""))
    brightness = body.get("brightness", 140)
    if isinstance(brightness, bool) or not isinstance(brightness, int):
        raise ValueError("brightness_must_be_0_to_255")
    if brightness < 0 or brightness > 255:
        raise ValueError("brightness_must_be_0_to_255")
    return (
        ["mode", "solid", color, "--brightness", str(brightness)],
        {"mode": mode},
    )


def optional_percentage(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 100:
        raise ValueError(f"{field}_must_be_0_to_100_or_null")
    return value


def telemetry_identifier(value, field):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,32}", value):
        raise ValueError(f"invalid_{field}")
    return value


def normalized_telemetry(body):
    if body.get("source") != "unraid":
        raise ValueError("telemetry_source_must_be_unraid")
    array = body.get("array")
    if not isinstance(array, dict):
        raise ValueError("array_must_be_an_object")
    array_state = str(array.get("state", "")).upper()
    if array_state not in ARRAY_STATES:
        raise ValueError("invalid_array_state")
    array_health = str(array.get("health", "")).upper()
    if array_health not in ARRAY_HEALTH:
        raise ValueError("invalid_array_health")
    normalized_array = {
        "state": array_state,
        "health": array_health,
        "usage_percent": optional_percentage(
            array.get("usage_percent"), "array_usage_percent"
        ),
    }
    disks = body.get("disks")
    if not isinstance(disks, list) or len(disks) > 4:
        raise ValueError("disks_must_be_an_array_of_up_to_4_items")
    slots = set()
    normalized_disks = []
    for disk in disks:
        if not isinstance(disk, dict):
            raise ValueError("disk_must_be_an_object")
        slot = disk.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 4:
            raise ValueError("disk_slot_must_be_1_to_4")
        if slot in slots:
            raise ValueError("disk_slots_must_be_unique")
        slots.add(slot)
        temperature = disk.get("temperature_c")
        if temperature is not None and (
            isinstance(temperature, bool)
            or not isinstance(temperature, int)
            or not 0 <= temperature <= 100
        ):
            raise ValueError("temperature_c_must_be_0_to_100_or_null")
        status = str(disk.get("status", "")).upper()
        if status not in DISK_STATUS:
            raise ValueError("invalid_disk_status")
        normalized_disks.append(
            {
                "slot": slot,
                "name": telemetry_identifier(disk.get("name", ""), "disk_name"),
                "device": telemetry_identifier(
                    disk.get("device", "unknown"), "disk_device"
                ),
                "temperature_c": temperature,
                "status": status,
                "usage_percent": optional_percentage(
                    disk.get("usage_percent"), "disk_usage_percent"
                ),
            }
        )
    normalized_disks.sort(key=lambda disk: disk["slot"])
    return {
        "source": "unraid",
        "received_at": int(time.time()),
        "array": normalized_array,
        "disks": normalized_disks,
    }


def telemetry_environment(telemetry):
    array = telemetry["array"]
    lines = [
        "# UGREEN_TELEMETRY_JSON="
        + json.dumps(telemetry, separators=(",", ":")),
        f"UGREEN_TELEMETRY_RECEIVED_AT={telemetry['received_at']}",
        f"UGREEN_TELEMETRY_ARRAY_STATE={array['state']}",
        f"UGREEN_TELEMETRY_ARRAY_HEALTH={array['health']}",
        "UGREEN_TELEMETRY_ARRAY_USAGE_PCT="
        + ("" if array["usage_percent"] is None else str(array["usage_percent"])),
    ]
    disks_by_slot = {disk["slot"]: disk for disk in telemetry["disks"]}
    for slot in range(1, 5):
        disk = disks_by_slot.get(slot)
        prefix = f"UGREEN_TELEMETRY_DISK{slot}_"
        if disk is None:
            lines.extend(
                [
                    f"{prefix}PRESENT=0",
                    f"{prefix}TEMP_C=",
                    f"{prefix}STATUS=MISSING",
                    f"{prefix}USAGE_PCT=",
                ]
            )
            continue
        lines.extend(
            [
                f"{prefix}PRESENT=1",
                f"{prefix}TEMP_C="
                + ("" if disk["temperature_c"] is None else str(disk["temperature_c"])),
                f"{prefix}STATUS={disk['status']}",
                f"{prefix}USAGE_PCT="
                + ("" if disk["usage_percent"] is None else str(disk["usage_percent"])),
            ]
        )
    return "\n".join(lines) + "\n"


def create_server(listen_address, port, token, led_command, **server_options):
    return LedApiServer(
        (listen_address, port), token, led_command, **server_options
    )


def read_token(token_file):
    token_path = os.path.abspath(token_file)
    token_stat = os.stat(token_path)
    if stat.S_IMODE(token_stat.st_mode) & 0o077:
        raise ValueError(f"token file must not be accessible by group or others: {token_path}")
    with open(token_path, encoding="utf-8") as handle:
        token = handle.read().strip()
    if len(token) < 32:
        raise ValueError("API token must contain at least 32 characters")
    return token


def read_telemetry_ttl(config_file):
    ttl = 90
    try:
        with open(config_file, encoding="utf-8") as handle:
            for line in handle:
                key, separator, value = line.partition("=")
                if separator and key.strip() == "TELEMETRY_TTL_SECONDS":
                    ttl = int(value.strip())
                    break
    except FileNotFoundError:
        return ttl
    except (OSError, ValueError) as error:
        raise ValueError("cannot read TELEMETRY_TTL_SECONDS from LED config") from error
    if not 10 <= ttl <= 3600:
        raise ValueError("TELEMETRY_TTL_SECONDS must be from 10 to 3600")
    return ttl


def main():
    listen_address = os.environ.get("UGREEN_LED_API_LISTEN", "127.0.0.1")
    try:
        port = int(os.environ.get("UGREEN_LED_API_PORT", "9842"))
    except ValueError as error:
        raise SystemExit("UGREEN_LED_API_PORT must be numeric") from error
    if port < 1 or port > 65535:
        raise SystemExit("UGREEN_LED_API_PORT must be from 1 to 65535")
    token_file = os.environ.get(
        "UGREEN_LED_API_TOKEN_FILE", "/etc/ugreen-led-api.token"
    )
    led_command = os.environ.get("UGREEN_LED_COMMAND", "/usr/local/bin/led")
    telemetry_file = os.environ.get(
        "UGREEN_LED_TELEMETRY_FILE", "/run/ugreen-led-cli/telemetry.env"
    )
    cli_config_file = os.environ.get(
        "UGREEN_LED_CONFIG", "/etc/ugreen-led-cli.conf"
    )
    try:
        telemetry_ttl_seconds = read_telemetry_ttl(cli_config_file)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    try:
        token = read_token(token_file)
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
    if not os.path.isfile(led_command) or not os.access(led_command, os.X_OK):
        raise SystemExit(f"led command is missing or not executable: {led_command}")

    server = create_server(
        listen_address,
        port,
        token,
        led_command,
        telemetry_file=telemetry_file,
        telemetry_ttl_seconds=telemetry_ttl_seconds,
    )

    def stop_service(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    print(
        f"UGREEN LED API listening on http://{listen_address}:{server.server_port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop_active_effect()
        server.server_close()


if __name__ == "__main__":
    main()
