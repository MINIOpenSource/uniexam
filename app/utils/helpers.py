# -*- coding: utf-8 -*-
"""
通用工具函数模块 (General Utility Functions Module)。

此模块包含项目中可能在多个地方被复用的一些辅助函数，
例如时间格式化、UUID缩写、客户端IP地址获取、数据结构处理和随机字符串生成等。
(This module contains auxiliary functions that may be reused in multiple places
in the project, such as time formatting, UUID abbreviation, client IP address
acquisition, data structure processing, and random string generation.)
"""

# region 模块导入 (Module Imports)
import datetime
import ipaddress  # 用于处理和验证IP地址 (For processing and validating IP addresses)
import logging
import random
import secrets  # 用于生成安全的随机数 (For generating cryptographically strong random numbers)
from typing import Any, Dict, List, Optional, Tuple, Union  # 类型提示 (Type hinting)
from uuid import UUID  # 用于类型提示 (For type hinting)

from fastapi import (
    Request,
)  # Request 对象用于获取客户端IP和请求头 (Request object for client IP and headers)

# endregion

# region 全局变量与初始化 (Global Variables & Initialization)
# 获取本模块的logger实例 (Get logger instance for this module)
_helpers_logger = logging.getLogger(__name__)
# endregion

# region 时间与UUID格式化工具 (Time & UUID Formatting Utilities)


