from girder.constants import AccessType
from girder.models.file import File
from girder.plugin import GirderPlugin, registerPluginStaticContent
from pathlib import Path


class MedViewerPlugin(GirderPlugin):
    DISPLAY_NAME = "GirderMedViewer Plugin"
    CLIENT_SOURCE_PATH = 'web_client'

    def load(self, info):
        File().exposeFields(level=AccessType.READ, fields="path")
        registerPluginStaticContent(
            plugin='girdermedviewer_plugin',
            css=[],
            js=['/girdermedviewer_plugin.umd.cjs'],
            staticDir=Path(__file__).parent / 'web_client' / 'dist',
            tree=info['serverRoot'],
        )
