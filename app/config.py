from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    panel_base_url: HttpUrl
    panel_api_token: str = Field(min_length=1)
    panel_nodes_path: str = "/api/nodes"
    panel_verify_tls: bool = True
    panel_request_timeout: float = Field(20, gt=0)
    panel_allow_empty_response: bool = False

    admin_api_token: str = Field(min_length=16)
    sync_interval_seconds: int = Field(3600, ge=60)
    run_sync_on_startup: bool = True

    ssh_private_key_path: Path = Path("/run/secrets/id_ed25519")
    ssh_known_hosts_path: Path = Path("/app/data/known_hosts")
    ssh_host_key_policy: Literal["strict", "accept-new"] = "accept-new"
    ssh_connect_timeout: float = Field(15, gt=0)
    ssh_command_timeout: float = Field(120, gt=0)
    ssh_retries: int = Field(2, ge=1, le=5)

    node_exporter_port: int = Field(9100, ge=1, le=65535)
    node_exporter_version: str = "1.9.1"
    configure_firewall: bool = False
    prometheus_source_ip: str | None = None

    prometheus_targets_file: Path = Path("/prometheus-targets/nodes.json")
    database_path: Path = Path("/app/data/state.db")
    log_level: str = "INFO"

    @field_validator("panel_nodes_path")
    @classmethod
    def validate_nodes_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("PANEL_NODES_PATH must start with /")
        return value

    @field_validator("node_exporter_version")
    @classmethod
    def validate_exporter_version(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) != 3 or any(not part.isdigit() for part in parts):
            raise ValueError("NODE_EXPORTER_VERSION must be numeric x.y.z")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
