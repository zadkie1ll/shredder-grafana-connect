from app.ssh.installer import NodeExporterInstaller


class FakeSSH:
    def __init__(self):
        self.commands = []

    async def run(self, node, command, *, input_data=None):
        self.commands.append((command, input_data))
        return "ready"


async def test_existing_exporter_does_not_require_specific_systemd_unit(settings) -> None:
    ssh = FakeSSH()
    installer = NodeExporterInstaller(settings, ssh)
    node = type("Node", (), {"exporter_port": 9100, "node_name": "ru1"})()
    installed = await installer.ensure_installed(node)
    assert installed is False
    assert len(ssh.commands) == 1
    assert "node_exporter_build_info" in ssh.commands[0][0]
    assert "systemctl is-active" not in ssh.commands[0][0]
