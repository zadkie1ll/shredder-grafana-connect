from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        panel_base_url="https://panel.example.com",
        panel_api_token="test-token",
        admin_api_token="0123456789abcdef",
        database_path=tmp_path / "state.db",
        prometheus_targets_file=tmp_path / "targets" / "nodes.json",
        ssh_private_key_path=tmp_path / "id_ed25519",
        ssh_known_hosts_path=tmp_path / "known_hosts",
    )
