import asyncio
import json
from pathlib import Path

import pytest
from girder_client import HttpError
from trame.app import get_server
from vtk import (
    VTK_SHORT,
    VTK_UNSIGNED_CHAR,
    vtkImageData,
    vtkMatrix4x4,
    vtkNIFTIImageWriter,
    vtkSphereSource,
    vtkXMLPolyDataReader,
    vtkXMLPolyDataWriter,
)

from girdermedviewer.app.widgets.logic.girder.girder_save_logic import (
    GirderSaveLogic,
    _get_name_stem,
    _get_output_extension,
)
from girdermedviewer.app.widgets.utils import (
    load_mesh,
    load_volume,
    save_mesh,
    save_volume,
)

DIMENSIONS = (5, 4, 3)


def _voxel_values(image: vtkImageData) -> list[float]:
    nx, ny, nz = image.GetDimensions()
    return [image.GetScalarComponentAsDouble(i, j, k, 0) for k in range(nz) for j in range(ny) for i in range(nx)]


def _assert_same_volume(actual: vtkImageData, expected: vtkImageData) -> None:
    assert actual.GetDimensions() == expected.GetDimensions()
    assert actual.GetBounds() == expected.GetBounds()
    assert actual.GetScalarType() == expected.GetScalarType()
    assert _voxel_values(actual) == _voxel_values(expected)


@pytest.fixture
def nifti_volume(tmp_path) -> vtkImageData:
    """A volume loaded from a NIfTI file whose x axis is flipped and which is offset, as load_volume reorients it."""
    image = vtkImageData()
    image.SetDimensions(*DIMENSIONS)
    image.SetSpacing(2, 3, 4)
    image.AllocateScalars(VTK_SHORT, 1)
    for k in range(DIMENSIONS[2]):
        for j in range(DIMENSIONS[1]):
            for i in range(DIMENSIONS[0]):
                image.SetScalarComponentFromDouble(i, j, k, 0, i + 10 * j + 100 * k)

    sform = vtkMatrix4x4()
    sform.SetElement(0, 0, -1)
    sform.SetElement(0, 3, 40)
    sform.SetElement(1, 3, -50)
    sform.SetElement(2, 3, 10)
    writer = vtkNIFTIImageWriter()
    writer.SetInputData(image)
    writer.SetFileName(str(tmp_path / "source.nii.gz"))
    writer.SetQFormMatrix(sform)
    writer.SetSFormMatrix(sform)
    writer.Write()

    volume = load_volume(str(tmp_path / "source.nii.gz"))
    assert volume.GetOrigin() == (32.0, -50.0, 10.0)
    return volume


@pytest.mark.parametrize("extension", [".nii.gz", ".nii", ".mha"])
def test_save_volume_can_be_loaded_back_unchanged(tmp_path, nifti_volume, extension):
    file_path = str(tmp_path / f"saved{extension}")

    save_volume(nifti_volume, file_path)

    _assert_same_volume(load_volume(file_path), nifti_volume)


def test_save_labelmap_keeps_unsigned_char(tmp_path, nifti_volume):
    labelmap = nifti_volume.NewInstance()
    labelmap.CopyStructure(nifti_volume)
    labelmap.AllocateScalars(VTK_UNSIGNED_CHAR, 1)
    labelmap.GetPointData().GetScalars().FillComponent(0, 0)
    labelmap.SetScalarComponentFromDouble(1, 2, 1, 0, 3)
    file_path = str(tmp_path / "labelmap.nii.gz")

    save_volume(labelmap, file_path)

    _assert_same_volume(load_volume(file_path), labelmap)


def test_save_volume_fails_on_unsupported_format_or_unwritable_path(tmp_path, nifti_volume):
    with pytest.raises(ValueError, match="not handled"):
        save_volume(nifti_volume, str(tmp_path / "saved.nrrd"))
    for name in ("saved.mha", "saved.nii.gz"):
        with pytest.raises(OSError, match="Could not write"):
            save_volume(nifti_volume, str(tmp_path / "missing_directory" / name))


def test_save_mesh_undoes_the_axes_inversion_of_load_mesh(tmp_path):
    sphere = vtkSphereSource()
    sphere.SetCenter(10, 20, 30)
    sphere.SetRadius(5)
    sphere.Update()
    original_path = str(tmp_path / "original.vtp")
    writer = vtkXMLPolyDataWriter()
    writer.SetInputData(sphere.GetOutput())
    writer.SetFileName(original_path)
    writer.Write()
    mesh = load_mesh(original_path)
    assert mesh.GetBounds() != sphere.GetOutput().GetBounds()

    saved_path = str(tmp_path / "saved.vtp")
    save_mesh(mesh, saved_path)

    reader = vtkXMLPolyDataReader()
    reader.SetFileName(saved_path)
    reader.Update()
    assert reader.GetOutput().GetBounds() == pytest.approx(sphere.GetOutput().GetBounds())
    assert reader.GetOutput().GetNumberOfCells() == mesh.GetNumberOfCells()
    assert load_mesh(saved_path).GetBounds() == pytest.approx(mesh.GetBounds())


