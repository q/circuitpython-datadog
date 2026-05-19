# SPDX-FileCopyrightText: Copyright (c) 2026 Corey Bertram
# SPDX-License-Identifier: MIT

"""code.py style example for CircuitPython ESP32 boards.

Create a secrets.py file on CIRCUITPY with:

secrets = {
    "ssid": "your-wifi",
    "password": "your-password",
    "datadog_api_key": "your-api-key",
    "datadog_site": "datadoghq.com",
}
"""

import time
import ssl
import board
import microcontroller
import socketpool
import wifi
import adafruit_requests

from datadog import DatadogClient
from secrets import secrets


FLUSH_INTERVAL = 60
SAMPLE_INTERVAL = 5


print("Connecting to WiFi...")
wifi.radio.connect(secrets["ssid"], secrets["password"])
print("Connected:", wifi.radio.ipv4_address)

pool = socketpool.SocketPool(wifi.radio)
session = adafruit_requests.Session(pool, ssl.create_default_context())

default_tags = [
    "runtime:circuitpython",
    "board:%s" % board.board_id,
]

client = DatadogClient(
    session,
    secrets["datadog_api_key"],
    site=secrets.get("datadog_site", "datadoghq.com"),
    default_tags=default_tags,
    max_retries=3,
    retry_delay=2,
)

last_flush = time.monotonic()

while True:
    now = time.monotonic()

    client.gauge(
        "circuitpython.cpu.temperature",
        microcontroller.cpu.temperature,
        tags=["source:esp32"],
    )
    client.gauge("circuitpython.uptime", now)

    if now - last_flush >= FLUSH_INTERVAL:
        if not client.flush():
            print("Datadog flush failed; metrics were dropped")
        last_flush = time.monotonic()

    time.sleep(SAMPLE_INTERVAL)
