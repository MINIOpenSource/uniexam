# -*- coding: utf-8 -*-
# region 模块导入
import datetime
import random
import secrets
from typing import Any, Dict, List, Tuple, Union, Optional # 确保导入了 Optional
from uuid import UUID # 用于类型提示

from fastapi import Request # Request 对象用于获取客户端IP和请求头
import ipaddress # 用于处理和验证IP地址
import logging

# 从应用的配置模块导入 Cloudflare IP 范围（如果需要在此处直接访问）
# 更好的做法可能是将 Cloudflare IP 列表作为参数传递给 get_client_ip，
# 或者 get_client_ip 内部依赖一个全局的 Cloudflare IP 管理器。
# 为保持此模块的通用性，暂时不直接导入全局的 cloudflare_ipv4_ranges。
# get_client_ip_from_request 将接收这些范围作为参数。
# from ..core.config import settings # 避免循环导入，config可能也需要utils

# endregion

# region 全局变量与初始化
# 获取本模块的logger实例
_helpers_logger = logging.getLogger(__name__)
# endregion

# region 时间与UUID格式化工具

def get_current_timestamp_str() -> str:
    """
    获取当前时间的格式化字符串。

    返回:
        格式为 "YYYY-MM-DD HH:MM:SS" 的当前时间字符串。
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def format_short_uuid(uuid_obj: Union[UUID, str]) -> str:
    """
    将UUID对象或字符串格式化为 "前四位....后四位" 的缩写形式，便于日志查看。

    参数:
        uuid_obj: UUID对象或其字符串表示。

    返回:
        格式化后的UUID字符串，如果输入字符串长度不足则返回原样。
    """
    s = str(uuid_obj)
    if len(s) > 8: # 确保UUID字符串足够长以进行缩写
        return f"{s[:4]}....{s[-4:]}"
    return s
# endregion

# region IP地址获取工具

def get_client_ip_from_request(
    request: Request,
    cloudflare_ipv4_cidrs: Optional[List[ipaddress.IPv4Network]] = None,
    cloudflare_ipv6_cidrs: Optional[List[ipaddress.IPv6Network]] = None
) -> str:
    """
    从FastAPI的Request对象中获取客户端的真实IP地址。
    如果请求疑似来自Cloudflare（基于传入的CIDR列表），则优先信任CF相关请求头。
    否则，使用直接连接的IP地址。

    参数:
        request: FastAPI的Request对象。
        cloudflare_ipv4_cidrs: (可选) Cloudflare的IPv4 CIDR范围列表。
        cloudflare_ipv6_cidrs: (可选) Cloudflare的IPv6 CIDR范围列表。

    返回:
        识别出的客户端IP地址字符串，如果无法确定则为 "Unknown"。
    """
    direct_connecting_ip_str: Optional[str] = None
    if request.client and request.client.host:
        direct_connecting_ip_str = request.client.host
    
    if not direct_connecting_ip_str:
        _helpers_logger.warning("无法从 request.client.host 获取直接连接IP。")
        # 尝试从常见的反向代理头部获取，但这些头部容易被伪造，需谨慎使用
        # 仅作为 request.client.host 不可用时的备选方案
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            _helpers_logger.debug(f"request.client.host 为空, 尝试使用 X-Real-IP: {x_real_ip}")
            direct_connecting_ip_str = x_real_ip
        else:
            x_forwarded_for = request.headers.get("x-forwarded-for")
            if x_forwarded_for:
                # X-Forwarded-For 可能包含多个IP，取最左边的（通常是原始客户端）
                first_ip = x_forwarded_for.split(",")[0].strip()
                _helpers_logger.debug(f"request.client.host 为空, 尝试使用 X-Forwarded-For 的第一个IP: {first_ip}")
                direct_connecting_ip_str = first_ip
        
        if not direct_connecting_ip_str:
            _helpers_logger.error("无法确定直接连接的IP地址。")
            return "Unknown" # 确实无法获取任何IP信息

    try:
        # 尝试将获取到的直接连接IP转换为ipaddress对象以进行验证和比较
        direct_connecting_ip_obj = ipaddress.ip_address(direct_connecting_ip_str)
    except ValueError:
        # 如果转换失败，说明获取到的可能不是一个有效的IP地址字符串
        _helpers_logger.warning(
            f"直接连接的IP字符串 '{direct_connecting_ip_str}' 不是有效的IP地址格式。"
            f"将直接使用此字符串作为IP，但可能不准确。"
        )
        # 在这种情况下，我们可能不应该信任代理头部，因为我们无法验证连接来源
        return direct_connecting_ip_str

    # 检查直接连接IP是否在已知的Cloudflare范围内
    is_from_cloudflare = False
    if cloudflare_ipv4_cidrs and direct_connecting_ip_obj.version == 4:
        is_from_cloudflare = any(direct_connecting_ip_obj in network for network in cloudflare_ipv4_cidrs)
    elif cloudflare_ipv6_cidrs and direct_connecting_ip_obj.version == 6:
        is_from_cloudflare = any(direct_connecting_ip_obj in network for network in cloudflare_ipv6_cidrs)
    
    if is_from_cloudflare:
        _helpers_logger.debug(
            f"连接来自已知的Cloudflare IP: {direct_connecting_ip_str}。"
            f"尝试从请求头获取真实客户端IP。"
        )
        # 如果连接来自Cloudflare，则信任Cloudflare设置的请求头
        cf_ip_header = request.headers.get("cf-connecting-ip")
        if cf_ip_header:
            try:
                ipaddress.ip_address(cf_ip_header) # 验证是否是有效IP格式
                _helpers_logger.debug(f"从 'CF-Connecting-IP' 获取到IP: {cf_ip_header}")
                return cf_ip_header
            except ValueError:
                _helpers_logger.warning(
                    f"'CF-Connecting-IP' 请求头的值 '{cf_ip_header}' "
                    f"不是一个有效的IP地址。"
                )

        # 如果没有 cf-connecting-ip，尝试 x-forwarded-for
        # 注意：当连接本身来自Cloudflare时，X-Forwarded-For也可能被Cloudflare设置或传递
        x_forwarded_for_header = request.headers.get("x-forwarded-for")
        if x_forwarded_for_header:
            # 取X-Forwarded-For列表中的第一个IP地址
            real_ip_from_xff = x_forwarded_for_header.split(",")[0].strip()
            try:
                ipaddress.ip_address(real_ip_from_xff) # 验证
                _helpers_logger.debug(
                    f"从 'X-Forwarded-For' 获取到IP: {real_ip_from_xff} "
                    f"(原始XFF: '{x_forwarded_for_header}')"
                )
                return real_ip_from_xff
            except ValueError:
                _helpers_logger.warning(
                    f"'X-Forwarded-For' 请求头的第一个IP值 '{real_ip_from_xff}' "
                    f"不是一个有效的IP地址。"
                )
        
        # 如果上述头部都无效或不存在，但连接确实来自Cloudflare IP
        _helpers_logger.warning(
            f"连接来自Cloudflare IP {direct_connecting_ip_str}，"
            f"但未找到有效的 'CF-Connecting-IP' 或 'X-Forwarded-For' 请求头。"
            f"将使用Cloudflare的连接IP作为客户端IP（这可能不是最终用户IP）。"
        )
        return direct_connecting_ip_str # 返回Cloudflare的连接IP作为最后的手段
    else:
        # 如果连接不是来自已知的Cloudflare IP范围，则不信任任何代理头部，
        # 直接使用 request.client.host (即 direct_connecting_ip_str)。
        # 这有助于处理本地反向代理（如Nginx/OpenResty）的情况，
        # 除非该本地代理被配置为安全地处理和传递真实IP（例如，通过设置X-Real-IP）。
        _helpers_logger.debug(
            f"连接来自非Cloudflare IP: {direct_connecting_ip_str}。"
            f"将使用此直接连接IP作为客户端IP。"
        )
        return direct_connecting_ip_str
# endregion

# region 数据结构与随机生成工具

def shuffle_dictionary_items(input_dict: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    创建一个新字典，其条目的插入顺序是随机的。
    依赖 Python 3.7+ 版本中字典顺序即插入顺序的行为。

    参数:
        input_dict: 需要打乱条目顺序的输入字典。

    返回:
        一个新字典，包含与 input_dict 相同的条目，但顺序是随机的。

    异常:
        TypeError: 如果输入不是一个字典。
    """
    if not isinstance(input_dict, dict):
        raise TypeError("输入必须是一个字典。")
    
    items_list: List[Tuple[Any, Any]] = list(input_dict.items())
    random.shuffle(items_list)  # 原地打乱列表顺序
    return dict(items_list)  # 从打乱后的列表创建新字典

def generate_random_hex_string_of_bytes(length_bytes: int) -> str:
    """
    生成指定字节长度的随机小写十六进制字符串。
    最终的十六进制字符串长度将是 length_bytes 的两倍。

    参数:
        length_bytes: 期望生成的随机字节的数量。

    返回:
        一个随机的小写十六进制字符串。

    异常:
        ValueError: 如果 length_bytes 小于1。
    """
    if length_bytes < 1:
        # 通常Token或ID至少需要几个字节
        raise ValueError("字节长度必须至少为1。")
    
    random_bytes: bytes = secrets.token_bytes(length_bytes)  # 生成安全的随机字节
    return random_bytes.hex()  # 将字节转换为小写十六进制字符串
# endregion