@pytest.mark.parametrize(
    ("is_volume", "source_file_name", "expected"),
    [
        (True, "brain.nii.gz", ".nii.gz"),
        (True, "BRAIN.NII", ".nii.gz"),
        (True, "brain.mha", ".mha"),
        (True, "brain.nrrd", ".mha"),
        (True, "dicom.zip", ".mha"),
        (True, None, ".mha"),
        (False, "tracts.vtp", ".vtp"),
        (False, "shape.stl", ".vtp"),
    ],
)
def test_output_extension_follows_source_format(is_volume, source_file_name, expected):
    assert _get_output_extension(is_volume, source_file_name) == expected


@pytest.mark.parametrize(
    ("name", "source_file_name", "expected"),
    [
        ("brain.nii.gz", "brain.nii.gz", "brain"),
        ("brain.nii.gz_gaussian blur", "brain.nii.gz", "brain_gaussian blur"),
        ("Brain.NII.GZ_segmentation", "brain.nii.gz", "Brain_segmentation"),
        ("patient/1: brain", None, "patient_1_ brain"),
        ("name without extension", "other.mha", "name without extension"),
        ("", None, "untitled"),
    ],
)
def test_name_stem_removes_source_extension_and_invalid_characters(name, source_file_name, expected):
    assert _get_name_stem(name, source_file_name) == expected


class FakeGirderClient:
    """Like Girder, uploading to a folder adds the file to the item with the same name if there is one."""

    def __init__(self, existing_names=(), error: HttpError | None = None):
        self.items = {"source": {"name": "brain.nii.gz", "folderId": "folder", "files": 1}}
        for index, name in enumerate(existing_names):
            self.items[f"existing{index}"] = {"name": name, "folderId": "folder", "files": 1}
        self.error = error
        self.uploads = []

    def getItem(self, item_id):
        return self.items[item_id]

    def listItem(self, folder_id, name=None):
        return iter(item for item in self.items.values() if item["folderId"] == folder_id and item["name"] == name)

    def uploadFileToFolder(self, folder_id, file_path, filename=None):
        if self.error:
            raise self.error
        self.uploads.append((folder_id, filename, Path(file_path).read_bytes()))
        self.items[f"uploaded{len(self.uploads)}"] = {"name": filename, "folderId": folder_id, "files": 1}


def _save(client: FakeGirderClient, data, is_volume=True, stem="brain_gaussian blur", extension=".nii.gz"):
    save_logic = GirderSaveLogic(get_server("test_save"), lambda: client, temp_directory=None)
    saved, failed = [], []
    save_logic.object_saved.connect(lambda *args: saved.append(args))
    save_logic.object_save_failed.connect(lambda *args: failed.append(args))
    asyncio.run(save_logic._save("object", data, is_volume, stem, extension, "source"))
    return saved, failed


def test_save_uploads_new_item_in_the_folder_of_the_source_item(nifti_volume, tmp_path):
    client = FakeGirderClient()

    saved, failed = _save(client, nifti_volume)

    assert failed == []
    assert saved == [("object", "brain_gaussian blur.nii.gz")]
    folder_id, name, content = client.uploads[0]
    assert (folder_id, name) == ("folder", "brain_gaussian blur.nii.gz")
    uploaded_path = tmp_path / "uploaded.nii.gz"
    uploaded_path.write_bytes(content)
    _assert_same_volume(load_volume(str(uploaded_path)), nifti_volume)


def test_save_never_adds_a_file_to_an_existing_item(nifti_volume):
    client = FakeGirderClient(existing_names=["brain_gaussian blur.nii.gz", "brain_gaussian blur_1.nii.gz"])

    saved, _ = _save(client, nifti_volume)

    assert saved == [("object", "brain_gaussian blur_2.nii.gz")]


def test_save_mesh_as_vtp():
    sphere = vtkSphereSource()
    sphere.Update()
    client = FakeGirderClient()

    saved, failed = _save(client, sphere.GetOutput(), is_volume=False, stem="tracts", extension=".vtp")

    assert failed == []
    assert saved == [("object", "tracts.vtp")]
    assert client.uploads[0][2].startswith(b"<?xml")


def test_save_reports_girder_error_message(nifti_volume):
    error = HttpError(403, json.dumps({"message": "Write access denied for folder.", "type": "access"}), "url", "POST")

    saved, failed = _save(FakeGirderClient(error=error), nifti_volume)

    assert saved == []
    assert failed == [("object", "Write access denied for folder.")]


def test_save_reports_http_status_when_girder_gives_no_message(nifti_volume):
    error = HttpError(502, "<html>Bad gateway</html>", "url", "POST")

    _, failed = _save(FakeGirderClient(error=error), nifti_volume)

    assert failed == [("object", "HTTP error 502")]
