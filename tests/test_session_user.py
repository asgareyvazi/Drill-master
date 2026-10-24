"""M44: every login path produces the same session dict.

The development auto-login used to hand ``MainWindow`` the object returned by
``authenticate_user``; ``MainWindow`` indexes ``user['username']`` and failed
with TypeError.  ``DrillMasterApp.show_login`` is called on a stub ``self``
(a second QApplication cannot be created in-process) with a real synthetic
file database and real authentication.
"""
from types import SimpleNamespace

import pytest

from core.permissions import session_user
from synthetic_operations import make_file_database


def test_session_user_shape_and_defaults():
    account = SimpleNamespace(id=7, username="syn", full_name="", role=None)
    assert session_user(account) == {"id": 7, "username": "syn", "full_name": "syn", "role": "user",
                                     "email": "syn@drillmaster.com"}
    full = SimpleNamespace(id=1, username="a", full_name="A B", role="admin", email="a@example.invalid")
    assert session_user(full)["role"] == "admin" and session_user(full)["email"] == "a@example.invalid"


@pytest.fixture
def database(tmp_path):
    db = make_file_database(tmp_path / "login.db")
    yield db
    db.engine.dispose()


def test_auto_login_yields_session_dict(database, monkeypatch):
    import app as app_module
    from core.permissions import permissions

    monkeypatch.setenv("DRILLMASTER_AUTO_LOGIN", "1")
    monkeypatch.setattr(app_module, "bootstrap_password_for_role", lambda role: "Synthetic-Admin-1!")
    monkeypatch.setattr(app_module, "is_production_environment", lambda: False)
    stub = SimpleNamespace(db_manager=database, user=None)
    previous = permissions.user
    try:
        assert app_module.DrillMasterApp.show_login(stub) is True
        assert isinstance(stub.user, dict)
        assert stub.user["username"] == "admin" and stub.user["role"] == "admin"
        assert stub.user == session_user(database.authenticate_user("admin", "Synthetic-Admin-1!"))
    finally:
        permissions.set_user(previous)


def test_auto_login_with_wrong_password_falls_back_to_dialog(database, monkeypatch):
    import app as app_module

    monkeypatch.setenv("DRILLMASTER_AUTO_LOGIN", "1")
    monkeypatch.setattr(app_module, "bootstrap_password_for_role", lambda role: "wrong-password")
    monkeypatch.setattr(app_module, "is_production_environment", lambda: False)

    class RejectingDialog:
        def __init__(self, _db):
            pass

        def exec(self):
            return 0                                   # cancelled

    monkeypatch.setattr(app_module, "LoginDialog", RejectingDialog)
    stub = SimpleNamespace(db_manager=database, user=None)
    assert app_module.DrillMasterApp.show_login(stub) is False
    assert stub.user is None
