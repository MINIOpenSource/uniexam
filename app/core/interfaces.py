# -*- coding: utf-8 -*-
"""
数据存储库接口模块。

此模块定义了数据存储库的抽象基类 (ABC)，为应用提供了一个统一的数据访问接口。
通过实现此接口，可以支持多种不同的后端存储（例如 JSON 文件、SQL 数据库、NoSQL 数据库等），
使得上层业务逻辑与具体的存储实现解耦。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class IDataStorageRepository(ABC):
    """
    通用数据存储库的抽象基类 (ABC)。
    定义了通用的 CRUD (创建、读取、更新、删除) 操作接口，
    允许应用与不同的存储后端（如JSON文件、SQL数据库、NoSQL数据库）进行交互。
    """

    @abstractmethod
    async def connect(self) -> None:
        """
        建立与数据存储的连接（如果适用）。
        例如，对于数据库，这可能意味着创建连接池。
        对于基于文件的存储，此方法可能为空操作。
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        关闭与数据存储的连接（如果适用）。
        例如，释放数据库连接池。
        对于基于文件的存储，此方法可能为空操作。
        """
        pass

    @abstractmethod
    async def get_by_id(
        self, entity_type: str, entity_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        根据ID检索单个实体。

        参数:
            entity_type (str): 实体的类型 (例如, 'user', 'paper')。
            entity_id (str): 实体的唯一标识符。

        返回:
            Optional[Dict[str, Any]]: 代表实体的字典，如果未找到则返回 None。
        """
        pass

    @abstractmethod
    async def get_all(
        self, entity_type: str, skip: int = 0, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        检索指定类型的所有实体，支持可选的分页。

        参数:
            entity_type (str): 实体类型。
            skip (int): 跳过的记录数 (用于分页)。
            limit (int): 返回的最大记录数 (用于分页)。

        返回:
            List[Dict[str, Any]]: 一个字典列表，每个字典代表一个实体。
        """
        pass

    @abstractmethod
    async def create(
        self, entity_type: str, entity_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建一个新的实体。

        参数:
            entity_type (str): 实体类型。
            entity_data (Dict[str, Any]): 包含实体数据的字典。
                                         假设此数据包含唯一ID，或者存储库负责在适当时生成ID。
        返回:
            Dict[str, Any]: 创建的实体（作为字典）。
        """
        pass

    @abstractmethod
    async def update(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        根据ID更新现有实体。

        参数:
            entity_type (str): 实体类型。
            entity_id (str): 要更新的实体的ID。
            update_data (Dict[str, Any]): 包含要更新字段的字典。

        返回:
            Optional[Dict[str, Any]]: 更新后的实体（作为字典），如果未找到实体则返回 None。
        """
        pass

    @abstractmethod
    async def delete(self, entity_type: str, entity_id: str) -> bool:
        """
        根据ID删除实体。

        参数:
            entity_type (str): 实体类型。
            entity_id (str): 要删除的实体的ID。

        返回:
            bool: 如果删除成功则返回 True，否则返回 False。
        """
        pass

    @abstractmethod
    async def query(
        self,
        entity_type: str,
        conditions: Dict[str, Any],
        skip: int = 0,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        根据一组条件查询实体。

        参数:
            entity_type (str): 实体类型。
            conditions (Dict[str, Any]): 一个字典，其中键是字段名，值是要匹配的值（目前为精确匹配）。
            skip (int): 跳过的记录数。
            limit (int): 返回的最大记录数。

        返回:
            List[Dict[str, Any]]: 匹配的实体列表。
        """
        pass

    @abstractmethod
    async def init_storage_if_needed(
        self, entity_type: str, initial_data: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        确保给定实体类型的存储已初始化。
        如果存储（例如JSON文件或数据库表）不存在，则可能会创建它。
        可选地，如果存储为空或新创建，可以使用 `initial_data` 填充初始数据。

        参数:
            entity_type (str): 实体类型 (例如, 'user', 'paper')。
            initial_data (Optional[List[Dict[str, Any]]]): 用于在存储为空时填充的初始数据列表 (可选)。
        """
        pass

    @abstractmethod
    async def get_all_entity_types(self) -> List[str]:
        """
        返回此存储库管理的所有实体类型的列表。
        具体的实现可能依赖于配置或动态发现。
        """
        pass

    @abstractmethod
    async def persist_all_data(self) -> None:
        """
        将所有内存中的数据（针对所有实体类型）持久化到后端存储。
        此方法对于基于文件的存储库尤其重要，以确保在应用程序关闭前数据被写入。
        对于某些数据库（如启用了autocommit的SQL数据库或Redis），此方法可能为空操作。
        """
        pass


__all__ = ["IDataStorageRepository"]

if __name__ == "__main__":
    # 此模块不应作为主脚本执行
    print(f"此模块 ({__name__}) 定义了接口，不应直接执行。")
