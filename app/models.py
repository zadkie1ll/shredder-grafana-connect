from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PanelNode(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str = Field(validation_alias="uuid")
    name: str
    address: str
    status: str | None = None
    notes: str | None = None
    country: str | None = None
    provider: str | None = None

    @field_validator("id", "name", "address")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class MonitoringConfig(BaseModel):
    ssh_host: str
    ssh_port: int = Field(22, ge=1, le=65535)
    ssh_user: str = "root"
    node_exporter_port: int = Field(9100, ge=1, le=65535)
    enabled: bool = True

    @field_validator("ssh_host")
    @classmethod
    def host_is_safe(cls, value: str) -> str:
        value = value.strip()
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-:_")
        if not value or any(char not in allowed for char in value):
            raise ValueError("invalid SSH host")
        return value

    @field_validator("ssh_user")
    @classmethod
    def user_is_safe(cls, value: str) -> str:
        if not value or len(value) > 32 or not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("invalid SSH user")
        return value


class DesiredNode(BaseModel):
    node_id: str
    node_name: str
    address: str
    ssh_host: str
    ssh_port: int
    ssh_user: str
    exporter_port: int
    panel_status: str | None = None
    country: str | None = None
    provider: str | None = None


class ManagedNode(BaseModel):
    node_id: str
    node_name: str
    address: str
    ssh_user: str
    ssh_port: int
    exporter_port: int
    last_seen_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_success_at: datetime | None = None
    status: Literal["discovered", "installing", "active", "error", "removed"]
    last_error: str | None = None
    panel_status: str | None = None
    country: str | None = None
    provider: str | None = None


class SyncResult(BaseModel):
    last_started_at: datetime
    last_finished_at: datetime
    status: Literal["success", "partial", "failed", "skipped"]
    nodes_total: int = 0
    nodes_active: int = 0
    nodes_error: int = 0
    detail: str | None = None


class TargetGroup(BaseModel):
    targets: list[str]
    labels: dict[str, str]


def panel_node_from_payload(item: dict[str, Any]) -> PanelNode:
    normalized = dict(item)
    if "uuid" not in normalized and "id" in normalized:
        normalized["uuid"] = str(normalized["id"])
    if "address" not in normalized:
        for key in ("ip", "host", "hostname"):
            if normalized.get(key):
                normalized["address"] = normalized[key]
                break
    return PanelNode.model_validate(normalized)
