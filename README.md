# circuitpython-datadog

[![Tests](https://github.com/q/circuitpython-datadog/actions/workflows/tests.yml/badge.svg)](https://github.com/q/circuitpython-datadog/actions/workflows/tests.yml)

A small CircuitPython 9.x library for sending custom
metrics to the Datadog HTTP API at `POST /api/v2/series`.

The library is designed for network-capable CircuitPython boards, including
boards with built-in WiFi, Ethernet, or a supported network coprocessor. It has
no runtime dependencies beyond `time` and the `adafruit_requests.Session` object
supplied by your own network setup code.

## Installation

Copy `datadog.py` to the `lib/` folder on your CircuitPython device:

```text
CIRCUITPY/
|-- code.py
`-- lib/
    `-- datadog.py
```

This repository follows the usual single-file CircuitPython library layout:

```text
circuitpython-datadog/
|-- datadog.py
|-- examples/
|   `-- basic_metrics.py
|-- tests/
|   `-- test_datadog.py
|-- README.md
`-- LICENSE
```

You are responsible for installing `adafruit_requests` and its required support
files on the device, and for connecting the network before creating the client.

## Usage

```python
import ssl
import socketpool
import wifi
import adafruit_requests
from datadog import DatadogClient

# This setup is for boards with built-in WiFi. If your board uses Ethernet
# or an external coprocessor, create the session for that network interface.
wifi.radio.connect("ssid", "password")
pool = socketpool.SocketPool(wifi.radio)
session = adafruit_requests.Session(pool, ssl.create_default_context())

client = DatadogClient(
    session,
    "DATADOG_API_KEY",
    site="datadoghq.com",
    default_tags=["runtime:circuitpython", "board:my-board"],
)

client.gauge("circuitpython.temperature", 24.5, tags=["room:lab"])
client.count("circuitpython.loop.count", 1)

if not client.flush():
    print("Datadog flush failed; continuing")
```

See `examples/basic_metrics.py` for a complete `code.py` style example.

## Constructor

```python
DatadogClient(
    session,
    api_key,
    site="datadoghq.com",
    default_tags=None,
    max_retries=3,
    retry_delay=2,
)
```

Parameters:

- `session`: an already configured `adafruit_requests.Session`.
- `api_key`: your Datadog API key string.
- `site`: Datadog site string used to build the intake host. The default is
  `datadoghq.com`, which sends to `https://api.datadoghq.com/api/v2/series`.
- `default_tags`: optional list of Datadog tag strings applied to every metric.
- `max_retries`: number of retry attempts after a failed request. The default
  is `3`, so `flush()` may try up to four total HTTP requests.
- `retry_delay`: seconds to wait between retry attempts using `time.sleep()`.

## Metrics

The client buffers metrics in RAM until `flush()` is called:

```python
client.gauge("sensor.temperature", 23.8)
client.count("button.press", 1, tags=["button:a"])
client.rate("sensor.samples_per_second", 2.0)
client.flush()
```

Pass `timestamp=` to use an explicit Unix timestamp instead of `time.time()`:

```python
client.gauge("sensor.temperature", 23.8, timestamp=1710000123)
```

`flush()` returns `True` when Datadog accepts the payload with a 2xx HTTP status.
It returns `False` on network errors, socket errors, HTTP error status codes, or
unexpected request failures. It never intentionally raises an exception, and it
clears the buffer after permanent failure to avoid memory buildup in sensor
loops.

Each request response is closed with `response.close()`.

## Testing

The core client can be tested on desktop Python because network access is
injected through the `session` object:

```sh
python3 -B -m unittest discover -s tests
```

The tests use fake sessions and responses. They validate payload shape, retry
behavior, response cleanup, URL construction, and buffer clearing without making
real network requests.

## Supported Datadog Sites

Pass the site hostname for your Datadog account:

- `datadoghq.com`
- `datadoghq.eu`
- `us3.datadoghq.com`
- `us5.datadoghq.com`
- `ap1.datadoghq.com`
- `ap2.datadoghq.com`
- `ddog-gov.com`

The client prepends `api.` when needed, so `us3.datadoghq.com` becomes
`https://api.us3.datadoghq.com/api/v2/series`.

## Notes

- Network setup, TLS setup, NTP/RTC time setup, and the requests session are
  caller responsibilities.
- Datadog expects metric timestamps to be close to current Unix time. If your
  board does not have correct time after boot, set the RTC before sending
  metrics.
- This library does not use threading, asyncio, subprocesses, or environment
  variables.
