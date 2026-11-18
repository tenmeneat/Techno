"""Small, idempotent migration limited to the notification feature."""
from pathlib import Path

from app.db.pool import db


async def migrate_notifications():
    sql = (Path(__file__).parent / "migrations" / "001_notification_history.sql").read_text(encoding="utf-8")
    async with db().acquire(timeout=5) as connection, connection.transaction():
        await connection.execute("SET LOCAL lock_timeout = '5s'")
        await connection.execute("SET LOCAL statement_timeout = '10s'")
        await connection.execute("SELECT pg_advisory_xact_lock(814332801)")
        await connection.execute(sql)
