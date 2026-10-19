"""core.api never builds an unauthenticated HTTP application (M43)."""
import sys
import types

from core.api.rest_api import DrillMasterAPI, create_app


def test_create_app_returns_the_in_process_object_even_when_fastapi_is_installed(monkeypatch):
    built = []

    class FastAPI:  # stand-in: records any attempt to construct an HTTP app
        def __init__(self, *args, **kwargs):
            built.append((args, kwargs))

        def get(self, *args, **kwargs):
            return lambda fn: fn

    monkeypatch.setitem(sys.modules, "fastapi", types.SimpleNamespace(FastAPI=FastAPI))
    api = create_app(db_manager=object())
    assert isinstance(api, DrillMasterAPI)
    assert built == []


def test_module_no_longer_claims_permission_enforcement():
    import core.api.rest_api as module

    assert "Permission enforcement via same PermissionManager" not in module.__doc__
    assert "does NOT check permissions" in module.__doc__
