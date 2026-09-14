import asyncio
from datetime import UTC, datetime
from time import monotonic

from app.errors import (
    NotesParseError,
    PanelAPIError,
    PrometheusTargetsWriteError,
    SSHConnectionError,
)
from app.logging import log
from app.metrics import (
    ACTIVE_NODES,
    ERROR_NODES,
    MANAGED_NODES,
    PROVISION_FAILURES,
    SSH_FAILURES,
    SYNC_DURATION,
    SYNC_FAILURES,
    SYNC_RUNS,
)
from app.models import DesiredNode, MonitoringConfig, PanelNode, SyncResult
from app.panel.client import PanelClient
from app.panel.parser import parse_monitoring_notes
from app.prometheus_sd import build_target_groups, write_targets_atomically
from app.repository import NodeRepository
from app.ssh.installer import NodeExporterInstaller


class NodeSyncService:
    def __init__(
        self,
        panel: PanelClient,
        repository: NodeRepository,
        installer: NodeExporterInstaller,
        targets_file: object,
        protected_node_ids: set[str] | None = None,
        protected_node_names: set[str] | None = None,
        manage_nodes_without_notes: bool = False,
        default_ssh_user: str = "root",
        default_exporter_port: int = 9100,
    ):
        self.panel = panel
        self.repository = repository
        self.installer = installer
        self.targets_file = targets_file
        self.protected_node_ids = protected_node_ids or set()
        self.protected_node_names = {name.casefold() for name in (protected_node_names or set())}
        self.manage_nodes_without_notes = manage_nodes_without_notes
        self.default_ssh_user = default_ssh_user
        self.default_exporter_port = default_exporter_port
        self._lock = asyncio.Lock()
        self.last_result: SyncResult | None = None

    async def sync(self) -> SyncResult:
        started = datetime.now(UTC)
        if self._lock.locked():
            result = SyncResult(
                last_started_at=started,
                last_finished_at=datetime.now(UTC),
                status="skipped",
                detail="another synchronization is running",
            )
            log.warning("sync_skipped", reason=result.detail)
            return result

        async with self._lock:
            timer = monotonic()
            SYNC_RUNS.inc()
            log.info("sync_started")
            try:
                panel_nodes = await self.panel.get_nodes()
            except PanelAPIError as exc:
                SYNC_FAILURES.inc()
                result = SyncResult(
                    last_started_at=started,
                    last_finished_at=datetime.now(UTC),
                    status="failed",
                    detail=str(exc),
                )
                self.last_result = result
                SYNC_DURATION.observe(monotonic() - timer)
                log.error("panel_sync_failed", error=str(exc))
                return result

            desired: dict[str, DesiredNode] = {}
            protected_ids: set[str] = set()
            parse_errors = 0
            for panel_node in panel_nodes:
                try:
                    node = self._to_desired(panel_node)
                except NotesParseError as exc:
                    parse_errors += 1
                    protected_ids.add(panel_node.id)
                    await self.repository.record_existing_error(panel_node.id, str(exc))
                    log.error(
                        "notes_parse_failed",
                        node=panel_node.name,
                        node_id=panel_node.id,
                        error=str(exc),
                    )
                    continue
                if node:
                    desired[node.node_id] = node

            current = {node.node_id: node for node in await self.repository.get_nodes()}
            errors = parse_errors
            for node in desired.values():
                previous = current.get(node.node_id)
                needs_provision = previous is None or previous.last_success_at is None
                if previous and (
                    previous.address != node.address
                    or previous.exporter_port != node.exporter_port
                    or previous.ssh_port != node.ssh_port
                    or previous.ssh_user != node.ssh_user
                ):
                    needs_provision = True
                    log.info(
                        "node_connection_changed",
                        node=node.node_name,
                        node_id=node.node_id,
                        old_address=previous.address,
                        new_address=node.address,
                    )
                try:
                    if needs_provision:
                        log.info(
                            "node_discovered" if previous is None else "node_reprovisioning",
                            node=node.node_name,
                            node_id=node.node_id,
                            address=node.address,
                        )
                        await self.installer.ensure_installed(node)
                        await self.repository.mark_success(node)
                        log.info(
                            "target_added",
                            node=node.node_name,
                            target=f"{node.address}:{node.exporter_port}",
                        )
                    else:
                        await self.repository.mark_seen(node)
                except Exception as exc:
                    errors += 1
                    PROVISION_FAILURES.inc()
                    if isinstance(exc, SSHConnectionError):
                        SSH_FAILURES.inc()
                    await self.repository.mark_error(node, str(exc))
                    log.error(
                        "provision_failed",
                        node=node.node_name,
                        node_id=node.node_id,
                        error=str(exc),
                    )

            retained_ids = set(desired) | protected_ids
            managed_before_removal = await self.repository.get_nodes()
            for node in managed_before_removal:
                if self._is_protected(node.node_id, node.node_name):
                    retained_ids.add(node.node_id)
                    if node.node_id not in desired:
                        log.warning(
                            "node_protected_from_removal",
                            node=node.node_name,
                            node_id=node.node_id,
                        )
            retained = [node for node in managed_before_removal if node.node_id in retained_ids]
            groups = build_target_groups(retained)
            try:
                write_targets_atomically(self.targets_file, groups)
            except PrometheusTargetsWriteError as exc:
                SYNC_FAILURES.inc()
                result = SyncResult(
                    last_started_at=started,
                    last_finished_at=datetime.now(UTC),
                    status="failed",
                    nodes_total=len(panel_nodes),
                    detail=str(exc),
                )
                self.last_result = result
                SYNC_DURATION.observe(monotonic() - timer)
                log.error("prometheus_targets_write_failed", error=str(exc))
                return result

            removed = await self.repository.mark_missing_removed(retained_ids)
            for node in removed:
                log.info("node_removed", node=node.node_name, node_id=node.node_id)

            managed = await self.repository.get_nodes()
            active = sum(node.status == "active" for node in managed)
            error_count = sum(node.status == "error" for node in managed)
            MANAGED_NODES.set(len(managed))
            ACTIVE_NODES.set(active)
            ERROR_NODES.set(error_count)
            status = "partial" if errors else "success"
            result = SyncResult(
                last_started_at=started,
                last_finished_at=datetime.now(UTC),
                status=status,
                nodes_total=len(panel_nodes),
                nodes_active=active,
                nodes_error=error_count + parse_errors,
            )
            self.last_result = result
            SYNC_DURATION.observe(monotonic() - timer)
            log.info("sync_finished", **result.model_dump(mode="json"))
            return result

    def _is_protected(self, node_id: str, node_name: str) -> bool:
        return (
            node_id in self.protected_node_ids or node_name.casefold() in self.protected_node_names
        )

    def _to_desired(self, node: PanelNode) -> DesiredNode | None:
        monitoring = parse_monitoring_notes(node.notes, node.address)
        if monitoring is None and self.manage_nodes_without_notes:
            monitoring = MonitoringConfig(
                ssh_host=node.address,
                ssh_user=self.default_ssh_user,
                node_exporter_port=self.default_exporter_port,
            )
        if monitoring is None or not monitoring.enabled:
            return None
        return DesiredNode(
            node_id=node.id,
            node_name=node.name,
            address=monitoring.ssh_host,
            ssh_host=monitoring.ssh_host,
            ssh_port=monitoring.ssh_port,
            ssh_user=monitoring.ssh_user,
            exporter_port=monitoring.node_exporter_port,
            panel_status=node.status,
            country=node.country,
            provider=node.provider,
        )
