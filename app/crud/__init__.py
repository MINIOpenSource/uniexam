# -*- coding: utf-8 -*-
"""
app.crud 包初始化文件。

此包包含所有与数据持久化层交互的 "Create, Read, Update, Delete" (CRUD) 操作逻辑。
每个模块通常对应应用中的一个核心数据实体或配置。
"""

from .user_crud import UserCRUD
from .paper_crud import PaperCRUD
from .qb_crud import QuestionBankCRUD
from .settings_crud import SettingsCRUD

user_crud_instance = UserCRUD()
qb_crud_instance = QuestionBankCRUD()
# PaperCRUD 依赖 qb_crud_instance
paper_crud_instance = PaperCRUD(qb_crud_instance=qb_crud_instance)
settings_crud_instance = SettingsCRUD()

__all__ = ["user_crud_instance", "paper_crud_instance", "qb_crud_instance", "settings_crud_instance"]

# 目前保持为空，按需添加。
