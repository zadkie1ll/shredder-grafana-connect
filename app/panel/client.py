import asyncio
from typing import Any

import httpx
from pydantic import ValidationError

from app.config import Settings
from app.errors import PanelAPIError, PanelAuthenticationError, PanelResponseError
from app.models import PanelNode, panel_node_from_payload


class PanelClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport

    async def get_nodes(self) -> list[PanelNode]:
        url = str(self.settings.panel_base_url).rstrip("/") + self.settings.panel_nodes_path
        delays = (0, 1, 3)
        last_error: Exception | None = None

        async with httpx.AsyncClient(
            timeout=self.settings.panel_request_timeout,
            verify=self.settings.panel_verify_tls,
            transport=self._transport,
        ) as client:
            for delay in delays:
                if delay:
                    await asyncio.sleep(delay)
                try:
                    response = await client.get(
                        url,
                        headers={"Authorization": f"Bearer {self.settings.panel_api_token}"},
                    )
                    if response.status_code in (401, 403):
                        raise PanelAuthenticationError("panel authentication failed")
                    response.raise_for_status()
                    return self._parse_response(response.json())
                except PanelAuthenticationError:
                    raise
                except (httpx.HTTPError, ValueError, PanelResponseError) as exc:
                    last_error = exc

        raise PanelAPIError(f"panel request failed after 3 attempts: {last_error}") from last_error

    def _parse_response(self, payload: Any) -> list[PanelNode]:
        items: Any = payload
        if isinstance(payload, dict):
            for key in ("nodes", "data", "response"):
                if key in payload:
                    items = payload[key]
                    if isinstance(items, dict) and "nodes" in items:
                        items = items["nodes"]
                    break
        if not isinstance(items, list):
            raise PanelResponseError("panel response does not contain a node list")
        if not items and not self.settings.panel_allow_empty_response:
            raise PanelResponseError("empty panel response rejected by safety policy")
        try:
            return [panel_node_from_payload(item) for item in items if isinstance(item, dict)]
        except ValidationError as exc:
            raise PanelResponseError("panel returned an invalid node") from exc
