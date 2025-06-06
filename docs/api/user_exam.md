---
title: 用户、认证、核心考试及公共API
---

本文档详细描述了与普通用户操作相关的API端点，包括用户认证、个人资料管理、核心的考试答题流程以及一些公开查询的接口。所有路径相对于应用根路径。

## 1. 用户认证 API (User Authentication API)

基础路径: `/auth`

### 1.1 用户注册 (`POST /signin`)

-   **摘要**: 用户注册
-   **描述**: 新用户通过提供用户名、密码等信息进行注册。成功后返回访问令牌。
-   **认证**: 无需。
-   **速率限制**: 应用标准认证尝试速率限制。
-   **请求体** (`application/json`): `UserCreationPayload` 模型
    ```json
    // UserCreationPayload 模型示例
    {
        "uid": "yonghu001",
        "password": "Mima123!@#",
        "nickname": "入门新手",
        "email": "user@example.com",
        "qq": "10000"
    }
    ```
-   **响应**:
    -   **`201 Created`**: 注册成功。返回 `TokenResponse` 模型。
        ```json
        // TokenResponse 模型示例
        {
            "access_token": "eyJhbGciOiJIUzI1NiIs...",
            "token_type": "bearer"
        }
        ```
    -   **`409 Conflict`**: 用户名已存在。响应体: `{"detail": "用户名 'yonghu001' 已被注册。"}`
    -   **`422 Unprocessable Entity`**: 请求数据验证失败 (例如，uid 或 password 不符合要求)。
    -   **`429 Too Many Requests`**: 请求过于频繁。响应体: `{"detail": "注册请求过于频繁，请稍后再试。"}`

### 1.2 用户登录 (`POST /login`)

-   **摘要**: 用户登录
-   **描述**: 用户通过提供用户名和密码进行登录。服务器期望的是标准的 `application/x-www-form-urlencoded` 表单数据（由FastAPI的 `OAuth2PasswordRequestForm` 处理），而非JSON。成功后返回访问令牌。
-   **认证**: 无需。
-   **速率限制**: 应用标准认证尝试速率限制。
-   **请求体** (`application/x-www-form-urlencoded`):
    -   `username`: (string, 必需) 用户名 (对应 `uid`)
    -   `password`: (string, 必需) 密码
-   **响应**:
    -   **`200 OK`**: 登录成功。返回 `TokenResponse` 模型。
    -   **`401 Unauthorized`**: 用户名或密码错误。响应体: `{"detail": "用户名或密码不正确。"}`
    -   **`422 Unprocessable Entity`**: 请求数据验证失败 (例如，表单字段缺失)。
    -   **`429 Too Many Requests`**: 请求过于频繁。响应体: `{"detail": "登录请求过于频繁，请稍后再试。"}`

### 1.3 刷新访问令牌 (`GET /login`)

-   **摘要**: 刷新访问令牌
-   **描述**: 使用一个有效的旧访问令牌（通过查询参数 `token` 提供）获取一个新的访问令牌。成功后，旧令牌将失效。
-   **认证**: 无需（但旧Token本身需有效）。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 待刷新的有效旧访问令牌。
-   **响应**:
    -   **`200 OK`**: 令牌刷新成功。返回 `TokenResponse` 模型。
    -   **`401 Unauthorized`**: 提供的旧令牌无效或已过期。响应体: `{"detail": "提供的令牌无效或已过期，无法刷新。"}`

---

## 2. 用户个人信息管理 API (User Profile Management API)

基础路径: `/users/me`
认证: 所有此部分接口都需要用户Token认证 (`?token={USER_ACCESS_TOKEN}` 作为查询参数)

### 2.1 获取当前用户信息 (`GET /`)

-   **摘要**: 获取当前用户信息
-   **描述**: 获取当前认证用户的公开个人资料，包括UID、昵称、邮箱、QQ以及用户标签等信息。
-   **响应**:
    -   **`200 OK`**: 成功获取用户信息。返回 `UserPublicProfile` 模型。
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`404 Not Found`**: 用户未找到（理论上在Token有效时此错误不应发生）。

### 2.2 更新当前用户个人资料 (`PUT /`)

