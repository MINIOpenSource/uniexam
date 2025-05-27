#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

# Adjust path to allow importing from the 'app' package
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.crud.user_crud import UserCRUD
from app.models.user_models import UserCreate, AdminUserUpdate, UserTag
from app.core.security import get_password_hash
# Initialize settings to ensure UserCRUD can access them if needed (e.g., for default paths)
from app.core.config import settings

# Initialize CRUD instance (UserCRUD's __init__ is synchronous)
user_crud = UserCRUD()

async def add_user_command(args):
    """Handles the 'add-user' command."""
    print(f"Attempting to add user: {args.uid}")
    user_create_payload = UserCreate(
        uid=args.uid,
        password=args.password,
        nickname=args.nickname,
        email=args.email,
        qq=args.qq
    )
    created_user = await user_crud.create_user(user_create_payload)
    if created_user:
        print(f"Successfully added user '{created_user.uid}' with tags: {[tag.value for tag in created_user.tags]}.")
    else:
        print(f"Failed to add user '{args.uid}'. User might already exist or data is invalid.")

async def update_user_command(args):
    """Handles the 'update-user' command."""
    print(f"Attempting to update user: {args.uid}")
    update_data = {}
    if args.nickname is not None:
        update_data["nickname"] = args.nickname
    if args.email is not None:
        update_data["email"] = args.email
    if args.qq is not None:
        update_data["qq"] = args.qq
    if args.tags is not None:
        try:
            update_data["tags"] = [UserTag(tag.strip()) for tag in args.tags.split(',')]
        except ValueError as e:
            print(f"Error: Invalid tag provided in --tags: {e}. Allowed tags: {[tag.value for tag in UserTag]}")
            return

    if not update_data:
        print("No update parameters provided. Exiting.")
        return

    admin_update_payload = AdminUserUpdate(**update_data)
    updated_user = await user_crud.admin_update_user(args.uid, admin_update_payload)

    if updated_user:
        print(f"Successfully updated user '{updated_user.uid}'.")
        print(f"  Nickname: {updated_user.nickname}")
        print(f"  Email: {updated_user.email}")
        print(f"  QQ: {updated_user.qq}")
        print(f"  Tags: {[tag.value for tag in updated_user.tags]}")
    else:
        print(f"Failed to update user '{args.uid}'. User might not exist or data is invalid.")

async def change_password_command(args):
    """Handles the 'change-password' command."""
    print(f"Attempting to change password for user: {args.uid}")
    
    # Validate new password against Pydantic model constraints if possible,
    # or rely on UserPasswordUpdate model if we were to use it directly.
    # For CLI, simple length check from settings.
    pw_config = settings.user_config
    if not (pw_config.password_min_len <= len(args.new_password) <= pw_config.password_max_len):
        print(f"Error: New password length must be between {pw_config.password_min_len} and {pw_config.password_max_len} characters.")
        return

    user = user_crud.get_user_by_uid(args.uid)
    if not user:
        print(f"Error: User '{args.uid}' not found.")
        return

    new_hashed_password = get_password_hash(args.new_password)
    success = await user_crud.update_user_password(args.uid, new_hashed_password)

    if success:
        print(f"Successfully changed password for user '{args.uid}'.")
    else:
        # This case should ideally not happen if user was found, unless persist fails.
        print(f"Failed to change password for user '{args.uid}'.")

def main():
    parser = argparse.ArgumentParser(description="Exam Control CLI - Manage users and application settings.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Available commands")

    # Add User command
    add_parser = subparsers.add_parser("add-user", help="Add a new user to the system.")
    add_parser.add_argument("--uid", required=True, help="User ID (username).")
    add_parser.add_argument("--password", required=True, help="User password.")
    add_parser.add_argument("--nickname", help="Optional nickname for the user.")
    add_parser.add_argument("--email", help="Optional email for the user (e.g., user@example.com).")
    add_parser.add_argument("--qq", help="Optional QQ number for the user.")
    add_parser.set_defaults(func=add_user_command)

    # Update User command
    update_parser = subparsers.add_parser("update-user", help="Update attributes of an existing user.")
    update_parser.add_argument("--uid", required=True, help="User ID (username) of the user to update.")
    update_parser.add_argument("--nickname", help="New nickname for the user.")
    update_parser.add_argument("--email", help="New email for the user.")
    update_parser.add_argument("--qq", help="New QQ number for the user.")
    update_parser.add_argument("--tags", help=f"Comma-separated list of new tags (e.g., user,admin). Allowed: {[t.value for t in UserTag]}")
    update_parser.set_defaults(func=update_user_command)

    # Change Password command
    pw_parser = subparsers.add_parser("change-password", help="Change a user's password.")
    pw_parser.add_argument("--uid", required=True, help="User ID (username) whose password to change.")
    pw_parser.add_argument("--new-password", required=True, help="The new password for the user.")
    pw_parser.set_defaults(func=change_password_command)

    args = parser.parse_args()

    # Ensure settings are loaded (UserCRUD init does this, but good to be explicit if other parts need it)
    if not settings:
        print("Error: Could not load application settings.", file=sys.stderr)
        sys.exit(1)

    # Execute the command
    if hasattr(args, 'func'):
        # For Python 3.7+ asyncio.run can be used directly
        if sys.version_info >= (3, 7):
            asyncio.run(args.func(args))
        else:
            # Fallback for older Python versions if needed, though 3.7+ is common
            loop = asyncio.get_event_loop()
            loop.run_until_complete(args.func(args))
    else:
        parser.print_help()

if __name__ == "__main__":
    # This check ensures that the script is being run directly and not imported.
    # It's good practice, though for a CLI tool, it's often the only way it's used.
    main()