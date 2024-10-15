# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from asyncio import Task

from ipylab.connection import Connection
from ipylab.ipylab import Ipylab, Transform, Unicode


class SessionManager(Ipylab):
    """
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html
    """

    SINGLETON = True
    _basename = Unicode("app.serviceManager.sessions").tag(sync=True)

    def refresh_running(self):
        """Force a call to refresh running sessions."""
        return self.execute_method("refreshRunning")

    def stop_if_needed(self, path):
        """
        https://jupyterlab.readthedocs.io/en/latest/api/interfaces/services.Session.IManager.html#stopIfNeeded
        """
        return self.execute_method("stopIfNeeded", path)

    def new_sessioncontext(self, path: str) -> Task[Connection]:
        """
        Create a new sessionContext.

        path: The session path.
        """
        return self.app.schedule_operation("newSessionContext", path=path, transform=Transform.connection)
