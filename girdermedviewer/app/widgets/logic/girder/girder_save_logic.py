import asyncio
import json
import logging
import re
import threading
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from girder_client import GirderClient, HttpError
from trame_server import Server
from trame_server.utils.asynchronous import create_task
from undo_stack import Signal
from vtk import vtkDataObject

from ...utils import SceneObjectType, save_mesh, save_volume
from ..base_logic import BaseLogic
from ..scene import SceneObjectLogic

logger = logging.getLogger(__name__)

NIFTI_EXTENSIONS = (".nii", ".nii.gz")
INVALID_NAME_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00]+')


def _get_extension(file_name: str) -> str:
    if file_name.lower().endswith(".nii.gz"):
        return ".nii.gz"
    return Path(file_name).suffix


def _get_output_extension(is_volume: bool, source_file_name: str | None) -> str:
    """
    Volumes are saved in the family of format they were loaded from, so that they keep the same orientation:
    NIfTI stays NIfTI, anything else is saved as MetaImage. Meshes are saved as VTK PolyData.
    """
    if not is_volume:
        return ".vtp"
    if _get_extension(source_file_name or "").lower() in NIFTI_EXTENSIONS:
        return ".nii.gz"
    return ".mha"


def _get_name_stem(name: str, source_file_name: str | None) -> str:
    """
    Name of the object without the extension of its source file.
    The extension is not always at the end, as filters append their name: "brain.nii.gz_gaussian blur".
    """
    extension = _get_extension(source_file_name or "")
    stem = re.sub(re.escape(extension), "", name, count=1, flags=re.IGNORECASE) if extension else name
    return INVALID_NAME_CHARACTERS.sub("_", stem).strip() or "untitled"


def _get_error_reason(error: Exception) -> str:
    if isinstance(error, HttpError):
        try:
            return str(json.loads(error.responseText)["message"])
        except (ValueError, KeyError, TypeError):
            return f"HTTP error {error.status}"
    return str(error) or type(error).__name__


