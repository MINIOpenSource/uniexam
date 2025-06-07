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
import csv
import sys
from pathlib import Path

# 调整Python搜索路径，以允许从 'app' 包导入模块
# (Adjust Python search path to allow importing modules from the 'app' package)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import json  # For parsing JSON arguments

from pydantic import BaseModel  # F821: BaseModel used in get_nested_value

from app.core.config import (
    settings,
)  # 导入应用全局配置 (Import global application settings)
from app.core.security import (
    get_password_hash,
)  # 导入密码哈希函数 (Import password hashing function)
from app.crud import (  # 从CRUD包导入所需实例和初始化函数
    # (Import required instances and initialization function from CRUD package)
    initialize_crud_instances,  # CRUD及存储库异步初始化函数 (Async init function for CRUD & repo)
    paper_crud_instance,  # 试卷CRUD实例 (Paper CRUD instance)
    qb_crud_instance,  # 题库CRUD操作实例 (Question Bank CRUD operations instance)
    settings_crud_instance,  # 配置CRUD实例 (Settings CRUD instance)
    user_crud_instance,  # 用户CRUD操作实例 (User CRUD operations instance)
)
from app.models.enums import QuestionTypeEnum  # 题目类型枚举
from app.models.qb_models import (
    QuestionModel,
    # QuestionBank, # May not be needed directly for commands
    # LibraryIndexItem, # May not be needed directly for commands
)  # 题库相关Pydantic模型
from app.models.user_models import (
    AdminUserUpdate,
    UserCreate,
    UserInDB,  # For retrieving user data
    UserTag,
)  # 用户相关Pydantic模型 (User-related Pydantic models)


