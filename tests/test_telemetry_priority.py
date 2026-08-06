#!/usr/bin/env python3
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_PATH = REPOSITORY_ROOT / "api" / "ugreen_led_api.py"
LED_PATH = REPOSITORY_ROOT / "led"
FAKE_BACKEND = REPOSITORY_ROOT / "tests" / "fake-backend.sh"


def load_api_module():
    spec = importlib.util.spec_from_file_location("ugreen_led_api_priority", API_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TelemetryPriorityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = load_api_module()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.telemetry_file = self.root / "telemetry.env"
        self.state_file = self.root / "state.tsv"
        self.service_state = self.root / "service-state"
        self.service_state.write_text("active\n")
        self.config_file = self.root / "led.conf"
        self.config_file.write_text(
            (REPOSITORY_ROOT / "config.example").read_text()
        )
        fake_bin = self.root / "bin"
        fake_bin.mkdir()
        fake_systemctl = fake_bin / "systemctl"
        fake_systemctl.write_text(
            "#!/usr/bin/env bash\n"
            "case \"$1\" in\n"
            "  is-active) [ \"$(cat \"$UGREEN_LED_FAKE_SERVICE_STATE\")\" = active ] ;;\n"
            "  stop) printf 'inactive\\n' > \"$UGREEN_LED_FAKE_SERVICE_STATE\" ;;\n"
            "  start|restart)\n"
            "    printf 'active\\n' > \"$UGREEN_LED_FAKE_SERVICE_STATE\"\n"
            "    (UGREEN_LED_SKIP_SYSTEMD=1 UGREEN_LED_ONCE=1 \"$UGREEN_LED_REAL_COMMAND\" mode resources >/dev/null 2>&1) &\n"
            "    ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n"
        )
        fake_systemctl.chmod(0o755)
        self.saved_environment = dict(os.environ)
        os.environ.update(
            {
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "UGREEN_LED_ALLOW_NONROOT": "1",
                "UGREEN_LED_SKIP_SYSTEMD": "0",
                "UGREEN_LED_CONFIG": str(self.config_file),
                "UGREEN_LED_BACKEND": str(FAKE_BACKEND),
                "UGREEN_LED_FAKE_STATE": str(self.state_file),
                "UGREEN_LED_FAKE_SERVICE_STATE": str(self.service_state),
                "UGREEN_LED_REAL_COMMAND": str(LED_PATH),
                "UGREEN_LED_LOCK": str(self.root / "led.lock"),
                "UGREEN_LED_MANUAL_FILE": str(self.root / "manual.tsv"),
                "UGREEN_LED_TELEMETRY_FILE": str(self.telemetry_file),
                "UGREEN_LED_TEST_CPU_PCT": "10",
                "UGREEN_LED_TEST_MEMORY_PCT": "10",
                "UGREEN_LED_TEST_IOWAIT_PCT": "0",
                "UGREEN_LED_TEST_ROOT_PCT": "10",
                "UGREEN_LED_TEST_TEMP_C": "50",
                "UGREEN_LED_TEST_NETWORK_SPEED": "2500",
                "UGREEN_LED_TEST_GATEWAY": "1",
                "UGREEN_LED_TEST_HEALTH": "1",
            }
        )
        self.server = self.api.create_server(
            "127.0.0.1",
            0,
            "test-token",
            str(LED_PATH),
            telemetry_file=str(self.telemetry_file),
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.stop_active_effect()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        os.environ.clear()
        os.environ.update(self.saved_environment)
        self.temporary.cleanup()

    def post(self, path, body):
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=4) as response:
            return response.status, json.load(response)

    def telemetry(self, disk1_temperature):
        return {
            "source": "unraid",
            "array": {
                "state": "STARTED",
                "health": "ONLINE",
                "usage_percent": 20,
            },
            "disks": [
                {
                    "slot": slot,
                    "name": "main" if slot == 1 else f"main{slot}",
                    "device": f"sd{chr(97 + slot)}",
                    "temperature_c": disk1_temperature if slot == 1 else 34,
                    "status": "OK",
                }
                for slot in range(1, 5)
            ],
        }

    def disk1_state(self):
        for line in self.state_file.read_text().splitlines():
            fields = line.split("\t")
            if fields[0] == "disk1":
                return fields
        self.fail("disk1 was absent from fake LED state")

    def wait_for_disk1_color(self, expected):
        for _attempt in range(80):
            if self.state_file.exists() and self.disk1_state()[3:6] == expected:
                return
            time.sleep(0.05)
        self.fail(f"disk1 did not reach RGB {expected}; state={self.disk1_state()}")

    def test_notification_preempts_and_restores_latest_unraid_telemetry(self):
        self.post("/v1/telemetry", self.telemetry(34))
        subprocess.run(
            [str(LED_PATH), "mode", "resources"],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "UGREEN_LED_SKIP_SYSTEMD": "1", "UGREEN_LED_ONCE": "1"},
        )
        self.assertEqual(["0", "255", "0"], self.disk1_state()[3:6])
        self.assertEqual("131", self.disk1_state()[2])

        self.post(
            "/v1/notifications",
            {"level": "critical", "message": "UPS on battery", "duration": "forever"},
        )
        self.wait_for_disk1_color(["255", "0", "0"])
        self.post("/v1/telemetry", self.telemetry(47))
        self.post(
            "/v1/notifications",
            {"level": "resolved", "message": "Utility restored", "duration": "1s"},
        )
        self.wait_for_disk1_color(["0", "255", "0"])
        for _attempt in range(80):
            if self.server.active_effect() is None:
                break
            time.sleep(0.05)
        else:
            self.fail("resolved notification did not finish")
        self.wait_for_disk1_color(["255", "96", "0"])
        time.sleep(0.2)
        self.assertEqual(["255", "96", "0"], self.disk1_state()[3:6])


if __name__ == "__main__":
    unittest.main()
