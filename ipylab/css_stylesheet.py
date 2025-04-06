# Distributed under the terms of the Modified BSD License.
# Copyright (c) ipylab contributors.

from __future__ import annotations

from ipywidgets import TypedTuple
from traitlets import Dict, Unicode

from ipylab.common import Obj
from ipylab.ipylab import Ipylab

__all__ = ["CSSStyleSheet"]


class CSSStyleSheet(Ipylab):
    """Adds a new CSSStyleSheet to the document."""

    _model_name = Unicode("CSSStyleSheetModel", help="Name of the model.", read_only=True).tag(sync=True)
    css_rules = TypedTuple(trait=Unicode(), read_only=True, help="css rules set in this object")
    variables = Dict(
        key_trait=Unicode(), read_only=True, value_trait=Unicode(), help="Variables set through this object"
    )

    def __init__(self, **kwgs):
        if self._ipylab_init_complete:
            return
        super().__init__(**kwgs)
        self.on_ready(self._restore)

    async def _restore(self, _):
        # Restore rules and variables
        if self.variables:
            await self.set_variables(self.variables)
        if self.css_rules:
            await self.replace("\n".join(self.css_rules))

    async def _css_operation(self, operation: str, kwgs: dict | None = None) -> tuple[str, ...]:
        # Updates css_rules once operation is done
        self.css_rules = await self.operation(operation, kwgs=kwgs)
        return self.css_rules

    async def delete_rule(self, item: int | str):
        """Delete a rule by index or pass the exact string of the rule."""
        if isinstance(item, str):
            item = list(self.css_rules).index(item)
        return await self._css_operation("deleteRule", {"index": item})

    async def insert_rule(self, rule: str, index=None):
        ""
        return await self._css_operation("insertRule", {"rule": rule, "index": index})

    async def get_css_rules(self):
        """Get a list of the css_text specified for this instance."""
        return await self._css_operation("listCSSRules")

    async def replace(self, text: str):
        """Replace all css rules for this instance.

        ref: https://developer.mozilla.org/en-US/docs/Web/API/CSSStyleSheet/replace"""
        return await self._css_operation("replace", {"text": text})

    async def get_variables(self) -> dict[str, str]:
        """Get a dict mapping **all** variable names to values in Jupyterlab.

        Variables set via this object can be found from the property 'variables'.
        """
        return await self.execute_method("listVariables", obj=Obj.this)

    async def set_variables(self, variables: dict[str, str]) -> dict[str, str]:
        "Set a css variable."
        if invalid_names := [n for n in variables if not n.startswith("--")]:
            msg = f'Variable names must start with "--"!  {invalid_names=}'
            raise ValueError(msg)
        v: dict[str, str] = await self.execute_method("setVariables", (variables,), obj=Obj.this)
        self.set_trait("variables", self.variables | v)
        return self.variables