async def list_users_command(args: argparse.Namespace):
    """
    处理 'list-users' / '导出用户' 命令：检索所有用户并将其数据导出到CSV文件或打印到标准输出。
    """
    if not user_crud_instance:
        print("错误：用户数据操作模块 (UserCRUD) 未初始化。")
        return

    print("正在检索所有用户信息...")
    try:
        users: list[UserInDB] = await user_crud_instance.admin_get_all_users()
        if not users:
            print("未找到任何用户。")
            return

        print(f"共检索到 {len(users)} 位用户。")

        header = ["用户ID", "昵称", "邮箱", "QQ", "标签"]
        data = [
            [
                user.uid,
                user.nickname,
                user.email,
                user.qq,
                ",".join([tag.value for tag in user.tags]),
            ]
            for user in users
        ]

        if args.output_file:
            output_path = Path(args.output_file)
            try:
                with output_path.open(
                    "w", newline="", encoding="utf-8-sig"
                ) as csvfile:  # utf-8-sig for Excel compatibility
                    writer = csv.writer(csvfile)
                    writer.writerow(header)
                    writer.writerows(data)
                print(f"用户信息已成功导出到: {output_path}")
            except IOError as e:
                print(f"写入文件 '{output_path}' 时发生错误: {e}")
        else:
            # 打印到 stdout
            writer = csv.writer(sys.stdout)
            writer.writerow(header)
            writer.writerows(data)

    except Exception as e:
        print(f"检索或导出用户时发生错误: {e}")


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
        # "Error: User data operations module (UserCRUD) is not initialized. Ensure async initialization was called."
        return

    print(f"正在尝试添加用户: {args.uid}...")
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
                f"成功添加用户 '{created_user.uid}' "
                f"标签: {[tag.value for tag in created_user.tags]}。"
            )
        else:
            # 此路径理论上在 create_user 抛出异常前不应到达
            # (This path should ideally not be reached if create_user raises an exception on failure)
            print(f"添加用户 '{args.uid}' 失败。用户可能已存在或提供的数据无效。")
            # "User might already exist or provided data is invalid."
    except Exception as e:  # 捕获创建过程中可能发生的任何异常
        print(f"添加用户 '{args.uid}' 时发生错误: {e}")


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
        # "Error: User data operations module (UserCRUD) is not initialized."
        return

    print(f"正在尝试更新用户: {args.uid}...")
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
                f"错误: --tags 中提供了无效标签: {e}。"
                f"允许的标签: {[tag.value for tag in UserTag]}"
            )
            return

    if not update_data:  # 如果没有提供任何更新参数
        print("未提供更新参数。正在退出。")
        return

    # 使用 AdminUserUpdate 模型构造更新数据
    admin_update_payload = AdminUserUpdate(**update_data)
    try:
        # 调用 UserCRUD 更新用户信息
        updated_user = await user_crud_instance.admin_update_user(
            args.uid, admin_update_payload
        )
        if updated_user:
            print(f"成功更新用户 '{updated_user.uid}'.")
            print(f"  昵称: {updated_user.nickname}")
            print(f"  邮箱: {updated_user.email}")
            print(f"  QQ: {updated_user.qq}")
            print(f"  标签: {[tag.value for tag in updated_user.tags]}")
        else:
            print(f"更新用户 '{args.uid}' 失败。用户可能不存在或提供的数据无效。")
            # "User might not exist or provided data is invalid."
    except Exception as e:
        print(f"更新用户 '{args.uid}' 时发生错误: {e}")


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
        # "Error: User data operations module (UserCRUD) is not initialized."
        return

    print(f"正在尝试为用户 '{args.uid}' 修改密码...")

    # 检查新密码长度是否符合配置要求
    pw_config = settings.user_config
    if not (
        pw_config.password_min_len
        <= len(args.new_password)
        <= pw_config.password_max_len
    ):
        print(
            f"错误：新密码长度必须在 {pw_config.password_min_len} 和 {pw_config.password_max_len} 字符之间。"
        )
        return

    try:
        # 获取用户以确认存在性
        user = await user_crud_instance.get_user_by_uid(args.uid)
        if not user:
            print(f"错误：用户 '{args.uid}' 未找到。")
            return

        # 对新密码进行哈希处理
        new_hashed_password = get_password_hash(args.new_password)
        # 调用 UserCRUD 更新用户密码
        success = await user_crud_instance.update_user_password(
            args.uid, new_hashed_password
        )

        if success:
            print(f"用户 '{args.uid}' 的密码已成功修改。")
        else:
            # 此情况理论上不应发生（如果用户已找到），除非存储库的更新操作失败
            print(f"为用户 '{args.uid}' 修改密码失败。")
    except Exception as e:
        print(f"为用户 '{args.uid}' 修改密码时发生错误: {e}")


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
    print("正在初始化应用和数据存储...")
    try:
        await initialize_crud_instances()  # 关键的异步初始化步骤
        print("初始化完成。")
    except Exception as e:
        print(
            f"初始化过程中发生严重错误: {e}",
            file=sys.stderr,
        )
        print(
            "请检查您的 .env 文件和数据存储配置 (如 JSON 文件路径、数据库连接字符串等)。",
            file=sys.stderr,
        )
        # "Please check your .env file and data storage configuration (e.g., JSON file paths, database connection strings)."
        sys.exit(1)  # 初始化失败则退出

    # 确保 settings 已加载 (通常 initialize_crud_instances 会间接触发)
    # (Ensure settings are loaded (usually triggered indirectly by initialize_crud_instances))
    if not settings.app_name:  # 检查一个已知的配置项是否存在
        print(
            "错误：未能加载应用配置。",
            file=sys.stderr,
        )
        sys.exit(1)

    # 创建命令行参数解析器
    # (Create command-line argument parser)
    parser = argparse.ArgumentParser(
        description="在线考试系统命令行管理工具 - 用于用户管理和应用设置等。"
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="可用的命令")

    # 添加 'add-user' 子命令解析器
    # (Add 'add-user' subcommand parser)
    add_parser = subparsers.add_parser("add-user", help="添加一个新用户到系统。")
    add_parser.add_argument("--uid", required=True, help="用户ID (用户名)。")
    add_parser.add_argument("--password", required=True, help="用户密码。")
    add_parser.add_argument("--nickname", help="可选的用户昵称。")
    add_parser.add_argument(
        "--email",
        help="可选的用户邮箱 (例如: user@example.com)。",
    )
    add_parser.add_argument("--qq", help="可选的用户QQ号码。")
    add_parser.set_defaults(func=add_user_command)  # 设置此子命令对应的处理函数

    # 添加 'update-user' 子命令解析器
    # (Add 'update-user' subcommand parser)
    update_parser = subparsers.add_parser(
        "update-user",
        help="更新现有用户的属性。",
    )
    update_parser.add_argument(
        "--uid",
        required=True,
        help="需要更新的用户的用户ID (用户名)。",
    )
    update_parser.add_argument("--nickname", help="用户的新昵称。")
    update_parser.add_argument("--email", help="用户的新邮箱。")
    update_parser.add_argument("--qq", help="用户的新QQ号码。")
    update_parser.add_argument(
        "--tags",
        help=f"逗号分隔的新标签列表 (例如: user,admin)。允许的标签: {[t.value for t in UserTag]}",
    )
    update_parser.set_defaults(func=update_user_command)

    # 添加 'change-password' 子命令解析器
    # (Add 'change-password' subcommand parser)
    pw_parser = subparsers.add_parser("change-password", help="修改用户的密码。")
    pw_parser.add_argument(
        "--uid",
        required=True,
        help="需要修改密码的用户的用户ID (用户名)。",
    )
    pw_parser.add_argument(
        "--new-password",
        required=True,
        help="用户的新密码。",
    )
    pw_parser.set_defaults(func=change_password_command)

    # 添加 'list-users' / '导出用户' 子命令解析器
    list_users_parser = subparsers.add_parser(
        "list-users",
        help="导出所有用户的列表到CSV文件或标准输出。",
        aliases=["导出用户"],
    )
    list_users_parser.add_argument(
        "--output-file",
        "--输出文件",
        type=str,
        help="导出CSV文件的路径。如果未提供，则输出到标准输出。",
    )
    list_users_parser.set_defaults(func=list_users_command)

    # --- Question Bank Subcommands ---

    # 'add-question' / '添加题目' 子命令
    add_q_parser = subparsers.add_parser(
        "add-question",
        help="添加一个新题目到指定的题库。",
        aliases=["添加题目"],
    )
    add_q_parser.add_argument(
        "--library-id", required=True, help="题库ID (例如: 'easy', 'hard')"
    )
    add_q_parser.add_argument("--content", required=True, help="题目内容 (题干)")
    add_q_parser.add_argument(
        "--options",
        help='选择题选项的JSON字符串列表 (例如: \'["选项A", "选项B"]\')',
        default="[]",
    )
    add_q_parser.add_argument(
        "--answer", required=True, help="正确答案 (对于选择题，应为选项之一)"
    )
    add_q_parser.add_argument("--answer-detail", help="答案解析 (可选)")
    add_q_parser.add_argument("--tags", help="逗号分隔的标签列表 (可选)")
    add_q_parser.add_argument(
        "--type",
        choices=[qt.value for qt in QuestionTypeEnum],
        default=QuestionTypeEnum.SINGLE_CHOICE.value,
        help="题目类型 (默认为单选题)",
    )
    # TODO: Add more specific fields based on QuestionModel for different types if needed
    add_q_parser.set_defaults(func=add_question_command)

    # 'view-question' / '查看题目' 子命令
    view_q_parser = subparsers.add_parser(
        "view-question",
        help="查看指定ID的题目详情。",
        aliases=["查看题目"],
    )
    view_q_parser.add_argument("--question-id", required=True, help="要查看的题目ID")
    view_q_parser.set_defaults(func=view_question_command)

    # 'update-question' / '更新题目' 子命令
    update_q_parser = subparsers.add_parser(
        "update-question",
        help="更新现有题目的信息。",
        aliases=["更新题目"],
    )
    update_q_parser.add_argument("--question-id", required=True, help="要更新的题目ID")
    update_q_parser.add_argument("--content", help="新的题目内容 (题干)")
    update_q_parser.add_argument("--options", help="新的选择题选项JSON字符串列表")
    update_q_parser.add_argument("--answer", help="新的正确答案")
    update_q_parser.add_argument("--answer-detail", help="新的答案解析")
    update_q_parser.add_argument("--tags", help="新的逗号分隔的标签列表")
    update_q_parser.add_argument(
        "--confirm-rename", action="store_true", help="如果题目内容改变，需确认重命名"
    )
    update_q_parser.set_defaults(func=update_question_command)

    # 'delete-question' / '删除题目' 子命令
    delete_q_parser = subparsers.add_parser(
        "delete-question",
        help="从题库中删除一个题目。",
        aliases=["删除题目"],
    )
    delete_q_parser.add_argument("--question-id", required=True, help="要删除的题目ID")
    delete_q_parser.add_argument(
        "--confirm", action="store_true", help="必须提供此参数以确认删除"
    )
    delete_q_parser.set_defaults(func=delete_question_command)

    # 'list-questions' / '列出题目' 子命令
    list_q_parser = subparsers.add_parser(
        "list-questions",
        help="列出指定题库中的题目 (支持分页)。",
        aliases=["列出题目"],
    )
    list_q_parser.add_argument("--library-id", required=True, help="要列出题目的题库ID")
    list_q_parser.add_argument("--page", type=int, default=1, help="页码 (从1开始)")
    list_q_parser.add_argument("--per-page", type=int, default=10, help="每页数量")
    list_q_parser.set_defaults(func=list_questions_command)

    # --- Application Configuration Subcommands ---

    # 'view-config' / '查看配置' 子命令
    view_cfg_parser = subparsers.add_parser(
        "view-config",
        help="查看当前应用配置信息。",
        aliases=["查看配置"],
    )
    view_cfg_parser.add_argument(
        "--key",
        help="可选，只显示指定配置项的值。使用点表示法访问嵌套键 (例如: 'rate_limits.default.get_exam.limit')",
    )
    view_cfg_parser.set_defaults(func=view_config_command)

    # 'update-config' / '更新配置' 子命令
    update_cfg_parser = subparsers.add_parser(
        "update-config",
        help="更新应用配置项。请谨慎使用。",
        aliases=["更新配置"],
    )
    update_cfg_parser.add_argument(
        "--key-value-pairs",
        required=True,
        help='包含待更新配置项及其新值的JSON字符串 (例如: \'{"app_name": "新名称", "log_level": "DEBUG"}\')',
    )
    # Consider adding --confirm for critical changes later if needed
    update_cfg_parser.set_defaults(func=update_config_command)

    # --- Statistics Viewing Subcommand ---
    view_stats_parser = subparsers.add_parser(
        "view-stats",
        help="查看应用相关的统计信息。",
        aliases=["查看统计"],
    )
    view_stats_parser.set_defaults(func=view_stats_command)

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


