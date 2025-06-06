---

## 1. 用户认证 (User Authentication)

基础路径: `/auth`

### 1.1 用户注册 (User Sign Up)

-   **路径 (Path)**: `/signin`
-   **方法 (Method)**: `POST`
-   **摘要 (Summary)**: 用户注册
-   **描述 (Description)**: 新用户通过提供用户名、密码等信息进行注册。成功后返回访问令牌。
-   **认证 (Authentication)**: 无需认证 (None required)。
-   **速率限制 (Rate Limit)**: 应用认证尝试速率限制 (Authentication attempt rate limits apply)。
-   **请求体**: `application/json`
    ```json
    // UserCreate 模型
    {
        "uid": "string (用户名, 5-16位，只能是小写字母、数字或下划线)",
        "password": "string (密码, 8-48 位)",
        "nickname": "string (可选, 用户昵称, 最长50个字符)",
        "email": "string (可选, 电子邮箱, 必须是有效的邮箱格式)",
        "qq": "string (可选, QQ号码, 5-15位数字)"
    }
    ```
-   **响应**:
    -   **201 Created**: 注册成功
        ```json
        // Token 模型
        {
            "access_token": "string (访问令牌)",
            "token_type": "bearer"
        }
        ```
    -   **409 Conflict**: 用户名已存在 (Username already exists)。
        ```json
        // 标准HTTPException响应体
        {
            "detail": "用户名 '您的用户名' 已被注册。"
        }
        ```
    -   **429 Too Many Requests**: 请求过于频繁 (Too many requests)。
        ```json
        {
            "detail": "注册请求过于频繁，请稍后再试。"
        }
        ```
    -   **422 Unprocessable Entity**: 请求体验证失败 (例如，uid 或 password 不符合要求)。响应体包含Pydantic验证错误详情。

### 1.2 用户登录 (User Login)

-   **路径 (Path)**: `/login`
-   **方法 (Method)**: `POST`
-   **摘要 (Summary)**: 用户登录
-   **描述 (Description)**: 用户通过提供用户名和密码进行登录。成功后返回访问令牌。
-   **认证 (Authentication)**: 无需认证 (None required)。
-   **速率限制 (Rate Limit)**: 应用认证尝试速率限制 (Authentication attempt rate limits apply)。
-   **请求体**: `application/json`
    ```json
    // UserCreate 模型 (与注册时相同，但 nickname, email, qq 通常不用于登录验证)
    {
        "uid": "string (用户名)",
        "password": "string (密码)"
    }
    ```
-   **响应**:
    -   **200 OK**: 登录成功
        ```json
        // Token 模型
        {
            "access_token": "string (访问令牌)",
            "token_type": "bearer"
        }
        ```
    -   **401 Unauthorized**: 用户名或密码错误 (Incorrect username or password)。
        ```json
        // 标准HTTPException响应体
        {
            "detail": "用户名或密码不正确。"
        }
        ```
    -   **429 Too Many Requests**: 请求过于频繁 (Too many requests)。
        ```json
        {
            "detail": "登录请求过于频繁，请稍后再试。"
        }
        ```
    -   **422 Unprocessable Entity**: 请求体验证失败 (Request data validation failed)。

### 1.3 刷新访问令牌 (Refresh Access Token)

-   **路径 (Path)**: `/login`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 刷新访问令牌
-   **描述 (Description)**: 使用一个有效的旧访问令牌获取一个新的访问令牌。成功后，旧令牌将失效。
-   **认证 (Authentication)**: 无需认证，但需提供有效的旧 `token` 作为查询参数 (None required, but a valid old `token` must be provided as a query parameter)。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 待刷新的有效旧访问令牌。
-   **响应 (Responses)**:
    -   **`200 OK`**: 令牌刷新成功 (Token refresh successful)。返回 `Token` 模型。
        ```json
        // Token 模型示例
        {
            "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            "token_type": "bearer"
        }
        ```
    -   **`401 Unauthorized`**: 提供的旧令牌无效或已过期 (Provided old token is invalid or expired)。
        ```json
        // 标准HTTPException响应体
        {
            "detail": "提供的令牌无效或已过期，无法刷新。"
        }
        ```

---

## 2. 用户个人信息管理 (User Profile API)

基础路径: `/users/me` (Base Path: `/users/me`)
认证: 所有接口都需要用户 Token (`?token={USER_ACCESS_TOKEN}`)

### 2.1 获取当前用户信息 (Get Current User Profile)

