"""M308 (D74, after the M307 D63 diagnosis): closed windows are freed only on a PySide6 without the D63 defect.

D63 is PySide6 6.8.1.1's SignalInstance weakref use-after-free (fixed upstream in 6.8.2, commit e226b5827c).
The policy keeps the M265 behaviour (closed windows retained) on 6.8.1.1, on an unknown version and when the
operator asks for it; on 6.8.2+ the three tab -> window attributes become weak. These tests never free a real
MainWindow on the pinned PySide6 (that is the crash); the release path is verified on plain classes and, for the
real window, by the opt-in probe ``tools/quality/d63_window_release_probe.py --mode product`` (M308 evidence).
"""
from __future__ import annotations

import weakref

import pytest

from core import qt_lifetime as lt


@pytest.mark.parametrize("version, release", [
    ("6.8.1.1", False), ("6.8.1", False), ("6.6.0", False), ("6.8.2", True), ("6.8.2.1", True),
    ("6.9.0", True), ("6.10.3", True), ("", False), ("6.8.x", False), ("garbage", False), (None, None),
])
def test_policy_by_version(version, release):
    policy = lt.window_release_policy(version, env={}) if version is not None else lt.window_release_policy(env={})
    if version is None:                                   # the installed PySide6 decides
        import PySide6
        expected = lt._version_tuple(PySide6.__version__) is not None and \
            lt._version_tuple(PySide6.__version__) >= lt.FIXED_PYSIDE
        assert policy["release"] is expected and policy["pyside"] == PySide6.__version__
    else:
        assert policy["release"] is release
    assert policy["reason"]                               # always explained
    if version == "6.8.1.1":
        assert "e226b5827c" in policy["reason"] and "retained" in policy["reason"]


def test_the_operator_can_force_retention():
    policy = lt.window_release_policy("6.9.0", env={lt.RETAIN_ENV: "1"})
    assert policy["release"] is False and lt.RETAIN_ENV in policy["reason"]


class _Window:
    pass


def _owner():
    class Tab:
        def __init__(self, window):
            self.parent_window = window
    return Tab


def test_release_installs_weak_attributes_that_let_the_window_go():
    Tab = _owner()
    early = Tab(_Window())                                  # created before the policy: plain attribute
    result = lt.apply_window_release_policy({"release": True, "pyside": "6.9.0", "reason": "test"},
                                            targets=[(Tab, "parent_window")])
    assert result["weak_attributes"] == ["Tab.parent_window"]
    assert isinstance(Tab.__dict__["parent_window"], lt.WeakWindowAttribute)
    assert isinstance(early.parent_window, _Window)         # never hidden by installing the descriptor
    window = _Window()
    tab = Tab(window)
    assert tab.parent_window is window
    ref = weakref.ref(window)
    del window                                              # refcount only, no gc pass
    assert ref() is None and tab.parent_window is None
    installed = Tab.__dict__["parent_window"]
    again = lt.apply_window_release_policy({"release": True, "pyside": "6.9.0", "reason": "test"},
                                           targets=[(Tab, "parent_window")])
    assert again["weak_attributes"] == ["Tab.parent_window"]
    assert Tab.__dict__["parent_window"] is installed               # idempotent: the same descriptor stays


def test_retention_installs_nothing_and_keeps_the_window_alive():
    Tab = _owner()
    result = lt.apply_window_release_policy({"release": False, "pyside": "6.8.1.1", "reason": "test"},
                                            targets=[(Tab, "parent_window")])
    assert result["weak_attributes"] == [] and "parent_window" not in Tab.__dict__
    window = _Window()
    tab = Tab(window)
    ref = weakref.ref(window)
    del window
    assert ref() is tab.parent_window is not None             # strong, as before (M265)


def test_the_product_classes_follow_the_installed_pyside():
    from tabs.home_tab import HomeTab
    from tabs.w1_well_info import WellInfoTab
    from tabs.w2_Daily_Report import DailyReportWidget

    result = lt.apply_window_release_policy()
    weak = {cls.__name__: isinstance(cls.__dict__.get(name), lt.WeakWindowAttribute)
            for cls, name in ((HomeTab, "parent_window"), (WellInfoTab, "main_window"),
                              (DailyReportWidget, "parent_window"))}
    assert set(weak.values()) == {result["release"]}
    if not result["release"]:                                  # the pinned 6.8.1.1: unchanged product behaviour
        assert result["weak_attributes"] == [] and "e226b5827c" in result["reason"]


def test_main_window_applies_the_policy_before_it_builds_any_tab():
    import inspect

    import main_window

    source = inspect.getsource(main_window.MainWindow.__init__)
    applied = source.find("self.window_release_policy = apply_window_release_policy()")
    assert 0 <= applied < source.find("self.init_ui()")             # init_ui -> create_tab_widget builds the tabs
