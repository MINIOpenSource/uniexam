"""
核心模块，包含应用配置、安全功能、接口定义和速率限制等。
"""

from . import config, interfaces, rate_limiter, security

__all__ = [
    "config",
    "settings",  # from config
    "interfaces",
    "IDataStorageRepository",  # from interfaces
    "rate_limiter",
    "RateLimiter",  # from rate_limiter
    "security",
    "create_access_token",  # from security
    "get_current_active_user",  # from security (assuming it's there or will be)
    "get_password_hash",  # from security
    "verify_password",  # from security
    "UserTag",  # from security
    "pwd_context",  # from security
]

# Re-export specific important names for easier access
settings = config.settings
IDataStorageRepository = interfaces.IDataStorageRepository
RateLimiter = rate_limiter.RateLimiter
create_access_token = security.create_access_token
get_password_hash = security.get_password_hash
verify_password = security.verify_password
UserTag = security.UserTag
pwd_context = security.pwd_context

# Placeholder for get_current_active_user if it's defined in security.py
# This is often a dependency for FastAPI routes.
if hasattr(security, "get_current_active_user"):
    get_current_active_user = security.get_current_active_user
else:
    # If it's not defined, remove it from __all__ to avoid runtime errors on import *
    if "get_current_active_user" in __all__:
        __all__.remove("get_current_active_user")

    async def get_current_active_user():  # type: ignore
        """
        Placeholder for dependency injection.
        Actual implementation should be in security.py.
        """
        raise NotImplementedError(
            "get_current_active_user is not implemented in security.py"
        )


# Ensure __all__ only contains names that are actually available
_available_names = [name for name in __all__ if name in globals() or name in locals()]
__all__ = _available_names
