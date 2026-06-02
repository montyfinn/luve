"""T7c-2: focused tests for the flag-gated outbox relay.

Fake DB pool/conn and fake publish are used, so no real DB/RabbitMQ is needed.
The default-off behavior, the claim-inside-transaction contract, publish
success/failure marking, empty batches, persistent messages, and config parsing
are all exercised without Docker.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import aio_pika

import src.worker as w


# ---- fakes ---------------------------------------------------------------

class _FakeConn:
    def __init__(self) -> None:
        self.in_txn = False

    def transaction(self):
        conn = self

        class _Txn:
            async def __aenter__(self_):
                conn.in_txn = True
                return None

            async def __aexit__(self_, *a):
                conn.in_txn = False
                return False

        return _Txn()


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(self_):
                return conn

            async def __aexit__(self_, *a):
                return False

        return _Acq()


def _wire(monkeypatch, *, rows, publish_raises=False):
    order: list = []
    conn = _FakeConn()
    pool = _FakePool(conn)

    async def fake_claim(c, limit):
        order.append(("claim", c.in_txn, limit))
        return rows

    async def fake_publish(channel, body, *, timeout):
        order.append(("publish", bytes(body), timeout))
        if publish_raises:
            raise RuntimeError("broker down")

    async def fake_mark_pub(c, outbox_id):
        order.append(("mark_published", outbox_id))

    async def fake_mark_retry(c, outbox_id, error, max_attempts):
        order.append(("mark_retry", outbox_id, max_attempts))

    monkeypatch.setattr(w, "claim_pending_session_events", fake_claim)
    monkeypatch.setattr(w, "_publish_outbox_message", fake_publish)
    monkeypatch.setattr(w, "mark_session_event_published", fake_mark_pub)
    monkeypatch.setattr(w, "mark_session_event_retry_or_failed", fake_mark_retry)
    return pool, order


# ---- main() routing (flag gate) -----------------------------------------

def test_main_flag_off_runs_consumer_only(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(coro):
        captured["name"] = coro.__name__
        coro.close()

    monkeypatch.setattr(w.asyncio, "run", fake_run)
    monkeypatch.setattr(w, "_get_outbox_relay_enabled", lambda: False)
    w.main()
    assert captured["name"] == "consume_forever"


def test_main_flag_on_runs_consumer_and_relay(monkeypatch) -> None:
    captured: dict = {}

    def fake_run(coro):
        captured["name"] = coro.__name__
        coro.close()

    monkeypatch.setattr(w.asyncio, "run", fake_run)
    monkeypatch.setattr(w, "_get_outbox_relay_enabled", lambda: True)
    w.main()
    assert captured["name"] == "_run_consumer_with_relay"


# ---- relay drain --------------------------------------------------------

def test_relay_drain_publishes_then_marks_inside_txn(monkeypatch) -> None:
    rows = [{"id": "o-1", "payload": '{"event_type":"session.completed"}'}]
    pool, order = _wire(monkeypatch, rows=rows)
    n = asyncio.run(
        w._relay_drain_once(pool, object(), batch_size=10, max_attempts=5, publish_timeout=10.0)
    )
    assert n == 1
    # claim ran INSIDE the transaction (in_txn True) with the batch limit
    assert ("claim", True, 10) in order
    # order: claim -> publish -> mark_published; no retry
    assert [x[0] for x in order] == ["claim", "publish", "mark_published"]
    # body is the outbox payload bytes
    pub = next(x for x in order if x[0] == "publish")
    assert pub[1] == b'{"event_type":"session.completed"}'
    assert pub[2] == 10.0  # publish timeout forwarded


def test_relay_drain_publish_failure_marks_retry_not_published(monkeypatch) -> None:
    rows = [{"id": "o-2", "payload": "{}"}]
    pool, order = _wire(monkeypatch, rows=rows, publish_raises=True)
    n = asyncio.run(
        w._relay_drain_once(pool, object(), batch_size=10, max_attempts=3, publish_timeout=10.0)
    )
    assert n == 0
    names = [x[0] for x in order]
    assert "mark_retry" in names
    assert "mark_published" not in names
    retry = next(x for x in order if x[0] == "mark_retry")
    assert retry[1] == "o-2" and retry[2] == 3


def test_relay_drain_empty_batch_no_publish(monkeypatch) -> None:
    pool, order = _wire(monkeypatch, rows=[])
    n = asyncio.run(
        w._relay_drain_once(pool, object(), batch_size=10, max_attempts=5, publish_timeout=10.0)
    )
    assert n == 0
    assert [x[0] for x in order] == ["claim"]  # claimed, nothing to publish


# ---- publisher produces a persistent message ----------------------------

def test_publish_uses_persistent_message_and_routing_key(monkeypatch) -> None:
    captured: dict = {}

    async def fake_exchange_publish(message, routing_key=None):
        captured["message"] = message
        captured["routing_key"] = routing_key

    channel = MagicMock()
    channel.default_exchange.publish = fake_exchange_publish
    asyncio.run(w._publish_outbox_message(channel, b'{"x":1}', timeout=5.0))

    msg = captured["message"]
    assert msg.body == b'{"x":1}'
    assert msg.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert captured["routing_key"] == w.QUEUE_NAME


# ---- config parsing -----------------------------------------------------

def test_relay_config_defaults_and_parsing(monkeypatch) -> None:
    monkeypatch.delenv("OUTBOX_RELAY_ENABLED", raising=False)
    assert w._get_outbox_relay_enabled() is False
    for v in ("true", "1", "yes", "on", "TRUE"):
        monkeypatch.setenv("OUTBOX_RELAY_ENABLED", v)
        assert w._get_outbox_relay_enabled() is True
    for v in ("false", "0", "no", "", "  "):
        monkeypatch.setenv("OUTBOX_RELAY_ENABLED", v)
        assert w._get_outbox_relay_enabled() is False

    monkeypatch.delenv("OUTBOX_RELAY_POLL_INTERVAL_SECONDS", raising=False)
    assert w._get_outbox_relay_poll_interval_seconds() == 5.0
    monkeypatch.setenv("OUTBOX_RELAY_POLL_INTERVAL_SECONDS", "notanumber")
    assert w._get_outbox_relay_poll_interval_seconds() == 5.0  # safe fallback

    monkeypatch.setenv("OUTBOX_RELAY_BATCH_SIZE", "bad")
    assert w._get_outbox_relay_batch_size() == 20
    monkeypatch.setenv("OUTBOX_RELAY_MAX_ATTEMPTS", "bad")
    assert w._get_outbox_relay_max_attempts() == 5
    monkeypatch.setenv("OUTBOX_RELAY_PUBLISH_TIMEOUT_SECONDS", "bad")
    assert w._get_outbox_relay_publish_timeout_seconds() == 10.0
