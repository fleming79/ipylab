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
async def caller(anyio_backend):
    async with Caller(create=True) as caller:
        yield caller


@pytest.fixture
async def app(caller, mocker):
    app = ipylab.App()
    mocker.patch.object(app, "ready")
    return app