-   **摘要**: 更新当前用户个人资料
-   **描述**: 允许当前认证用户更新其个人资料，如昵称、邮箱或QQ号码。请求体中应包含待更新的字段及其新值。
-   **请求体** (`application/json`): `UserProfileUpdatePayload` 模型 (所有字段可选)
-   **响应**:
    -   **`200 OK`**: 更新成功。返回更新后的 `UserPublicProfile` 模型。
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`404 Not Found`**: 用户未找到。
    -   **`422 Unprocessable Entity`**: 请求体验证失败。

### 2.3 修改当前用户密码 (`PUT /password`)</h3>

-   **摘要**: 修改当前用户密码
-   **描述**: 允许当前认证用户修改自己的密码。请求体中必须提供当前密码和新密码。
-   **请求体** (`application/json`): `UserPasswordUpdatePayload` 模型
-   **响应**:
    -   **`204 No Content`**: 密码修改成功。无响应体。
    -   **`400 Bad Request`**: 当前密码不正确。响应体: `{"detail": "当前密码不正确。"}`
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`404 Not Found`**: 用户未找到。
    -   **`422 Unprocessable Entity`**: 新密码不符合要求。
    -   **`500 Internal Server Error`**: 更新密码时发生未知错误。

---

## 3. 核心答题接口 (Core Exam Taking API)

认证: 所有此部分接口都需要用户Token认证 (`?token={USER_ACCESS_TOKEN}` 作为查询参数)

### 3.1 请求新试卷 (`GET /get_exam`)

-   **摘要**: 请求新试卷
-   **描述**: 为当前认证用户创建一份指定难度（可选题目数量）的新试卷。返回试卷的详细信息，包括题目列表。题目内容会经过处理，对用户隐藏正确答案和答案解析。非管理员用户受速率限制。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
    -   `difficulty` (string, 可选, 默认: "hybrid"): 新试卷的难度级别 (来自 `DifficultyLevel` 枚举)。
    -   `num_questions` (integer, 可选, 1-200): 请求的题目数量。
-   **响应**:
    -   **`200 OK`**: 成功获取新试卷。返回 `PaperDetailModel` 模型，其中 `questions` 列表中的题目为 `ExamQuestionClientView` 类型。
        ```json
        // PaperDetailModel (部分) 结合 ExamQuestionClientView 示例
        {
            "paper_id": "uuid-string-paper-id",
            "user_uid": "yonghu001",
            "difficulty": "hybrid",
            "num_questions": 2, // 实际生成的题目数
            "questions": [
                {
                    "question_id": "uuid-string-q1", // 题目在试卷中的唯一ID
                    "body": "题目1的题干内容...",
                    "choices": [ // 所有选项合并打乱后呈现给用户
                        "选项A文本",
                        "选项B文本",
                        "选项C文本",
                        "选项D文本"
                    ],
                    "question_type": "single_choice" // 题目类型
                },
                {
                    "question_id": "uuid-string-q2",
                    "body": "题目2的题干内容...",
                    "choices": [
                        "选项X文本",
                        "选项Y文本",
                        "选项Z文本"
                    ],
                    "question_type": "single_choice"
                }
            ],
            "created_at": "2024-01-01T10:00:00Z",
            "pass_status": "PENDING" // 初始为待处理
            // ... 其他试卷元数据
        }
        ```
    -   **`400 Bad Request`**: 请求参数无效或业务逻辑错误（如题库题目不足）。
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`429 Too Many Requests`**: 获取新试卷请求过于频繁。
    -   **`500 Internal Server Error`**: 创建新试卷时发生意外服务器错误。

### 3.2 更新答题进度 (`POST /update`)

-   **摘要**: 更新答题进度
-   **描述**: 用户提交一部分答案以保存当前答题进度。此接口不进行批改，仅保存用户答案。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
-   **请求体** (`application/json`): `PaperSubmissionPayload` 模型
-   **响应**:
    -   **`200 OK`**: 进度已成功保存。返回 `ProgressUpdateResponse` 模型。
        ```json
        // ProgressUpdateResponse 示例
        {
            "status_code": "PROGRESS_SAVED",
            "message": "试卷进度已成功保存。",
            "paper_id": "uuid-string-paper-id",
            "last_update_time_utc": "2024-01-01T12:00:00Z"
        }
        ```
    -   **`400 Bad Request`**: 请求数据无效（如答案数量错误）。
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 试卷已完成，无法更新进度。
    -   **`404 Not Found`**: 试卷未找到或用户无权访问。
    -   **`500 Internal Server Error`**: 更新进度时发生意外服务器错误。

