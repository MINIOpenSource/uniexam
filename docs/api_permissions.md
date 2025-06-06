# API 端点权限需求

本文档定义了在线考试系统中各个API端点所需的最低用户权限级别。权限基于 `app.models.user_models.UserTag` 枚举中定义的标签。

## 权限说明

-   **(公开)**: 此类接口无需任何认证即可访问。
-   **(认证用户)**: 访问此类接口需要一个有效的用户Token，但对用户标签无特定要求（除了用户不能是被封禁状态，该检查已内置于Token验证逻辑中，例如通过 `Depends(get_current_active_user_uid)` 实现）。
-   **USER标签**: （此文档中特指）通过 `Depends(get_current_active_user_uid)` 隐式要求。由于新用户默认被赋予 `UserTag.USER` 标签，并且该依赖确保了用户是活跃且未被封禁的认证用户，因此这些接口实际上对拥有 `USER` 标签的普通用户开放。
-   **ADMIN标签**: 用户必须明确拥有 `UserTag.ADMIN` 标签。通过 `Depends(RequireTags({UserTag.ADMIN}))` 强制实现，此依赖也包含了基础的Token认证和用户有效性检查。

## API权限列表

| HTTP方法 | URL路径                                     | 功能描述                     | 所需最低权限/UserTag(s)             |
| :------- | :------------------------------------------ | :--------------------------- | :---------------------------------- |
| **app/main.py (用户 & 公共 APIs)**      |                                             |                              |                                     |
| POST     | `/auth/signin`                              | 用户注册                     | (公开)                              |
| POST     | `/auth/login`                               | 用户登录                     | (公开)                              |
| GET      | `/auth/login`                               | 刷新Token                    | (认证用户) - 依赖旧Token有效性      |
| GET      | `/users/me`                                 | 获取当前用户信息             | 认证用户 (默认拥有USER标签)         |
| PUT      | `/users/me`                                 | 更新当前用户信息             | 认证用户 (默认拥有USER标签)         |
| PUT      | `/users/me/password`                        | 修改当前用户密码             | 认证用户 (默认拥有USER标签)         |
| GET      | `/get_exam`                                 | 请求新试卷                   | 认证用户 (默认拥有USER标签)         |
| POST     | `/update`                                   | 更新答题进度                 | 认证用户 (默认拥有USER标签)         |
| POST     | `/finish`                                   | 提交试卷以供批改             | 认证用户 (默认拥有USER标签)         |
| GET      | `/history`                                  | 获取用户答题历史             | 认证用户 (默认拥有USER标签)         |
| GET      | `/history_paper`                            | 获取指定历史试卷详情         | 认证用户 (默认拥有USER标签)         |
| GET      | `/difficulties`                             | 获取可用题库难度列表         | (公开)                              |
| GET      | `/users/directory`                          | 获取公开用户目录             | (公开)                              |
| **app/admin_routes.py (Admin APIs)**    |                                             |                              |                                     |
| GET      | `/admin/settings`                           | 获取当前系统配置             | ADMIN                               |
| POST     | `/admin/settings`                           | 更新系统配置                 | ADMIN                               |
| GET      | `/admin/users`                              | 管理员获取用户列表           | ADMIN                               |
| GET      | `/admin/users/{user_uid}`                   | 管理员获取特定用户信息       | ADMIN                               |
| PUT      | `/admin/users/{user_uid}`                   | 管理员更新特定用户信息       | ADMIN                               |
| GET      | `/admin/papers`                             | 管理员获取所有试卷摘要列表   | ADMIN                               |
| GET      | `/admin/papers/{paper_id}`                  | 管理员获取特定试卷的完整信息 | ADMIN                               |
| DELETE   | `/admin/papers/{paper_id}`                  | 管理员删除特定试卷           | ADMIN                               |
| GET      | `/admin/question-banks`                     | 管理员获取所有题库的元数据列表 | ADMIN                               |
| GET      | `/admin/question-banks/{difficulty_id}/content` | 管理员获取特定题库的完整内容 | ADMIN                               |
| POST     | `/admin/question-banks/{difficulty_id}/questions` | 管理员向特定题库添加新题目   | ADMIN                               |
| DELETE   | `/admin/question-banks/{difficulty_id}/questions` | 管理员从特定题库删除题目     | ADMIN                               |
| **app/admin_routes.py (Grading APIs)**  |                                             |                              |                                     |
| GET      | `/admin/grading/pending-papers`             | 获取待人工批阅的试卷列表     | ADMIN (未来可考虑GRADER)            |
| GET      | `/admin/grading/papers/{paper_id}/subjective-questions` | 获取试卷中待批阅主观题详情 | ADMIN (未来可考虑GRADER)            |
| POST     | `/admin/grading/papers/{paper_id}/questions/{question_internal_id}/grade` | 提交单个主观题的批阅结果   | ADMIN (未来可考虑GRADER)            |

## 关于 `RequireTags` 依赖项

`app/core/security.py` 中的 `RequireTags` 类用于实现基于标签的权限控制。其实例化时接收一个必需标签的集合 (e.g., `RequireTags({UserTag.ADMIN})`)。
在API端点中使用此依赖项时，它首先会通过依赖 `get_current_user_info_from_token` 确保用户已通过Token认证且账户有效（未被封禁）。然后，它会检查用户是否拥有**所有**在依赖项实例化时指定的标签。如果用户认证失败或缺少任何一个必需标签，则会返回相应的HTTP 401或403错误。
这种“拥有所有指定标签”的逻辑是当前权限系统的基础。

## 未来权限标签的初步考虑

以下标签已在 `UserTag` 枚举中定义，可用于未来更细致的权限划分：

-   **`UserTag.GRADER` (阅卷员)**：
    -   未来可能用于访问专门的阅卷接口，例如对主观题进行打分、查看待批阅试卷列表等。
    -   权限级别可能需要与 `ADMIN` 结合（如 `RequireTags({UserTag.ADMIN, UserTag.GRADER})`）或独立存在 (`RequireTags({UserTag.GRADER})`)。
-   **`UserTag.EXAMINER` (出题人/题库管理员)**：
    -   可能用于对题库内容进行更细致的管理，例如仅允许其修改特定学科或难度的题库，或审核用户提交的题目。
    -   可能与 `ADMIN` 权限部分重叠或作为其子集。
-   **`UserTag.MANAGER` (运营管理员)**：
    -   可能拥有部分管理权限，如用户管理（不包括修改管理员账户）、查看统计数据、管理公告等，但不涉及核心系统配置或题库内容的修改。

当前的权限设计主要侧重于区分公共访问、普通认证用户 (隐式拥有 `USER` 标签) 和完全管理员 (`ADMIN`)。未来在实现新功能时，可以利用上述额外标签并结合 `RequireTags` 或创建新的自定义依赖项来实现更复杂的权限逻辑。
[end of docs/api_permissions.md]
