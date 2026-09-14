from pydantic import ValidationError

from app.errors import NotesParseError
from app.models import MonitoringConfig, PanelNode


def parse_monitoring_notes(notes: str | None, fallback_host: str) -> MonitoringConfig | None:
    if not notes:
        return None

    lines = notes.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == "monitoring:")
    except StopIteration:
        return None

    values: dict[str, str] = {}
    allowed = {"ssh_host", "ssh_port", "ssh_user", "node_exporter_port", "enabled"}
    for raw_line in lines[start + 1 :]:
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith(":") or "=" not in line:
            break
        key, value = (part.strip() for part in line.split("=", 1))
        if key not in allowed:
            raise NotesParseError(f"unsupported monitoring key: {key}")
        if key in values:
            raise NotesParseError(f"duplicate monitoring key: {key}")
        values[key] = value

    if "ssh_user" not in values:
        raise NotesParseError("monitoring block requires ssh_user")
    values.setdefault("ssh_host", fallback_host)
    try:
        return MonitoringConfig.model_validate(values)
    except ValidationError as exc:
        raise NotesParseError("invalid monitoring configuration") from exc


def desired_from_panel(node: PanelNode) -> MonitoringConfig | None:
    return parse_monitoring_notes(node.notes, node.address)
