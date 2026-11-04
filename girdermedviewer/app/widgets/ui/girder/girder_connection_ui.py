from dataclasses import dataclass
from pathlib import Path

from trame.widgets import client
from trame.widgets import vuetify3 as v3
from trame_client.widgets.core import AbstractElement
from trame_server.utils.typed_state import TypedState

GIRDER_AUTH_SCRIPT = client.register_external_script(
    Path(__file__).with_name("girder_auth.js"),
    function_names=["authenticateGirder"],
    name="girder_auth",
)

@dataclass
class GirderConnectionState:
    girder_user_name: str | None = None
    girder_api_root: str | None = None
    girder_url: str | None = None
    girder_url_error: str | None = None

class GirderConnectionUI(AbstractElement):

    def __init__(self):
        super().__init__("girder-connection")
        self._typed_state = TypedState(self.state, GirderConnectionState)

        self._build_ui()

    def _build_ui(self):
        v3.VSpacer()
        v3.VLabel(
            v_if=(self._typed_state.name.girder_user_name,),
            text=(self._typed_state.name.girder_user_name,),
        )
        v3.VLabel(
            v_if=(f"!{self._typed_state.name.girder_user_name}",),
            text="Not connected",
        )
        v3.VSpacer()
        client.ClientTriggers(
            mounted=(
                f"import('/{GIRDER_AUTH_SCRIPT.module_path}')"
                ".then(m => m.authenticateGirder())"
            ),
        )