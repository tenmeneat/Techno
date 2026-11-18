"""Notification task/lifespan regression tests; no database or external sends.

Run: python -m unittest discover -s backend/tests -p test_notifications.py
"""
import asyncio
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as app_main
from app.mqtt import ingest
from app.workers import notifier


class NotificationTasks(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await ingest.stop_notifications()
        self.assertFalse(ingest._notification_tasks)
        self.assertFalse(ingest._notification_keys)

    async def test_slow_delivery_does_not_block_state_transition(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow(*args):
            entered.set()
            await release.wait()

        connection = MagicMock()
        connection.fetchval = AsyncMock(return_value=1)
        connection.execute = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=connection)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        at = datetime.now(UTC)
        with patch.object(ingest, 'db', return_value=pool), \
             patch.object(ingest, 'broadcast', new=AsyncMock()), \
             patch.object(notifier, 'on_state', side_effect=slow) as on_state:
            runtime = ingest.Runtime(state='WATCH')
            await asyncio.wait_for(ingest.set_state('test', runtime, 'ALERT', at), 1)
            await asyncio.wait_for(entered.wait(), 1)
            self.assertEqual(runtime.state, 'ALERT')
            self.assertEqual(len(ingest._notification_tasks), 1)
            on_state.assert_awaited_once_with('test', 'WATCH', 'ALERT', at)
            release.set()
            await asyncio.gather(*list(ingest._notification_tasks))

    async def test_duplicate_forecast_is_closed_without_queueing(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow():
            entered.set()
            await release.wait()

        key = ('forecast', 'test')
        ingest.start_notification(slow(), key=key)
        await entered.wait()
        duplicate = slow()
        ingest.start_notification(duplicate, key=key)
        self.assertIsNone(duplicate.cr_frame)
        self.assertEqual(len(ingest._notification_tasks), 1)
        release.set()
        await asyncio.gather(*list(ingest._notification_tasks))

    async def test_overload_closes_rejected_coroutine(self):
        async def slow():
            await asyncio.Event().wait()

        with patch.object(ingest, 'MAX_NOTIFICATION_TASKS', 1), \
             patch.object(ingest.log, 'warning') as warning:
            ingest.start_notification(slow())
            rejected = slow()
            ingest.start_notification(rejected)
            self.assertIsNone(rejected.cr_frame)
            self.assertEqual(len(ingest._notification_tasks), 1)
            warning.assert_called_once()

    async def test_cancel_before_first_execution_has_no_orphan_coroutine(self):
        body = AsyncMock()
        ingest.start_notification(body())
        await ingest.stop_notifications()
        body.assert_not_awaited()

    async def test_background_exception_is_consumed(self):
        async def failing():
            raise RuntimeError('synthetic failure')

        with patch.object(ingest.log, 'error') as error:
            ingest.start_notification(failing())
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            error.assert_called_once()
            self.assertFalse(ingest._notification_tasks)


class Lifespan(unittest.IsolatedAsyncioTestCase):
    async def test_failed_migration_closes_pool_before_workers_start(self):
        with patch.object(app_main, 'open_pool', new=AsyncMock()), \
             patch.object(app_main, 'close_pool', new=AsyncMock()) as close, \
             patch.object(app_main, 'migrate_notifications', new=AsyncMock(side_effect=RuntimeError('test'))), \
             patch.object(ingest, 'stop_notifications', new=AsyncMock()) as stop:
            with self.assertRaises(RuntimeError):
                async with app_main.lifespan(None):
                    self.fail('Application must not start with an incompatible notification schema')
            stop.assert_awaited_once()
            close.assert_awaited_once()

    async def test_shutdown_stops_producers_then_notifications_then_pool(self):
        order = []

        async def worker():
            try:
                await asyncio.Event().wait()
            finally:
                order.append('worker stopped')

        async def stop():
            order.append('notifications stopped')

        async def close():
            order.append('pool closed')

        database = MagicMock()
        database.execute = AsyncMock()
        with patch.object(app_main, 'open_pool', new=AsyncMock()), \
             patch.object(app_main, 'close_pool', side_effect=close), \
             patch.object(app_main, 'migrate_notifications', new=AsyncMock()), \
             patch.object(app_main, 'db', return_value=database), \
             patch.object(notifier, 'reconcile_history', new=AsyncMock()), \
             patch.object(ingest, 'run', side_effect=worker), \
             patch.object(ingest, 'watch_stale', side_effect=worker), \
             patch.object(app_main.weather_sync, 'run', side_effect=worker), \
             patch.object(app_main.diagnostics, 'run', side_effect=worker), \
             patch.object(notifier, 'maintain_history', side_effect=worker), \
             patch.object(ingest, 'stop_notifications', side_effect=stop):
            async with app_main.lifespan(None):
                await asyncio.sleep(0)
        self.assertEqual(order, ['worker stopped'] * 5 + ['notifications stopped', 'pool closed'])


if __name__ == '__main__':
    unittest.main()
