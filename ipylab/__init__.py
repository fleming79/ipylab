# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from ipylab import common, log, menu, widgets
from ipylab._frontend import module_version as __version__
from ipylab.common import Area, Fixed, InsertMode, Obj, Transform, pack, to_selector
from ipylab.connection import Connection, ShellConnection
from ipylab.ipylab import Ipylab
from ipylab.jupyterfrontend import JupyterFrontEnd
from ipylab.widgets import Icon, Panel, SplitPanel

__all__ = [
    "Area",
    "Connection",
    "Fixed",
    "Icon",
    "InsertMode",
    "Ipylab",
    "JupyterFrontEnd",
    "JupyterFrontEnd",
    "Obj",
    "Panel",
    "ShellConnection",
    "SplitPanel",
    "Transform",
    "__version__",
    "_jupyter_labextension_paths",
    "common",
    "log",
    "menu",
    "pack",
    "to_selector",
    "widgets",
]


def _jupyter_labextension_paths():
    "Called by Jupyterlab see: jupyterlab.federated_labextensions._get_labextension_metadata."
    return [{"src": "labextension", "dest": "ipylab"}]
