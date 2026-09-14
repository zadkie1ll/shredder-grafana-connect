import pytest

from app.errors import NotesParseError
from app.panel.parser import parse_monitoring_notes


def test_parses_monitoring_block_with_defaults() -> None:
    result = parse_monitoring_notes("Comment\nmonitoring:\nssh_user=root", "1.2.3.4")
    assert result is not None
    assert result.ssh_host == "1.2.3.4"
    assert result.ssh_port == 22
    assert result.node_exporter_port == 9100
    assert result.enabled is True


def test_parses_all_fields_and_disabled() -> None:
    result = parse_monitoring_notes(
        "monitoring:\nssh_host=node.example.com\nssh_port=2222\nssh_user=root\n"
        "node_exporter_port=9200\nenabled=false",
        "1.2.3.4",
    )
    assert result is not None
    assert result.ssh_port == 2222
    assert result.enabled is False


def test_missing_block_is_not_managed() -> None:
    assert parse_monitoring_notes("human notes", "1.2.3.4") is None


def test_rejects_unknown_keys() -> None:
    with pytest.raises(NotesParseError):
        parse_monitoring_notes("monitoring:\nssh_user=root\ncommand=oops", "1.2.3.4")