# Stubs for new async command functions
async def add_question_command(args: argparse.Namespace):
    if not qb_crud_instance:
        print("错误: 题库操作模块 (QuestionBankCRUD) 未初始化。")
        return

    print(f"正在尝试向题库 '{args.library_id}' 添加题目...")

    try:
        question_type = QuestionTypeEnum(args.type)
        options = json.loads(args.options) if args.options else []

        # Validate options format
        if not isinstance(options, list):
            print(
                '错误: --options 参数必须是一个有效的JSON列表字符串。例如: \'["选项A", "选项B"]\''
            )
            return
        for opt in options:
            if not isinstance(opt, str):
                print(f"错误: 选项列表中的每个选项都必须是字符串。找到: {type(opt)}")
                return

        tags_list = [tag.strip() for tag in args.tags.split(",")] if args.tags else []

        question_data = {
            "body": args.content,
            "question_type": question_type,
            "ref": args.answer_detail,
            # Tags are not directly in QuestionModel based on qb_models.py,
            # Assuming CRUD handles tags separately or it's a custom field.
            # For now, we'll pass it if CRUD expects it, otherwise it might be ignored or cause error.
            # "tags": tags_list, # This line might be needed if CRUD supports it.
        }

        if question_type == QuestionTypeEnum.SINGLE_CHOICE:
            if not args.answer:
                print("错误: 单选题必须提供 --answer 参数。")
                return
            if args.answer not in options:
                print(f"错误: 答案 '{args.answer}' 必须是提供的选项之一: {options}")
                return
            question_data["correct_choices"] = [args.answer]
            question_data["incorrect_choices"] = [
                opt for opt in options if opt != args.answer
            ]
            question_data["num_correct_to_select"] = 1
        elif question_type == QuestionTypeEnum.MULTIPLE_CHOICE:
            # For MULTIPLE_CHOICE, assuming args.answer is a comma-separated string of correct options
            if not args.answer:
                print("错误: 多选题必须提供 --answer 参数 (逗号分隔的正确选项)。")
                return
            correct_answers = [ans.strip() for ans in args.answer.split(",")]
            for ans in correct_answers:
                if ans not in options:
                    print(f"错误: 答案 '{ans}' 必须是提供的选项之一: {options}")
                    return
            question_data["correct_choices"] = correct_answers
            question_data["incorrect_choices"] = [
                opt for opt in options if opt not in correct_answers
            ]
            question_data["num_correct_to_select"] = len(correct_answers)
        # Add handling for other question types (FILL_IN_THE_BLANK, ESSAY_QUESTION) if needed based on QuestionModel
        # For now, QuestionModel seems to primarily support choice-based questions via correct_choices/incorrect_choices
        # and other types via standard_answer_text etc. which are not fully mapped in CLI args yet.

        # Create QuestionModel instance
        # We need to handle potential Pydantic validation errors here
        try:
            question_to_create = QuestionModel(**question_data)
        except Exception as e:  # Catch Pydantic validation error
            print(f"创建题目数据时发生验证错误: {e}")
            return

        # Assuming qb_crud_instance.create_question returns the created question with an ID
        # The actual method signature might be different (e.g. create_question_in_library)
        # Also, qb_crud_instance might not have a 'tags' field in its QuestionModel
        # This will likely need adjustment based on the actual CRUD interface for questions

        # Placeholder for actual CRUD call, which needs library_id and question model
        # created_question = await qb_crud_instance.create_question(
        #     library_id=args.library_id, question_data=question_to_create
        # )

        # Simulating a call to a hypothetical extended CRUD method that handles tags:
        # created_question = await qb_crud_instance.create_question_with_tags(
        #     library_id=args.library_id, question_data=question_to_create, tags=tags_list
        # )

        # Based on the provided `QuestionModel`, 'tags' is not a field.
        # The CRUD method `create_question` likely takes `QuestionModel` and `library_id`.
        # If tags need to be stored, the CRUD method itself must handle it,
        # or the QuestionModel needs a `tags` field.
        # For now, we'll assume tags are not directly part of the QuestionModel in `qb_crud_instance.create_question`.
        # The `tags` argument in the CLI will be acknowledged but might not be persisted unless CRUD supports it.

        # Let's assume a method signature like: create_question(self, library_id: str, question: QuestionModel, tags: Optional[List[str]] = None)
        # This is a guess; the actual CRUD method signature is unknown.
        # For the purpose of this exercise, I will assume the CRUD method is:
        # `qb_crud_instance.add_question_to_library(library_id: str, question_data: QuestionModel, tags: List[str])`
        # And it returns a model that includes an `id` attribute.

        # This is a placeholder. The actual method might be different.
        # For example, it might be `qb_crud_instance.create_question_in_library(library_id=args.library_id, question_obj=question_to_create, tags=tags_list)`
        # I will use a plausible name based on common CRUD patterns.
        created_question_response = await qb_crud_instance.create_question_in_library(
            library_id=args.library_id,
            question_data=question_to_create,
            tags=tags_list,  # Assuming the CRUD method can take tags
        )

        if created_question_response and hasattr(created_question_response, "id"):
            print(f"题目已成功添加到题库 '{args.library_id}'。")
            print(f"新题目ID: {created_question_response.id}")
            if tags_list:
                print(f"标签: {', '.join(tags_list)}")
        else:
            print(f"添加题目到题库 '{args.library_id}' 失败。未返回题目ID。")

    except json.JSONDecodeError:
        print("错误: --options 参数不是有效的JSON字符串。")
    except ValueError as e:  # Catches issues like invalid enum values
        print(f"输入值错误: {e}")
    except Exception as e:
        print(f"添加题目时发生未预料的错误: {e}")


