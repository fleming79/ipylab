# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ipywidgets import Widget
from traitlets import Unicode

from ipylab import Ipylab

if TYPE_CHECKING:
    from typing import Any


def _combine(options: dict | None, **kwgs) -> dict[str, Any]:
    if options:
        kwgs.update(options)
    return kwgs


class Dialog(Ipylab):
    _model_name = Unicode("DialogModel", help="Name of the model.", read_only=True).tag(sync=True)

    async def get_boolean(self, title: str, options: dict | None = None) -> bool:
        """Open a Jupyterlab dialog to get a boolean value.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getBoolean.html
        """
        return await self.operation("getBoolean", kwgs=_combine(options, title=title))

    async def get_item(self, title: str, items: tuple | list, *, options: dict | None = None) -> str:
        """Open a Jupyterlab dialog to get an item from a list value.

        note: will always return a string representation of the selected item.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getItem.html
        """
        return await self.operation("getItem", kwgs=_combine(options, title=title, items=tuple(items)))

    async def get_number(self, title: str, options: dict | None = None) -> float:
        """Open a Jupyterlab dialog to get a number.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getNumber.html
        """
        return await self.operation("getNumber", kwgs=_combine(options, title=title))

    async def get_text(self, title: str, options: dict | None = None) -> str:
        """Open a Jupyterlab dialog to get a string.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getText.html
        """
        return await self.operation("getText", kwgs=_combine(options, title=title))

    async def get_password(self, title: str, options: dict | None = None) -> str:
        """Open a Jupyterlab dialog to get a number.
        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.InputDialog.getPassword.html
        """
        return await self.operation("getPassword", kwgs=_combine(options, title=title))

    async def show_dialog(
        self, title: str = "", body: str | Widget = "", options: dict | None = None, *, has_close=True
    ) -> dict[str, Any]:
        """Open a Jupyterlab dialog to get user response with custom buttons and
        checkbox.

        returns {'value':any, 'isChecked':bool|None}

        'value' is the button 'accept' value of the selected button.

        title: str
            The dialog title.  // Can be text or a react element

        body: str | Widget
            Text to show in the body or a widget. 'Dialog body', // Can be text,
            a widget or a react element

        has_close: bool [True]
            By default (), clicking outside the dialog will close it.
            When `False`, the user must specifically cancel or accept a result.

        options:
            specify options can be passed as below.
            buttons: [ // List of buttons
            buttons=[
            {
                "ariaLabel": "Accept",
                "label": "Accept",
                "iconClass": "",
                "iconLabel": "",
                "caption": "Accept the result",
                "className": "",
                "accept": True,
                "actions": [],
                "displayType": "default",
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
                "displayType": "warn",
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
            renderer: undefined // To define customized dialog structure

        see: https://jupyterlab.readthedocs.io/en/stable/api/functions/apputils.showDialog.html
        source: https://jupyterlab.readthedocs.io/en/stable/extension/ui_helpers.html#generic-dialog
        """
        kwgs = _combine(options, title=title, body=body, hasClose=has_close)
        to_lumino_widget = ["body"] if isinstance(body, Widget) else None
        return await self.operation("showDialog", kwgs=kwgs, toLuminoWidget=to_lumino_widget)

    async def show_error_message(self, title: str, error: str, options: dict | None = None) -> None:
        """Open a Jupyterlab error message dialog.

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
        return await self.operation("showErrorMessage", kwgs=_combine(options, title=title, error=error))

    async def get_open_files(self, options: dict | None = None) -> bool:
        """Get a list of files using a Jupyterlab dialog relative to the current
        path in Jupyterlab.

        https://jupyterlab.readthedocs.io/en/latest/api/functions/filebrowser.FileDialog.getOpenFiles.html#getOpenFiles
        """
        return await self.operation("getOpenFiles", kwgs=options)

    async def get_existing_directory(self, options: dict | None = None) -> str:
        """Get an existing directory using a Jupyterlab dialog relative to the
        current path in Jupyterlab.
        https://jupyterlab.readthedocs.io/en/latest/api/functions/filebrowser.FileDialog.getExistingDirectory.html#getExistingDirectory
        """
        return await self.operation("getExistingDirectory", kwgs=options)
