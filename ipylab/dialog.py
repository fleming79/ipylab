# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Unpack

from ipywidgets import Widget
from traitlets import Unicode

from ipylab import Ipylab

if TYPE_CHECKING:
    from asyncio import Task
    from typing import Any

    from ipylab.common import IpylabKwgs


def _combine(options: dict | None, **kwgs):
    if options:
        kwgs.update(options)
    return kwgs


class Dialog(Ipylab):
    _model_name = Unicode("DialogModel", help="Name of the model.", read_only=True).tag(sync=True)

    def get_boolean(self, title: str, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]) -> Task[bool]:
        """Jupyter dialog to get a boolean value.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getBoolean.html
        """
        return self.operation("getBoolean", _combine(options, title=title), **kwgs)

    def get_item(
        self, title: str, items: tuple | list, *, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]
    ) -> Task[str]:
        """Jupyter dialog to get an item from a list value.

        note: will always return a string representation of the selected item.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getItem.html
        """
        return self.operation("getItem", _combine(options, title=title, items=tuple(items)), **kwgs)

    def get_number(self, title: str, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]) -> Task[float]:
        """Jupyter dialog to get a number.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getNumber.html
        """
        return self.operation("getNumber", _combine(options, title=title), **kwgs)

    def get_text(self, title: str, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]) -> Task[str]:
        """Jupyter dialog to get a string.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getText.html
        """
        return self.operation("getText", _combine(options, title=title), **kwgs)

    def get_password(self, title: str, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]) -> Task[str]:
        """Jupyter dialog to get a number.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getPassword.html
        """
        return self.operation("getPassword", _combine(options, title=title), **kwgs)

    def show_dialog(
        self,
        title: str = "",
        body: str | Widget = "",
        options: dict | None = None,
        **kwgs: Unpack[IpylabKwgs],
    ) -> Task[dict[str, Any]]:
        """Jupyter dialog to get user response with custom buttons and checkbox.

            returns {'value':any, 'isChecked':bool|None}

            'value' is the button 'accept' value of the selected button.

            title: 'Dialog title', // Can be text or a react element
            body: 'Dialog body', // Can be text, a widget or a react element
            specify kwgs passed as below.
            buttons: [ // List of buttons
            buttons=[
            {
                "ariaLabel": "Accept",
                "label": "Accept",
                "iconClass": "",
                "iconLabel": "",
                "caption": "Accept the result",
                "className": "",
                "accept": False,
                "actions": [],
                "displayType": "warn",
            },
            {
                "ariaLabel": "Cancel",
                "label": "Cancel",
                "iconClass": "",
                "iconLabel": "",
                "caption": "",
                "className": "",
                "accept": False,
                "actions": [],
                "displayType": "default",
            },
        ],
        ],
            ],
            checkbox: { // Optional checkbox in the dialog footer
                label: 'check me', // Checkbox label
                caption: 'check me I\'magic', // Checkbox title
                className: 'my-checkbox', // Additional checkbox CSS class
                checked: true, // Default checkbox state
            },
            defaultButton: 0, // Index of the default button
            focusNodeSelector: '.my-input', // Selector for focussing an input element when dialog opens
            hasClose: false, // Whether to display a close button or not
            renderer: undefined // To define customized dialog structure

            see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.showDialog.html
            source: https://jupyterlab.readthedocs.io/en/stable/extension/ui_helpers.html#generic-dialog
        """
        kwgs["toLuminoWidget"] = ["body"] if isinstance(body, Widget) else []
        return self.operation("showDialog", _combine(options, title=title, body=body), **kwgs)

    def show_error_message(
        self, title: str, error: str, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]
    ) -> Task[None]:
        """Jupyter error message.

        buttons = [
            {
                "ariaLabel": "Accept error",
                "label": "Okay",
                "iconClass": "",
                "iconLabel": "",
                "caption": "",
                "className": 'error-circle',
                "accept": False,
                "actions": [],
                "displayType": "warn",
            }
        ]

        https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.showErrorMessage.html#showErrorMessage
        """
        return self.operation("showErrorMessage", _combine(options, title=title, error=error), **kwgs)

    def get_open_files(self, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]) -> Task[list[str]]:
        """Get a list of files

        https://jupyterlab.readthedocs.io/en/latest/api/functions/filebrowser.FileDialog.getOpenFiles.html#getOpenFiles
        """
        return self.operation("getOpenFiles", options, **kwgs)

    def get_existing_directory(self, options: dict | None = None, **kwgs: Unpack[IpylabKwgs]) -> Task[str]:
        """
        https://jupyterlab.readthedocs.io/en/latest/api/functions/filebrowser.FileDialog.getExistingDirectory.html#getExistingDirectory
        """
        return self.operation("getExistingDirectory", options, **kwgs)
