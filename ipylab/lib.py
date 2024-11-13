# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
import weakref
from asyncio import Task
from typing import TYPE_CHECKING, Any

from ipywidgets import HTML, Button, Combobox, HBox, Select, Widget, dlink

import ipylab
from ipylab.common import ErrorSource, IpylabFrontendError, IpylabKwgs, TaskHooks, hookimpl
from ipylab.ipylab import Ipylab
from ipylab.notification import NotifyAction

objects = {}

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from traitlets import HasTraits

    from ipylab import App


def trait_tuple_add(owner: HasTraits, name: str, value: Any):
    items = getattr(owner, name)
    if value not in items:
        owner.set_trait(name, (*items, value))


@hookimpl
def launch_jupyterlab():
    import sys

    from jupyterlab.labapp import LabApp

    if not sys.argv:
        sys.argv = ["--ServerApp.token=''"]
    sys.exit(LabApp.launch_instance())


def truncated(obj: Any, maxlen=40) -> str:
    "Do string representation of ob truncated to maxlen."
    rep = repr(obj)
    if len(rep) > maxlen:
        return rep[0:maxlen] + "…"
    return rep


@hookimpl
def on_error(obj: ipylab.Ipylab, error: Exception, msg: str):
    obj.log.exception(str(msg), exc_info=error)
    if "error_objects" not in objects:
        objects["error objects"] = weakref.WeakValueDictionary()
    message = f"{truncated(ipylab.app.vpath)}: {truncated(error, 100)} "
    objects["error objects"][f'{truncated(obj)}→{truncated(msg, 60)} {truncated(error, 100)} "'] = obj
    task = objects.get("error_task")
    if isinstance(task, Task):
        # Limit to one notification.
        if not task.done():
            return
        task.result().close()
    a = NotifyAction(label="📄", caption="Show error panel.", callback=show_error_panel, keep_open=True)
    objects["error_task"] = ipylab.app.notification.notify(message, type=ipylab.NotificationType.error, actions=[a])


def show_error_panel():
    "Show an error panel making it possible to view the log and then add an object to the console."
    if "error_panel" not in objects:
        header = HTML(
            f"<h3>Vpath: {ipylab.app.vpath}</h3>",
            tooltip="Use this panel to access the log console from either\n"
            "1. The icon in the status bar, or,\n"
            "2. The context menu (right click).\n"
            "The controls below are provided to put an object into a console.\n"
            "Note: Jupyterlab loads a different 'log console'  for the 'console'.",
        )
        select_objs = objects["select_objects"] = Select(layout={"width": "auto", "height": "80%"})
        obj_name = Combobox(
            placeholder="Name to use in console ['obj'])",
            options=[f"ojb_{i}" for i in range(10)],
            layout={"flex": "1 0 auto"},
        )
        objects["namespace"] = namespace = Combobox(
            placeholder="Namespace ['']",
            layout={"flex": "1 0 auto"},
        )
        button_add_to_console = Button(
            description="Add to console",
            tooltip="Add an object to the console.\nTip: use the context menu of this pane to access log console.",
            layout={"width": "auto"},
        )
        controls = HBox([obj_name, namespace, button_add_to_console], layout={"height": "80px"})
        objects["error_panel"] = error_panel = ipylab.Panel(
            [header, select_objs, controls],
            layout={"justify_content": "space-between", "padding": "20px"},
        )
        error_panel.title.label = "Error panel"
        dlink((obj_name, "value"), (button_add_to_console, "disabled"), transform=lambda value: not value)

        def on_click(_):
            if obj := objects["error objects"].get(select_objs.value):
                ipylab.app.open_console(objects={obj_name.value or "obj": obj}, namespace_name=namespace.value)
            else:
                show_error_panel()

        button_add_to_console.on_click(on_click)
        objects["select_objects"].options = tuple(reversed(list(objects.get("error objects", []))))
    objects["namespace"].options = tuple(ipylab.app.namespaces)
    objects["error_panel"].add_to_shell(mode=ipylab.InsertMode.split_bottom)


@hookimpl
async def autostart(app: ipylab.App) -> None | Awaitable[None]:
    # Register some default context menu items for Ipylab
    cmd = await app.commands.add_command("Open console", app._context_open_console)  # noqa: SLF001
    await app.context_menu.add_item(command=cmd, rank=20)
    await app.context_menu.add_item(command="logconsole:open", args={"source": app.vpath}, rank=21)


@hookimpl
def ensure_run(obj: ipylab.Ipylab, aw: Callable | Awaitable | None):
    try:
        if callable(aw):
            try:
                aw = aw(obj)
            except TypeError:
                aw = aw()
        if inspect.iscoroutine(aw):
            obj.to_task(aw, f"Ensure run {aw}")
    except Exception as e:
        obj.on_error(e, ErrorSource.EnsureRun)
        raise
    else:
        return True


@hookimpl
def task_result(obj: Ipylab, result: HasTraits, hooks: TaskHooks):
    # close with
    for owner in hooks.pop("close_with_fwd", ()):
        # Close result with each item.
        if isinstance(owner, Ipylab) and isinstance(result, Widget):
            if not owner.comm:
                result.close()
                raise RuntimeError(str(owner))
            owner.close_extras.add(result)
    for obj_ in hooks.pop("close_with_rev", ()):
        # Close each item with the result.
        if isinstance(result, Ipylab):
            result.close_extras.add(obj_)

    # tuple add
    for owner, name in hooks.pop("add_to_tuple_fwd", ()):
        # Add each item of to tuple of result.
        if isinstance(result, Ipylab):
            result.add_to_tuple(owner, name)
        else:
            trait_tuple_add(owner, name, result)
    for name, value in hooks.pop("add_to_tuple_rev", ()):
        # Add the result the the tuple with 'name' for each item.
        if isinstance(value, Ipylab):
            value.add_to_tuple(result, name)
        else:
            trait_tuple_add(result, name, value)

    # trait add
    for name, value in hooks.pop("trait_add_fwd", ()):
        # Set each trait of result with value.
        if isinstance(value, Ipylab):
            value.add_as_trait(result, name)
        else:
            result.set_trait(name, value)
    for owner, name in hooks.pop("trait_add_rev", ()):
        # Set set trait of each value with result.
        if isinstance(result, Ipylab):
            result.add_as_trait(owner, name)
        else:
            owner.set_trait(name, result)

    for cb in hooks.pop("callbacks", ()):
        ensure_run(obj, cb(result))

    if hooks:
        msg = f"Invalid hooks detected: {hooks}"
        raise ValueError(msg)


@hookimpl
def opening_console(app: App, args: dict, objects: dict, kwgs: IpylabKwgs):
    "no-op"


@hookimpl
def vpath_getter(app: App, kwgs: dict) -> Awaitable[str] | str:
    return app.dialog.get_text(**kwgs)


@hookimpl
def ready(obj: Ipylab):
    "Pass through"


@hookimpl
def to_frontend_error(obj: ipylab.Ipylab, content: dict) -> IpylabFrontendError:
    error = content["error"]
    operation = content.get("operation")
    max_chars = 40
    if operation:
        s = str(obj)
        if len(s) > max_chars:
            s = s[0:max_chars] + "…"
        msg = f'{s} operation "{operation}" failed with the message "{error}"'
        return IpylabFrontendError(msg)
    return IpylabFrontendError(error)
