from types import SimpleNamespace

from app_nativa import get_storage


def test_get_storage_creates_page_fallback_storage():
    page = SimpleNamespace()
    storage = get_storage(page)

    assert storage is page._app_storage
    storage["token"] = "abc"
    assert get_storage(page)["token"] == "abc"


def test_get_storage_uses_client_storage_when_available():
    storage_backend = {"token": "xyz"}
    page = SimpleNamespace(client_storage=storage_backend)

    assert get_storage(page) is storage_backend
