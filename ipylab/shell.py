# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.
from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import Widget

from ipylab import Area, Connection, InsertMode, ShellConnection, Transform, pack
from ipylab.ipylab import Ipylab, Unicode

if TYPE_CHECKING:
    import inspect
    from asyncio import Task


__all__ = ["Shell"]


class Shell(Ipylab):
    """
    Provides access to the shell.
    The minimal interface is:
    https://jupyterlab.readthedocs.io/en/latest/api/interfaces/application.JupyterFrontEnd.IShell.html

    Likely the full labShell interface.

    ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/application.JupyterFrontEnd.IShell.html#add
    """

    SINGLETON = True
    _basename = Unicode("shell").tag(sync=True)

    def add(
        self,
        obj: Widget | inspect._SourceObjectType,
        *,
        area: Area = Area.main,
        activate: bool = True,
        mode: InsertMode = InsertMode.tab_after,
        rank: int | None = None,
        ref: ShellConnection | None = None,
        options: dict | None = None,
        cid: ShellConnection | Widget | str | None = None,
        **kwgs,
    ) -> Task[ShellConnection]:
        """
        Add a widget or evaluation to the shell.

        When `obj` is NOT a Widget it is assumed `obj` should be evaluated in a python kernel.

        This uses the same method `evaluate` The evaluation must return a Widget.

            Additional **kwgs:
                kernelId: leave blank to start a new kernel.
                path: The path of the sessionContext to use when creating a new kernel.


        ref: https://jupyterlab.readthedocs.io/en/latest/api/interfaces/application.JupyterFrontEnd.IShell.html#add

        options: dict
            mode: InsertMode
            https://jupyterlab.readthedocs.io/en/latest/api/interfaces/docregistry.DocumentRegistry.IOpenOptions.html

        cid:
            Specify the cid to use. Useful to restrict the view in the shell to one. If there is
            already an existing shell connection, it will be used even if an obj is provided.

        Basic example
        -------------

        The example evaluates code in a session with path="test".
        ```
        ipylab.app.shell.add("ipylab.Panel([ipw.HTML('<h1>Test')])", path="test")
        ```
        """

        async def add_to_shell():
            async with self.app as app:
                if isinstance(obj, Widget) and "kernelId" not in kwgs and "path" not in kwgs and app.current_session:
                    kwgs["path"] = app.current_session["path"]
                    kwgs["kernelId"] = app.current_session["kernel"]["id"]

                kwgs["options"] = {
                    "activate": activate,
                    "mode": InsertMode(mode),
                    "rank": int(rank) if rank else None,
                    "ref": ref.id if isinstance(ref, Connection) else None,
                } | (options or {})
                if isinstance(obj, Widget):
                    kwgs["id"] = obj.id if isinstance(obj, Connection) else pack(obj)
                else:
                    kwgs["evaluate"] = pack(obj)
                cid_ = ShellConnection.to_cid(cid) if cid else ShellConnection.to_cid()
                kwgs["transform"] = {"transform": Transform.connection, "cid": cid_}
            return await self.execute_command("ipylab:add-to-shell", cid=cid_, area=area, **kwgs)

        return self.to_task(add_to_shell())

    def expand_left(self):
        return self.execute_method("expandLeft")

    def expand_right(self):
        return self.execute_method("expandRight")

    def collapse_left(self):
        return self.execute_method("collapseLeft")

    def collapse_right(self):
        return self.execute_method("collapseRight")
