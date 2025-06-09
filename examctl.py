#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
examctl.py - 新一代命令行与终端UI管理工具
"""

import argparse
import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中，以便导入 app 包中的模块
# (如果 examctl.py 最终需要直接导入 app 内的模块)
# sys.path.insert(0, str(Path(__file__).resolve().parent))

async def run_tui():
    """启动 Textual TUI 应用程序。"""
    print('[TUI Mode] TUI 应用程序将在此启动...')
    # 在后续步骤中，这里会导入并运行 Textual App
    # from rich.text import Text # 示例导入
    # print(Text.from_markup("[b blue]启动TUI...[/b blue]"))
    # try:
    #     from .tui_app import ExamTextualApp # 假设TUI应用类在 tui_app.py
    #     app = ExamTextualApp()
    #     await app.run_async()
    # except ImportError:
    #     print('错误: 未能导入TUI应用。请确保Textual已安装且TUI模块存在。')
    #     print('请运行: pip install textual')
    pass

async def handle_cli_command(args, parser_ref): # Added parser_ref for print_help
    """根据解析的CLI参数处理具体的子命令。"""
    print(f'[CLI Mode] 接收到参数: {args}')

    if args.command == 'tui': # 如果 tui 是一个子命令 (main() handles this via func_to_call)
        # await run_tui() # This path might not be hit if func_to_call is used
        return

    # 后续将根据 args.command 和 args 中其他参数分发到具体命令处理函数
    if args.command == 'pwd':
        if hasattr(args, 'sub_command_pwd') and args.sub_command_pwd == 'change':
            print(f'CLI: 处理密码修改，用户: {args.username}, 密码: {args.password}')
        elif hasattr(args, 'sub_command_pwd'):
            print(f'未知的 pwd 子命令: {args.sub_command_pwd}')
            # pwd_parser.print_help() # Need to pass pwd_parser
        else: # Should be caught by 'required=True' in subparser
            print('pwd 命令需要子命令。')
            # pwd_parser.print_help()
    elif args.command == 'usr':
        print(f'CLI: 处理用户命令...')
    elif args.command == 'server':
        print(f'CLI: 处理服务器命令...')
    else:
        # This else might not be reached if subparsers.required = False is removed or default TUI is handled
        # Or if a default func is set for the top-level parser
        print(f'未知的顶级命令: {args.command}')
        parser_ref.print_help()


async def main():
    """主异步函数，解析参数并分发任务。"""

    parser = argparse.ArgumentParser(
        description='在线考试系统命令行管理工具 (examctl.py)',
        formatter_class=argparse.RawTextHelpFormatter # 允许在help信息中使用换行
    )

    subparsers = parser.add_subparsers(dest='command', title='可用的命令模块')
    # Making subparsers not strictly required to allow 'examctl.py' (no args) to default to TUI
    # subparsers.required = False # Default is False if no command is given AND no handler is set for empty 'command'

    # 添加 'tui' 子命令
    tui_parser = subparsers.add_parser('tui', help='启动交互式终端UI模式。')
    # Set a default function to call for this subparser
    # This function will be called with the parsed args for this subparser
    tui_parser.set_defaults(func_to_execute=run_tui)

    # --- CLI 子命令定义占位符 ---
    # pwd (密码管理)
    pwd_parser = subparsers.add_parser('pwd', help='密码管理')
    pwd_subparsers = pwd_parser.add_subparsers(dest='sub_command_pwd', title='密码操作', required=True)
    pwd_change_parser = pwd_subparsers.add_parser('change', help='修改用户密码')
    pwd_change_parser.add_argument('username', nargs='?', default=None, help='目标用户名 (可选，如果省略则进入交互模式)')
    pwd_change_parser.add_argument('password', nargs='?', default=None, help='新密码 (可选，如果省略则进入交互模式)')
    pwd_change_parser.set_defaults(func_to_execute=handle_cli_command, command_name='pwd_change')


    # usr (用户管理)
    usr_parser = subparsers.add_parser('usr', help='用户管理')
    # Example: usr list
    usr_list_parser = usr_parser.add_subparsers(dest='sub_command_usr', title='用户操作').add_parser('list', help='列出用户')
    usr_list_parser.set_defaults(func_to_execute=handle_cli_command, command_name='usr_list')


    # server (服务器控制)
    server_parser = subparsers.add_parser('server', help='服务器控制')
    server_start_parser = server_parser.add_subparsers(dest='sub_command_server', title='服务器操作').add_parser('start', help='启动服务器')
    server_start_parser.set_defaults(func_to_execute=handle_cli_command, command_name='server_start')


    args = parser.parse_args()

    if hasattr(args, 'func_to_execute'):
        # If a subparser set a specific function, call it
        # This is useful if the function doesn't need the full 'args' or needs specific parts
        # For commands routed through handle_cli_command, we pass args and the top parser
        if args.func_to_execute == run_tui:
            await args.func_to_execute()
        else:
            await args.func_to_execute(args, parser) # Pass parser for help
    elif args.command is None:
        # No command was provided (e.g., just 'examctl.py')
        # This case is now handled by the __main__ block directly for clarity
        # Defaulting to TUI if no args are passed is handled in __main__
        # If args are present but no command matched, print help
        parser.print_help()
    else:
        # Fallback for other CLI commands not using set_defaults with func_to_execute
        # (or if a command is recognized by name but has no specific handler set up via set_defaults)
        # This path should ideally be minimized by using set_defaults for all commands.
        await handle_cli_command(args, parser)


if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('以无参数方式运行，启动 TUI 模式...')
        asyncio.run(run_tui())
    else:
        asyncio.run(main())

