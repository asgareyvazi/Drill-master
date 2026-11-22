"""M265 (D74): lifetime helpers for references between a window, its children and process-wide services.

* ``SignalRoutes`` / ``routes_of`` / ``disconnect_window_routes``: connections from the process-wide
  ``SelectionManager`` to slots owned by one window, disconnected on the window's accepted close, so a closed
  window gets no stale selection updates and a reopened one gets exactly one set of routes.
* ``weak_or_strong``: a weak reference where possible (``StatusBarManager`` no longer keeps a closed window).
* ``WeakWindowAttribute`` + ``window_release_policy`` / ``apply_window_release_policy`` (M308): the three tab
  attributes that pointed back at their window (``HomeTab.parent_window``, ``WellInfoTab.main_window``,
  ``DailyReportWidget.parent_window``) kept every closed window alive (D74).  Making them weak lets a closed window
  be freed, and on PySide6 6.8.1.1 freeing closed windows reproduces the D63 SIGSEGV deterministically.
  M307 identified the D63 cause: PySide6 6.8.1.1 registers a weakref callback on the signal source whose user
  data is a raw pointer to the SignalInstance (``instanceInitialize`` -> ``WeakRef::create(source, sourceGone,
  self)``); when the SignalInstance is freed first, ``sourceGone`` writes into freed memory.  Upstream commit
  e226b5827c ("Reduce number of weakref handlers for sender tracking", PYSIDE-2201) replaced it with shared
  state; it ships in 6.8.2.  The policy therefore releases closed windows only on PySide6 >= 6.8.2 and keeps them
  retained (the M265 behaviour) on older versions, on an unparseable version, or when
  ``DRILLMASTER_RETAIN_CLOSED_WINDOWS=1``.
"""
from __future__ import annotations

import logging
import weakref


class _Strong:
    """Holder with the call interface of ``weakref.ref`` for objects that cannot be weakly referenced."""

    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def weak_or_strong(value):
    """``weakref.ref(value)`` when possible, else a strong holder; ``None`` stays ``None``."""
    if value is None:
        return None
    try:
        return weakref.ref(value)
    except TypeError:
        return _Strong(value)


class WeakWindowAttribute:
    """Data descriptor: ``self.parent_window = window`` stores a weak reference; reading it returns the window or
    ``None`` once the window has been freed.  A value stored as a plain instance attribute before the descriptor
    was installed is still returned (installing it never hides an existing reference)."""

    def __set_name__(self, owner, name):
        self._name = name
        self._slot = f"_weak_ref_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        if self._slot not in obj.__dict__:
            return obj.__dict__.get(self._name)
        ref = obj.__dict__[self._slot]
        return ref() if ref is not None else None

    def __set__(self, obj, value):
        obj.__dict__[self._slot] = weak_or_strong(value)


FIXED_PYSIDE = (6, 8, 2)     # first PySide6 release with upstream commit e226b5827c (M307, D63)
RETAIN_ENV = "DRILLMASTER_RETAIN_CLOSED_WINDOWS"
WINDOW_ATTRIBUTES = (("tabs.home_tab", "HomeTab", "parent_window"),
                     ("tabs.w1_well_info", "WellInfoTab", "main_window"),
                     ("tabs.w2_Daily_Report", "DailyReportWidget", "parent_window"))


def _version_tuple(text):
    parts = []
    for piece in str(text or "").split(".")[:3]:
        digits = "".join(ch for ch in piece if ch.isdigit())
        if not digits or digits != piece:
            return None
        parts.append(int(digits))
    return tuple(parts) if len(parts) == 3 else None


def window_release_policy(version=None, env=None) -> dict:
    """Whether closed MainWindows may be freed: ``{"release": bool, "pyside": str, "reason": str}``.  Never raises."""
    import os

    env = os.environ if env is None else env
    if version is None:
        try:
            import PySide6
            version = PySide6.__version__
        except ImportError:  # silent-ok: unknown version -> unparseable -> windows are retained (the safe M265 default)
            version = ""
    if str(env.get(RETAIN_ENV, "")).strip() == "1":
        return {"release": False, "pyside": version, "reason": f"{RETAIN_ENV}=1: closed windows are retained"}
    parsed = _version_tuple(version)
    if parsed is None:
        return {"release": False, "pyside": version,
                "reason": f"PySide6 version {version!r} is not recognised; closed windows are retained (safe default)"}
    if parsed < FIXED_PYSIDE:
        return {"release": False, "pyside": version,
                "reason": (f"PySide6 {version} has the D63 SignalInstance use-after-free (fixed upstream in 6.8.2, "
                           f"commit e226b5827c); closed windows are retained")}
    return {"release": True, "pyside": version,
            "reason": f"PySide6 {version} includes the D63 fix; closed windows can be freed"}


