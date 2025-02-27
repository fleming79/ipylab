import pytest

import ipylab


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
async def anyio_backend_autouse(anyio_backend):
    return anyio_backend


@pytest.fixture
async def app(mocker):
    app = ipylab.app
    mocker.patch.object(app, "ready")
    return app