### 3.3 提交试卷答案以供批改 (`POST /finish`)

-   **摘要**: 提交试卷答案以供批改
-   **描述**: 用户提交已完成作答的试卷。系统将对答案进行批改，并返回详细的批改结果，包括得分、通过状态以及可能的通行码（如果通过考试）。此操作会记录提交时间及用户IP。
    *(注意：此端点的部分错误处理逻辑的后台实现仍在优化中，当前文档反映的是其OpenAPI装饰器中定义的理想行为。实际调用时，部分业务错误细节可能仍通过响应体内的字段传递。)*
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
-   **请求体** (`application/json`): `PaperSubmissionPayload` 模型
-   **响应**:
    -   **`200 OK`**: 试卷已成功接收并完成批改。返回 `GradingResultResponse` 模型。
        ```json
        // GradingResultResponse 示例
        {
            "status_code": "PASSED", // PaperPassStatusEnum 值: "PASSED" 或 "FAILED"
            "passcode": "PASSCODE_EXAMPLE", // (如果通过)
            "score": 90,
            "score_percentage": 90.0
        }
        ```
    -   **`400 Bad Request`**: 无效的提交数据（例如，提交的答案数量与试卷题目总数不匹配）。
    -   **`401 Unauthorized`**: 用户未认证（Token无效或缺失）。
    -   **`403 Forbidden`**: 用户无权进行此操作（非预期，但为完备性保留）。
    -   **`404 Not Found`**: 要提交的试卷ID不存在，或不属于当前用户。
    -   **`409 Conflict`**: 操作冲突（例如，该试卷已被最终批改且系统配置为不允许重复提交）。
    -   **`422 Unprocessable Entity`**: 请求体数据校验失败。
    -   **`500 Internal Server Error`**: 服务器内部错误（例如，因试卷数据结构问题导致无法批改，或在批改过程中发生其他意外）。

### 3.4 获取用户答题历史 (`GET /history`)

-   **摘要**: 获取用户答题历史
-   **描述**: 获取当前认证用户的简要答题历史记录列表，包含每次答题的试卷ID、难度、得分等信息。列表按提交时间倒序排列。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
-   **响应**:
    -   **`200 OK`**: 成功获取答题历史。返回 `List[UserPaperHistoryItem]`。
    -   **`401 Unauthorized`**: 令牌无效或已过期。

### 3.5 获取指定历史试卷详情 (`GET /history_paper`)</h3>

-   **摘要**: 获取指定历史试卷详情
-   **描述**: 用户获取自己答题历史中某一份特定试卷的详细题目、作答情况和批改结果（如果已批改）。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
    -   `paper_id` (string, 必需, UUID格式): 要获取详情的历史试卷ID。
-   **响应**:
    -   **`200 OK`**: 成功获取历史试卷详情。返回 `PaperDetailModel` (或类似的包含完整题目、用户答案和正确答案的详细模型)。
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`404 Not Found`**: 指定的历史试卷未找到或用户无权查看。响应体: `{"detail": "指定的历史试卷未找到或您无权查看。"}`

---

## 4. 公共接口 (Public APIs)

此部分包含所有公开访问的API端点，无需用户认证。

### 4.1 获取可用题库难度列表 (`GET /difficulties`)

-   **摘要**: 获取可用题库难度列表
-   **描述**: 公开接口，返回系统中所有已定义的题库难度级别及其元数据（如名称、描述、默认题量等）。
-   **响应**:
    -   **`200 OK`**: 成功获取题库难度列表。返回 `List[LibraryIndexItem]`。
    -   **`500 Internal Server Error`**: 获取题库元数据时发生服务器内部错误。

### 4.2 获取公开用户目录 (`GET /users/directory`)</h3>

-   **摘要**: 获取公开用户目录
-   **描述**: 公开接口，返回系统中拥有特定公开角色标签（例如：管理员、出题人等）的用户子集。
-   **响应**:
    -   **`200 OK`**: 成功获取用户目录列表。返回 `List[UserDirectoryEntry]`。
    -   **`500 Internal Server Error`**: 获取用户目录时发生服务器内部错误。

---
[end of docs/api/user_exam.md]
