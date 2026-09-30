import logging
from typing import Any

from aiohttp import web
from trame.widgets.gwc import GirderProvider
from trame_server import Server
from undo_stack import Signal

from ...ui import GirderConnectionState
from ...utils import GirderConfig, is_valid_url
from ..base_logic import BaseLogic

logger = logging.getLogger(__name__)


class GirderConnectionLogic(BaseLogic[GirderConnectionState]):
    girder_connected = Signal(GirderConfig | None)
    user_connected = Signal(dict[str, Any] | None, str | None)

    def __init__(self, server: Server, girder_configs: dict[str, GirderConfig], default_url: str | None) -> None:
        super().__init__(server, GirderConnectionState)
        self._girder_configs = girder_configs
        self._girder_config = GirderConfig()

        self._init_girder(default_url)
        self.provider = GirderProvider(
            ref="girder_provider",
            trame_server=self.server,
            api_root=self._girder_config.api_url,
            user_fetched=(self._on_user_connected, "[$event.user, $event.token]"),
            user_logged_out=(self._on_user_disconnected,),
        )

        self.server.controller.on_server_bind.add(self._register_routes)

    def _register_routes(self, web_server) -> None:
        web_server.app.router.add_get("/__girder_token", self._get_girder_token)

    def _get_girder_token(self, request: web.Request) -> web.Response:
        return web.json_response(
            {"token": request.cookies.get("girderToken")},
            headers={"Cache-Control": "no-store"},
        )

    def _init_girder(self, girder_url) -> None:
        self.data.girder_url = girder_url
        self._load_girder()

    def _load_girder(self) -> None:
        if not self.data.girder_url:
            return

        girder_config: GirderConfig = self._girder_configs.get(
            self.data.girder_url.strip("/"), GirderConfig(url=self.data.girder_url)
        )
        valid_url, self.data.girder_url_error = is_valid_url(girder_config.api_url)
        if valid_url:
            self.data.girder_api_root = girder_config.api_url
            self._girder_config = girder_config

    def _connect_girder(self, girder_api_root: str | None) -> None:
        self.provider.connect(girder_api_root)
        self.girder_connected(self._girder_config)

    def _disconnect_girder(self) -> None:
        self.provider.disconnect()
        self._girder_config = GirderConfig()
        self.girder_connected(None)

    def _on_user_connected(self, info: dict[str, Any] | None, token: str | None) -> None:
        if info is None:
            self._on_user_disconnected()
            return

        self.data.girder_user_name = f"{info.get('firstName', '')} {info.get('lastName', '')}"
        self.user_connected(info, token)

    def _on_user_disconnected(self) -> None:
        self.data.girder_user_name = None
        self.user_connected(None, None)