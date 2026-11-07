"""M136: Qt side of the session lock (``core.session_lock``).

* ``LockOverlay`` — an opaque child covering the whole host window (menus included), so nothing of the work
  stays readable while locked; it follows the host's size.
* ``UnlockDialog`` — application-modal (shown with ``show()``: ``QDialog.open()`` would make it only
  window-modal), so no other window or shortcut takes input; password only (the user is fixed); Escape and the
  window's close button do nothing; "Exit DrillMaster" closes the host through its normal close path.
* Other visible non-modal top-level windows (floating panels, tool dialogs) are hidden while locked and shown
  again after the unlock. LIMIT: an open modal dialog stays visible (input-blocked) behind the unlock dialog —
  hiding it would end it and lose what was typed into it.
* ``IdleWatcher`` — an application event filter that restarts a single-shot timer on keyboard / mouse input.
* ``SessionLockController`` — owns these; the host is its Qt parent (no Python reference back to the host).
"""
from __future__ import annotations

from typing import Mapping, Optional

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
                               QWidget)

from core.session_lock import SessionLock, idle_minutes

HIDDEN_PROPERTY = "drillmaster_hidden_by_session_lock"   # marks windows to show again; no reference is kept
INPUT_EVENTS = frozenset({QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.Wheel,
                          QEvent.TouchBegin})


class LockOverlay(QWidget):
    def __init__(self, host: QWidget, username: str):
        super().__init__(host)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:#263238;")
        layout = QVBoxLayout(self)
        label = QLabel(f"🔒 Session locked — {username}")
        label.setStyleSheet("color:white; font-size:16pt;")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        host.installEventFilter(self)
        self.hide()

    def cover(self) -> None:
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self.setGeometry(watched.rect())
        return False


class UnlockDialog(QDialog):
    unlock_requested = Signal(str)
    exit_requested = Signal()

    def __init__(self, parent: QWidget, username: str):
        super().__init__(parent)
        self.setWindowTitle("DrillMaster — session locked")
        self.setWindowModality(Qt.ApplicationModal)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"The session of <b>{username}</b> is locked. Enter this user's password."))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.returnPressed.connect(self._submit)
        layout.addWidget(self.password)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QHBoxLayout()
        self.unlock_btn = QPushButton("Unlock")
        self.unlock_btn.clicked.connect(self._submit)
        self.exit_btn = QPushButton("Exit DrillMaster")
        self.exit_btn.clicked.connect(self.exit_requested)
        buttons.addWidget(self.unlock_btn)
        buttons.addStretch()
        buttons.addWidget(self.exit_btn)
        layout.addLayout(buttons)

    def _submit(self) -> None:
        password = self.password.text()
        self.password.clear()                   # the typed password does not stay in the widget
        self.unlock_requested.emit(password)

    def reject(self) -> None:                   # Escape: the lock stays
        self.message.setText("The session stays locked until the password is entered.")

    def closeEvent(self, event) -> None:        # the window's close button: the lock stays
        event.ignore()
        self.reject()


class IdleWatcher(QObject):
    idle = Signal()

    def __init__(self, minutes: int, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(minutes * 60_000)
        self.timer.timeout.connect(self.idle)
        self.paused = False

    def start(self) -> None:
        QApplication.instance().installEventFilter(self)
        self.timer.start()

    def stop(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.timer.stop()

    def eventFilter(self, watched, event) -> bool:
        if not self.paused and event.type() in INPUT_EVENTS:
            self.timer.start()                  # restart: input resets the idle time
        return False


class SessionLockController(QObject):
    locked_changed = Signal(bool)

    def __init__(self, host: QWidget, db, user: Mapping, environ: Optional[Mapping[str, str]] = None):
        super().__init__(host)
        self.state = SessionLock(db, user.get("id"), str(user.get("username") or ""))
        self.idle_limit, self.idle_note = idle_minutes(environ)
        self.overlay = LockOverlay(host, self.state.username)
        self.dialog: Optional[UnlockDialog] = None
        self.watcher: Optional[IdleWatcher] = None
        if self.idle_limit:
            self.watcher = IdleWatcher(self.idle_limit, self)
            self.watcher.idle.connect(self._idle)
            self.watcher.start()

    @property
    def locked(self) -> bool:
        return self.state.locked

    def _idle(self) -> None:
        self.lock("idle")

    def lock(self, reason: str = "manual") -> bool:
        if not self.state.lock(reason):
            return False
        if self.watcher is not None:
            self.watcher.paused = True
        self.overlay.cover()
        self.dialog = UnlockDialog(self.parent(), self.state.username)
        self.dialog.unlock_requested.connect(self.try_unlock)
        self.dialog.exit_requested.connect(self._exit)
        self._hide_other_windows()
        self.dialog.show()
        self.locked_changed.emit(True)
        return True

    def try_unlock(self, password: str) -> bool:
        if not self.state.unlock(password):
            if self.dialog is not None:
                self.dialog.message.setText(f"Not unlocked ({self.state.failures} failed attempt(s)): wrong password, "
                                            "or the account is temporarily locked after repeated failures.")
            return False
        self.overlay.hide()
        self._restore_other_windows()
        if self.dialog is not None:
            self.dialog.done(QDialog.Accepted)
            self.dialog.deleteLater()
            self.dialog = None
        if self.watcher is not None:
            self.watcher.paused = False
            self.watcher.timer.start()
        self.locked_changed.emit(False)
        return True

    def _hide_other_windows(self) -> None:
        host = self.parent()
        for window in QApplication.topLevelWidgets():
            if (window is host or window is self.dialog or not window.isVisible()
                    or window.windowModality() != Qt.NonModal):
                continue
            window.setProperty(HIDDEN_PROPERTY, True)
            window.hide()

    def _restore_other_windows(self) -> None:
        for window in QApplication.topLevelWidgets():      # a window deleted meanwhile is simply not listed
            if window.property(HIDDEN_PROPERTY):
                window.setProperty(HIDDEN_PROPERTY, None)
                window.show()

    def _exit(self) -> None:
        """Close the host through its normal close path; if that is refused, the lock and its dialog stay."""
        if self.dialog is not None:
            self.dialog.hide()
        if not self.parent().close() and self.state.locked and self.dialog is not None:
            self.dialog.show()

    def shutdown(self) -> None:
        if self.watcher is not None:
            self.watcher.stop()
