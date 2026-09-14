from app.config import Settings
from app.errors import NodeExporterInstallError, NodeExporterVerificationError
from app.logging import log
from app.models import DesiredNode
from app.ssh.client import SSHClient


CHECK_COMMAND = """set -eu
if command -v node_exporter >/dev/null 2>&1 \
  && systemctl is-active --quiet node_exporter \
  && curl -fsS --max-time 5 http://127.0.0.1:${EXPORTER_PORT}/metrics >/dev/null; then
  printf ready
else
  printf missing
fi
"""


class NodeExporterInstaller:
    def __init__(self, settings: Settings, ssh: SSHClient):
        self.settings = settings
        self.ssh = ssh

    async def ensure_installed(self, node: DesiredNode) -> bool:
        check = CHECK_COMMAND.replace("${EXPORTER_PORT}", str(node.exporter_port))
        result = (await self.ssh.run(node, check)).strip()
        if result == "ready":
            log.info("node_exporter_already_ready", node=node.node_name)
            return False

        script = self._install_script(node.exporter_port)
        try:
            await self.ssh.run(node, "/bin/sh -s", input_data=script)
        except Exception as exc:
            raise NodeExporterInstallError(str(exc)) from exc
        result = (await self.ssh.run(node, check)).strip()
        if result != "ready":
            raise NodeExporterVerificationError("node_exporter /metrics verification failed")
        log.info(
            "node_exporter_installed",
            node=node.node_name,
            version=self.settings.node_exporter_version,
        )
        return True

    def _install_script(self, port: int) -> str:
        version = self.settings.node_exporter_version
        firewall = ""
        if self.settings.configure_firewall:
            source = self.settings.prometheus_source_ip
            if not source:
                raise NodeExporterInstallError(
                    "PROMETHEUS_SOURCE_IP is required when CONFIGURE_FIREWALL=true"
                )
            firewall = f"""
if command -v ufw >/dev/null 2>&1; then
  ufw allow from {source} to any port {port} proto tcp
elif command -v firewall-cmd >/dev/null 2>&1; then
  firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address={source} port port={port} protocol=tcp accept'
  firewall-cmd --reload
fi
"""
        return f"""set -eu
VERSION='{version}'
case "$(uname -m)" in
  x86_64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo 'unsupported architecture' >&2; exit 20 ;;
esac
NAME="node_exporter-${{VERSION}}.linux-${{ARCH}}"
BASE="https://github.com/prometheus/node_exporter/releases/download/v${{VERSION}}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
curl -fsSLO "$BASE/$NAME.tar.gz"
curl -fsSLO "$BASE/sha256sums.txt"
EXPECTED="$(awk -v file="$NAME.tar.gz" '$2 == file {{print $1}}' sha256sums.txt)"
test -n "$EXPECTED"
printf '%s  %s\n' "$EXPECTED" "$NAME.tar.gz" | sha256sum -c -
tar -xzf "$NAME.tar.gz"
install -m 0755 "$NAME/node_exporter" /usr/local/bin/node_exporter
if ! id node_exporter >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin node_exporter
fi
cat > /etc/systemd/system/node_exporter.service <<'UNIT'
[Unit]
Description=Prometheus Node Exporter
Wants=network-online.target
After=network-online.target

[Service]
User=node_exporter
Group=node_exporter
Type=simple
ExecStart=/usr/local/bin/node_exporter --web.listen-address=:{port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now node_exporter
systemctl is-active --quiet node_exporter
curl -fsS --max-time 10 http://127.0.0.1:{port}/metrics >/dev/null
{firewall}
"""

