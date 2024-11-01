# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, TypeAlias, TypedDict

if sys.version_info < (3, 11):
    from typing_extensions import NotRequired, Self, TypedDict, Unpack, override
else:
    from typing import NotRequired, Self, TypedDict, Unpack, override

__all__ = ["NotRequired", "TYPE_CHECKING", "Any", "TypeAlias", "TypedDict", "Self", "Unpack", "override"]


def __dir__() -> list[str]:
    return __all__
