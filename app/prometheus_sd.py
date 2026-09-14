import json
import os
from pathlib import Path

from app.errors import PrometheusTargetsWriteError
from app.models import ManagedNode, TargetGroup


def build_target_groups(nodes: list[ManagedNode]) -> list[TargetGroup]:
    groups: list[TargetGroup] = []
    seen: set[str] = set()
    for node in nodes:
        if node.status == "removed" or node.last_success_at is None:
            continue
        address = f"[{node.address}]" if ":" in node.address else node.address
        target = f"{address}:{node.exporter_port}"
        if node.node_id in seen:
            continue
        seen.add(node.node_id)
        labels = {
            "node_id": node.node_id,
            "node_name": node.node_name,
            "managed_by": "panel-sync",
        }
        for key, value in (
            ("country", node.country),
            ("provider", node.provider),
            ("panel_status", node.panel_status),
        ):
            if value:
                labels[key] = value
        groups.append(TargetGroup(targets=[target], labels=labels))
    return groups


def write_targets_atomically(path: Path, groups: list[TargetGroup]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        payload = (
            json.dumps([group.model_dump() for group in groups], ensure_ascii=False, indent=2)
            + "\n"
        )
        json.loads(payload)
        with temp_path.open("w", encoding="utf-8") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, path)
    except (OSError, ValueError, TypeError) as exc:
        raise PrometheusTargetsWriteError(f"cannot write targets: {exc}") from exc