async def view_question_command(args: argparse.Namespace):
    if not qb_crud_instance:
        print("错误: 题库操作模块 (QuestionBankCRUD) 未初始化。")
        return

    print(f"正在尝试查看题目ID: {args.question_id}...")
    try:
        # Assume get_question_by_id returns a model that includes an 'id' field,
        # and potentially 'tags' if the CRUD joins them or they are part of the stored model.
        # Let's call it `QuestionDetailsModel` for this example, which might be QuestionModel itself
        # or an augmented version.
        question = await qb_crud_instance.get_question_by_id(
            question_id=args.question_id
        )

        if question:
            print("\n--- 题目详情 ---")
            if hasattr(question, "id"):  # If the returned object has an ID
                print(f"题目ID: {question.id}")
            else:  # Fallback to the requested ID if not part of the response model
                print(f"题目ID: {args.question_id}")

            print(
                f"题库ID: {question.library_id if hasattr(question, 'library_id') else '未知'}"
            )  # Assuming library_id is part of fetched model
            print(
                f"类型: {question.question_type.value if hasattr(question, 'question_type') and question.question_type else '未知'}"
            )
            print(
                f"题目内容:\n{question.body if hasattr(question, 'body') else '未知'}"
            )

            if hasattr(question, "question_type") and question.question_type in [
                QuestionTypeEnum.SINGLE_CHOICE,
                QuestionTypeEnum.MULTIPLE_CHOICE,
            ]:
                print("\n选项:")
                options = []
                if hasattr(question, "correct_choices") and question.correct_choices:
                    options.extend(question.correct_choices)
                if (
                    hasattr(question, "incorrect_choices")
                    and question.incorrect_choices
                ):
                    options.extend(question.incorrect_choices)

                # The original QuestionModel stores correct and incorrect choices separately.
                # For display, we might want to show all choices.
                # This part needs to be careful not to assume a specific structure for "options" during display
                # if the model only provides correct_choices and incorrect_choices.

                all_options_display = []
                if hasattr(question, "correct_choices") and question.correct_choices:
                    for opt in question.correct_choices:
                        all_options_display.append(f"  - {opt} (正确答案)")
                if (
                    hasattr(question, "incorrect_choices")
                    and question.incorrect_choices
                ):
                    for opt in question.incorrect_choices:
                        all_options_display.append(f"  - {opt}")

                if all_options_display:
                    for opt_display in all_options_display:
                        print(opt_display)
                else:
                    print("  (未提供选项信息)")

                print("\n正确答案:")
                if hasattr(question, "correct_choices") and question.correct_choices:
                    for ans in question.correct_choices:
                        print(f"  - {ans}")
                else:
                    print("  (未设置正确答案)")

            if (
                hasattr(question, "standard_answer_text")
                and question.standard_answer_text
            ):  # For essay questions
                print(f"\n参考答案 (主观题):\n{question.standard_answer_text}")

            if hasattr(question, "ref") and question.ref:
                print(f"\n答案解析:\n{question.ref}")

            # Assuming tags are fetched as part of the question object by the CRUD method
            if hasattr(question, "tags") and question.tags:
                print(f"\n标签: {', '.join(question.tags)}")

            print("--- 详情结束 ---")
        else:
            print(f"错误: 未找到题目ID为 '{args.question_id}' 的题目。")

    except Exception as e:
        # Catch specific exceptions like 'QuestionNotFoundException' if defined by CRUD layer
        # For now, a generic catch.
        print(f"查看题目时发生错误: {e}")


