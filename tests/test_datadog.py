import os
import sys
import unittest


sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import datadog


class FakeResponse:
    def __init__(self, status_code, close_raises=False):
        self.status_code = status_code
        self.closed = False
        self.close_raises = close_raises

    def close(self):
        self.closed = True
        if self.close_raises:
            raise RuntimeError("close failed")


class FakeSession:
    def __init__(self, events=None):
        self.events = events or []
        self.posts = []
        self.responses = []

    def post(self, url, headers=None, json=None):
        self.posts.append({
            "url": url,
            "headers": headers,
            "json": json,
        })

        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        if isinstance(event, FakeResponse):
            response = event
        else:
            response = FakeResponse(event)

        self.responses.append(response)
        return response


class DatadogClientTest(unittest.TestCase):
    def setUp(self):
        self._old_time = datadog.time.time
        self._old_sleep = datadog.time.sleep
        self.sleeps = []
        datadog.time.time = lambda: 1710000000
        datadog.time.sleep = self.sleeps.append

    def tearDown(self):
        datadog.time.time = self._old_time
        datadog.time.sleep = self._old_sleep

    def test_builds_metric_payloads_with_types_and_tags(self):
        session = FakeSession([202])
        client = datadog.DatadogClient(
            session,
            "api-key",
            default_tags=["env:test"],
        )

        client.gauge("sensor.temperature", 22.5, tags=["room:lab"])
        client.count("button.press", 1)
        client.rate("sensor.samples_per_second", 2.0)

        self.assertTrue(client.flush())
        series = session.posts[0]["json"]["series"]

        self.assertEqual(series[0]["metric"], "sensor.temperature")
        self.assertEqual(series[0]["type"], 3)
        self.assertEqual(series[0]["points"], [{
            "timestamp": 1710000000,
            "value": 22.5,
        }])
        self.assertEqual(series[0]["tags"], ["env:test", "room:lab"])

        self.assertEqual(series[1]["metric"], "button.press")
        self.assertEqual(series[1]["type"], 1)
        self.assertEqual(series[1]["tags"], ["env:test"])

        self.assertEqual(series[2]["metric"], "sensor.samples_per_second")
        self.assertEqual(series[2]["type"], 2)
        self.assertEqual(series[2]["tags"], ["env:test"])

    def test_accepts_explicit_metric_timestamps(self):
        session = FakeSession([202])
        client = datadog.DatadogClient(session, "api-key")

        client.gauge("sensor.temperature", 22.5, timestamp=1710000123)
        client.count("button.press", 1, timestamp=1710000124)
        client.rate("sensor.samples_per_second", 2.0, timestamp=1710000125)

        self.assertTrue(client.flush())
        series = session.posts[0]["json"]["series"]
        self.assertEqual(series[0]["points"][0]["timestamp"], 1710000123)
        self.assertEqual(series[1]["points"][0]["timestamp"], 1710000124)
        self.assertEqual(series[2]["points"][0]["timestamp"], 1710000125)

    def test_constructs_datadog_site_urls(self):
        cases = (
            ("datadoghq.com", "https://api.datadoghq.com/api/v2/series"),
            ("datadoghq.eu", "https://api.datadoghq.eu/api/v2/series"),
            ("us3.datadoghq.com", "https://api.us3.datadoghq.com/api/v2/series"),
            (
                "https://api.us5.datadoghq.com/",
                "https://api.us5.datadoghq.com/api/v2/series",
            ),
        )

        for site, expected_url in cases:
            client = datadog.DatadogClient(FakeSession(), "api-key", site=site)
            self.assertEqual(client.url, expected_url)

    def test_flush_success_closes_response_and_clears_buffer(self):
        session = FakeSession([202])
        client = datadog.DatadogClient(session, "api-key")
        client.gauge("sensor.temperature", 22.5)

        self.assertTrue(client.flush())
        self.assertEqual(client._buffer, [])
        self.assertEqual(len(session.posts), 1)
        self.assertTrue(session.responses[0].closed)
        self.assertEqual(session.posts[0]["headers"]["DD-API-KEY"], "api-key")

    def test_flush_http_errors_retry_then_clear_buffer(self):
        session = FakeSession([500, 503, 400])
        client = datadog.DatadogClient(
            session,
            "api-key",
            max_retries=2,
            retry_delay=5,
        )
        client.count("button.press", 1)

        self.assertFalse(client.flush())
        self.assertEqual(len(session.posts), 3)
        self.assertEqual(self.sleeps, [5, 5])
        self.assertEqual(client._buffer, [])
        for response in session.responses:
            self.assertTrue(response.closed)

    def test_flush_network_error_retries_and_can_succeed(self):
        session = FakeSession([OSError("socket down"), 202])
        client = datadog.DatadogClient(
            session,
            "api-key",
            max_retries=1,
            retry_delay=2,
        )
        client.gauge("sensor.temperature", 22.5)

        self.assertTrue(client.flush())
        self.assertEqual(len(session.posts), 2)
        self.assertEqual(self.sleeps, [2])
        self.assertEqual(client._buffer, [])
        self.assertTrue(session.responses[0].closed)

    def test_flush_never_raises_on_unexpected_request_failure(self):
        session = FakeSession([RuntimeError("request failed")])
        client = datadog.DatadogClient(session, "api-key", max_retries=0)
        client.gauge("sensor.temperature", 22.5)

        self.assertFalse(client.flush())
        self.assertEqual(client._buffer, [])

    def test_flush_never_raises_when_response_close_fails(self):
        session = FakeSession([FakeResponse(500, close_raises=True)])
        client = datadog.DatadogClient(session, "api-key", max_retries=0)
        client.gauge("sensor.temperature", 22.5)

        self.assertFalse(client.flush())
        self.assertEqual(client._buffer, [])
        self.assertTrue(session.responses[0].closed)

    def test_flush_empty_buffer_returns_true_without_posting(self):
        session = FakeSession()
        client = datadog.DatadogClient(session, "api-key")

        self.assertTrue(client.flush())
        self.assertEqual(session.posts, [])


if __name__ == "__main__":
    unittest.main()
