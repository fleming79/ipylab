# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations  # noqa: I001

from ipylab._frontend import module_version as __version__
from ipylab.common import Area, InsertMode, NotificationType, Obj, Transform, hookimpl, pack
from ipylab.ipylab import Ipylab, _get_plugin_manager
from ipylab.connection import Connection, ShellConnection
from ipylab import menu
from ipylab.jupyterfrontend import App
from ipylab.widgets import Icon, Panel, SplitPanel

__all__ = [
    "__version__",
    "Connection",
    "ShellConnection",
    "Panel",
    "SplitPanel",
    "Icon",
    "Area",
    "NotificationType",
    "InsertMode",
    "hookimpl",
    "Transform",
    "pack",
    "_jupyter_labextension_paths",
    "Ipylab",
    "App",
    "Obj",
    "menu",
    "JupyterFrontEnd",
]


def _jupyter_labextension_paths():
    "Called by Jupyterlab see: jupyterlab.federated_labextensions._get_labextension_metadata."
    return [{"src": "labextension", "dest": "ipylab"}]


JupyterFrontEnd = App

plugin_manager = _get_plugin_manager()
del _get_plugin_manager