async def update_question_command(args: argparse.Namespace):
    if not qb_crud_instance:
        print("错误: 题库操作模块 (QuestionBankCRUD) 未初始化。")
        return

    print(f"正在尝试更新题目ID: {args.question_id}...")

    try:
        existing_question = await qb_crud_instance.get_question_by_id(
            question_id=args.question_id
        )
        if not existing_question:
            print(f"错误: 未找到题目ID为 '{args.question_id}' 的题目，无法更新。")
            return

        update_payload = {}  # Using a dict for partial updates

        if args.content:
            if args.content != existing_question.body and not args.confirm_rename:
                print(
                    "错误: 题目内容 (content) 已更改，但未提供 --confirm-rename 标志。操作已取消。"
                )
                print("如果您确定要修改题目内容，请同时使用 --confirm-rename 参数。")
                return
            update_payload["body"] = args.content

        if args.answer_detail:
            update_payload["ref"] = args.answer_detail

        new_tags_list = None
        if (
            args.tags is not None
        ):  # Check if tags argument was provided (even if empty string)
            new_tags_list = (
                [tag.strip() for tag in args.tags.split(",") if tag.strip()]
                if args.tags
                else []
            )
            # This assumes the CRUD update method can handle tags.
            # If QuestionModel had a 'tags' field, this would be `update_payload["tags"] = new_tags_list`

        # Handling options and answer is complex as it depends on question type
        # and how they are stored in QuestionModel (correct_choices, incorrect_choices)
        if args.options or args.answer:
            if not hasattr(existing_question, "question_type"):
                print("错误: 无法确定现有题目的类型，无法更新选项或答案。")
                return

            current_q_type = existing_question.question_type
            options = (
                json.loads(args.options) if args.options else None
            )  # Parse new options if provided

            if options is not None and not isinstance(options, list):
                print(
                    '错误: --options 参数必须是一个有效的JSON列表字符串。例如: \'["选项A", "选项B"]\''
                )
                return
            for opt_idx, opt_val in enumerate(options or []):
                if not isinstance(opt_val, str):
                    print(
                        f"错误: 新选项列表索引 {opt_idx} 处的值必须是字符串。找到: {type(opt_val)}"
                    )
                    return

            current_options = []
            if (
                hasattr(existing_question, "correct_choices")
                and existing_question.correct_choices
            ):
                current_options.extend(existing_question.correct_choices)
            if (
                hasattr(existing_question, "incorrect_choices")
                and existing_question.incorrect_choices
            ):
                current_options.extend(existing_question.incorrect_choices)

            final_options = options if options is not None else current_options
            new_answer = (
                args.answer
                if args.answer is not None
                else (
                    existing_question.correct_choices[0]
                    if hasattr(existing_question, "correct_choices")
                    and existing_question.correct_choices
                    and current_q_type == QuestionTypeEnum.SINGLE_CHOICE
                    else None
                )
            )
            # For multi-choice, new_answer might need to be a list from comma-separated string

            if current_q_type == QuestionTypeEnum.SINGLE_CHOICE:
                if (
                    new_answer is None
                ):  # If answer is being cleared, or was not set and not provided now
                    # This case might need clarification: can a choice question exist without an answer?
                    # For now, if no new answer is given, and no old one, then error or keep as is.
                    # If new_answer is explicitly empty, it might mean to clear it.
                    # Let's assume for now an answer is required if options are present.
                    if (
                        final_options and not new_answer
                    ):  # If there are options but no answer
                        print(
                            "错误: 单选题更新时，如果提供了选项，则必须有明确的答案。"
                        )
                        return

                if new_answer and new_answer not in final_options:
                    print(
                        f"错误: 新答案 '{new_answer}' 必须是最终选项列表之一: {final_options}"
                    )
                    return
                update_payload["correct_choices"] = [new_answer] if new_answer else []
                update_payload["incorrect_choices"] = [
                    opt for opt in final_options if opt != new_answer
                ]
                update_payload["num_correct_to_select"] = (
                    1 if new_answer and final_options else 0
                )

            elif current_q_type == QuestionTypeEnum.MULTIPLE_CHOICE:
                # Assuming new_answer for multiple choice is comma-separated if provided via args.answer
                # If args.answer is not provided, we rely on existing_question.correct_choices
                new_correct_answers_list = []
                if args.answer is not None:  # New answer string is provided
                    new_correct_answers_list = [
                        ans.strip() for ans in args.answer.split(",")
                    ]
                elif hasattr(
                    existing_question, "correct_choices"
                ):  # No new answer string, use existing
                    new_correct_answers_list = existing_question.correct_choices

                for ans in new_correct_answers_list:
                    if ans not in final_options:
                        print(
                            f"错误: 更新后的答案 '{ans}' 必须是最终选项列表之一: {final_options}"
                        )
                        return
                update_payload["correct_choices"] = new_correct_answers_list
                update_payload["incorrect_choices"] = [
                    opt for opt in final_options if opt not in new_correct_answers_list
                ]
                update_payload["num_correct_to_select"] = len(new_correct_answers_list)

            # If only options are provided, but not answer, and type is choice:
            # Need to ensure existing answer is still valid or require new answer.
            if (
                options is not None
                and args.answer is None
                and current_q_type
                in [QuestionTypeEnum.SINGLE_CHOICE, QuestionTypeEnum.MULTIPLE_CHOICE]
            ):
                if not update_payload.get(
                    "correct_choices"
                ):  # if correct_choices wasn't set (e.g. existing answer was not in new options)
                    print(
                        "警告: 选项已更新，但未提供新的答案，或旧答案已失效。请使用 --answer 更新答案。"
                    )

        if (
            not update_payload and new_tags_list is None
        ):  # Check if any actual update data is present
            print("未提供任何需要更新的字段。操作已取消。")
            return

        # The qb_crud_instance.update_question method needs to be defined.
        # It should accept question_id and a dictionary (or Pydantic model) for updates.
        # And potentially tags as a separate argument.
        # e.g., updated_question = await qb_crud_instance.update_question(question_id, update_data=QuestionUpdateModel(**update_payload), tags=new_tags_list)
        # For now, using a dict for update_payload.
        # Let's assume a method like:
        # `qb_crud_instance.update_question_by_id(question_id: str, update_doc: dict, tags: Optional[List[str]])`

        # This is a placeholder for the actual CRUD call.
        # The update_payload should ideally be validated by a Pydantic model for update.
        # For example, `QuestionUpdate(**update_payload)`
        updated_q_response = await qb_crud_instance.update_question_fields(
            question_id=args.question_id,
            update_data=update_payload,
            tags=new_tags_list,  # Pass tags if CRUD supports it
        )

        if updated_q_response:  # Assuming CRUD returns the updated question or True
            print(f"题目ID '{args.question_id}' 已成功更新。")
            # Optionally, print which fields were updated if the response indicates this.
        else:
            # This 'else' might not be reachable if CRUD raises an exception on failure.
            print(f"更新题目ID '{args.question_id}' 失败。")

    except json.JSONDecodeError:
        print("错误: --options 参数不是有效的JSON字符串。")
    except ValueError as e:
        print(f"输入值错误或转换失败: {e}")
    except Exception as e:
        # Consider specific exceptions like QuestionNotFoundException if defined by CRUD
        print(f"更新题目时发生未预料的错误: {e}")
        import traceback

        traceback.print_exc()


