"""M265 (D74): lifetime helpers for references between a window, its children and process-wide services.

* ``SignalRoutes`` / ``routes_of`` / ``disconnect_window_routes``: connections from the process-wide
  ``SelectionManager`` to slots owned by one window, disconnected on the window's accepted close, so a closed
  window gets no stale selection updates and a reopened one gets exactly one set of routes.
* ``weak_or_strong``: a weak reference where possible (``StatusBarManager`` no longer keeps a closed window).
* ``WeakWindowAttribute``: NOT used by the product.  Making the tabs' window attributes weak lets a closed
  window be freed - and freeing closed windows reproduces the D63 SIGSEGV deterministically once three windows
  have been built (auto gc 3/3, 5/5 in scratch runs).  M265 therefore keeps closed windows retained, by
  design, and the descriptor survives only for the opt-in reproducer ``tools/quality/d63_window_release_probe.py``.
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
    """D63 diagnostic only (see the module docstring).  Data descriptor: ``self.parent_window = window`` stores a weak reference; reading it returns the window
    or ``None`` once the window has been freed."""

    def __set_name__(self, owner, name):
        self._slot = f"_weak_ref_{name}"

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        ref = obj.__dict__.get(self._slot)
        return ref() if ref is not None else None

    def __set__(self, obj, value):
        obj.__dict__[self._slot] = weak_or_strong(value)


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
