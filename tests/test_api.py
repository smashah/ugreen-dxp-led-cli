#!/usr/bin/env python3
import importlib.util
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_PATH = REPOSITORY_ROOT / "api" / "ugreen_led_api.py"


def load_api_module():
    spec = importlib.util.spec_from_file_location("ugreen_led_api", API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiHttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_api_module()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fake_led = Path(self.temporary.name) / "led"
        self.fake_log = Path(self.temporary.name) / "commands.log"
        self.telemetry_file = Path(self.temporary.name) / "telemetry.env"
        os.environ["UGREEN_LED_FAKE_LOG"] = str(self.fake_log)
        self.fake_led.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"$UGREEN_LED_FAKE_LOG\"\n"
            "if [ \"${UGREEN_LED_FAKE_FAIL:-0}\" = 1 ]; then exit 42; fi\n"
            "if [ \"${1:-}\" = status ]; then\n"
            "  printf 'mode: resources\\nservice: active\\n'\n"
            "  exit 0\n"
            "fi\n"
            "if [ \"${1:-}\" = trick ]; then\n"
            "  if [ \"${UGREEN_LED_FAKE_IGNORE_TERM:-0}\" = 1 ]; then\n"
            "    trap '' INT TERM\n"
            "  else\n"
            "    trap 'printf \"effect-restored\\n\" >> \"$UGREEN_LED_FAKE_LOG\"; exit 0' INT TERM\n"
            "  fi\n"
            "  while true; do sleep 1; done\n"
            "fi\n"
            "if [ \"${1:-}\" = mode ]; then\n"
            "  if [ -n \"${UGREEN_LED_FAKE_MODE_DELAY:-}\" ]; then sleep \"$UGREEN_LED_FAKE_MODE_DELAY\"; fi\n"
            "  printf 'mode-finished\\n' >> \"$UGREEN_LED_FAKE_LOG\"\n"
            "  exit 0\n"
            "fi\n"
            "exit 2\n"
        )
        os.chmod(self.fake_led, 0o755)
        self.server = self.api.create_server(
            "127.0.0.1",
            0,
            "test-token",
            str(self.fake_led),
            telemetry_file=str(self.telemetry_file),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server.stop_active_effect()
        os.environ.pop("UGREEN_LED_FAKE_LOG", None)
        self.temporary.cleanup()

    def request(self, path, token=None, method="GET", body=None):
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}", headers=headers, data=data, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def wait_for_log(self, text):
        for _ in range(40):
            if self.fake_log.exists() and text in self.fake_log.read_text():
                return
            time.sleep(0.05)
        self.fail(f"fake led log did not contain {text!r}")

    def test_health_is_available_without_authentication(self):
        status, body = self.request("/v1/health")

        self.assertEqual(200, status)
        self.assertEqual({"status": "ok"}, body)

    def test_status_requires_the_bearer_token_and_runs_led_status(self):
        denied_status, denied_body = self.request("/v1/status")
        status, body = self.request("/v1/status", token="test-token")

        self.assertEqual(401, denied_status)
        self.assertEqual({"error": "unauthorized"}, denied_body)
        self.assertEqual(200, status)
        self.assertEqual("mode: resources\nservice: active\n", body["led_status"])
        self.assertIsNone(body["active_effect"])

    def test_unraid_telemetry_is_authenticated_validated_and_persisted(self):
        telemetry = {
            "source": "unraid",
            "array": {
                "state": "STARTED",
                "health": "ONLINE",
                "usage_percent": 61,
            },
            "disks": [
                {
                    "slot": 1,
                    "name": "main",
                    "device": "sdb",
                    "temperature_c": 29,
                    "status": "OK",
                    "usage_percent": 61,
                },
                {
                    "slot": 2,
                    "name": "main2",
                    "device": "sdc",
                    "temperature_c": 43,
                    "status": "OK",
                    "usage_percent": 61,
                },
            ],
        }

        denied_status, denied = self.request(
            "/v1/telemetry", method="POST", body=telemetry
        )
        status, body = self.request(
            "/v1/telemetry",
            token="test-token",
            method="POST",
            body=telemetry,
        )
        read_status, read_body = self.request(
            "/v1/telemetry", token="test-token"
        )

        self.assertEqual(401, denied_status)
        self.assertEqual({"error": "unauthorized"}, denied)
        self.assertEqual(202, status)
        self.assertTrue(body["accepted"])
        self.assertEqual("unraid", body["telemetry"]["source"])
        self.assertEqual(200, read_status)
        self.assertTrue(read_body["fresh"])
        self.assertEqual(43, read_body["telemetry"]["disks"][1]["temperature_c"])
        persisted = self.telemetry_file.read_text()
        self.assertIn("UGREEN_TELEMETRY_ARRAY_STATE=STARTED\n", persisted)
        self.assertIn("UGREEN_TELEMETRY_DISK1_TEMP_C=29\n", persisted)
        self.assertIn("UGREEN_TELEMETRY_DISK2_STATUS=OK\n", persisted)

        reloaded_server = self.api.create_server(
            "127.0.0.1",
            0,
            "test-token",
            str(self.fake_led),
            telemetry_file=str(self.telemetry_file),
        )
        reloaded_thread = threading.Thread(
            target=reloaded_server.serve_forever, daemon=True
        )
        reloaded_thread.start()
        original_base_url = self.base_url
        self.base_url = f"http://127.0.0.1:{reloaded_server.server_port}"
        try:
            reloaded_status, reloaded = self.request(
                "/v1/telemetry", token="test-token"
            )
        finally:
            self.base_url = original_base_url
            reloaded_server.shutdown()
            reloaded_server.server_close()
            reloaded_thread.join(timeout=2)
        self.assertEqual(200, reloaded_status)
        self.assertEqual(telemetry["array"], reloaded["telemetry"]["array"])

    def test_telemetry_rejects_unsafe_or_duplicate_disk_data(self):
        status, body = self.request(
            "/v1/telemetry",
            token="test-token",
            method="POST",
            body={
                "source": "unraid",
                "array": {"state": "STARTED", "health": "ONLINE"},
                "disks": [
                    {
                        "slot": 1,
                        "name": "main;touch /tmp/nope",
                        "device": "sdb",
                        "temperature_c": 150,
                        "status": "OK",
                    },
                    {
                        "slot": 1,
                        "name": "main2",
                        "device": "sdc",
                        "temperature_c": 35,
                        "status": "OK",
                    },
                ],
            },
        )

        self.assertEqual(400, status)
        self.assertIn(
            body["error"],
            {
                "invalid_disk_name",
                "temperature_c_must_be_0_to_100_or_null",
                "disk_slots_must_be_unique",
            },
        )

    def test_effect_is_async_exclusive_and_cancellable(self):
        denied_status, _ = self.request(
            "/v1/effects",
            method="POST",
            body={"effect": "pulse", "duration": "30s", "color": "red"},
        )
        started_status, started = self.request(
            "/v1/effects",
            token="test-token",
            method="POST",
            body={"effect": "pulse", "duration": "30s", "color": "red"},
        )
        self.wait_for_log("trick pulse 30s red")
        conflict_status, conflict = self.request(
            "/v1/effects",
            token="test-token",
            method="POST",
            body={"effect": "rainbow"},
        )
        cancelled_status, cancelled = self.request(
            "/v1/effects/current", token="test-token", method="DELETE"
        )

        self.assertEqual(401, denied_status)
        self.assertEqual(202, started_status)
        self.assertEqual(
            {"effect": "pulse", "duration": "30s", "color": "red"},
            started["active_effect"],
        )
        self.assertEqual(409, conflict_status)
        self.assertEqual("effect_already_active", conflict["error"])
        self.assertEqual(200, cancelled_status)
        self.assertEqual({"cancelled": True}, cancelled)
        self.assertIn("trick pulse 30s red", self.fake_log.read_text())
        self.assertIn("effect-restored", self.fake_log.read_text())

    def test_critical_notification_replaces_an_effect_until_cleared(self):
        self.request(
            "/v1/effects",
            token="test-token",
            method="POST",
            body={"effect": "rainbow", "duration": "30s"},
        )
        status, body = self.request(
            "/v1/notifications",
            token="test-token",
            method="POST",
            body={
                "level": "critical",
                "message": "UPS is on battery",
                "duration": "forever",
            },
        )

        self.assertEqual(202, status)
        self.assertEqual("pulse", body["active_effect"]["effect"])
        self.assertEqual("red", body["active_effect"]["color"])
        self.assertEqual("forever", body["active_effect"]["duration"])
        self.assertEqual(
            {"level": "critical", "message": "UPS is on battery"},
            body["active_effect"]["notification"],
        )
        self.wait_for_log("trick pulse forever red")

        recovered_status, recovered = self.request(
            "/v1/notifications",
            token="test-token",
            method="POST",
            body={
                "level": "resolved",
                "message": "Utility power restored",
                "duration": "10s",
            },
        )

        self.assertEqual(202, recovered_status)
        self.assertEqual("green", recovered["active_effect"]["color"])
        self.wait_for_log("trick pulse 10s green")

    def test_persistent_solid_mode_is_validated_and_applied(self):
        invalid_status, invalid = self.request(
            "/v1/mode",
            token="test-token",
            method="POST",
            body={"mode": "solid", "color": "cyan", "brightness": 999},
        )
        status, body = self.request(
            "/v1/mode",
            token="test-token",
            method="POST",
            body={"mode": "solid", "color": "cyan", "brightness": 120},
        )

        self.assertEqual(400, invalid_status)
        self.assertEqual("brightness_must_be_0_to_255", invalid["error"])
        self.assertEqual(200, status)
        self.assertEqual({"mode": "solid", "applied": True}, body)
        self.assertIn(
            "mode solid cyan --brightness 120",
            self.fake_log.read_text(),
        )

    def test_led_command_failure_returns_json_gateway_error(self):
        os.environ["UGREEN_LED_FAKE_FAIL"] = "1"
        try:
            status, body = self.request("/v1/status", token="test-token")
            mode_status, mode_body = self.request(
                "/v1/mode",
                token="test-token",
                method="POST",
                body={"mode": "resources"},
            )
        finally:
            os.environ.pop("UGREEN_LED_FAKE_FAIL", None)

        self.assertEqual(502, status)
        self.assertEqual({"error": "led_command_failed"}, body)
        self.assertEqual(502, mode_status)
        self.assertEqual({"error": "led_command_failed"}, mode_body)

    def test_effect_start_failure_returns_json_gateway_error(self):
        self.fake_led.unlink()

        status, body = self.request(
            "/v1/effects",
            token="test-token",
            method="POST",
            body={"effect": "rainbow"},
        )

        self.assertEqual(502, status)
        self.assertEqual({"error": "led_command_failed"}, body)

    def test_mode_finishes_before_a_concurrent_effect_starts(self):
        os.environ["UGREEN_LED_FAKE_MODE_DELAY"] = "0.3"
        mode_result = {}

        def apply_mode():
            mode_result["response"] = self.request(
                "/v1/mode",
                token="test-token",
                method="POST",
                body={"mode": "resources"},
            )

        mode_thread = threading.Thread(target=apply_mode)
        mode_thread.start()
        self.wait_for_log("mode resources")
        effect_status, _ = self.request(
            "/v1/effects",
            token="test-token",
            method="POST",
            body={"effect": "rainbow"},
        )
        mode_thread.join(timeout=2)
        os.environ.pop("UGREEN_LED_FAKE_MODE_DELAY", None)

        self.assertEqual(200, mode_result["response"][0])
        self.assertEqual(202, effect_status)
        self.wait_for_log("trick rainbow")
        log = self.fake_log.read_text()
        self.assertLess(log.index("mode-finished"), log.index("trick rainbow"))

    def test_forced_effect_kill_is_reported_as_restore_failure(self):
        os.environ["UGREEN_LED_FAKE_IGNORE_TERM"] = "1"
        self.server.effect_stop_timeout = 0.1
        self.request(
            "/v1/effects",
            token="test-token",
            method="POST",
            body={"effect": "rainbow", "duration": "forever"},
        )
        self.wait_for_log("trick rainbow forever")

        status, body = self.request(
            "/v1/effects/current", token="test-token", method="DELETE"
        )
        os.environ.pop("UGREEN_LED_FAKE_IGNORE_TERM", None)

        self.assertEqual(503, status)
        self.assertEqual({"error": "effect_restore_failed"}, body)

    def test_notification_rejects_control_characters(self):
        status, body = self.request(
            "/v1/notifications",
            token="test-token",
            method="POST",
            body={"level": "critical", "message": "UPS lost\nforged journal line"},
        )

        self.assertEqual(400, status)
        self.assertEqual("notification_message_contains_control_characters", body["error"])

    def test_slow_clients_are_bounded_and_rejected_when_workers_are_full(self):
        bounded_server = self.api.create_server(
            "127.0.0.1",
            0,
            "test-token",
            str(self.fake_led),
            max_request_workers=1,
            request_read_timeout=1,
        )
        bounded_thread = threading.Thread(
            target=bounded_server.serve_forever, daemon=True
        )
        bounded_thread.start()
        slow_client = socket.create_connection(
            ("127.0.0.1", bounded_server.server_port), timeout=1
        )
        slow_client.sendall(b"GET /v1/health HTTP/1.0\r\n")
        time.sleep(0.05)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{bounded_server.server_port}/v1/health",
                timeout=1,
            ) as response:
                status = response.status
                body = json.load(response)
        except urllib.error.HTTPError as error:
            status = error.code
            body = json.load(error)
        finally:
            slow_client.close()
            bounded_server.shutdown()
            bounded_server.server_close()
            bounded_thread.join(timeout=2)

        self.assertEqual(503, status)
        self.assertEqual({"error": "server_busy"}, body)


if __name__ == "__main__":
    unittest.main()
