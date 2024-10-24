# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from asyncio import Task
from typing import TYPE_CHECKING

from ipylab.common import Obj
from ipylab.connection import Connection
from ipylab.ipylab import Ipylab, IpylabBase, Transform

if TYPE_CHECKING:
    from ipylab.common import TransformType


class SessionManager(Ipylab):
    """
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html
    """

    SINGLE = True

    ipylab_base = IpylabBase(Obj.IpylabModel, "app.serviceManager.sessions").tag(sync=True)

    def refresh_running(self):
        """Force a call to refresh running sessions."""
        return self.execute_method("refreshRunning")

    def stop_if_needed(self, path):
        """
        https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html#stopIfNeeded
        """
        return self.execute_method("stopIfNeeded", path)

    def new_sessioncontext(self, vpath: str) -> Task[Connection]:
        """
        Create a new sessionContext.

        vpath: The session path.
        """
        transform: TransformType = {"transform": Transform.connection, "cid": Connection.to_cid(), "auto_dispose": True}
        return self.execute_method("newSessionContext", vpath, obj=Obj.IpylabModel, transform=transform)
