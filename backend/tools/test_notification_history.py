"""Exercise notifier against real PostgreSQL and a local Web Push HTTP receiver.

Run from the repository root (PowerShell):
  Get-Content -Raw backend/tools/test_notification_history.py | docker compose exec -T api python -

Only synthetic subscriptions are selected. All database writes are rolled back.
VAPID and subscription keys are ephemeral and never printed or saved.
"""
import asyncio
import base64
import json
import logging
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import asyncpg
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.core import config
from app.domain.forecast import Forecast
from app.workers import notifier


def b64(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


async def main():
    logging.disable(logging.CRITICAL)
    conn = await asyncpg.connect(config.DATABASE_URL)
    transaction = conn.transaction()
    await transaction.start()
    marker = 'notification-test-' + uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    received = []
    server_errors = []
    selected = []
    response_status = 201

    class TestDatabase:
        def __init__(self):
            self.connection_held = False
            self.fail_inserts = False
            self.inserts_until_failure = None
            self.fail_updates = 0
            self.update_attempts = 0

        @asynccontextmanager
        async def acquire(self, **kwargs):
            # Keep every operation, including advisory-locked reservations, test-only.
            self.connection_held = True
            try:
                yield self
            finally:
                self.connection_held = False

        def transaction(self):
            return conn.transaction()

        async def fetch(self, query, *args):
            assert 'FROM push_subscriptions' in query
            return await conn.fetch(
                'SELECT endpoint, keys, quiet_start, quiet_end FROM push_subscriptions '
                'WHERE endpoint = ANY($1::text[]) ORDER BY endpoint', selected)

        async def fetchrow(self, query, *args):
            return await conn.fetchrow(query, *args)

        async def fetchval(self, query, *args):
            if 'INSERT INTO notification_history' in query:
                if self.fail_inserts or self.inserts_until_failure == 0:
                    raise RuntimeError('synthetic history insertion failure')
                if self.inserts_until_failure is not None:
                    self.inserts_until_failure -= 1
            return await conn.fetchval(query, *args)

        async def execute(self, query, *args):
            if 'WHERE id = $1' in query:
                self.update_attempts += 1
                if self.fail_updates:
                    self.fail_updates -= 1
                    raise RuntimeError('synthetic history update failure')
            return await conn.execute(query, *args)

    test_db = TestDatabase()

    class Receiver(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                assert not test_db.connection_held, 'HTTP must not hold a pooled DB connection'
                body = self.rfile.read(int(self.headers['Content-Length']))
                assert body and self.headers.get('Content-Encoding') == 'aes128gcm'
                assert self.headers.get('Authorization', '').startswith('vapid ')
                pending = asyncio.run_coroutine_threadsafe(conn.fetchval(
                    "SELECT count(*) FROM notification_history WHERE device_id=$1 AND endpoint=$2 AND status='PENDING'",
                    marker, f'http://127.0.0.1:{server.server_port}{self.path}'), loop).result(timeout=3)
                assert pending == 1, 'PENDING must exist before the HTTP request'
                received.append(self.path)
                self.send_response(response_status)
                self.end_headers()
            except Exception as exc:
                server_errors.append(type(exc).__name__)
                self.send_response(500)
                self.end_headers()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}/{marker}'
    subscription_key = ec.generate_private_key(ec.SECP256R1())
    keys = json.dumps({
        'p256dh': b64(subscription_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)),
        'auth': b64(uuid.uuid4().bytes),
    })
    vapid_key = b64(ec.generate_private_key(ec.SECP256R1()).private_numbers().private_value.to_bytes(32, 'big'))

    async def prepare(count=1, quiet=False, bad_keys=False):
        nonlocal selected
        await conn.execute('DELETE FROM notification_history WHERE device_id=$1', marker)
        await conn.execute('DELETE FROM push_subscriptions WHERE endpoint LIKE $1', base + '%')
        selected = [base + '/' + str(i) for i in range(count)]
        hour = notifier.datetime.now(config.TZ).hour
        for endpoint in selected:
            await conn.execute(
                'INSERT INTO push_subscriptions(endpoint, keys, quiet_start, quiet_end) VALUES ($1,$2,$3,$4)',
                endpoint, '{}' if bad_keys else keys, hour if quiet else 0, (hour+1) % 24 if quiet else 0)

    async def check(statuses, kind='STATE'):
        rows = await conn.fetch(
            'SELECT status, sent_at, error, notification_type FROM notification_history '
            'WHERE device_id=$1 ORDER BY endpoint, id', marker)
        assert [r['status'] for r in rows] == statuses
        for row in rows:
            assert row['notification_type'] == kind
            assert (row['sent_at'] is not None) == (row['status'] == 'SENT')
            assert bool(row['error']) == (
                row['status'] in ('FAILED', 'UNKNOWN')
            )
        assert not server_errors, server_errors

    async def send():
        return await notifier.send('integration test', 'local receiver', '/',
                                   device_id=marker, notification_type='STATE')

    try:
        migration_sql = (Path('/srv/app/db/migrations') / '001_notification_history.sql').read_text()
        for old_schema in (False, True):
            migration_test = conn.transaction()
            await migration_test.start()
            try:
                schema = 'migration_' + uuid.uuid4().hex
                await conn.execute(f'CREATE SCHEMA {schema}')
                await conn.execute(f'SET LOCAL search_path TO {schema}')
                await conn.execute('CREATE TABLE devices(id text PRIMARY KEY)')
                if old_schema:
                    await conn.execute("""CREATE TABLE notification_history (
                        id bigserial PRIMARY KEY, device_id text NOT NULL REFERENCES devices(id),
                        endpoint text NOT NULL, notification_type text NOT NULL,
                        status text DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENT','FAILED')),
                        created_at timestamptz DEFAULT now(), sent_at timestamptz, error text)""")
                    await conn.execute("INSERT INTO devices VALUES ('existing')")
                    await conn.execute("INSERT INTO notification_history(device_id,endpoint,notification_type) VALUES('existing','local','FORECAST')")
                await conn.execute(migration_sql)
                await conn.execute(migration_sql)
                assert await conn.fetchval(
                    "SELECT count(*) FROM information_schema.columns WHERE table_schema=$1 AND table_name='notification_history' AND column_name='dispatch_id'", schema) == 1
                if old_schema:
                    assert await conn.fetchval('SELECT count(*) FROM notification_history') == 1
                    await conn.execute("UPDATE notification_history SET status='UNKNOWN'")
            finally:
                await migration_test.rollback()
        print('PASS: migration initializes empty and upgrades old notification schemas; repeat-safe and preserves rows')

        await conn.execute('INSERT INTO homes(id) VALUES ($1)', marker)
        await conn.execute('INSERT INTO devices(id,home_id) VALUES ($1,$1)', marker)
        with patch.object(notifier, 'db', return_value=test_db), \
             patch.object(config, 'VAPID_PRIVATE_KEY', vapid_key), \
             patch.object(config, 'VAPID_SUBJECT', 'mailto:test@example.com'):
            await prepare()
            assert await send() is True
            await check(['SENT'])
            print('PASS: real encrypted HTTP 201, PENDING -> SENT and sent_at')

            for code in [500, 404, 410]:
                response_status = code
                await prepare()
                assert await send() is False
                await check(['FAILED'])
                remaining = await conn.fetchval('SELECT count(*) FROM push_subscriptions WHERE endpoint=$1', selected[0])
                assert remaining == (1 if code == 500 else 0)
                print(f'PASS: HTTP {code}, FAILED/error and subscription retention/deletion')

            response_status = 201
            await prepare(quiet=True)
            before = len(received)
            assert await send() is False
            await check([])
            assert len(received) == before
            await notifier.on_state(
                marker, 'ALERT', 'CONDENSING', datetime.now(UTC)
            )
            await check(['SENT'])
            print('PASS: quiet hours skip; CONDENSING bypass and STATE arguments')

            await prepare(bad_keys=True)
            assert await send() is False
            await check(['FAILED'])
            print('PASS: invalid subscription keys -> FAILED')

            await prepare()
            with patch.object(notifier, 'webpush', side_effect=TimeoutError('synthetic timeout')):
                assert await send() is False
            await check(['UNKNOWN'])
            print('PASS: timeout exception -> UNKNOWN')

            await prepare(2)
            await conn.execute('UPDATE push_subscriptions SET keys=$2 WHERE endpoint=$1', selected[1], '{}')
            assert await send() is True
            await check(['SENT', 'FAILED'])
            print('PASS: mixed success/failure -> True with separate history rows')

            await prepare()
            with patch.object(config, 'VAPID_PRIVATE_KEY', ''):
                assert await send() is False
            await check([])
            print('PASS: missing VAPID -> False without history')

            await prepare(0)
            assert await send() is False
            await check([])
            print('PASS: no subscribers -> False without history')

            fc = Forecast(80, 0.5, 1.0, 2.0, 0.9)
            await prepare()
            response_status = 500
            await notifier.on_forecast(marker, 'SAFE', fc)
            await check(['FAILED'], 'FORECAST')
            # Preserve the failure: a retry must be allowed despite its history.
            response_status = 201
            await notifier.on_forecast(marker, 'SAFE', fc)
            await check(['FAILED', 'SENT'], 'FORECAST')
            before = len(received)
            await notifier.on_forecast(marker, 'SAFE', fc)
            assert len(received) == before
            await check(['FAILED', 'SENT'], 'FORECAST')
            print('PASS: failed FORECAST does not consume quota; successful retry blocks repeats')

            await prepare(3)
            await notifier.on_forecast(marker, 'SAFE', fc)
            await check(['SENT'] * 3, 'FORECAST')
            batches = await conn.fetchval(
                'SELECT count(DISTINCT dispatch_id) FROM notification_history WHERE device_id=$1', marker)
            assert batches == 1
            assert await conn.fetchval(
                'SELECT count(*) FROM notification_history WHERE device_id=$1 AND dispatch_id IS NULL', marker) == 0
            # Discard process-local locks to simulate losing memory at restart.
            notifier._forecast_locks.pop(marker, None)
            before = len(received)
            await notifier.on_forecast(marker, 'SAFE', fc)
            assert len(received) == before
            print('PASS: three subscribers count as one dispatch; DB quota survives memory reset')

            await conn.execute(
                "UPDATE notification_history SET sent_at=now()-interval '4 hours' WHERE device_id=$1", marker)
            await notifier.on_forecast(marker, 'SAFE', fc)
            assert len(received) == before + 3
            assert await conn.fetchval(
                'SELECT count(DISTINCT dispatch_id) FROM notification_history WHERE device_id=$1', marker) == 2
            await conn.execute(
                "UPDATE notification_history SET sent_at=now()-interval '4 hours' WHERE device_id=$1", marker)
            before = len(received)
            await notifier.on_forecast(marker, 'SAFE', fc)
            assert len(received) == before
            print('PASS: second dispatch after 3 hours allowed; third within 24 hours blocked')

            await conn.execute(
                "UPDATE notification_history SET sent_at=now()-interval '25 hours' WHERE device_id=$1", marker)
            await notifier.on_forecast(marker, 'SAFE', fc)
            assert len(received) == before + 3
            print('PASS: expired successful history does not consume quota')

            for minutes, expected in [(16, 'UNKNOWN'), (5, 'PENDING')]:
                await prepare()
                history_id = await conn.fetchval(
                    """INSERT INTO notification_history
                           (device_id, endpoint, notification_type, dispatch_id, created_at)
                       VALUES ($1, $2, 'FORECAST', $3,
                               now() - $4::int * interval '1 minute')
                       RETURNING id""",
                    marker, selected[0], uuid.uuid4(), minutes)
                before = len(received)
                await notifier.on_forecast(marker, 'SAFE', fc)
                assert len(received) == before
                await check([expected], 'FORECAST')
                assert await conn.fetchval(
                    'SELECT status FROM notification_history WHERE id=$1', history_id) == expected
            print('PASS: old PENDING becomes UNKNOWN; recent PENDING preserved; both block repeat')

            await prepare()
            with patch.object(notifier, 'webpush', side_effect=TimeoutError('synthetic timeout')):
                await notifier.on_forecast(marker, 'SAFE', fc)
            await check(['UNKNOWN'], 'FORECAST')
            before = len(received)
            await notifier.on_forecast(marker, 'SAFE', fc)
            assert len(received) == before
            await check(['UNKNOWN'], 'FORECAST')
            print('PASS: UNKNOWN forecast timeout consumes quota and is not automatically resent')

            await prepare()
            before = len(received)
            await notifier.on_state(marker, 'CONDENSING', 'ALERT', datetime.now(UTC))
            await notifier.on_state(marker, 'SAFE', 'WATCH', datetime.now(UTC))
            await notifier.on_state(marker, 'ALERT', 'ALERT', datetime.now(UTC))
            await check([])
            assert len(received) == before
            print('PASS: improving, WATCH and unchanged states do not send notifications')

            await prepare()
            test_db.fail_inserts = True
            before = len(received)
            try:
                assert await send() is False
                await check([])
                assert len(received) == before
            finally:
                test_db.fail_inserts = False
            print('PASS: history insertion failure prevents unrecorded delivery and quota bypass')

            await prepare(2)
            test_db.inserts_until_failure = 1
            before = len(received)
            try:
                assert await send() is False
                assert len(received) == before
                await check([])
            finally:
                test_db.inserts_until_failure = None
            print('PASS: partial reservation failure rolls back all rows before any HTTP delivery')


            await prepare()
            test_db.fail_updates = 2
            before = test_db.update_attempts
            assert await send() is True
            assert test_db.update_attempts == before + 3
            await check(['SENT'])
            print('PASS: transient history update errors retry without repeating push')

            await prepare()
            test_db.fail_updates = 3
            assert await send() is True
            await check(['PENDING'])
            await conn.execute(
                "UPDATE notification_history SET created_at=now()-interval '16 minutes' WHERE device_id=$1", marker)
            await notifier.reconcile_history(test_db)
            await check(['UNKNOWN'])
            print('PASS: exhausted retries remain PENDING, then global recovery marks UNKNOWN')

            await prepare()
            from requests.exceptions import ConnectionError
            with patch.object(notifier, 'webpush', side_effect=ConnectionError('synthetic disconnect')):
                assert await send() is False
            await check(['UNKNOWN'])
            print('PASS: transport connection errors preserve uncertain delivery as UNKNOWN')

            await prepare()
            started = asyncio.Event()
            release = threading.Event()
            real_to_thread = asyncio.to_thread

            async def observed_thread(function, *args, **kwargs):
                started.set()
                return await real_to_thread(function, *args, **kwargs)

            task = None
            try:
                with patch.object(notifier, 'webpush', side_effect=lambda **kwargs: release.wait(2)), \
                     patch.object(notifier.asyncio, 'to_thread', side_effect=observed_thread):
                    task = asyncio.create_task(send())
                    await asyncio.wait_for(started.wait(), 2)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError('Delivery cancellation must propagate')
                await check(['UNKNOWN'])
            finally:
                release.set()
                if task is not None and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
            print('PASS: shutdown cancellation records UNKNOWN before propagating cancellation')

            # An independent database session models another API process.
            key = 'notification-forecast:' + marker
            probe = await asyncpg.connect(config.DATABASE_URL)

            class OtherProcessPool:
                def transaction(self):
                    return probe.transaction()

                @asynccontextmanager
                async def acquire(self, **kwargs):
                    yield self

                async def fetchval(self, query, *args):
                    return await probe.fetchval(query, *args)

            await conn.execute('SELECT pg_advisory_lock(hashtextextended($1, 0))', key)
            try:
                before = len(received)
                with patch.object(notifier, 'db', return_value=OtherProcessPool()):
                    await notifier.on_forecast(marker, 'SAFE', fc)
                assert len(received) == before
                assert await probe.fetchval('SELECT pg_try_advisory_lock(hashtextextended($1, 0))', key) is False
            finally:
                await conn.execute('SELECT pg_advisory_unlock(hashtextextended($1, 0))', key)
                await probe.close()
            print('PASS: PostgreSQL lock prevents another API process from checking/sending concurrently')

    finally:
        await transaction.rollback()
        leftovers = await conn.fetchval('SELECT count(*) FROM notification_history WHERE device_id=$1', marker)
        assert leftovers == 0
        await conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        print('CLEANUP: database transaction rolled back; no test records retained')


if __name__ == '__main__':
    asyncio.run(main())