-   **路径 (Path)**: `/` (即 `/users/me/`)
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 获取当前用户信息
-   **描述 (Description)**: 获取当前认证用户的公开个人资料，包括UID、昵称、邮箱、QQ以及用户标签等信息。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取用户信息。返回 `UserPublicProfile` 模型。
        ```json
        // UserPublicProfile 模型示例
        {
            "uid": "currentuser",
            "nickname": "我的昵称",
            "email": "current@example.com",
            "qq": "1234567",
            "tags": ["user"]
        }
        ```
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`404 Not Found`**: 用户未找到 (理论上在Token有效时此错误不应发生)。

### 2.2 更新当前用户个人资料 (Update Current User Profile)

-   **路径 (Path)**: `/` (即 `/users/me/`)
-   **方法 (Method)**: `PUT`
-   **摘要 (Summary)**: 更新当前用户个人资料
-   **描述 (Description)**: 允许当前认证用户更新其个人资料，如昵称、邮箱或QQ号码。请求体中应包含待更新的字段及其新值。
-   **请求体 (Request Body)**: `application/json`, `UserProfileUpdate` 模型 (所有字段可选)
    ```json
    // UserProfileUpdate 模型示例
    {
        "nickname": "我的新昵称",
        "email": "new_email@example.com"
    }
    ```
-   **响应 (Responses)**:
    -   **`200 OK`**: 更新成功。返回更新后的 `UserPublicProfile` 模型。
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`404 Not Found`**: 用户未找到或更新数据无效。
    -   **`422 Unprocessable Entity`**: 请求体验证失败。

### 2.3 修改当前用户密码 (Change Current User Password)

-   **路径 (Path)**: `/password` (即 `/users/me/password`)
-   **方法 (Method)**: `PUT`
-   **摘要 (Summary)**: 修改当前用户密码
-   **描述 (Description)**: 允许当前认证用户修改自己的密码。请求体中必须提供当前密码和新密码。
-   **请求体 (Request Body)**: `application/json`, `UserPasswordUpdate` 模型
    ```json
    // UserPasswordUpdate 模型示例
    {
        "current_password": "OldSecurePassword",
        "new_password": "NewVerySecurePassword123!"
    }
    ```
-   **响应 (Responses)**:
    -   **`204 No Content`**: 密码修改成功。无响应体。
    -   **`400 Bad Request`**: 当前密码不正确。响应体: `{"detail": "当前密码不正确。"}`
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`404 Not Found`**: 用户未找到。
    -   **`422 Unprocessable Entity`**: 请求体验证失败 (例如新密码不符合要求)。
    -   **`500 Internal Server Error`**: 更新密码时发生未知错误。

---

## 3. 核心答题接口 (Core Exam Taking API)

认证: 所有接口都需要用户 Token (`?token={USER_ACCESS_TOKEN}`)

### 3.1 请求新试卷 (Request New Exam Paper)

-   **路径 (Path)**: `/get_exam`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 请求新试卷
-   **描述 (Description)**: 为当前认证用户创建一份指定难度（可选题目数量）的新试卷。返回试卷的详细信息，包括题目列表。非管理员用户受速率限制。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
    -   `difficulty` (string, 可选, 默认: "hybrid"): 新试卷的难度级别 (来自 `DifficultyLevel` 枚举, 例如 "easy", "hybrid", "hard")。
    -   `num_questions` (integer, 可选, 1-200): 请求的题目数量，覆盖该难度默认题量。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取新试卷。返回 `ExamPaperResponse` 模型。
        ```json
        // ExamPaperResponse 模型示例
        {
            "paper_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
            "difficulty": "hybrid", // DifficultyLevel 枚举值
            "paper": [
                { // ExamQuestionClientView 模型
                    "body": "这是第一题的题干...",
                    "choices": {
                        "choice_id_A": "选项A文本",
                        "choice_id_B": "选项B文本"
                    },
                    "question_type": "single_choice" // QuestionTypeEnum 枚举值
                }
                // ... 更多题目
            ]
        }
        ```
    -   **`400 Bad Request`**: 请求参数无效或业务逻辑错误（例如题库题目不足）。响应体: `{"detail": "具体错误描述"}`
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`403 Forbidden`**: 用户账户已被封禁。
    -   **`429 Too Many Requests`**: 获取新试卷请求过于频繁。响应体: `{"detail": "Too many requests for new exam."}`
    -   **`500 Internal Server Error`**: 创建新试卷时发生意外服务器错误。

### 3.2 更新答题进度 (Update Exam Progress)

