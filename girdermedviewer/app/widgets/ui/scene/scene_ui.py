from typing import Any

from trame.widgets import gwc, html
from trame.widgets import vuetify3 as v3
from trame_dataclass.v2 import Provider, get_instance
from trame_server.utils.typed_state import TypedState
from undo_stack import Signal

from ...utils import (
    Button,
    FilterType,
    LayerButton,
    LoadingButton,
    SceneObjectSubtype,
    SceneObjectType,
    Text,
)
from .filters.filter_ui import FilterToolbarUI, FilterUI
from .objects.object_display_ui import SceneObjectDisplayUI
from .objects.object_info_ui import SceneObjectInfoUI
from .objects.object_metadata_ui import SceneObjectMetadataUI
from .scene_state import SceneState


class SceneObjectUI(v3.VExpansionPanel):
    load_canceled = Signal(Any)
    delete_clicked = Signal(str)
    visibility_clicked = Signal(str)
    overlay_clicked = Signal(str)
    save_clicked = Signal(str)

    def __init__(self, obj: str, scene: str, **kwargs) -> None:
        super().__init__(classes="item-card", **kwargs)

        self._typed_state = TypedState(self.state, SceneState)
        self._obj = obj
        self._scene = scene
        self._build_ui()

    def _is_labelmap(self) -> str:
        return f"({self._obj}.object_subtype === '{SceneObjectSubtype.LABELMAP.value}')"

    def _is_active_labelmap(self) -> str:
        return f"({self._typed_state.name.active_labelmap_id} === {self._obj}._id)"

    def _is_volume(self, include_labelmap: bool = False) -> str:
        is_volume = f"({self._obj}.object_type === '{SceneObjectType.VOLUME.value}')"
        if include_labelmap:
            return f"({is_volume})"
        return f"({is_volume} && !{self._is_labelmap()})"

    def _is_primary_volume(self) -> str:
        return f"{self._typed_state.name.primary_volume_ids}.includes({self._obj}._id)"

    def _is_active_primary_volume(self) -> str:
        return f"({self._typed_state.name.active_primary_volume_id} === {self._obj}._id)"

    def _build_ui(self):
        with self, Provider(name="display", instance=(f"{self._obj}.display",)):
            with v3.VExpansionPanelTitle(v_if=(f"{self._obj}.gui.loading",), classes="item-card-title"):
                Text("{{ " + self._obj + ".name }}", classes="text-header font-weight-medium")
                with v3.Template(v_slot_actions="{ expanded }"):
                    LoadingButton(
                        click_stop=(self.load_canceled, f"[{self._obj}._id]"),
                        size="small",
                        tooltip="Cancel",
                    )

            with v3.VExpansionPanelTitle(v_else=True, classes="item-card-title"):
                v3.VIcon(
                    icon=(f"{self._obj}.gui.icon",),
                    color=(f"{self._is_active_labelmap()} ? 'primary' : 'undefined'",),
                )
                Text("{{ " + self._obj + ".name }}", classes="text-header font-weight-medium")
                v3.VChip(
                    v_if=(self._is_active_primary_volume(),),
                    color="primary",
                    text="main",
                )
                with v3.Template(v_slot_actions="{ expanded }"):
                    Button(
                        v_if=("display_available",),
                        click_stop=(self.visibility_clicked, f"[{self._obj}._id]"),
                        icon=("display.is_visible ? 'mdi-eye-outline' : 'mdi-eye-off-outline'",),
                        size="small",
                        tooltip=("display.is_visible ? 'Hide' : 'Show'",),
                    )
                    LoadingButton(
                        v_if=(f"{self._obj}.gui.saving",),
                        size="small",
                        tooltip="Saving to Girder...",
                    )
                    Button(
                        v_if=(f"!{self._obj}.gui.saving && {self._obj}.filter_type",),
                        click_stop=(self.save_clicked, f"[{self._obj}._id]"),
                        icon="mdi-content-save-outline",
                        size="small",
                        tooltip="Save to Girder",
                    )

            with v3.VExpansionPanelText(v_if=(f"!{self._obj}.gui.loading",)), v3.VCard():
                with (
                    v3.VCardTitle(classes="d-flex justify-center"),
                    v3.VItemGroup(
                        v_model=(f"{self._obj}.gui.current_window",),
                        mandatory=True,
                    ),
                ):
                    with v3.VItem(
                        v_if=(f"{self._obj}.filter_type",),
                        v_slot="{ isSelected }",
                        value="filter",
                    ):
                        Button(
                            text="{{ " + f"{self._obj}.filter_type" + " }}",
                            variant="text",
                            color=("isSelected ? 'primary' : 'grey'",),
                            click=f"{self._obj}.gui.current_window = 'filter'",
                        )
                    with v3.VItem(
                        v_if=(f"{self._obj}.display",),
                        v_slot="{ isSelected }",
                        value="display",
                    ):
                        Button(
                            text="display",
                            variant="text",
                            color=("isSelected ? 'primary' : 'grey'",),
                            click=f"{self._obj}.gui.current_window = 'display'",
                        )

                    with v3.VItem(
                        v_if=(f"{self._obj}.info",),
                        v_slot="{ isSelected }",
                        value="info",
                    ):
                        Button(
                            text="info",
                            variant="text",
                            color=("isSelected ? 'primary' : 'grey'",),
                            click=f"{self._obj}.gui.current_window = 'info'",
                        )

                    with v3.VItem(
                        v_if=(f"{self._obj}.metadata",),
                        v_slot="{ isSelected }",
                        value="metadata",
                    ):
                        Button(
                            text="metadata",
                            variant="text",
                            color=("isSelected ? 'primary' : 'grey'",),
                            click=f"{self._obj}.gui.current_window = 'metadata'",
                        )

                with (
                    v3.VCardText(),
                    v3.VWindow(v_model=(f"{self._obj}.gui.current_window"), style="overflow: unset;"),
                ):
                    with (
                        v3.VWindowItem(value="filter", v_if=(f"display_available && {self._obj}.filter_type",)),
                    ):
                        self.filter_ui = FilterUI(
                            classes=("display.is_visible ? '' : 'disabled'",),
                            obj=self._obj,
                        )

                    with (
                        v3.VWindowItem(value="display", v_if=("display_available",)),
                    ):
                        SceneObjectDisplayUI(
                            classes=("display.is_visible ? '' : 'disabled'",),
                            color_presets=f"{self._scene}.color_presets",
                            is_primary=self._is_primary_volume(),
                            obj=self._obj,
                            obj_display="display",
                            volume_presets=f"{self._scene}.volume_presets",
                        )

                    with v3.VWindowItem(value="info", v_if=(f"{self._obj}.info",)):
                        SceneObjectInfoUI(obj_info=f"{self._obj}.info")

                    with v3.VWindowItem(value="metadata", v_if=(f"{self._obj}.metadata",)):
                        SceneObjectMetadataUI(obj_metadata=f"{self._obj}.metadata")

                with v3.VCardActions():
                    self.filter_toolbar = FilterToolbarUI(
                        v_if=(f"!{self._is_labelmap()}",),
                        obj_id=f"{self._obj}._id",
                        obj_type=f"{self._obj}.object_type",
                    )
                    v3.VSpacer()
                    with html.Div(classes="d-flex"):
                        LayerButton(
                            v_if=(f"{self._is_volume()} && !{self._is_active_primary_volume()}",),
                            main_layer=(self._is_primary_volume(),),
                            tooltip=(f"{self._is_primary_volume()} ? 'Set as overlay' : 'Set as main'",),
                            click=(self.overlay_clicked, f"[{self._obj}._id]"),
                        )
                        Button(
                            icon="mdi-delete",
                            tooltip="Delete",
                            color="error",
                            click=(self.delete_clicked, f"[{self._obj}._id]"),
                        )


