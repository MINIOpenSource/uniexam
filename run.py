# -*- coding: utf-8 -*-
"""
应用启动脚本 (Application Startup Script)。

此脚本使用 Uvicorn ASGI 服务器来运行在 `app.main` 中定义的 FastAPI 应用。
它从 `app.core.config` 模块加载全局配置（如监听主机、端口、日志级别等），
并将其传递给 Uvicorn 服务器。

主要用途：
- 开发环境：通过 `python run.py` 命令方便地启动应用进行本地开发和测试。
- 生产环境参考：虽然生产环境通常使用更健壮的进程管理器（如 Gunicorn + Uvicorn workers 或 Supervisor），
  但此脚本展示了 Uvicorn 如何配置和运行应用。

(This script uses the Uvicorn ASGI server to run the FastAPI application defined in `app.main`.
It loads global configurations (such as listening host, port, log level, etc.) from the
`app.core.config` module and passes them to the Uvicorn server.

Main Uses:
- Development Environment: Conveniently start the application for local development and testing
  using the `python run.py` command.
- Production Environment Reference: Although production environments typically use more robust
  process managers (like Gunicorn + Uvicorn workers or Supervisor), this script demonstrates
  how Uvicorn can be configured and run.)
"""

# run.py (位于项目根目录 / Located in the project root directory)
import uvicorn

from app.core.config import (
    settings,
)  # 导入全局应用配置 (Import global application settings)
from app.main import (
    app,
)  # 从 app.main 模块导入 FastAPI 应用实例 (Import FastAPI app instance from app.main)

if __name__ == "__main__":
    # 当此脚本作为主程序直接运行时执行以下代码
    # (The following code is executed when this script is run directly as the main program)

    # 打印一些启动信息到控制台 (Print some startup information to the console)
    print(f"准备启动 FastAPI 应用 '{settings.app_name}' (版本: {app.version})...")
    print("  监听地址 (Host): 0.0.0.0 (所有网络接口)")
    print(f"  监听端口 (Port): {settings.listening_port}")
    print(f"  Uvicorn 日志级别 (Log Level): {settings.log_level.lower()}")
    print(
        f"  Uvicorn 访问日志 (Access Log): {'启用' if settings.enable_uvicorn_access_log else '禁用'}"
    )  # 根据配置显示
    print(
        f"  代码自动重载 (Reload): {'启用 (开发模式)' if settings.debug_mode else '禁用 (生产模式推荐)'}"
    )  # 根据配置显示

    uvicorn.run(
        app,  # FastAPI 应用实例 (FastAPI application instance)
        # 也可以使用字符串 "app.main:app"，Uvicorn 会自动导入
        # (Alternatively, "app.main:app" string can be used, Uvicorn will import it)
        host="0.0.0.0",  # 监听所有可用的网络接口 (Listen on all available network interfaces)
        port=settings.listening_port,  # 从配置对象获取监听端口 (Get listening port from settings)
        log_level=settings.log_level.lower(),  # 从配置获取日志级别 (Uvicorn需要小写)
        # (Get log level from settings (Uvicorn requires lowercase))
        access_log=settings.enable_uvicorn_access_log,  # 从配置控制是否启用Uvicorn的访问日志
        # (Control Uvicorn access log via settings)
        reload=settings.debug_mode,  # 开发模式下启用自动重载，生产环境应禁用
        # (Enable auto-reload in development mode, disable in production)
        # reload_dirs=["app"] if settings.debug_mode else None, # 指定重载监控目录 (可选)
        # (Specify directories to monitor for reload (optional))
    )

# 通常顶层可执行脚本不导出任何内容，或者导出一个主函数 (如 main)
# (Typically, top-level executable scripts do not export anything, or export a main function)
__all__ = []