-   **路径 (Path)**: `/update`
-   **方法 (Method)**: `POST`
-   **摘要 (Summary)**: 更新答题进度
-   **描述 (Description)**: 用户提交一部分答案以保存当前答题进度。此接口不进行批改，仅保存用户答案。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
-   **请求体 (Request Body)**: `application/json`, `PaperSubmissionPayload` 模型
    ```json
    // PaperSubmissionPayload 模型示例
    {
        "paper_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef", // UUID 字符串
        "result": ["choice_id_A", null, "choice_id_C"] // null 表示某题未作答
    }
    ```
-   **响应 (Responses)**:
    -   **`200 OK`**: 进度已成功保存。返回 `UpdateProgressResponse` 模型。
        ```json
        // UpdateProgressResponse 模型示例 (注意：旧的 'code' 字段已移除)
        {
            "status_code": "PROGRESS_SAVED", // 业务状态文本
            "message": "试卷进度已成功保存。", // 详细消息
            "paper_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
            "last_update_time_utc": "2024-01-01T12:00:00Z"
        }
        ```
    -   **`400 Bad Request`**: 请求数据无效（如答案数量错误）。响应体: `{"detail": "具体错误信息"}`
    -   **`403 Forbidden`**: 试卷已完成，无法更新进度。响应体: `{"detail": "具体错误信息"}`
    -   **`404 Not Found`**: 试卷未找到或用户无权访问。响应体: `{"detail": "具体错误信息"}`
    -   **`422 Unprocessable Entity`**: 请求体验证失败。
    -   **`500 Internal Server Error`**: 更新进度时发生意外错误。

### 3.3 提交并批改试卷 (Submit and Grade Exam Paper)

-   **路径 (Path)**: `/finish`
-   **方法 (Method)**: `POST`
-   **摘要 (Summary)**: 提交并批改试卷
-   **描述 (Description)**: 用户提交最终答案以完成试卷并进行批改。成功时返回包含得分、通过状态和（如果通过）通行码的详细结果。
    *(注意：此端点的内部逻辑重构（将自定义状态码完全映射到HTTP状态码）仍在进行中。当前文档描述的是API的理想行为及OpenAPI装饰器中已部分更新的定义。实际的错误响应细节可能在完全重构前与此描述有细微差异。)*
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
-   **请求体 (Request Body)**: `application/json`, `PaperSubmissionPayload` 模型
    ```json
    // PaperSubmissionPayload 模型示例
    {
        "paper_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef", // UUID 字符串
        "result": ["choice_id_A", "choice_id_D", "choice_id_C"] // 所有题目均需作答
    }
    ```
-   **响应 (Responses)**:
    -   **`200 OK`**: 试卷已成功接收并完成批改（无论通过与否，具体结果见响应体）。返回 `GradingResultResponse` 模型。
        ```json
        // GradingResultResponse 模型示例 (注意：旧的 'code', 'message', 'previous_result' 字段已移除)
        {
            "status_code": "PASSED", // PaperPassStatusEnum: "PASSED" 或 "FAILED"
            "passcode": "EXAM_PASS_XYZ123", // (如果通过)
            "score": 18,
            "score_percentage": 90.0
        }
        ```
    -   **`400 Bad Request`**: 提交数据无效（例如，提交的答案数量与试卷题目总数不匹配）。响应体: `{"detail": "具体错误信息"}`
    -   **`404 Not Found`**: 要提交的试卷ID不存在或不属于当前用户。响应体: `{"detail": "具体错误信息"}`
    -   **`409 Conflict`**: 操作冲突（例如，该试卷已经被最终批改且不允许重复提交）。响应体: `{"detail": "这份试卷已经被批改过了。"}`
    -   **`422 Unprocessable Entity`**: 请求体数据校验失败。
    -   **`500 Internal Server Error`**: 服务器内部错误（例如，试卷数据结构损坏导致无法批改，或批改过程中发生意外）。响应体: `{"detail": "具体错误信息"}`

### 3.4 获取用户答题历史 (Get User Exam History)

-   **路径 (Path)**: `/history`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 获取用户答题历史
-   **描述 (Description)**: 获取当前认证用户的简要答题历史记录列表，包含每次答题的试卷ID、难度、得分等信息。列表按提交时间倒序排列。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取答题历史。返回 `List[HistoryItem]` 模型。
        ```json
        // List[HistoryItem] 示例
        [
            {
                "paper_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
                "difficulty": "hybrid", // DifficultyLevel 枚举值
                "score": 18,
                "score_percentage": 90.0,
                "pass_status": "PASSED", // PaperPassStatusEnum 枚举值
                "submission_time_utc": "2024-01-01T12:30:00Z"
            }
            // ... 更多历史记录
        ]
        ```
    -   **`401 Unauthorized`**: 令牌无效或已过期。

