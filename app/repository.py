from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from app.models import DesiredNode, ManagedNode

SCHEMA = """
CREATE TABLE IF NOT EXISTS managed_nodes (
    node_id TEXT PRIMARY KEY,
    node_name TEXT NOT NULL,
    address TEXT NOT NULL,
    ssh_user TEXT NOT NULL,
    ssh_port INTEGER NOT NULL,
    exporter_port INTEGER NOT NULL,
    last_seen_at TEXT,
    last_sync_at TEXT,
    last_success_at TEXT,
    status TEXT NOT NULL,
    last_error TEXT,
    panel_status TEXT,
    country TEXT,
    provider TEXT
);
"""


class NodeRepository:
    def __init__(self, path: Path):
        self.path = path

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(SCHEMA)
            await db.commit()

    async def ready(self) -> bool:
        try:
            async with aiosqlite.connect(self.path) as db:
                await db.execute("SELECT 1")
            return True
        except aiosqlite.Error:
            return False

    async def get_nodes(self, include_removed: bool = False) -> list[ManagedNode]:
        query = "SELECT * FROM managed_nodes"
        if not include_removed:
            query += " WHERE status != 'removed'"
        query += " ORDER BY node_name, node_id"
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            rows = await (await db.execute(query)).fetchall()
        return [ManagedNode.model_validate(dict(row)) for row in rows]

    async def get_node(self, node_id: str) -> ManagedNode | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            row = await (
                await db.execute("SELECT * FROM managed_nodes WHERE node_id = ?", (node_id,))
            ).fetchone()
        return ManagedNode.model_validate(dict(row)) if row else None

    async def mark_success(self, node: DesiredNode) -> None:
        now = datetime.now(UTC).isoformat()
        values = (
            node.node_id,
            node.node_name,
            node.address,
            node.ssh_user,
            node.ssh_port,
            node.exporter_port,
            now,
            now,
            now,
            "active",
            None,
            node.panel_status,
            node.country,
            node.provider,
        )
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO managed_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                  node_name=excluded.node_name, address=excluded.address,
                  ssh_user=excluded.ssh_user, ssh_port=excluded.ssh_port,
                  exporter_port=excluded.exporter_port, last_seen_at=excluded.last_seen_at,
                  last_sync_at=excluded.last_sync_at, last_success_at=excluded.last_success_at,
                  status='active', last_error=NULL, panel_status=excluded.panel_status,
                  country=excluded.country, provider=excluded.provider""",
                values,
            )
            await db.commit()

    async def mark_seen(self, node: DesiredNode) -> None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE managed_nodes SET node_name=?, last_seen_at=?, last_sync_at=?,
                status='active', last_error=NULL, panel_status=?, country=?, provider=?
                WHERE node_id=?""",
                (
                    node.node_name,
                    now,
                    now,
                    node.panel_status,
                    node.country,
                    node.provider,
                    node.node_id,
                ),
            )
            await db.commit()

    async def mark_error(self, node: DesiredNode, error: str) -> None:
        now = datetime.now(UTC).isoformat()
        current = await self.get_node(node.node_id)
        # Keep the last verified address on IP-change failures.
        address = current.address if current and current.last_success_at else node.address
        last_success = (
            current.last_success_at.isoformat() if current and current.last_success_at else None
        )
        values = (
            node.node_id,
            node.node_name,
            address,
            node.ssh_user,
            node.ssh_port,
            node.exporter_port,
            now,
            now,
            last_success,
            "error",
            error[:1000],
            node.panel_status,
            node.country,
            node.provider,
        )
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """INSERT INTO managed_nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET node_name=excluded.node_name,
                last_seen_at=excluded.last_seen_at, last_sync_at=excluded.last_sync_at,
                status='error', last_error=excluded.last_error, panel_status=excluded.panel_status,
                country=excluded.country, provider=excluded.provider""",
                values,
            )
            await db.commit()

    async def record_existing_error(self, node_id: str, error: str) -> None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE managed_nodes SET status='error', last_sync_at=?, last_error=?
                WHERE node_id=? AND status != 'removed'""",
                (now, error[:1000], node_id),
            )
            await db.commit()

    async def mark_missing_removed(self, desired_ids: set[str]) -> list[ManagedNode]:
        current = await self.get_nodes()
        removed = [node for node in current if node.node_id not in desired_ids]
        if removed:
            placeholders = ",".join("?" for _ in removed)
            async with aiosqlite.connect(self.path) as db:
                await db.execute(
                    f"UPDATE managed_nodes SET status='removed' WHERE node_id IN ({placeholders})",
                    tuple(node.node_id for node in removed),
                )
                await db.commit()
        return removed
