import httpx
import pytest

from app.errors import PanelResponseError
from app.models import panel_node_from_payload
from app.panel.client import PanelClient


def test_panel_model_normalizes_id_and_ip() -> None:
    node = panel_node_from_payload({"id": 123, "name": "ru1", "ip": "10.0.0.1"})
    assert node.id == "123"
    assert node.address == "10.0.0.1"


@pytest.mark.asyncio
async def test_panel_client_parses_nested_nodes(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={"response": {"nodes": [{"uuid": "n1", "name": "ru1", "address": "10.0.0.1"}]}},
        )

    nodes = await PanelClient(settings, httpx.MockTransport(handler)).get_nodes()
    assert [node.id for node in nodes] == ["n1"]


def test_empty_response_is_rejected(settings) -> None:
    with pytest.raises(PanelResponseError):
        PanelClient(settings)._parse_response([])
