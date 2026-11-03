"""Optional torque_drag integration with an explicit, version-neutral boundary."""
class TorqueDragAdapter:
    package = "torque_drag"

    @staticmethod
    def available():
        try:
            import torque_drag  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def calculate(*args, **kwargs):
        try:
            import torque_drag
        except ImportError:  # silent-ok: optional LGPL package, owner-gated and never installed; None = no result
            return None
        # Keep third-party API isolated; callers receive None until a supported
        # package version is detected rather than a guessed engineering result.
        calculator = getattr(torque_drag, "calculate", None)
        return calculator(*args, **kwargs) if callable(calculator) else None
