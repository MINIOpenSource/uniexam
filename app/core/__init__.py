"""
核心模块，包含应用配置、安全功能、接口定义和速率限制等。
"""

from . import config, interfaces, rate_limiter, security

__all__ = [
    "config",
    "settings",  # 来自 config 模块
    "interfaces",
    "IDataStorageRepository",  # 来自 interfaces 模块
    "rate_limiter",
    "RateLimiter",  # 来自 rate_limiter 模块
    "security",
    "create_access_token",  # 来自 security 模块
    "get_current_active_user",  # 来自 security 模块 (假设存在或后续会添加)
    "get_password_hash",  # 来自 security 模块
    "verify_password",  # 来自 security 模块
    "UserTag",  # 来自 security 模块 (实际定义在 models.user_models, security 模块中可能重导出或使用)
    "pwd_context",  # 来自 security 模块
]

# 重新导出特定的重要名称，以便更方便地从 app.core 直接访问
# (Re-export specific important names for easier access directly from app.core)
settings = config.settings
IDataStorageRepository = interfaces.IDataStorageRepository
RateLimiter = (
    rate_limiter.RateLimiter
)  # 假设 RateLimiter 类在 rate_limiter 模块中定义并导出
create_access_token = security.create_access_token
get_password_hash = security.get_password_hash
verify_password = security.verify_password

# UserTag 通常在 models.user_models 中定义，并可能在 security 模块中被导入和使用/重导出。
# 此处假设它最终可以从 security 模块访问到。
if hasattr(security, "UserTag"):
    UserTag = security.UserTag  # type: ignore
elif "UserTag" in __all__:  # 如果 security 中没有，但 __all__ 中错误地包含了
    __all__.remove("UserTag")


pwd_context = security.pwd_context

# 如果 get_current_active_user 在 security.py 中定义，则导出它
# (If get_current_active_user is defined in security.py, then export it)
# 这通常是 FastAPI 路由的一个依赖项。
# (This is often a dependency for FastAPI routes.)
if hasattr(
    security, "get_current_active_user_uid"
):  # 应该检查 get_current_active_user_uid
    # 在 app/main.py 中，实际使用的依赖项是 get_current_active_user_uid
    # get_current_active_user 这个名称似乎是一个遗留的或计划中的名称
    # 为了与实际使用保持一致，这里可以不导出 get_current_active_user，
    # 或者如果确实计划添加，则保留下面的逻辑。
    # 当前，main.py 使用 get_current_active_user_uid。
    # 除非 security.py 中真的定义了 get_current_active_user，否则下面的代码块意义不大。
    # 为保持 __init__ 文件简洁和准确，暂时注释掉对 get_current_active_user 的处理，
    # 因为它在 security.py 中当前未以该确切名称定义为主要导出项。
    # get_current_active_user = security.get_current_active_user
    pass

if "get_current_active_user" in __all__ and not hasattr(
    security, "get_current_active_user"
):
    # 如果在 __all__ 中声明了但 security 模块中没有，则移除以避免运行时导入错误
    # (If declared in __all__ but not in security module, remove to avoid runtime import error)
    __all__.remove("get_current_active_user")

    # 定义一个占位符函数，如果被意外调用则抛出错误
    async def get_current_active_user():  # type: ignore
        """
        依赖注入的占位符。
        实际的实现应位于 security.py 模块中。
        """
        raise NotImplementedError(
            "get_current_active_user 函数未在 security.py 中实现。"
        )


# 确保 __all__ 列表中的所有名称都确实在当前模块的全局作用域中可用
# (Ensure all names in __all__ are actually available in the current module's global scope)
_available_names = [name for name in __all__ if name in globals() or name in locals()]
__all__ = _available_names
