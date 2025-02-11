import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend
