#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
命令行管理工具 (examctl.py) - 版本 2.0 (异步兼容)
(Command Line Management Tool (examctl.py) - Version 2.0 (Async Compatible))

此脚本提供了一系列命令行接口 (CLI)，用于管理在线考试系统的某些方面，
例如用户管理（添加用户、更新用户信息、修改密码等）。
它通过异步初始化应用的CRUD层，并直接与其交互，主要供系统管理员使用。
(This script provides a series of command-line interfaces (CLIs) for managing
certain aspects of the online examination system, such as user management
(adding users, updating user information, changing passwords, etc.).
It interacts directly with the application's CRUD layer after asynchronous
initialization, and is primarily intended for system administrators.)

使用示例 (Usage Examples):
  python examctl.py add-user --uid newuser --password "SecurePassword123" --nickname "New User"
  python examctl.py update-user --uid existinguser --email "new_email@example.com" --tags "user,limited"
  python examctl.py change-password --uid someuser --new-password "AnotherSecurePassword"
"""
import argparse
import asyncio
import sys
from pathlib import Path

# 调整Python搜索路径，以允许从 'app' 包导入模块
# (Adjust Python search path to allow importing modules from the 'app' package)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import (
    settings,
)  # 导入应用全局配置 (Import global application settings)
from app.core.security import (
    get_password_hash,
)  # 导入密码哈希函数 (Import password hashing function)
from app.crud import (  # 从CRUD包导入所需实例和初始化函数
    # (Import required instances and initialization function from CRUD package)
    initialize_crud_instances,  # CRUD及存储库异步初始化函数 (Async init function for CRUD & repo)
    user_crud_instance,  # 用户CRUD操作实例 (User CRUD operations instance)
    # paper_crud_instance, # (可选) 试卷CRUD实例 (Optional: Paper CRUD instance)
    # qb_crud_instance,    # (可选) 题库CRUD实例 (Optional: Question Bank CRUD instance)
    # settings_crud_instance, # (可选) 配置CRUD实例 (Optional: Settings CRUD instance)
)
from app.models.user_models import (
    AdminUserUpdate,
    UserCreate,
    UserTag,
)  # 用户相关Pydantic模型 (User-related Pydantic models)


async def add_user_command(args: argparse.Namespace):
    """
    处理 'add-user' 命令：添加一个新用户到系统。
    (Handles the 'add-user' command: Adds a new user to the system.)

    参数 (Args):
        args (argparse.Namespace): 通过命令行参数解析得到的对象，包含用户ID、密码等信息。
                                     (Object obtained from command-line argument parsing,
                                      containing user ID, password, etc.)
    """
    if not user_crud_instance:  # 确保 user_crud_instance 已被初始化
        print(
            "错误：用户数据操作模块 (UserCRUD) 未初始化。请确保异步初始化已成功调用。"
        )
        print(
            "Error: User data operations module (UserCRUD) is not initialized. Ensure async initialization was called."
        )
        return

    print(f"正在尝试添加用户 (Attempting to add user): {args.uid}...")
    # 从命令行参数构造用户创建数据模型
    user_create_payload = UserCreate(
        uid=args.uid,
        password=args.password,
        nickname=args.nickname,
        email=args.email,
        qq=args.qq,
    )
    try:
        # 调用 UserCRUD 创建用户
        created_user = await user_crud_instance.create_user(user_create_payload)
        if created_user:
            print(
                f"成功添加用户 (Successfully added user) '{created_user.uid}' "
                f"标签 (Tags): {[tag.value for tag in created_user.tags]}."
            )
        else:
            # 此路径理论上在 create_user 抛出异常前不应到达
            # (This path should ideally not be reached if create_user raises an exception on failure)
            print(
                f"添加用户 (Failed to add user) '{args.uid}' 失败。用户可能已存在或提供的数据无效。"
            )
            print("User might already exist or provided data is invalid.")
    except Exception as e:  # 捕获创建过程中可能发生的任何异常
        print(f"添加用户 (Error adding user) '{args.uid}' 时发生错误: {e}")


async def update_user_command(args: argparse.Namespace):
    """
    处理 'update-user' 命令：更新现有用户的属性。
    (Handles the 'update-user' command: Updates attributes of an existing user.)

    参数 (Args):
        args (argparse.Namespace): 命令行参数对象，包含用户ID及待更新的属性。
                                     (Command-line argument object, containing user ID
                                      and attributes to be updated.)
    """
    if not user_crud_instance:
        print("错误：用户数据操作模块 (UserCRUD) 未初始化。")
        print("Error: User data operations module (UserCRUD) is not initialized.")
        return

    print(f"正在尝试更新用户 (Attempting to update user): {args.uid}...")
    update_data = {}  # 存储需要更新的字段
    if args.nickname is not None:
        update_data["nickname"] = args.nickname
    if args.email is not None:
        update_data["email"] = args.email
    if args.qq is not None:
        update_data["qq"] = args.qq
    if args.tags is not None:  # 如果命令行提供了标签
        try:
            # 将逗号分隔的标签字符串转换为 UserTag 枚举列表
            update_data["tags"] = [UserTag(tag.strip()) for tag in args.tags.split(",")]
        except ValueError as e:  # 如果提供的标签无效
            print(
                f"错误: --tags 中提供了无效标签 (Invalid tag provided in --tags): {e}。"
                f"允许的标签 (Allowed tags): {[tag.value for tag in UserTag]}"
            )
            return

    if not update_data:  # 如果没有提供任何更新参数
        print("未提供更新参数。正在退出。 (No update parameters provided. Exiting.)")
        return

    # 使用 AdminUserUpdate 模型构造更新数据
    admin_update_payload = AdminUserUpdate(**update_data)
    try:
        # 调用 UserCRUD 更新用户信息
        updated_user = await user_crud_instance.admin_update_user(
            args.uid, admin_update_payload
        )
        if updated_user:
            print(f"成功更新用户 (Successfully updated user) '{updated_user.uid}'.")
            print(f"  昵称 (Nickname): {updated_user.nickname}")
            print(f"  邮箱 (Email): {updated_user.email}")
            print(f"  QQ: {updated_user.qq}")
            print(f"  标签 (Tags): {[tag.value for tag in updated_user.tags]}")
        else:
            print(
                f"更新用户 (Failed to update user) '{args.uid}' 失败。用户可能不存在或提供的数据无效。"
            )
            print("User might not exist or provided data is invalid.")
    except Exception as e:
        print(f"更新用户 (Error updating user) '{args.uid}' 时发生错误: {e}")


async def change_password_command(args: argparse.Namespace):
    """
    处理 'change-password' 命令：修改指定用户的密码。
    (Handles the 'change-password' command: Changes the password of a specified user.)

    参数 (Args):
        args (argparse.Namespace): 命令行参数对象，包含用户ID和新密码。
                                     (Command-line argument object, containing user ID and new password.)
    """
    if not user_crud_instance:
        print("错误：用户数据操作模块 (UserCRUD) 未初始化。")
        print("Error: User data operations module (UserCRUD) is not initialized.")
        return

    print(
        f"正在尝试为用户 (Attempting to change password for user) '{args.uid}' 修改密码..."
    )

    # 检查新密码长度是否符合配置要求
    pw_config = settings.user_config
    if not (
        pw_config.password_min_len
        <= len(args.new_password)
        <= pw_config.password_max_len
    ):
        print(
            f"错误：新密码长度必须在 {pw_config.password_min_len} 和 {pw_config.password_max_len} 字符之间。"
            f"(Error: New password length must be between {pw_config.password_min_len} and {pw_config.password_max_len} characters.)"
        )
        return

    try:
        # 获取用户以确认存在性
        user = await user_crud_instance.get_user_by_uid(args.uid)
        if not user:
            print(f"错误：用户 (Error: User) '{args.uid}' 未找到。")
            return

        # 对新密码进行哈希处理
        new_hashed_password = get_password_hash(args.new_password)
        # 调用 UserCRUD 更新用户密码
        success = await user_crud_instance.update_user_password(
            args.uid, new_hashed_password
        )

        if success:
            print(
                f"用户 (User) '{args.uid}' 的密码已成功修改。 (Password changed successfully.)"
            )
        else:
            # 此情况理论上不应发生（如果用户已找到），除非存储库的更新操作失败
            print(
                f"为用户 (Failed to change password for user) '{args.uid}' 修改密码失败。"
            )
    except Exception as e:
        print(
            f"为用户 (Error changing password for user) '{args.uid}' 修改密码时发生错误: {e}"
        )


async def main_async():
    """
    CLI工具的异步主入口函数。
    (Asynchronous main entry point for the CLI tool.)

    首先异步初始化CRUD实例和数据存储库，然后解析命令行参数，
    并根据子命令调用相应的异步处理函数。
    (First, asynchronously initializes CRUD instances and the data repository,
    then parses command-line arguments and calls the corresponding asynchronous
    handler function based on the subcommand.)
    """
    # 初始化 CRUD 实例和存储库
    # (Initialize CRUD instances and repository)
    print("正在初始化应用和数据存储... (Initializing application and data storage...)")
    try:
        await initialize_crud_instances()  # 关键的异步初始化步骤
        print("初始化完成。 (Initialization complete.)")
    except Exception as e:
        print(
            f"初始化过程中发生严重错误 (Critical error during initialization): {e}",
            file=sys.stderr,
        )
        print(
            "请检查您的 .env 文件和数据存储配置 (如 JSON 文件路径、数据库连接字符串等)。",
            file=sys.stderr,
        )
        print(
            "Please check your .env file and data storage configuration (e.g., JSON file paths, database connection strings).",
            file=sys.stderr,
        )
        sys.exit(1)  # 初始化失败则退出

    # 确保 settings 已加载 (通常 initialize_crud_instances 会间接触发)
    # (Ensure settings are loaded (usually triggered indirectly by initialize_crud_instances))
    if not settings.app_name:  # 检查一个已知的配置项是否存在
        print(
            "错误：未能加载应用配置。 (Error: Could not load application settings.)",
            file=sys.stderr,
        )
        sys.exit(1)

    # 创建命令行参数解析器
    # (Create command-line argument parser)
    parser = argparse.ArgumentParser(
        description="在线考试系统命令行管理工具 - 用于用户管理和应用设置等。\n(Online Examination System CLI Management Tool - For user management, application settings, etc.)"
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="可用的命令 (Available commands)"
    )

    # 添加 'add-user' 子命令解析器
    # (Add 'add-user' subcommand parser)
    add_parser = subparsers.add_parser(
        "add-user", help="添加一个新用户到系统。 (Add a new user to the system.)"
    )
    add_parser.add_argument(
        "--uid", required=True, help="用户ID (用户名)。 (User ID (username))"
    )
    add_parser.add_argument(
        "--password", required=True, help="用户密码。 (User password)"
    )
    add_parser.add_argument(
        "--nickname", help="可选的用户昵称。 (Optional: User nickname)"
    )
    add_parser.add_argument(
        "--email",
        help="可选的用户邮箱 (例如: user@example.com)。 (Optional: User email (e.g., user@example.com))",
    )
    add_parser.add_argument(
        "--qq", help="可选的用户QQ号码。 (Optional: User QQ number)"
    )
    add_parser.set_defaults(func=add_user_command)  # 设置此子命令对应的处理函数

    # 添加 'update-user' 子命令解析器
    # (Add 'update-user' subcommand parser)
    update_parser = subparsers.add_parser(
        "update-user",
        help="更新现有用户的属性。 (Update attributes of an existing user.)",
    )
    update_parser.add_argument(
        "--uid",
        required=True,
        help="需要更新的用户的用户ID (用户名)。 (User ID (username) of the user to update.)",
    )
    update_parser.add_argument(
        "--nickname", help="用户的新昵称。 (New nickname for the user.)"
    )
    update_parser.add_argument(
        "--email", help="用户的新邮箱。 (New email for the user.)"
    )
    update_parser.add_argument(
        "--qq", help="用户的新QQ号码。 (New QQ number for the user.)"
    )
    update_parser.add_argument(
        "--tags",
        help=f"逗号分隔的新标签列表 (例如: user,admin)。允许的标签: {[t.value for t in UserTag]}\n"
        f"(Comma-separated list of new tags (e.g., user,admin). Allowed: {[t.value for t in UserTag]})",
    )
    update_parser.set_defaults(func=update_user_command)

    # 添加 'change-password' 子命令解析器
    # (Add 'change-password' subcommand parser)
    pw_parser = subparsers.add_parser(
        "change-password", help="修改用户的密码。 (Change a user's password.)"
    )
    pw_parser.add_argument(
        "--uid",
        required=True,
        help="需要修改密码的用户的用户ID (用户名)。 (User ID (username) whose password to change.)",
    )
    pw_parser.add_argument(
        "--new-password",
        required=True,
        help="用户的新密码。 (The new password for the user.)",
    )
    pw_parser.set_defaults(func=change_password_command)

    # 解析命令行参数
    # (Parse command-line arguments)
    args = parser.parse_args()

    # 根据解析到的子命令，调用相应的异步处理函数
    # (Call the corresponding async handler function based on the parsed subcommand)
    if hasattr(args, "func"):
        await args.func(args)
    else:
        # 如果没有提供有效的子命令，则打印帮助信息
        # (If no valid subcommand is provided, print help information)
        parser.print_help()


# 定义模块对外暴露的接口 (Define the module's public interface)
__all__ = ["main_async"]

if __name__ == "__main__":
    # 这个检查确保脚本是直接运行的 (`python examctl.py ...`)，而不是被导入的。
    # (This check ensures the script is run directly (`python examctl.py ...`), not imported.)
    asyncio.run(main_async())  # 运行异步主函数