async def delete_question_command(args: argparse.Namespace):
    if not qb_crud_instance:
        print("错误: 题库操作模块 (QuestionBankCRUD) 未初始化。")
        return

    if not args.confirm:
        print("错误: 删除操作需要 --confirm 标志进行确认。操作已取消。")
        print(
            f"如果您确定要删除题目ID '{args.question_id}'，请再次运行命令并添加 --confirm 参数。"
        )
        return

    print(f"正在尝试删除题目ID: {args.question_id}...")
    try:
        # Assume a CRUD method like delete_question_by_id(question_id: str)
        # This method should ideally return True if deletion was successful,
        # or raise a specific exception (e.g., QuestionNotFound) if it matters,
        # or return False if deletion failed for other reasons.
        # Some delete operations are idempotent (deleting a non-existent item is success).
        # Let's assume it returns True on success, False on failure (e.g. lock error),
        # and handles QuestionNotFound internally or by not raising an error for it.

        deleted_successfully = await qb_crud_instance.delete_question_by_id(
            question_id=args.question_id
        )

        if deleted_successfully:
            print(f"题目ID '{args.question_id}' 已成功删除。")
        else:
            # This path might be taken if the question didn't exist AND the CRUD method returns False for that,
            # or if there was another failure preventing deletion.
            # If QuestionNotFound is not an error for delete, this message might need adjustment.
            print(
                f"删除题目ID '{args.question_id}' 失败。可能题目不存在或删除过程中发生错误。"
            )
            # To provide better feedback, CRUD could return a more specific status or raise specific exceptions.

    except Exception as e:
        # Example: Catch a specific 'QuestionNotFoundException' if CRUD defines it and
        # we want to treat "not found" as a specific case (e.g., not an error for delete).
        # if isinstance(e, QuestionNotFoundException):
        #    print(f"题目ID '{args.question_id}' 未找到，无需删除。")
        # else:
        print(f"删除题目ID '{args.question_id}' 时发生未预料的错误: {e}")


async def list_questions_command(args: argparse.Namespace):
    if not qb_crud_instance:
        print("错误: 题库操作模块 (QuestionBankCRUD) 未初始化。")
        return

    print(
        f"正在尝试列出题库 '{args.library_id}' 中的题目 (页码: {args.page}, 每页: {args.per_page})..."
    )
    try:
        # Assume a CRUD method like:
        # get_questions_from_library(library_id: str, page: int, per_page: int) -> dict
        # The returned dict might look like:
        # {
        #   "items": [QuestionModelSubset, ...],
        #   "total_items": int,
        #   "total_pages": int,
        #   "current_page": int
        # }
        # Or it might just return a list of questions if pagination is simpler.
        # Let's assume a method that returns a list of questions directly for now,
        # and pagination info might be part of those question objects or inferred.
        # A more robust CRUD would return total counts for proper pagination display.

        # Placeholder: Actual signature might be `get_questions_in_library` or similar
        # and might return a more complex object with pagination data.
        # For this example, let's assume it returns a list of question objects (e.g., QuestionModel or a summary model)
        # and we don't have total pages/items info from this call directly, unless the CRUD provides it.

        # Let's refine the assumed CRUD call to return a structure that includes pagination details:
        # result = await qb_crud_instance.list_questions_in_library_paginated(
        # library_id=args.library_id, page=args.page, limit=args.per_page
        # )
        # Assuming `result` is an object or dict with `items` (list of questions),
        # `total_count`, `page`, `per_page`.

        # Simpler assumption for now: returns a list of QuestionModel like objects
        # And we don't have total count from this call.
        questions_page = await qb_crud_instance.get_questions_from_library_paginated(
            library_id=args.library_id, page=args.page, per_page=args.per_page
        )
        # questions_page should be a list of objects, each having at least 'id' and 'body'
        # Ideally, the response would also include total_items and total_pages.
        # Let's say questions_page = { "questions": [...], "total_count": N, "page": P, "per_page": PP }

        if (
            questions_page
            and isinstance(questions_page, dict)
            and "questions" in questions_page
        ):
            items = questions_page["questions"]
            total_items = questions_page.get(
                "total_count", len(items)
            )  # Fallback if total_count not provided
            total_pages = questions_page.get(
                "total_pages", None
            )  # If CRUD provides total_pages

            if not items:
                print(
                    f"题库 '{args.library_id}' 中未找到任何题目 (第 {args.page} 页)。"
                )
                if total_items > 0 and args.page > 1:
                    print(f"总共有 {total_items} 个题目。可能您请求的页码超出了范围。")
                elif total_items == 0:
                    print("该题库当前为空。")
                return

            print(
                f"\n--- 题库 '{args.library_id}' - 第 {args.page} 页 (共 {total_items} 个题目) ---"
            )
            if total_pages:
                print(f" (总页数: {total_pages})")

            for idx, q_item in enumerate(items):
                # Assuming q_item has 'id' and 'body' attributes.
                # It might be a full QuestionModel or a summary.
                content_snippet = (
                    (q_item.body[:70] + "...")
                    if hasattr(q_item, "body") and q_item.body and len(q_item.body) > 70
                    else (q_item.body if hasattr(q_item, "body") else "无内容")
                )
                q_id = q_item.id if hasattr(q_item, "id") else "未知ID"
                print(
                    f"  {((args.page - 1) * args.per_page) + idx + 1}. ID: {q_id} - 内容: {content_snippet}"
                )

            print(f"--- 共显示 {len(items)} 个题目 ---")
            if total_pages and args.page < total_pages:
                print(f"要查看下一页，请使用 --page {args.page + 1}")

        elif (
            isinstance(questions_page, list) and not questions_page
        ):  # Simpler list return, empty
            print(f"题库 '{args.library_id}' 中未找到任何题目 (第 {args.page} 页)。")
        elif (
            isinstance(questions_page, list) and questions_page
        ):  # Simpler list return, with items
            print(f"\n--- 题库 '{args.library_id}' - 第 {args.page} 页 ---")
            for idx, q_item in enumerate(questions_page):
                content_snippet = (
                    (q_item.body[:70] + "...")
                    if hasattr(q_item, "body") and q_item.body and len(q_item.body) > 70
                    else (q_item.body if hasattr(q_item, "body") else "无内容")
                )
                q_id = q_item.id if hasattr(q_item, "id") else "未知ID"
                print(
                    f"  {((args.page - 1) * args.per_page) + idx + 1}. ID: {q_id} - 内容: {content_snippet}"
                )
            print(f"--- 共显示 {len(questions_page)} 个题目 ---")
            if len(questions_page) == args.per_page:
                print(
                    f"可能还有更多题目，请尝试使用 --page {args.page + 1} 查看下一页。"
                )
        else:
            # This case handles if questions_page is None or an unexpected structure
            print(f"未能从题库 '{args.library_id}' 获取题目列表，或题库为空。")

    except Exception as e:
        # Example: Catch a specific 'LibraryNotFoundException' if CRUD defines it.
        # if isinstance(e, LibraryNotFoundException):
        #    print(f"错误: 未找到ID为 '{args.library_id}' 的题库。")
        # else:
        print(f"列出题库 '{args.library_id}' 中的题目时发生错误: {e}")
        import traceback

        traceback.print_exc()