_APPLIED: dict = {}


def apply_window_release_policy(policy=None, targets=None) -> dict:
    """Install ``WeakWindowAttribute`` on the tab classes when the policy allows releasing closed windows.

    Idempotent.  Called by ``MainWindow.__init__`` before its tabs exist.  ``targets`` (``(owner_class, name)``
    pairs) is for tests; by default the three ``WINDOW_ATTRIBUTES``.  Returns the policy plus the attributes
    that are weak now.
    """
    import importlib

    policy = policy or window_release_policy()
    weak = []
    if policy["release"]:
        if targets is None:
            targets = [(getattr(importlib.import_module(module), cls), name) for module, cls, name in WINDOW_ATTRIBUTES]
        for owner, name in targets:
            if not isinstance(owner.__dict__.get(name), WeakWindowAttribute):
                descriptor = WeakWindowAttribute()
                descriptor.__set_name__(owner, name)
                setattr(owner, name, descriptor)
            weak.append(f"{owner.__name__}.{name}")
            _APPLIED[f"{owner.__module__}.{owner.__name__}.{name}"] = policy["pyside"]
    return {**policy, "weak_attributes": weak}


class SignalRoutes:
    """Connections from a process-wide sender (``SelectionManager``) to slots owned by one window.

    The sender outlives every window, so a closed window's tabs kept receiving every later selection and
    loading data for a hidden window (M263: stale updates, wasted work while the window waited to be freed).
    Each owner records the routes it connects; the window disconnects them on its accepted close.  Connecting
    through the same object twice is refused, so reopening a window cannot double a route.

    The registry lives in the owner's ``__dict__``, so it must not refer back to the owner: a bound-method slot
    is recorded as a ``weakref.WeakMethod``.  A strong bound method there formed the cycle owner -> registry ->
    method -> owner, which turned every tab into cyclic garbage that only a gc pass frees - and freeing Qt
    wrappers inside an arbitrary gc pass is the D63 crash path (M265 found this: test_m132 SIGSEGV 2/2 with the
    strong registry, 0/2 on ac7657b).  Plain functions are recorded as given.
    """

    def __init__(self):
        self._routes = []

    @staticmethod
    def _record(slot):
        if getattr(slot, "__self__", None) is not None and getattr(slot, "__func__", None) is not None:
            return weakref.WeakMethod(slot)
        return _Strong(slot)

    def connect(self, signal, slot):
        for recorded_signal, recorded_slot in self._routes:
            if recorded_signal == signal and recorded_slot() == slot:
                raise ValueError("route already connected")
        signal.connect(slot)
        self._routes.append((signal, self._record(slot)))

    def __len__(self):
        return len(self._routes)

    def disconnect_all(self) -> int:
        """Disconnect every recorded route once; returns how many were disconnected."""
        routes, self._routes = self._routes, []
        done = 0
        for signal, recorded in routes:
            slot = recorded()
            if slot is None:                # the owner is gone; Qt dropped its receiver connections with it
                continue
            try:
                if signal.disconnect(slot) is not False:
                    done += 1
            except RuntimeError as exc:     # the sender's C++ object is gone: nothing left to disconnect
                logging.getLogger(__name__).debug("route sender already destroyed: %s", exc)
        return done


def routes_of(owner) -> SignalRoutes:
    """The ``SignalRoutes`` of ``owner`` (created on first use)."""
    routes = owner.__dict__.get("_lifetime_routes")
    if routes is None:
        routes = owner.__dict__["_lifetime_routes"] = SignalRoutes()
    return routes


def disconnect_window_routes(window) -> int:
    """Disconnect the ``SignalRoutes`` of ``window`` and of every descendant that has them (accepted close)."""
    from PySide6.QtCore import QObject

    owners = [window, *window.findChildren(QObject)]
    total = 0
    for owner in owners:
        routes = owner.__dict__.get("_lifetime_routes") if hasattr(owner, "__dict__") else None
        if isinstance(routes, SignalRoutes):
            total += routes.disconnect_all()
    return total
