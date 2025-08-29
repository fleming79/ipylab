import ipylab
import pytest
from async_kernel import Caller


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture
async def app(mocker):
    async with Caller(create=True):
        app = ipylab.App()
        mocker.patch.object(app, "ready")
        yield app
