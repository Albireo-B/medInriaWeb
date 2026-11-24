from dataclasses import dataclass, field

@dataclass
class SceneState:
    scene_id: str | None = None
    active_segment_id: str | None = None
    active_labelmap_id: str | None = None
    active_primary_volume_id: str | None = None
    primary_volume_ids: list[str] = field(default_factory=list)
    notification_message: str | None = None
    notification_color: str = "success"
    is_notification_visible: bool = False
    # Save dialog state
    save_dialog_visible: bool = False
    save_dialog_object_id: str | None = None
    save_dialog_folder_id: str | None = None
    save_dialog_folder_name: str | None = None
    save_dialog_filename: str = ""
    save_dialog_overwrite: bool = False
    # Folder selection dialog state
    folder_dialog_visible: bool = False
    folder_dialog_location: dict[str, str] | None = None