"""The signed-in principal never leaks from one test into the next (M46).

The two tests run in file order: the first signs a SYNTHETIC user in and does
not sign out (as several older modules do); the second must start with the
principal that was current before the first test.  Without the autouse
``_isolate_session_principal`` fixture in ``tests/conftest.py`` the second
test sees the leaked user.
"""
import pytest

from core.permissions import permissions

_SENTINEL = {"id": 987654, "username": "syn-leak-probe", "role": "admin"}
_seen = {}


def test_a_test_that_signs_in_and_never_signs_out():
    _seen["before"] = permissions.user
    permissions.set_user(dict(_SENTINEL))
    assert permissions.user["username"] == "syn-leak-probe"


def test_the_next_test_starts_with_the_previous_principal():
    assert "before" in _seen, "file order changed; the probe needs the first test to run first"
    assert permissions.user == _seen["before"]
    assert (permissions.user or {}).get("username") != "syn-leak-probe"


# A module-scoped sign-in (as tests/test_documents_tab.py and tests/test_m45_ui.py
# use) must survive a test that switches to another user: the fixture restores the
# principal that was current BEFORE the test, not "nobody".
_MODULE_USER = {"id": 987655, "username": "syn-module-principal", "role": "engineer"}


@pytest.fixture(scope="module")
def module_principal():
    previous = permissions.user
    permissions.set_user(dict(_MODULE_USER))
    yield
    permissions.set_user(previous)


def test_a_test_switches_away_from_the_module_principal(module_principal):
    assert permissions.user["username"] == "syn-module-principal"
    permissions.set_user(dict(_SENTINEL))


def test_the_module_principal_is_current_again(module_principal):
    assert (permissions.user or {}).get("username") == "syn-module-principal"
