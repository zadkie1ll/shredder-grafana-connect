from app.ssh.client import TOFUClient


class FakeKey:
    def __init__(self, public: str):
        self.public = public

    def export_public_key(self, fmt: str) -> bytes:
        assert fmt == "openssh"
        return self.public.encode()

    def get_fingerprint(self, fmt: str) -> str:
        assert fmt == "sha256"
        return "SHA256:test"


def test_accept_new_persists_and_rejects_changed_key(tmp_path) -> None:
    path = tmp_path / "known_hosts"
    client = TOFUClient("node.example.com", path, "accept-new")
    assert client.validate_host_public_key("ignored", "10.0.0.1", 22, FakeKey("ssh-ed25519 AAAA"))
    assert path.read_text() == "node.example.com ssh-ed25519 AAAA\n"
    assert client.validate_host_public_key("ignored", "10.0.0.1", 22, FakeKey("ssh-ed25519 AAAA"))
    assert not client.validate_host_public_key(
        "ignored", "10.0.0.1", 22, FakeKey("ssh-ed25519 BBBB")
    )


def test_strict_rejects_unknown_key(tmp_path) -> None:
    client = TOFUClient("node.example.com", tmp_path / "known_hosts", "strict")
    assert not client.validate_host_public_key(
        "ignored", "10.0.0.1", 22, FakeKey("ssh-ed25519 AAAA")
    )
