# -*- coding: utf-8 -*-
# region 包初始化
"""
app.utils 包初始化文件。

此包包含项目中可被多个模块复用的通用工具函数和辅助类。
"""

# 从 helpers.py 导入常用的工具函数，方便其他模块通过 app.utils 直接访问
from .helpers import (
    format_short_uuid,
    generate_random_hex_string_of_bytes,  # 重命名以更清晰地表明长度参数是字节数
    get_client_ip_from_request,  # 重命名以更清晰地表明它需要 Request 对象
    get_current_timestamp_str,
    shuffle_dictionary_items,
)

__all__ = [
    "get_current_timestamp_str",
    "format_short_uuid",
    "get_client_ip_from_request",
    "shuffle_dictionary_items",
    "generate_random_hex_string_of_bytes",
]
# endregion
