# Copyright (c) ipylab contributors.
# Distributed under the terms of the Modified BSD License.

from __future__ import annotations

import sys

if sys.version_info < (3, 12):
    from typing_extensions import override
else:
    from typing import override

__all__ = ["override"]


def __dir__() -> list[str]:
    return __all__
