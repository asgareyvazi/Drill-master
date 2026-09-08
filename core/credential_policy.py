"""Shared desktop/CLI credential policy. No Qt, file-based mode or .env discovery."""
from __future__ import annotations

import os

_DEVELOPMENT_FIXTURE_PASSWORDS = {"admin": "admin123", "engineer": "user123", "viewer": "viewer123"}
_BOOTSTRAP_PASSWORD_ENV = {
    "admin": "DRILLMASTER_ADMIN_PASSWORD",
    "engineer": "DRILLMASTER_USER_PASSWORD",
    "viewer": "DRILLMASTER_VIEWER_PASSWORD",
}


class CredentialLifecycleError(RuntimeError):
    """Only fixed, password-free messages may cross the startup UI/log boundary."""
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def runtime_environment() -> str:
    aliases = {"production": "production", "prod": "production",
               "development": "development", "dev": "development", "test": "test", "testing": "test"}
    modes = []
    for key in ("DRILLMASTER_ENV", "DRILLMASTER_ENVIRONMENT"):
        value = os.environ.get(key)
        if value is not None:
            mode = aliases.get(value.strip().lower())
            if mode is None:
                raise CredentialLifecycleError("ENVIRONMENT_INVALID",
                    "DRILLMASTER_ENV / DRILLMASTER_ENVIRONMENT must explicitly select production, development or test.")
            modes.append(mode)
    if len(set(modes)) > 1:
        raise CredentialLifecycleError("ENVIRONMENT_INVALID",
            "DRILLMASTER_ENV and DRILLMASTER_ENVIRONMENT conflict; configure one consistent environment.")
    return modes[0] if modes else "production"


def is_production_environment() -> bool:
    return runtime_environment() == "production"


def is_development_password(value: str) -> bool:
    return isinstance(value, str) and value.strip().casefold() in _DEVELOPMENT_FIXTURE_PASSWORDS.values()


def validate_production_password(value: str, setting: str = "Administrator password") -> None:
    if not isinstance(value, str) or not value.strip():
        raise CredentialLifecycleError("BOOTSTRAP_REQUIRED",
            "Production database requires initial administrator credentials. Configure DRILLMASTER_ADMIN_PASSWORD "
            "or complete secure first-run setup. Optional account settings must be unset, not empty.")
    if is_development_password(value):
        raise CredentialLifecycleError("BOOTSTRAP_INVALID",
            "Production bootstrap credentials must not use development fixture values.")
    if len(value) < 12 or len(value.encode("utf-8")) > 72:
        # Never interpolate the supplied password (or arbitrary setting text).
        raise CredentialLifecycleError("BOOTSTRAP_INVALID",
            "Production passwords require at least 12 characters and at most 72 UTF-8 bytes (bcrypt limit).")


def resolve_bootstrap_passwords(overrides: dict | None = None) -> dict[str, str]:
    configured = ({role: os.environ[name] for role, name in _BOOTSTRAP_PASSWORD_ENV.items() if name in os.environ}
                  if overrides is None else dict(overrides))
    if is_production_environment():
        validate_production_password(configured.get("admin"))
        for role, value in configured.items():
            if role not in _BOOTSTRAP_PASSWORD_ENV:
                raise CredentialLifecycleError("BOOTSTRAP_INVALID", "Unknown bootstrap account role.")
            validate_production_password(value)
        return configured  # admin required; other accounts only when explicitly configured
    return {role: configured.get(role) or password for role, password in _DEVELOPMENT_FIXTURE_PASSWORDS.items()}


def bootstrap_password_for_role(role: str) -> str | None:
    env_name = _BOOTSTRAP_PASSWORD_ENV.get(role)
    configured = os.getenv(env_name) if env_name else None
    if configured:
        return configured
    if is_production_environment():
        return None
    return _DEVELOPMENT_FIXTURE_PASSWORDS.get(role)
