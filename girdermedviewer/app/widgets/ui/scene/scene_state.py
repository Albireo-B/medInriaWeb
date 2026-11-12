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
