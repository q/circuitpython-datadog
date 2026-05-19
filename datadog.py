# SPDX-FileCopyrightText: Copyright (c) 2026 Corey Bertram
# SPDX-License-Identifier: MIT

"""Small CircuitPython client for Datadog metrics intake.

Copy this file to ``CIRCUITPY/lib/datadog.py`` and pass in an already
configured ``adafruit_requests.Session``.
"""

import time


__version__ = "0.0.0+auto.0"
__repo__ = "https://github.com/your-name/CircuitPython_DataDog.git"

_TYPE_COUNT = 1
_TYPE_RATE = 2
_TYPE_GAUGE = 3


class DatadogClient:
    """Buffer metrics and send them to Datadog's v2 series endpoint."""

    def __init__(
        self,
        session,
        api_key,
        site="datadoghq.com",
        default_tags=None,
        max_retries=3,
        retry_delay=2,
    ):
        self.session = session
        self.api_key = api_key
        self.default_tags = default_tags or []
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._buffer = []

        site = self._normalize_site(site)
        if site.startswith("api."):
            host = site
        else:
            host = "api." + site

        self.url = "https://" + host + "/api/v2/series"
        self._headers = {
            "DD-API-KEY": api_key,
            "Content-Type": "application/json",
        }

    def gauge(self, metric, value, tags=None):
        """Buffer a gauge metric."""
        self._add_metric(metric, value, _TYPE_GAUGE, tags)

    def count(self, metric, value, tags=None):
        """Buffer a count metric."""
        self._add_metric(metric, value, _TYPE_COUNT, tags)

    def rate(self, metric, value, tags=None):
        """Buffer a rate metric."""
        self._add_metric(metric, value, _TYPE_RATE, tags)

    def flush(self):
        """Send buffered metrics.

        Returns ``True`` when Datadog accepts the payload, otherwise ``False``.
        This method never raises intentionally; on permanent failure it clears
        the buffer to avoid unbounded RAM growth in long-running loops.
        """
        if not self._buffer:
            return True

        payload = {"series": self._buffer}
        retries = self.max_retries
        if retries < 0:
            retries = 0

        attempt = 0
        while attempt <= retries:
            response = None
            try:
                response = self.session.post(
                    self.url,
                    headers=self._headers,
                    json=payload,
                )

                if self._status_ok(response.status_code):
                    self._buffer = []
                    return True

                # HTTP error status. The response is still closed below.
            except OSError:
                # Network/socket failure. Retry after cleanup.
                pass
            except Exception:
                # Keep sensor loops alive even for unexpected request failures.
                pass
            finally:
                if response is not None:
                    try:
                        response.close()
                    except Exception:
                        pass

            if attempt < retries:
                time.sleep(self.retry_delay)
            attempt += 1

        self._buffer = []
        return False

    def _add_metric(self, metric, value, metric_type, tags):
        point = {
            "timestamp": int(time.time()),
            "value": value,
        }
        item = {
            "metric": metric,
            "type": metric_type,
            "points": [point],
        }

        metric_tags = self._combined_tags(tags)
        if metric_tags:
            item["tags"] = metric_tags

        self._buffer.append(item)

    def _combined_tags(self, tags):
        if self.default_tags:
            if tags:
                return self.default_tags + tags
            return self.default_tags
        return tags

    def _normalize_site(self, site):
        if site.startswith("https://"):
            site = site[8:]
        elif site.startswith("http://"):
            site = site[7:]

        while site.endswith("/"):
            site = site[:-1]

        return site

    def _status_ok(self, status_code):
        return status_code >= 200 and status_code < 300
