# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import inspect
from enum import StrEnum
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

import traitlets
from ipywidgets import TypedTuple, register
from traitlets import Container, Instance, Unicode
from typing_extensions import override

from ipylab import Transform, pack
from ipylab.common import Obj, Singular, TransformType
from ipylab.connection import InfoConnection
from ipylab.ipylab import Ipylab, IpylabBase

if TYPE_CHECKING:
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

    async def update(
        self,
        message: str,
        type: NotificationType | None = None,  # noqa: A002
        *,
        auto_close: float | Literal[False] | None = None,
        actions: Iterable[NotifyAction | ActionConnection] = (),
    ) -> bool:
        await self.ready()
        args = {
            "id": f"{pack(self)}.id",
            "message": message,
            "type": NotificationType(type) if type else None,
            "autoClose": auto_close,
        }
        to_object = ["args.id"]

        actions_ = [await self.app.notification._ensure_action(v) for v in actions]  # noqa: SLF001
        if actions_:
            args["actions"] = list(map(pack, actions_))  # type: ignore
            to_object.extend(f"options.actions.{i}" for i in range(len(actions_)))
            for action in actions_:
                self.close_with_self(action)
        return await self.app.notification.operation("update", {"args": args}, toObject=to_object)


@register
class NotificationManager(Singular, Ipylab):
    """Create new notifications with access to the notification manager as base.

    ref: https://jupyterlab.readthedocs.io/en/stable/extension/ui_helpers.html#notifications
    """

    _model_name = Unicode("NotificationManagerModel").tag(sync=True)
    ipylab_base = IpylabBase(Obj.IpylabModel, "Notification.manager").tag(sync=True)

    connections: Container[tuple[NotificationConnection | ActionConnection, ...]] = TypedTuple(
        trait=Instance(InfoConnection)
    )

    @override
    async def _do_operation_for_frontend(self, operation: str, payload: dict, buffers: list):
        """Overload this function as required."""
        action = ActionConnection(payload["connection_id"])
        match operation:
            case "action_callback":
                action = ActionConnection(payload["connection_id"])
                await action.ready()
                callback = action.callback
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

    async def notify(
        self,
        message: str,
        type: NotificationType = NotificationType.default,  # noqa: A002
        *,
        auto_close: float | Literal[False] | None = None,
        actions: Iterable[NotifyAction | ActionConnection] = (),
    ) -> NotificationConnection:
        """Create a new notification.

        To update a notification use the update method of the returned `NotificationConnection`.

        NotifyAction:
            label: str
            callback: Callable[[], Any]
            display_type: NotRequired[Literal["default", "accent", "warn", "link"]]
            keep_open: NotRequired[bool]
            caption: NotRequired[str]
        """
        await self.ready()
        options = {"autoClose": auto_close}
        kwgs = {"type": NotificationType(type), "message": message, "options": options}
        actions_ = [await self._ensure_action(v) for v in actions]
        if actions_:
            options["actions"] = actions_  # type: ignore
        connection_id = NotificationConnection.to_id()
        notification: NotificationConnection = await self.operation(
            operation="notification",
            kwgs=kwgs,
            transform={"transform": Transform.connection, "connection_id": connection_id},
            toObject=[f"options.actions[{i}]" for i in range(len(actions_))] if actions_ else [],
        )
        notification.add_to_tuple(self, "connections")
        notification.info = kwgs
        return notification

    async def new_action(
        self,
        label: str,
        callback: Callable[[], Any],
        display_type: Literal["default", "accent", "warn", "link"] = "default",
        *,
        keep_open: bool = False,
        caption: str = "",
    ) -> ActionConnection:
        "Create an action to use in a notification."
        await self.ready()
        connection_id = ActionConnection.to_id()
        kwgs = {
            "label": label,
            "displayType": display_type,
            "keep_open": keep_open,
            "caption": caption,
            "connection_id": connection_id,
        }
        transform: TransformType = {"transform": Transform.connection, "connection_id": connection_id}
        ac: ActionConnection = await self.operation("createAction", kwgs, transform=transform)
        self.close_with_self(ac)
        ac.callback = callback
        ac.info = kwgs
        ac.add_to_tuple(self, "connections")
        return ac
