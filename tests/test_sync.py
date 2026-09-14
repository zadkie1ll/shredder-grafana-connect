from app.models import PanelNode
from app.repository import NodeRepository
from app.services import NodeSyncService


class FakePanel:
    def __init__(self, nodes):
        self.nodes = nodes

    async def get_nodes(self):
        return self.nodes


class FakeInstaller:
    def __init__(self):
        self.calls = []

    async def ensure_installed(self, node):
        self.calls.append(node)
        return True


def panel_node(node_id="id1", address="1.2.3.4"):
    return PanelNode(
        uuid=node_id,
        name="ru1",
        address=address,
        notes="monitoring:\nssh_user=root",
    )


async def test_repeat_sync_does_not_reprovision(settings) -> None:
    repository = NodeRepository(settings.database_path)
    await repository.initialize()
    installer = FakeInstaller()
    service = NodeSyncService(
        FakePanel([panel_node()]), repository, installer, settings.prometheus_targets_file
    )
    await service.sync()
    await service.sync()
    assert len(installer.calls) == 1


async def test_ip_change_reprovisions(settings) -> None:
    repository = NodeRepository(settings.database_path)
    await repository.initialize()
    installer = FakeInstaller()
    panel = FakePanel([panel_node()])
    service = NodeSyncService(panel, repository, installer, settings.prometheus_targets_file)
    await service.sync()
    panel.nodes = [panel_node(address="5.6.7.8")]
    await service.sync()
    assert [call.address for call in installer.calls] == ["1.2.3.4", "5.6.7.8"]


async def test_removed_node_is_removed_from_targets(settings) -> None:
    settings.panel_allow_empty_response = True
    repository = NodeRepository(settings.database_path)
    await repository.initialize()
    installer = FakeInstaller()
    panel = FakePanel([panel_node()])
    service = NodeSyncService(panel, repository, installer, settings.prometheus_targets_file)
    await service.sync()
    panel.nodes = []
    await service.sync()
    node = await repository.get_node("id1")
    assert node is not None and node.status == "removed"
    assert settings.prometheus_targets_file.read_text().strip() == "[]"


async def test_protected_node_survives_panel_removal(settings) -> None:
    repository = NodeRepository(settings.database_path)
    await repository.initialize()
    installer = FakeInstaller()
    panel = FakePanel([panel_node()])
    service = NodeSyncService(
        panel,
        repository,
        installer,
        settings.prometheus_targets_file,
        protected_node_names={"ru1"},
    )
    await service.sync()
    panel.nodes = []
    await service.sync()
    node = await repository.get_node("id1")
    assert node is not None and node.status == "active"
    assert "1.2.3.4:9100" in settings.prometheus_targets_file.read_text()


async def test_node_without_notes_uses_global_ssh_settings(settings) -> None:
    repository = NodeRepository(settings.database_path)
    await repository.initialize()
    installer = FakeInstaller()
    node = panel_node()
    node.notes = None
    service = NodeSyncService(
        FakePanel([node]),
        repository,
        installer,
        settings.prometheus_targets_file,
    )
    result = await service.sync()
    assert result.nodes_active == 1
    assert installer.calls[0].ssh_user == "root"
