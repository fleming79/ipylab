# Distributed under the terms of the Modified BSD License.
# Copyright (c) ipylab contributors.

from __future__ import annotations

from typing import TYPE_CHECKING

from ipywidgets import TypedTuple
from traitlets import Dict, Unicode

from ipylab.common import Obj
from ipylab.ipylab import Ipylab

if TYPE_CHECKING:
    from asyncio import Task

__all__ = ["CSSStyleSheet"]


class CSSStyleSheet(Ipylab):
    """Adds a new CSSStyleSheet to the document."""

    _model_name = Unicode("CSSStyleSheetModel", help="Name of the model.", read_only=True).tag(sync=True)
    css_rules = TypedTuple(trait=Unicode(), read_only=True, help="css rules set in this object")
    variables = Dict(
        key_trait=Unicode(), read_only=True, value_trait=Unicode(), help="Variables set through this object"
    )

    def __init__(self, **kwgs):
        super().__init__(**kwgs)
        self.on_ready(self._restore)

    def _restore(self, _):
        # Restore rules and variables
        if self.variables:
            self.set_variables(self.variables)
        if self.css_rules:
            self.replace("\n".join(self.css_rules))

    def _css_operation(self, operation: str, kwgs: dict | None = None):
        # Updates css_rules once operation is done
        return self.operation(operation, kwgs, hooks={"trait_add_rev": [(self, "css_rules")]})

    def delete_rule(self, item: int | str):
        """Delete a rule by index or pass the exact string of the rule."""
        if isinstance(item, str):
            item = list(self.css_rules).index(item)
        return self._css_operation("deleteRule", {"index": item})

    def insert_rule(self, rule: str, index=None):
        ""
        return self._css_operation("insertRule", {"rule": rule, "index": index})

    def get_css_rules(self):
        """Get a list of the css_text specified for this instance."""
        return self._css_operation("listCSSRules")

    def replace(self, text: str):
        """Replace all css rules for this instance.

        ref: https://developer.mozilla.org/en-US/docs/Web/API/CSSStyleSheet/replace"""
        return self._css_operation("replace", {"text": text})

    def get_variables(self) -> Task[dict[str, str]]:
        """Get a dict mapping **all** variable names to values in Jupyterlab.

        Variables set via this object can be found from the property 'variables'.
        """
        return self.execute_method("listVariables", obj=Obj.this)

    def set_variables(self, variables: dict[str, str]) -> Task[dict[str, str]]:
        "Set a css variable."
        if invalid_names := [n for n in variables if not n.startswith("--")]:
            msg = f'Variable names must start with "--"!  {invalid_names=}'
            raise ValueError(msg)
        return self.execute_method(
            "setVariables", variables, obj=Obj.this, hooks={"callbacks": [self.variables.update]}
        )