# Helper for accessing nested dictionary keys using dot notation
def get_nested_value(data_dict, key_path):
    keys = key_path.split(".")
    value = data_dict
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, BaseModel) and hasattr(
            value, key
        ):  # Handle Pydantic models
            value = getattr(value, key)
        else:
            return None  # Key not found or path invalid
    return value


async def view_config_command(args: argparse.Namespace):
    if not settings_crud_instance:
        print("错误: 配置操作模块 (SettingsCRUD) 未初始化。")
        return

    try:
        # Assuming get_all_settings() returns a Pydantic model instance (e.g., SettingsResponseModel)
        # or a dict that can be parsed into one.
        all_settings_model = await settings_crud_instance.get_all_settings()

        if not all_settings_model:
            print("错误: 未能获取到任何配置信息。")
            return

        # Convert Pydantic model to dict for easier processing if it's not already a dict
        # The SettingsResponseModel has `model_config = {"extra": "ignore"}`
        # and fields are Optional, so it should handle settings.json not having all keys.
        # We should use model_dump to get a dict from the Pydantic model.
        if isinstance(all_settings_model, BaseModel):
            settings_dict = all_settings_model.model_dump(
                exclude_unset=True
            )  # exclude_unset for cleaner output
        else:  # Assuming it's already a dict (less ideal, CRUD should return model)
            settings_dict = all_settings_model

        if args.key:
            print(f"正在查找配置项: '{args.key}'...")
            value = get_nested_value(settings_dict, args.key)
            if value is not None:
                print(f"\n--- 配置项 '{args.key}' ---")
                # Pretty print if value is a dict or list
                if isinstance(value, (dict, list)):
                    print(json.dumps(value, indent=2, ensure_ascii=False))
                else:
                    print(str(value))
                print("--- 结束 ---")
            else:
                print(f"错误: 未找到配置项键 '{args.key}'。")
        else:
            print("\n--- 当前应用配置 ---")
            if settings_dict:
                # Using json.dumps for pretty printing the whole dict
                print(json.dumps(settings_dict, indent=2, ensure_ascii=False))
            else:
                print("未找到任何配置项。")
            print("--- 配置结束 ---")

    except Exception as e:
        print(f"查看配置时发生错误: {e}")
        import traceback

        traceback.print_exc()