class SceneUI(html.Div):
    load_canceled = Signal(str)
    filter_clicked = Signal(str, FilterType)
    delete_clicked = Signal(str)
    add_segment_clicked = Signal(str)
    delete_segment_clicked = Signal(str, str)
    segment_clicked = Signal(str, str)
    visibility_clicked = Signal(str)
    overlay_clicked = Signal(str)
    save_clicked = Signal(str)
    save_confirmed = Signal()
    folder_selected = Signal(dict[str, Any])  # folder_id
    save_dialog_cancel = Signal()
    folder_dialog_cancel = Signal()
    location_updated = Signal(dict[str, Any])

    def __init__(self, **kwargs):
        super().__init__(classes="scene-drawer", **kwargs)
        self._typed_state = TypedState(self.state, SceneState)
        self._scene = get_instance(self._typed_state.data.scene_id)
        self._build_ui()

        self.object_ui.load_canceled.connect(self.load_canceled)
        self.object_ui.delete_clicked.connect(self.delete_clicked)
        self.object_ui.visibility_clicked.connect(self.visibility_clicked)
        self.object_ui.overlay_clicked.connect(self.overlay_clicked)
        self.object_ui.save_clicked.connect(self.save_clicked)
        self.object_ui.filter_toolbar.filter_clicked.connect(self.filter_clicked)
        self.object_ui.filter_ui.segmentation_filter.add_segment_clicked.connect(self.add_segment_clicked)
        self.object_ui.filter_ui.segmentation_filter.delete_segment_clicked.connect(self.delete_segment_clicked)
        self.object_ui.filter_ui.segmentation_filter.segment_clicked.connect(self.segment_clicked)
        self.save_dialog_cancel.connect(self._close_save_dialog)
        self.folder_dialog_cancel.connect(self._close_folder_dialog)
        self.location_updated.connect(self._on_location_updated)

    def _open_folder_dialog(self):
        self._typed_state.data.folder_dialog_visible = True

    def _close_save_dialog(self):
        self._typed_state.data.save_dialog_visible = False

    def _close_folder_dialog(self):
        self._typed_state.data.folder_dialog_visible = False

    def _on_location_updated(self, location):
        self._typed_state.data.folder_dialog_location = location

    def _build_ui(self):
        with self, self._scene.provide_as("scene"):
            with v3.VExpansionPanels(
                v_if=("scene.objects?.length > 0",),
                v_model=("scene.gui.expanded_object",),
                variant="accordion",
                focusable=True,
            ):
                self.object_ui = SceneObjectUI(
                    obj="obj",
                    scene="scene",
                    v_for="obj in scene.objects",
                    readonly=("obj.gui.loading",),
                    value=("obj._id",),
                )
            Text(
                v_else=True,
                classes="d-flex justify-center font-italic",
                text="Select data to get started",
            )
            v3.VSnackbar(
                v_model=(self._typed_state.name.is_notification_visible,),
                color=(self._typed_state.name.notification_color,),
                text=(self._typed_state.name.notification_message,),
                timeout=5000,
            )
            # Save dialog
            with v3.VDialog(
                v_model=(self._typed_state.name.save_dialog_visible,),
                max_width="500px",
            ):
                with v3.VCard():
                    v3.VCardTitle(text="Save to Girder")
                    with v3.VCardText():
                        v3.VTextField(
                            label="Filename",
                            v_model=(self._typed_state.name.save_dialog_filename,),
                            hint="Enter filename for the saved item",
                        )
                        with html.Div(classes="d-flex align-center ga-2"):
                            v3.VTextField(
                                label="Folder",
                                v_model=(self._typed_state.name.save_dialog_folder_name,),
                                readonly=True,
                                hint="Select folder to save to",
                                classes="flex-grow-1",
                            )
                            Button(
                                icon="mdi-folder-outline",
                                tooltip="Select folder",
                                click=f"{self._typed_state.name.folder_dialog_visible} = true",
                            )
                        v3.VCheckbox(
                            label="Overwrite if exists",
                            v_model=(self._typed_state.name.save_dialog_overwrite,),
                        )
                    with v3.VCardActions():
                        v3.VSpacer()
                        v3.VBtn(
                            text="Cancel",
                            click=f"{self._typed_state.name.save_dialog_visible} = false",
                        )
                        v3.VBtn(
                            text="Save",
                            color="primary",
                            click=(self.save_confirmed,),
                        )
            # Folder selection dialog
            with v3.VDialog(
                v_model=(self._typed_state.name.folder_dialog_visible,),
                width=800,
            ):
                with v3.VCard():
                    v3.VCardTitle(text="Select folder")
                    with v3.VCardText(classes="pa-0"):
                        gwc.GirderFileManager(
                            classes="girder-browser",
                            v_if=(self._typed_state.name.folder_dialog_location,),
                            location=(self._typed_state.name.folder_dialog_location,),
                            update_location=(self._on_location_updated, "[$event]"),
                        )
                    with v3.VCardActions(classes="justify-end"):
                        v3.VSpacer()
                        v3.VBtn(
                            text="Cancel",
                            click=f"{self._typed_state.name.folder_dialog_visible} = false",
                        )
                        v3.VBtn(
                            text="Select Folder",
                            color="primary",
                            click=(self.folder_selected, f"[{self._typed_state.name.folder_dialog_location}]"),
                        )
