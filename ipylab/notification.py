# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict, override

import traitlets
from ipywidgets import TypedTuple, register
from traitlets import Container, Instance, Unicode

import ipylab
from ipylab import Transform, pack
from ipylab.common import Obj, TaskHooks, TransformType
from ipylab.connection import InfoConnection
from ipylab.ipylab import Ipylab, IpylabBase

if TYPE_CHECKING:
    from asyncio import Task
    from collections.abc import Callable, Iterable
    from typing import Any


__all__ = ["NotificationManager"]


class NotificationType(StrEnum):
    info = "info"
    progress = "in-progress"
    success = "success"
    warning = "warning"
    error = "error"
    default = "default"


class NotifyAction(TypedDict):
    label: str
    callback: Callable[[], Any]
    display_type: NotRequired[Literal["default", "accent", "warn", "link"]]
    keep_open: NotRequired[bool]
    caption: NotRequired[str]


class ActionConnection(InfoConnection):
    callback = traitlets.Callable()


class NotificationConnection(InfoConnection):
    actions: Container[tuple[ActionConnection, ...]] = TypedTuple(trait=Instance(ActionConnection))

    def update(
        self,
        message: str,
        type: NotificationType | None = None,  # noqa: A002
        *,
        auto_close: float | Literal[False] | None = None,
        actions: Iterable[NotifyAction | ActionConnection] = (),
    ) -> Task[bool]:
        args = {
            "id": f"{pack(self)}.id",
            "message": message,
            "type": NotificationType(type) if type else None,
            "autoClose": auto_close,
        }
        to_object = ["args.id"]

        async def update():
            actions_ = [await ipylab.app.notification._ensure_action(v) for v in actions]  # noqa: SLF001
            if actions_:
                args["actions"] = list(map(pack, actions_))  # type: ignore
                to_object.extend(f"options.actions.{i}" for i in range(len(actions_)))
                for action in actions_:
                    self.close_extras.add(action)
            return await ipylab.app.notification.operation("update", {"args": args}, toObject=to_object)

        return self.to_task(update())


@register
class NotificationManager(Ipylab):
    """Create new notifications with access to the notification manager as base.

    ref: https://jupyterlab.readthedocs.io/en/stable/extension/ui_helpers.html#notifications
    """

    SINGLE = True

    _model_name = Unicode("NotificationManagerModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "Notification.manager").tag(sync=True)

    connections: Container[tuple[NotificationConnection | ActionConnection, ...]] = TypedTuple(
        trait=Instance(InfoConnection)
    )

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Overload this function as required."""
        match operation:
            case "action_callback":
                callback = ActionConnection.get_existing_connection(payload["cid"]).callback
                result = callback()
                while inspect.isawaitable(result):
                    result = await result
                return result
        return await super()._do_operation_for_frontend(operation, payload, buffers)

    async def _ensure_action(self, value: ActionConnection | NotifyAction) -> ActionConnection:
        "Create a new action."
        if isinstance(value, ActionConnection):
            await value.ready()
            return value
        return await self.new_action(**value)  # type: ignore

    def notify(
        self,
        message: str,
        type: NotificationType = NotificationType.default,  # noqa: A002
        *,
        auto_close: float | Literal[False] | None = None,
        actions: Iterable[NotifyAction | ActionConnection] = (),
    ) -> Task[NotificationConnection]:
        """Create a new notification.

        To update a notification use the update method of the returned `NotificationConnection`.

        NotifyAction:
            label: str
            callback: Callable[[], Any]
            display_type: NotRequired[Literal["default", "accent", "warn", "link"]]
            keep_open: NotRequired[bool]
            caption: NotRequired[str]
        """

        options = {"autoClose": auto_close}
        kwgs = {"type": NotificationType(type), "message": message, "options": options}
        hooks: TaskHooks = {
            "add_to_tuple_fwd": [(self, "connections")],
            "trait_add_fwd": [("info", kwgs)],
        }

        async def notify():
            actions_ = [await self._ensure_action(v) for v in actions]
            if actions_:
                options["actions"] = actions_  # type: ignore
            cid = NotificationConnection.to_cid()
            notification: NotificationConnection = await self.operation(
                "notification",
                kwgs,
                transform={"transform": Transform.connection, "cid": cid},
                toObject=[f"options.actions[{i}]" for i in range(len(actions_))] if actions_ else [],
            )
            return notification

        return self.to_task(notify(), hooks=hooks)

    def new_action(
        self,
        label: str,
        callback: Callable[[], Any],
        display_type: Literal["default", "accent", "warn", "link"] = "default",
        *,
        keep_open: bool = False,
        caption: str = "",
    ) -> Task[ActionConnection]:
        "Create an action to use in a notification."
        cid = ActionConnection.to_cid()
        kwgs = {"label": label, "displayType": display_type, "keep_open": keep_open, "caption": caption, "cid": cid}
        transform: TransformType = {"transform": Transform.connection, "cid": cid}
        hooks: TaskHooks = {
            "trait_add_fwd": [("callback", callback), ("info", kwgs)],
            "add_to_tuple_fwd": [(self, "connections")],
            "close_with_fwd": [self],
        }
        return self.operation("createAction", kwgs, transform=transform, hooks=hooks)
