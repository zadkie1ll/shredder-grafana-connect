import asyncio
from pathlib import Path

import asyncssh

from app.config import Settings
from app.errors import SSHAuthenticationError, SSHConnectionError, SSHHostKeyError
from app.logging import log
from app.models import DesiredNode


class TOFUClient(asyncssh.SSHClient):
    def __init__(self, requested_host: str, known_hosts_path: Path, policy: str):
        self.requested_host = requested_host
        self.known_hosts_path = known_hosts_path
        self.policy = policy

    def validate_host_public_key(self, host: str, addr: str, port: int, key: object) -> bool:
        del host, addr
        token = self.requested_host if port == 22 else f"[{self.requested_host}]:{port}"
        public = key.export_public_key("openssh").decode().strip()  # type: ignore[attr-defined]
        fingerprint = key.get_fingerprint("sha256")  # type: ignore[attr-defined]
        existing: list[str] = []
        if self.known_hosts_path.exists():
            existing = self.known_hosts_path.read_text(encoding="utf-8").splitlines()
        matches = [line for line in existing if line.split(maxsplit=1)[0] == token]
        if matches:
            valid = any(line.split(maxsplit=1)[1] == public for line in matches)
            if not valid:
                log.warning(
                    "ssh_host_key_changed",
                    host=self.requested_host,
                    fingerprint=fingerprint,
                )
            return valid
        if self.policy == "strict":
            log.warning("ssh_unknown_host_key", host=self.requested_host, fingerprint=fingerprint)
            return False
        self.known_hosts_path.parent.mkdir(parents=True, exist_ok=True)
        with self.known_hosts_path.open("a", encoding="utf-8") as known_hosts:
            known_hosts.write(f"{token} {public}\n")
        log.warning("ssh_host_key_accepted", host=self.requested_host, fingerprint=fingerprint)
        return True


class SSHClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def run(self, node: DesiredNode, command: str, *, input_data: str | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.ssh_retries + 1):
            try:
                client = TOFUClient(
                    node.ssh_host,
                    self.settings.ssh_known_hosts_path,
                    self.settings.ssh_host_key_policy,
                )
                async with asyncssh.connect(
                    node.ssh_host,
                    port=node.ssh_port,
                    username=node.ssh_user,
                    client_keys=[str(self.settings.ssh_private_key_path)],
                    # A non-None empty source enables AsyncSSH's validation callback.
                    known_hosts=b"",
                    client_factory=lambda: client,
                    connect_timeout=self.settings.ssh_connect_timeout,
                    login_timeout=self.settings.ssh_connect_timeout,
                ) as connection:
                    result = await connection.run(
                        command,
                        input=input_data,
                        check=False,
                        timeout=self.settings.ssh_command_timeout,
                    )
                    if result.exit_status != 0:
                        detail = (result.stderr or result.stdout or "command failed").strip()
                        raise SSHConnectionError(detail[:1000])
                    return result.stdout
            except asyncssh.PermissionDenied as exc:
                raise SSHAuthenticationError(f"SSH authentication failed for {node.node_name}") from exc
            except asyncssh.HostKeyNotVerifiable as exc:
                raise SSHHostKeyError(f"SSH host key rejected for {node.node_name}") from exc
            except (asyncssh.Error, OSError, asyncio.TimeoutError, SSHConnectionError) as exc:
                last_error = exc
                if attempt < self.settings.ssh_retries:
                    await asyncio.sleep(attempt)
        raise SSHConnectionError(f"SSH failed for {node.node_name}: {last_error}") from last_error
