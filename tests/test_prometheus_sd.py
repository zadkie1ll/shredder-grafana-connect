import json
from datetime import UTC, datetime

from app.models import ManagedNode
from app.prometheus_sd import build_target_groups, write_targets_atomically


def managed(node_id: str = "id1", address: str = "1.2.3.4", status: str = "active") -> ManagedNode:
    return ManagedNode(
        node_id=node_id,
        node_name="ru1",
        address=address,
        ssh_user="root",
        ssh_port=22,
        exporter_port=9100,
        status=status,
        last_success_at=datetime.now(UTC),
        country="RU",
    )


def test_generates_prometheus_groups() -> None:
    groups = build_target_groups([managed()])
    assert groups[0].targets == ["1.2.3.4:9100"]
    assert groups[0].labels == {
        "node_id": "id1",
        "node_name": "ru1",
        "managed_by": "panel-sync",
        "country": "RU",
    }


def test_excludes_never_successful_error() -> None:
    node = managed(status="error")
    node.last_success_at = None
    assert build_target_groups([node]) == []


def test_atomic_write_replaces_valid_json(tmp_path) -> None:
    target = tmp_path / "nested" / "nodes.json"
    write_targets_atomically(target, build_target_groups([managed()]))
    payload = json.loads(target.read_text())
    assert payload[0]["targets"] == ["1.2.3.4:9100"]
    assert not target.with_name("nodes.json.tmp").exists()
