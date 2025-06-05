# 管理员接口 (Admin API)

本文档描述了仅供管理员使用的API端点。所有这些端点都需要有效的管理员Token进行认证，并且通常以 `/admin` 作为路径前缀。

## 1. 系统配置管理 (System Configuration Management)

基础路径: `/admin/settings` (Base Path: `/admin/settings`)

这些端点允许管理员查看和修改应用的核心配置。

### 1.1 获取当前系统配置

-   **路径 (Path)**: `/settings`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 获取当前系统配置
-   **描述 (Description)**: 管理员获取当前应用的主要配置项信息。注意：此接口返回的配置主要反映 `settings.json` 文件的内容，可能不完全包含通过环境变量最终生效的配置值。敏感信息（如数据库密码）不会在此接口返回。
-   **认证 (Authentication)**: 需要管理员权限 (Admin privileges required)。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取配置信息。返回 `SettingsResponseModel`。
        ```json
        // SettingsResponseModel 示例 (仅展示部分字段)
        {
            "app_name": "在线考试系统",
            "token_expiry_hours": 24,
            "log_level": "INFO",
            "rate_limits": {
                "default_user": {"get_exam": {"limit": 3, "window": 120}, "auth_attempts": {"limit": 5, "window": 60}},
                "limited_user": {"get_exam": {"limit": 1, "window": 300}, "auth_attempts": {"limit": 2, "window": 300}}
            }
            // ... 其他配置项
        }
        ```
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员或无权访问。
    -   **`500 Internal Server Error`**: 服务器内部错误导致无法获取配置。响应体: `{"detail": "服务器内部错误导致无法获取配置"}`

### 1.2 更新系统配置

-   **路径 (Path)**: `/settings`
-   **方法 (Method)**: `POST` (注意：虽然`PUT`通常用于完整替换，但此接口接受部分更新，行为更接近`PATCH`，但使用`POST`以简化)
-   **摘要 (Summary)**: 更新系统配置
-   **描述 (Description)**: 管理员更新应用的部分或全部可配置项。请求体中仅需包含需要修改的字段及其新值。更新操作会写入 `settings.json` 文件并尝试动态重新加载配置到应用内存。注意：通过环境变量设置的配置项具有最高优先级，其在内存中的值不会被此API调用修改，但 `settings.json` 文件中的对应值会被更新。
-   **认证 (Authentication)**: 需要管理员权限 (Admin privileges required)。
-   **请求体 (Request Body)**: `application/json`, `SettingsUpdatePayload` 模型
    ```json
    // SettingsUpdatePayload 示例 (仅更新部分字段)
    {
        "app_name": "新版在线考试平台",
        "token_expiry_hours": 48,
        "log_level": "DEBUG"
    }
    ```
-   **响应 (Responses)**:
    -   **`200 OK`**: 配置成功更新并已重新加载，返回更新后的配置状态。返回 `SettingsResponseModel`。
    -   **`400 Bad Request`**: 提供的配置数据无效或不符合约束。响应体: `{"detail": "具体错误信息"}`
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员或无权访问。
    -   **`422 Unprocessable Entity`**: 请求体验证失败 (FastAPI自动处理)。
    -   **`500 Internal Server Error`**: 配置文件写入失败或更新时发生未知服务器错误。响应体: `{"detail": "具体错误信息"}`

---

## 2. 用户账户管理 (User Account Management)

基础路径: `/admin/users` (Base Path: `/admin/users`)

这些端点允许管理员管理用户账户。

### 2.1 管理员获取用户列表

-   **路径 (Path)**: `/users`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 管理员获取用户列表
-   **描述 (Description)**: 获取系统中的用户账户列表，支持分页查询。返回的用户信息不包含敏感数据（如哈希密码）。
-   **认证 (Authentication)**: 需要管理员权限。
-   **请求参数 (Query Parameters)**:
    -   `skip` (integer, 可选, 默认: 0): 跳过的记录数，用于分页。
    -   `limit` (integer, 可选, 默认: 100, 最大: 200): 返回的最大记录数。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取用户列表。返回 `List[UserPublicProfile]`。
        ```json
        // List[UserPublicProfile] 示例
        [
            {
                "uid": "user1",
                "nickname": "用户一",
                "email": "user1@example.com",
                "qq": "10001",
                "tags": ["user"]
            },
            {
                "uid": "adminuser",
                "nickname": "管理员账户",
                "email": "admin@example.com",
                "qq": null,
                "tags": ["admin", "user"]
            }
        ]
        ```
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`500 Internal Server Error`**: 获取用户列表时发生服务器内部错误。响应体: `{"detail": "获取用户列表时发生服务器内部错误"}`

### 2.2 管理员获取特定用户信息

-   **路径 (Path)**: `/users/{user_uid}`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 管理员获取特定用户信息
-   **描述 (Description)**: 根据用户UID（用户名）获取其公开的详细信息，不包括密码等敏感内容。
-   **认证 (Authentication)**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `user_uid` (string, 必需): 要获取详情的用户的UID。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取用户信息。返回 `UserPublicProfile` 模型。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定UID的用户未找到。响应体: `{"detail": "用户未找到"}`

### 2.3 管理员更新特定用户信息

-   **路径 (Path)**: `/users/{user_uid}`
-   **方法 (Method)**: `PUT`
-   **摘要 (Summary)**: 管理员更新特定用户信息
-   **描述 (Description)**: 管理员修改用户的昵称、邮箱、QQ、用户标签，或为其重置密码。请求体中仅需包含需要修改的字段。
-   **认证 (Authentication)**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `user_uid` (string, 必需): 要更新信息的用户的UID。
-   **请求体 (Request Body)**: `application/json`, `AdminUserUpdate` 模型
    ```json
    // AdminUserUpdate 模型示例 (仅更新部分字段)
    {
        "nickname": "更新后的昵称",
        "tags": ["user", "limited"],
        "new_password": "a_new_strong_password"
    }
    ```
-   **响应 (Responses)**:
    -   **`200 OK`**: 用户信息成功更新。返回更新后的 `UserPublicProfile` 模型。
    -   **`400 Bad Request`**: 提供的更新数据无效（例如，无效的标签值）。响应体: `{"detail": "具体错误信息"}`
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定UID的用户未找到。响应体: `{"detail": "用户未找到或更新失败。"}`
    -   **`422 Unprocessable Entity`**: 请求体验证失败 (FastAPI自动处理)。

---
<!-- 后续将添加试卷管理、题库管理API的文档 -->
