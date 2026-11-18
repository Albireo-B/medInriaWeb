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

    def _get_unique_item_name(self, client: GirderClient, folder_id: str, stem: str, extension: str) -> str:
        name = f"{stem}{extension}"
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
    ) -> str:
        """Blocking, to be run in a thread. Returns the name of the item created in Girder."""
        client = self._get_girder_client()
        folder_id = client.getItem(source_item_id)["folderId"]

        with TemporaryDirectory(dir=self._temp_directory) as temp_dir:
            file_path = str(Path(temp_dir) / f"data{extension}")
            if is_volume:
                save_volume(data, file_path)
            else:
                save_mesh(data, file_path)

            with self._upload_lock:
                name = self._get_unique_item_name(client, folder_id, stem, extension)
                logger.debug(f"Uploading {name} to folder {folder_id}")
                client.uploadFileToFolder(folder_id, file_path, filename=name)
        return name

    async def _save(
        self,
        object_id: str,
        data: vtkDataObject,
        is_volume: bool,
        stem: str,
        extension: str,
        source_item_id: str,
    ) -> None:
        try:
            name = await asyncio.to_thread(self._write_and_upload, data, is_volume, stem, extension, source_item_id)
            self.object_saved(object_id, name)
        except Exception as error:  # The task must always report back, otherwise the object stays "saving"
            logger.exception(f"Error saving {object_id} to Girder")
            self.object_save_failed(object_id, _get_error_reason(error))
        finally:
            self.state.flush()
            self.save_tasks.pop(object_id, None)

    def save_object(self, object_logic: SceneObjectLogic) -> None:
        object_id = object_logic._id
        if object_logic.object_data is None or not object_logic.source_database_id:
            self.object_save_failed(object_id, "the Girder location of this data is unknown")
            return

        # The upload can take a while and the data can be edited meanwhile (e.g. segmentation): save a snapshot
        data = object_logic.object_data.NewInstance()
        data.DeepCopy(object_logic.object_data)

        is_volume = object_logic.scene_object.object_type == SceneObjectType.VOLUME
        self.save_tasks[object_id] = create_task(
            self._save(
                object_id,
                data,
                is_volume,
                _get_name_stem(object_logic.scene_object.name, object_logic.source_file_name),
                _get_output_extension(is_volume, object_logic.source_file_name),
                object_logic.source_database_id,
            )
        )
