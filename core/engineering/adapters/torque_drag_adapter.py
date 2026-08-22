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
        if not TorqueDragAdapter.available():
            return None
        import torque_drag
        # Keep third-party API isolated; callers receive None until a supported
        # package version is detected rather than a guessed engineering result.
        calculator = getattr(torque_drag, "calculate", None)
        return calculator(*args, **kwargs) if callable(calculator) else None
