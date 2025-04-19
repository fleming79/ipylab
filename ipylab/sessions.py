# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from traitlets import Unicode

from ipylab.common import Obj, Singular
from ipylab.ipylab import Ipylab, IpylabBase


class SessionManager(Singular, Ipylab):
    """
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html
    """

    _model_name = Unicode("SessionManagerModel", help="Name of the model.", read_only=True).tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "app.serviceManager.sessions").tag(sync=True)

    async def get_running(self, *, refresh=True) -> dict:
        "Get a dict of running sessions."
        return await self.operation("getRunning", {"refresh": refresh})

    async def get_current(self):
        "Get the session of the current widget in the shell."
        return await self.operation("getCurrentSession")

    async def stop_if_needed(self, *, path: str):
        """
        https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html#stopIfNeeded
        """
        return await self.execute_method("stopIfNeeded", (path,))