### 3.5 获取指定历史试卷详情 (Get Specific History Paper Details)

-   **路径 (Path)**: `/history_paper`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 获取指定历史试卷详情
-   **描述 (Description)**: 用户获取自己答题历史中某一份特定试卷的详细题目、作答情况和批改结果（如果已批改）。
-   **请求参数 (Query Parameters)**:
    -   `token` (string, 必需): 用户访问令牌。
    -   `paper_id` (string, 必需, UUID): 要获取详情的历史试卷ID。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取历史试卷详情。返回 `HistoryPaperDetailResponse` 模型。
        ```json
        // HistoryPaperDetailResponse 模型示例
        {
            "paper_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
            "difficulty": "hybrid", // DifficultyLevel 枚举值
            "user_uid": "currentuser",
            "paper_questions": [
                { // HistoryPaperQuestionClientView 模型示例
                    "body": "这是第一题的题干...",
                    "question_type": "single_choice", // QuestionTypeEnum 枚举值
                    "choices": {
                        "choice_id_A": "选项A文本",
                        "choice_id_B": "选项B文本"
                    },
                    "submitted_answer": "choice_id_A"
                }
                // ...
            ],
            "score": 18,
            "score_percentage": 90.0,
            "submitted_answers_card": ["choice_id_A", /* ... */],
            "pass_status": "PASSED", // PaperPassStatusEnum 枚举值
            "passcode": "EXAM_PASS_XYZ123",
            "submission_time_utc": "2024-01-01T12:30:00Z"
        }
        ```
    -   **`401 Unauthorized`**: 令牌无效或已过期。
    -   **`404 Not Found`**: 指定的历史试卷未找到或用户无权查看。响应体: `{"detail": "指定的历史试卷未找到或您无权查看。"}`

---

## 4. 公共接口 (Public APIs)

此部分包含所有公开访问的API端点，无需用户认证。

### 4.1 获取可用题库难度列表 (Get Available Question Bank Difficulty List)

-   **路径 (Path)**: `/difficulties`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 获取可用题库难度列表
-   **描述 (Description)**: 公开接口，返回系统中所有已定义的题库难度级别及其元数据（如名称、描述、默认题量等）。此接口无需认证。
-   **认证 (Authentication)**: 无需认证 (None required)。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取题库难度列表。返回 `List[LibraryIndexItem]` 模型。
        ```json
        // List[LibraryIndexItem] 示例
        [
            {
                "id": "easy",
                "name": "简单难度",
                "description": "入门级题目",
                "default_questions": 20,
                "total_questions": 150
            },
            {
                "id": "hybrid",
                "name": "混合难度",
                "description": "中等难度题目",
                "default_questions": 50,
                "total_questions": 250
            }
            // ... 更多难度
        ]
        ```
    -   **`500 Internal Server Error`**: 获取题库元数据时发生服务器内部错误。响应体: `{"detail": "获取题库难度列表时发生服务器内部错误。"}`

### 4.2 获取公开用户目录 (Get Public User Directory)

-   **路径 (Path)**: `/users/directory`
-   **方法 (Method)**: `GET`
-   **摘要 (Summary)**: 获取公开用户目录
-   **描述 (Description)**: 公开接口，无需认证。返回系统中拥有特定公开角色标签（例如：管理员、出题人、运营经理、批阅员等）的用户子集，主要用于展示项目团队或关键贡献者等公开信息。
-   **认证 (Authentication)**: 无需认证 (None required)。
-   **响应 (Responses)**:
    -   **`200 OK`**: 成功获取用户目录列表。返回 `List[UserDirectoryEntry]` 模型。
        ```json
        // List[UserDirectoryEntry] 示例
        [
            {
                "uid": "admin_user",
                "nickname": "系统管理员",
                "tags": ["admin", "manager"]
            },
            {
                "uid": "examiner01",
                "nickname": "出题专家张老师",
                "tags": ["examiner", "user"]
            }
            // ... 更多符合条件的用户
        ]
        ```
    -   **`500 Internal Server Error`**: 获取用户目录时发生服务器内部错误。响应体: `{"detail": "获取用户目录时发生服务器内部错误。"}`
