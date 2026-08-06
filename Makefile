BACKEND_DIR := vendor/ugreen_leds_controller/cli

.PHONY: all backend test clean

all: backend

backend:
	$(MAKE) -C $(BACKEND_DIR)
	cp $(BACKEND_DIR)/ugreen_leds_cli ./ugreen_leds_cli

test:
	bash -n led install.sh uninstall.sh tests/*.sh
	python3 -m py_compile api/ugreen_led_api.py tests/test_api.py tests/test_telemetry_priority.py
	python3 -m unittest tests/test_api.py tests/test_telemetry_priority.py
	bash tests/smoke.sh
	bash tests/install.sh

clean:
	$(MAKE) -C $(BACKEND_DIR) clean
	rm -f ugreen_leds_cli