def get_current_timestamp_str() -> str:
    """
    获取当前时间的格式化字符串。
    (Get a formatted string of the current time.)

    返回 (Returns):
        str: 格式为 "YYYY-MM-DD HH:MM:SS" 的当前时间字符串。
             (Current time string in "YYYY-MM-DD HH:MM:SS" format.)
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_short_uuid(uuid_obj: Union[UUID, str]) -> str:
    """
    将UUID对象或字符串格式化为 "前四位....后四位" 的缩写形式，便于日志查看。
    (Formats a UUID object or string into an abbreviated form "first_four....last_four"
     for easier log viewing.)

    参数 (Args):
        uuid_obj (Union[UUID, str]): UUID对象或其字符串表示。
                                     (UUID object or its string representation.)

    返回 (Returns):
        str: 格式化后的UUID字符串，如果输入字符串长度不足则返回原样。
             (Formatted UUID string, or the original string if it's too short.)
    """
    s = str(uuid_obj)
    if (
        len(s) > 8
    ):  # 确保UUID字符串足够长以进行缩写 (Ensure UUID string is long enough for abbreviation)
        return f"{s[:4]}....{s[-4:]}"
    return s


# endregion

# region IP地址获取工具 (IP Address Acquisition Utilities)


def get_client_ip_from_request(
    request: Request,
    cloudflare_ipv4_cidrs: Optional[List[ipaddress.IPv4Network]] = None,
    cloudflare_ipv6_cidrs: Optional[List[ipaddress.IPv6Network]] = None,
) -> str:
    """
    从FastAPI的Request对象中获取客户端的真实IP地址。
    如果请求疑似来自Cloudflare（基于传入的CIDR列表），则优先信任CF相关请求头。
    否则，使用直接连接的IP地址。

    (Gets the client's real IP address from FastAPI's Request object.
    If the request appears to be from Cloudflare (based on the provided CIDR lists),
    CF-related headers are trusted preferentially. Otherwise, the direct connecting IP is used.)

    参数 (Args):
        request (Request): FastAPI的Request对象。 (FastAPI Request object.)
        cloudflare_ipv4_cidrs (Optional[List[ipaddress.IPv4Network]]):
            (可选) Cloudflare的IPv4 CIDR范围列表。
            ((Optional) List of Cloudflare's IPv4 CIDR ranges.)
        cloudflare_ipv6_cidrs (Optional[List[ipaddress.IPv6Network]]):
            (可选) Cloudflare的IPv6 CIDR范围列表。
            ((Optional) List of Cloudflare's IPv6 CIDR ranges.)

    返回 (Returns):
        str: 识别出的客户端IP地址字符串，如果无法确定则为 "Unknown"。
             (Identified client IP address string, or "Unknown" if it cannot be determined.)
    """
    direct_connecting_ip_str: Optional[str] = None
    if request.client and request.client.host:
        direct_connecting_ip_str = request.client.host  # 直接连接的客户端IP

    if not direct_connecting_ip_str:
        _helpers_logger.warning(
            "无法从 request.client.host 获取直接连接IP。尝试从请求头获取。"
        )
        # 尝试从常见的反向代理头部获取，但这些头部容易被伪造，需谨慎使用
        # (Attempt to get from common reverse proxy headers, but use with caution as they can be spoofed)
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            _helpers_logger.debug(
                f"request.client.host 为空, 尝试使用 X-Real-IP: {x_real_ip}"
            )
            direct_connecting_ip_str = x_real_ip
        else:
            x_forwarded_for = request.headers.get("x-forwarded-for")
            if x_forwarded_for:
                # X-Forwarded-For 可能包含多个IP，取最左边的（通常是原始客户端）
                # (X-Forwarded-For may contain multiple IPs, take the leftmost one (usually original client))
                first_ip = x_forwarded_for.split(",")[0].strip()
                _helpers_logger.debug(
                    f"request.client.host 为空, 尝试使用 X-Forwarded-For 的第一个IP: {first_ip}"
                )
                direct_connecting_ip_str = first_ip

        if not direct_connecting_ip_str:
            _helpers_logger.error("无法确定直接连接的IP地址，所有尝试均失败。")
            return "Unknown"  # 确实无法获取任何IP信息 (Truly unable to get any IP info)

    try:
        # 尝试将获取到的直接连接IP转换为ipaddress对象以进行验证和比较
        # (Try to convert the obtained direct IP to an ipaddress object for validation and comparison)
        direct_connecting_ip_obj = ipaddress.ip_address(direct_connecting_ip_str)
    except ValueError:
        _helpers_logger.warning(
            f"直接连接的IP字符串 '{direct_connecting_ip_str}' 不是有效的IP地址格式。"
            f"将直接使用此字符串作为IP，但可能不准确。"
        )
        return direct_connecting_ip_str  # 返回原始字符串，因为它无法被验证为标准IP

    # 检查直接连接IP是否在已知的Cloudflare范围内
    # (Check if the direct connecting IP is within known Cloudflare ranges)
    is_from_cloudflare = False
    if cloudflare_ipv4_cidrs and direct_connecting_ip_obj.version == 4:
        is_from_cloudflare = any(
            direct_connecting_ip_obj in network for network in cloudflare_ipv4_cidrs
        )
    elif cloudflare_ipv6_cidrs and direct_connecting_ip_obj.version == 6:
        is_from_cloudflare = any(
            direct_connecting_ip_obj in network for network in cloudflare_ipv6_cidrs
        )

    if is_from_cloudflare:
        _helpers_logger.debug(
            f"连接来自已知的Cloudflare IP: {direct_connecting_ip_str}。"
            f"尝试从Cloudflare特定请求头获取真实客户端IP。"
        )
        # 如果连接来自Cloudflare，则信任Cloudflare设置的请求头
        # (If connection is from Cloudflare, trust Cloudflare-set headers)
        cf_ip_header = request.headers.get("cf-connecting-ip")
        if cf_ip_header:
            try:
                ipaddress.ip_address(
                    cf_ip_header
                )  # 验证是否是有效IP格式 (Validate if it's a valid IP format)
                _helpers_logger.debug(f"从 'CF-Connecting-IP' 获取到IP: {cf_ip_header}")
                return cf_ip_header
            except ValueError:
                _helpers_logger.warning(
                    f"'CF-Connecting-IP' 请求头的值 '{cf_ip_header}' 不是一个有效的IP地址。"
                )

        x_forwarded_for_header = request.headers.get("x-forwarded-for")
        if x_forwarded_for_header:
            real_ip_from_xff = x_forwarded_for_header.split(",")[0].strip()
            try:
                ipaddress.ip_address(real_ip_from_xff)  # 验证 (Validate)
                _helpers_logger.debug(
                    f"从 'X-Forwarded-For' 获取到IP: {real_ip_from_xff} (原始XFF: '{x_forwarded_for_header}')"
                )
                return real_ip_from_xff
            except ValueError:
                _helpers_logger.warning(
                    f"'X-Forwarded-For' 请求头的第一个IP值 '{real_ip_from_xff}' 不是一个有效的IP地址。"
                )

        _helpers_logger.warning(
            f"连接来自Cloudflare IP {direct_connecting_ip_str}，"
            f"但未找到有效的 'CF-Connecting-IP' 或 'X-Forwarded-For' 请求头。"
            f"将使用Cloudflare的连接IP作为客户端IP（这可能不是最终用户IP）。"
        )
        return direct_connecting_ip_str  # 最后手段：返回CF的连接IP (Last resort: return CF's connecting IP)
    else:
        # 如果连接不是来自已知的Cloudflare IP范围，则不信任任何代理头部，直接使用 request.client.host
        # (If not from Cloudflare, don't trust proxy headers, use request.client.host directly)
        _helpers_logger.debug(
            f"连接来自非Cloudflare IP: {direct_connecting_ip_str}。"
            f"将使用此直接连接IP作为客户端IP。"
        )
        return direct_connecting_ip_str


# endregion

# region 数据结构与随机生成工具 (Data Structure & Random Generation Utilities)


def shuffle_dictionary_items(input_dict: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    创建一个新字典，其条目的插入顺序是随机的。
    依赖 Python 3.7+ 版本中字典顺序即插入顺序的行为。

    (Creates a new dictionary whose items have a random insertion order.
    Relies on the behavior of Python 3.7+ where dictionary order is insertion order.)

    参数 (Args):
        input_dict (Dict[Any, Any]): 需要打乱条目顺序的输入字典。
                                     (Input dictionary whose items need to be shuffled.)

    返回 (Returns):
        Dict[Any, Any]: 一个新字典，包含与 input_dict 相同的条目，但顺序是随机的。
                        (A new dictionary with the same items as input_dict, but in random order.)

    异常 (Raises):
        TypeError: 如果输入不是一个字典。 (If the input is not a dictionary.)
    """
    if not isinstance(input_dict, dict):
        _helpers_logger.error("shuffle_dictionary_items 的输入不是字典类型。")
        raise TypeError("输入必须是一个字典。 (Input must be a dictionary.)")

    items_list: List[Tuple[Any, Any]] = list(input_dict.items())
    random.shuffle(items_list)  # 原地打乱列表顺序 (Shuffle list in-place)
    return dict(
        items_list
    )  # 从打乱后的列表创建新字典 (Create new dict from shuffled list)


def generate_random_hex_string_of_bytes(length_bytes: int) -> str:
    """
    生成指定字节长度的随机小写十六进制字符串。
    最终的十六进制字符串长度将是 length_bytes 的两倍。

    (Generates a random lowercase hexadecimal string of a specified byte length.
    The final hexadecimal string length will be twice length_bytes.)

    参数 (Args):
        length_bytes (int): 期望生成的随机字节的数量。
                            (Number of random bytes to generate.)

    返回 (Returns):
        str: 一个随机的小写十六进制字符串。
             (A random lowercase hexadecimal string.)

    异常 (Raises):
        ValueError: 如果 length_bytes 小于1。 (If length_bytes is less than 1.)
    """
    if length_bytes < 1:
        _helpers_logger.error(
            f"generate_random_hex_string_of_bytes 的字节长度太小: {length_bytes}"
        )
        raise ValueError("字节长度必须至少为1。 (Byte length must be at least 1.)")

    random_bytes: bytes = secrets.token_bytes(
        length_bytes
    )  # 生成安全的随机字节 (Generate secure random bytes)
    return (
        random_bytes.hex()
    )  # 将字节转换为小写十六进制字符串 (Convert bytes to lowercase hex string)


# endregion


__all__ = [
    "get_current_timestamp_str",
    "format_short_uuid",
    "get_client_ip_from_request",
    "shuffle_dictionary_items",
    "generate_random_hex_string_of_bytes",
]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行。它定义了一系列工具函数，应由其他模块导入和使用。
    # (This module should not be executed as the main script. It defines utility functions
    #  that should be imported and used by other modules.)
    _helpers_logger.info(
        f"模块 {__name__} 定义了通用工具函数，不应直接执行。它应被其他模块导入。"
    )
    print(f"模块 {__name__} 定义了通用工具函数，不应直接执行。它应被其他模块导入。")