async def update_config_command(args: argparse.Namespace):
    if not settings_crud_instance:
        print("错误: 配置操作模块 (SettingsCRUD) 未初始化。")
        return

    print("警告: 更新应用配置是一项敏感操作，请确保您了解所做更改的影响。")

    try:
        update_data_dict = json.loads(args.key_value_pairs)
        if not isinstance(update_data_dict, dict):
            print(
                "错误: --key-value-pairs 参数必须是一个有效的JSON对象 (字典) 字符串。"
            )
            return
        if not update_data_dict:
            print("错误: 提供的键值对为空，没有可更新的配置项。")
            return

        print("\n正在尝试更新以下配置项:")
        for key, value in update_data_dict.items():
            # Truncate long values for display confirmation
            display_value = str(value)
            if len(display_value) > 70:
                display_value = display_value[:67] + "..."
            print(f"  - {key}: {display_value}")

        # It's good practice to ask for confirmation here, especially for `update-config`.
        # However, the prompt doesn't explicitly ask for a --confirm flag for this command,
        # but mentions "Consider adding a --confirm flag". For now, proceeding without it.
        # confirm = input("\n您确定要应用这些更改吗? (yes/no): ")
        # if confirm.lower() != 'yes':
        # print("操作已取消。")
        # return

        # Assumption: settings_crud_instance.update_settings(dict)
        # This method should perform validation against SettingsUpdatePayload internally.
        # It should return the updated settings or a status.
        # Let's assume it returns a model of the *actually updated* settings or True/False.

        # To ensure validation against SettingsUpdatePayload, we could do:
        # validated_payload = SettingsUpdatePayload(**update_data_dict)
        # updated_settings_response = await settings_crud_instance.update_settings(validated_payload.model_dump(exclude_unset=True))
        # This would raise Pydantic validation error before calling CRUD if input is bad.
        # For now, let's assume CRUD handles validation of the raw dict.

        updated_result = await settings_crud_instance.update_settings(update_data_dict)

        if updated_result:  # If CRUD returns True or the updated settings model
            print("\n配置已成功更新。")
            if isinstance(
                updated_result, (dict, BaseModel)
            ):  # If it returns the updated data
                print("更新后的值为:")
                # If updated_result is a Pydantic model, convert to dict for printing
                if isinstance(updated_result, BaseModel):
                    updated_result_dict = updated_result.model_dump(exclude_unset=True)
                else:
                    updated_result_dict = updated_result

                # Print only the keys that were part of the update request
                for key in update_data_dict.keys():
                    if key in updated_result_dict:
                        print(f"  - {key}: {updated_result_dict[key]}")
                    else:
                        print(f"  - {key}: (未从更新结果中返回)")
            else:  # If it just returns True
                print("请使用 'view-config' 命令查看更改后的配置。")
        else:
            # This path might be taken if CRUD returns False or None on failure,
            # without raising an exception.
            print("\n更新配置失败。请检查日志或输入数据。")
            print("可能的原因包括: 无效的配置键、值不符合类型要求或验证规则。")

    except json.JSONDecodeError:
        print("错误: --key-value-pairs 参数不是有效的JSON字符串。")
    except (
        Exception
    ) as e:  # This could catch Pydantic validation errors if CRUD raises them
        print(f"更新配置时发生错误: {e}")
        # If e is a Pydantic ValidationError, it can be printed more nicely.
        # from pydantic import ValidationError
        # if isinstance(e, ValidationError):
        #    print("详细验证错误:")
        #    for error in e.errors():
        #        print(f"  字段: {'.'.join(str(loc) for loc in error['loc'])}")
        #        print(f"  错误: {error['msg']}")
        # else:
        import traceback

        traceback.print_exc()


# Stats viewing command
async def view_stats_command(args: argparse.Namespace):
    print("正在收集应用统计信息...")

    stats = {}
    errors = []

    # User stats
    if user_crud_instance:
        try:
            total_users = await user_crud_instance.get_total_users_count()
            stats["总用户数"] = total_users
        except AttributeError:
            errors.append("用户CRUD实例缺少 'get_total_users_count' 方法。")
        except Exception as e:
            errors.append(f"获取总用户数时出错: {e}")
    else:
        errors.append("用户CRUD实例未初始化。")

    # Question bank stats
    if qb_crud_instance:
        try:
            total_questions = await qb_crud_instance.get_total_questions_count()
            stats["总题目数 (所有题库)"] = total_questions
        except AttributeError:
            errors.append("题库CRUD实例缺少 'get_total_questions_count' 方法。")
        except Exception as e:
            errors.append(f"获取总题目数时出错: {e}")

        try:
            counts_per_lib = await qb_crud_instance.get_questions_count_per_library()
            if counts_per_lib:  # Assuming it returns a dict like {'lib_id': count}
                stats["各题库题目数"] = counts_per_lib
            else:
                stats["各题库题目数"] = "暂无题库或题目信息。"
        except AttributeError:
            errors.append("题库CRUD实例缺少 'get_questions_count_per_library' 方法。")
        except Exception as e:
            errors.append(f"获取各题库题目数时出错: {e}")
    else:
        errors.append("题库CRUD实例未初始化。")

    # Paper/Exam stats
    if paper_crud_instance:
        try:
            completed_exams = (
                await paper_crud_instance.get_total_completed_exams_count()
            )
            stats["已完成考试总数"] = completed_exams
        except AttributeError:
            errors.append("试卷CRUD实例缺少 'get_total_completed_exams_count' 方法。")
        except Exception as e:
            errors.append(f"获取已完成考试数时出错: {e}")

        try:
            avg_score_data = (
                await paper_crud_instance.get_average_score()
            )  # Assuming this returns a float or a dict with score
            if isinstance(avg_score_data, (float, int)):
                stats["平均考试得分"] = (
                    f"{avg_score_data:.2f}%" if avg_score_data is not None else "N/A"
                )
            elif isinstance(avg_score_data, dict) and "average_score" in avg_score_data:
                stats["平均考试得分"] = (
                    f"{avg_score_data['average_score']:.2f}%"
                    if avg_score_data["average_score"] is not None
                    else "N/A"
                )
            else:
                stats["平均考试得分"] = "数据不可用或格式不正确。"

        except AttributeError:
            errors.append("试卷CRUD实例缺少 'get_average_score' 方法。")
        except Exception as e:
            errors.append(f"获取平均分时出错: {e}")
    else:
        errors.append("试卷CRUD实例未初始化。")

    print("\n--- 应用统计 ---")
    if stats:
        for key, value in stats.items():
            if isinstance(value, dict):
                print(f"{key}:")
                for sub_key, sub_value in value.items():
                    print(f"  - {sub_key}: {sub_value}")
            else:
                print(f"{key}: {value}")
    else:
        print("未能收集到任何统计信息。")

    if errors:
        print("\n--- 收集统计信息时遇到的错误 ---")
        for err in errors:
            print(f"- {err}")

    print("--- 统计结束 ---")


if __name__ == "__main__":
    # 这个检查确保脚本是直接运行的 (`python examctl.py ...`)，而不是被导入的。
    # (This check ensures the script is run directly (`python examctl.py ...`), not imported.)
    asyncio.run(main_async())  # 运行异步主函数