class GirderSaveLogic(BaseLogic[None]):
    """
    Saves the data of a scene object as a new Girder item, in the same folder as the item the data comes from.
    Existing items are never modified.
    """

    object_saved = Signal(str, str)
    object_save_failed = Signal(str, str)

    def __init__(
        self,
        server: Server,
        get_girder_client: Callable[[], GirderClient],
        temp_directory: str | None,
    ) -> None:
        super().__init__(server, None)
        self._get_girder_client = get_girder_client
        self._temp_directory = temp_directory
        # Girder adds the file to the item with the same name if there is one, which makes the item unreadable
        # here (only one file per item is supported): choosing a name and uploading must not be interleaved.
        self._upload_lock = threading.Lock()
        self.save_tasks: dict[str, asyncio.Task] = {}

    def _get_unique_item_name(self, client: GirderClient, folder_id: str, stem: str, extension: str, overwrite: bool = False) -> str:
        name = f"{stem}{extension}"
        if overwrite:
            return name
        counter = 0
        while next(iter(client.listItem(folder_id, name=name)), None) is not None:
            counter += 1
            name = f"{stem}_{counter}{extension}"
        return name

    def _write_and_upload(
        self,
        data: vtkDataObject,
        is_volume: bool,
        stem: str,
        extension: str,
        source_item_id: str,
        folder_id: str | None = None,
        filename: str = "",
        overwrite: bool = False,
        segmentation_metadata: dict | None = None,
    ) -> str:
        """Blocking, to be run in a thread. Returns the name of the item created in Girder."""
        client = self._get_girder_client()
        if folder_id is None:
            folder_id = client.getItem(source_item_id)["folderId"]

        with TemporaryDirectory(dir=self._temp_directory) as temp_dir:
            # Use provided filename or generate one
            if filename:
                name = filename
                # Ensure extension matches
                if not name.endswith(extension):
                    name = f"{Path(name).stem}{extension}"
            else:
                name = self._get_unique_item_name(client, folder_id, stem, extension, overwrite)

            file_path = str(Path(temp_dir) / name)
            if is_volume:
                save_volume(data, file_path)
            else:
                save_mesh(data, file_path)

            with self._upload_lock:
                logger.debug(f"Uploading {name} to folder {folder_id}")
                existing_item = (
                    next(iter(client.listItem(folder_id, name=name)), None)
                    if overwrite
                    else None
                )

                if existing_item is not None:
                    files = list(client.listFile(existing_item["_id"]))
                    if not files or len(files) != 1:
                        raise RuntimeError(f"Cannot overwrite '{name}': existing item doesn't have the correct amount of file (expected : 1)")

                    existing_file = files[0]
                    with open(file_path, "rb") as stream:
                        client.put(f"file/{existing_file['_id']}/contents", parameters={"size": Path(file_path).stat().st_size}, data=stream,)

                    item_id = existing_item["_id"]
                    item_name = existing_item["name"]
                else:
                    file = client.uploadFileToFolder(folder_id, file_path, filename=name)
                    item_id = file["itemId"]
                    item_name = client.getItem(item_id)["name"]

                # Save segmentation metadata as Girder item metadata
                if segmentation_metadata:
                    client.addMetadataToItem(item_id, segmentation_metadata)

        return item_name

    async def _save(
        self,
        object_id: str,
        data: vtkDataObject,
        is_volume: bool,
        stem: str,
        extension: str,
        source_item_id: str,
        folder_id: str | None = None,
        filename: str = "",
        overwrite: bool = False,
        segmentation_metadata: dict | None = None,
    ) -> None:
        try:
            name = await asyncio.to_thread(
                self._write_and_upload,
                data,
                is_volume,
                stem,
                extension,
                source_item_id,
                folder_id,
                filename,
                overwrite,
                segmentation_metadata,
            )
            self.object_saved(object_id, name)
        except Exception as error:  # The task must always report back, otherwise the object stays "saving"
            logger.exception(f"Error saving {object_id} to Girder")
            self.object_save_failed(object_id, _get_error_reason(error))
        finally:
            self.state.flush()
            self.save_tasks.pop(object_id, None)

    def _extract_segmentation_metadata(self, object_logic: SceneObjectLogic) -> dict | None:
        """Extract segmentation metadata to save as Girder item metadata."""
        from ..scene.filters.segmentation_filter_logic import SegmentationFilterLogic

        if not isinstance(object_logic, SegmentationFilterLogic):
            return None

        segments_data = []
        for segment in object_logic.segments:
            segments_data.append({
                "name": segment.name,
                "value": segment.value,
                "color": segment.display.color,
                "is_visible": segment.display.is_visible,
            })

        return {
            "segmentation": {
                "segments": segments_data,
                "source_image_id": object_logic.input_id,
            }
        }

    def save_object(
        self,
        object_logic: SceneObjectLogic,
        folder_id: str | None = None,
        filename: str = "",
        overwrite: bool = False,
    ) -> None:
        object_id = object_logic._id
        if object_logic.object_data is None or not object_logic.source_database_id:
            self.object_save_failed(object_id, "the Girder location of this data is unknown")
            return

        # The upload can take a while and the data can be edited meanwhile (e.g. segmentation): save a snapshot
        data = object_logic.object_data.NewInstance()
        data.DeepCopy(object_logic.object_data)

        is_volume = object_logic.scene_object.object_type == SceneObjectType.VOLUME
        segmentation_metadata = self._extract_segmentation_metadata(object_logic)

        self.save_tasks[object_id] = create_task(
            self._save(
                object_id,
                data,
                is_volume,
                _get_name_stem(object_logic.scene_object.name, object_logic.source_file_name),
                _get_output_extension(is_volume, object_logic.source_file_name),
                object_logic.source_database_id,
                folder_id,
                filename,
                overwrite,
                segmentation_metadata,
            )
        )
