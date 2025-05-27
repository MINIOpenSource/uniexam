# API 文档 - 在线考试系统

版本: 3.0.0

## 简介

本文档详细描述了在线考试系统的 API 接口。系统功能包括用户认证、试卷获取、答题、进度保存、历史记录查看以及管理员后台管理等。

## 认证机制

大部分核心 API 端点需要通过 Token 进行认证。Token 在用户登录或注册成功后返回。

-   **用户 Token**: 通过在请求的 Query 参数中附加 `token={USER_ACCESS_TOKEN}` 来传递。
-   **管理员 Token**: 管理员接口同样通过 Query 参数中的 `token` 进行认证，并且服务器端会校验该 Token 对应的用户是否拥有 `admin` 标签。

## 数据模型速查

为方便理解，以下列出一些关键的 Pydantic 模型（详细字段请参考各 API 说明）：

-   `UserCreate`: 用户注册/登录请求体。
-   `Token`: 认证成功后的 Token 响应。
-   `AuthStatusResponse`: 认证失败或特定状态的响应。
-   `UserPublicProfile`: 用户公开信息响应。
-   `UserProfileUpdate`: 用户更新个人资料请求。
-   `UserPasswordUpdate`: 用户更新密码请求。
-   `ExamPaperResponse`: 获取新试卷的响应。
-   `PaperSubmissionPayload`: 提交/更新试卷答案的请求。
-   `UpdateProgressResponse`: 更新试卷进度的响应。
-   `GradingResultResponse`: 试卷批改结果的响应。
-   `HistoryItem`: 历史记录条目。
-   `HistoryPaperDetailResponse`: 历史试卷详情。
-   `LibraryIndexItem`: 题库元数据。
-   `SettingsResponseModel`: 管理员获取配置响应。
-   `SettingsUpdatePayload`: 管理员更新配置请求。
-   `PaperAdminView`: 管理员查看试卷摘要。
-   `PaperFullDetailModel`: 管理员查看试卷完整详情。
-   `QuestionModel`: 题库题目模型。

---

## 1. 用户认证 (User Authentication)

基础路径: `/auth`

### 1.1 用户注册

-   **路径**: `/signin`
-   **方法**: `POST`
-   **摘要**: 用户注册接口。
-   **认证**: 无需认证。
-   **速率限制**: 应用认证尝试速率限制。
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
    -   **409 Conflict**: 用户名已存在
        ```json
        // AuthStatusResponse 模型
        {
            "status_code": "DUPLICATE",
            "message": "Username already exists."
        }
        ```
    -   **429 Too Many Requests**: 请求过于频繁
        ```json
        {
            "detail": "Too many sign-up attempts."
        }
        ```
    -   **422 Unprocessable Entity**: 请求体验证失败 (例如，uid 或 password 不符合要求)

### 1.2 用户登录

-   **路径**: `/login`
-   **方法**: `POST`
-   **摘要**: 用户登录接口。
-   **认证**: 无需认证。
-   **速率限制**: 应用认证尝试速率限制。
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
    -   **401 Unauthorized**: 用户名或密码错误
        ```json
        // AuthStatusResponse 模型
        {
            "status_code": "WRONG",
            "message": "Incorrect username or password."
        }
        ```
    -   **429 Too Many Requests**: 请求过于频繁
        ```json
        {
            "detail": "Too many login attempts."
        }
        ```
    -   **422 Unprocessable Entity**: 请求体验证失败

### 1.3 刷新访问 Token

-   **路径**: `/login`
-   **方法**: `GET`
-   **摘要**: 使用有效的旧 Token 获取一个新的访问 Token，旧 Token 将同时失效。
-   **认证**: 无需认证（但需要有效的旧 Token）。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 需要刷新的旧 Token。
-   **响应**:
    -   **200 OK**: Token 刷新成功
        ```json
        // Token 模型
        {
            "access_token": "string (新的访问令牌)",
            "token_type": "bearer"
        }
        ```
    -   **401 Unauthorized**: 旧 Token 无效或已过期
        ```json
        // AuthStatusResponse 模型
        {
            "status_code": "WRONG",
            "message": "Invalid or expired token provided for refresh."
        }
        ```

---

## 2. 用户个人信息管理 (User Profile)

基础路径: `/users/me`
认证: 所有接口都需要用户 Token (`?token={USER_ACCESS_TOKEN}`)

### 2.1 获取当前用户信息

-   **路径**: `/`
-   **方法**: `GET`
-   **摘要**: 获取当前认证用户的公开个人资料。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // UserPublicProfile 模型
        {
            "uid": "string",
            "nickname": "string (可选)",
            "email": "string (可选, EmailStr)",
            "qq": "string (可选)",
            "tags": ["string (UserTag 枚举值列表, 例如 'user', 'admin')"]
        }
        ```
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。
    -   **404 Not Found**: 用户在数据库中未找到（理论上不应发生）。

### 2.2 更新当前用户个人资料

-   **路径**: `/`
-   **方法**: `PUT`
-   **摘要**: 更新当前认证用户的昵称、邮箱或 QQ 号。
-   **请求体**: `application/json`
    ```json
    // UserProfileUpdate 模型 (所有字段可选)
    {
        "nickname": "string (新的用户昵称, 最长50个字符)",
        "email": "string (新的电子邮箱, EmailStr)",
        "qq": "string (新的QQ号码, 5-15位数字)"
    }
    ```
-   **响应**:
    -   **200 OK**: 更新成功
        ```json
        // UserPublicProfile 模型 (更新后的用户信息)
        {
            "uid": "string",
            "nickname": "string (可选)",
            "email": "string (可选, EmailStr)",
            "qq": "string (可选)",
            "tags": ["string (UserTag 枚举值列表)"]
        }
        ```
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。
    -   **404 Not Found**: 用户未找到或更新数据无效。
    -   **422 Unprocessable Entity**: 请求体验证失败。

### 2.3 修改当前用户密码

-   **路径**: `/password`
-   **方法**: `PUT`
-   **摘要**: 当前认证用户修改自己的密码。
-   **请求体**: `application/json`
    ```json
    // UserPasswordUpdate 模型
    {
        "current_password": "string (当前密码)",
        "new_password": "string (新密码, 8-48 位)"
    }
    ```
-   **响应**:
    -   **204 No Content**: 密码修改成功。
    -   **400 Bad Request**: 当前密码不正确。
        ```json
        {
            "detail": "Incorrect current password."
        }
        ```
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。
    -   **404 Not Found**: 用户未找到。
    -   **422 Unprocessable Entity**: 请求体验证失败 (例如新密码不符合要求)。
    -   **500 Internal Server Error**: 更新密码时发生未知错误。

---

## 3. 核心答题接口 (Exam Taking)

认证: 所有接口都需要用户 Token (`?token={USER_ACCESS_TOKEN}`)

### 3.1 请求一份新试卷

-   **路径**: `/get_exam`
-   **方法**: `GET`
-   **摘要**: 为认证用户创建一份指定难度和（可选）指定题目数量的新试卷。
-   **速率限制**: 应用 `get_exam` 速率限制 (非 admin 用户)。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 用户访问 Token。
    -   `difficulty` (string, 可选, 默认: "hybrid"): 新试卷的难度级别。有效值取决于 `DifficultyLevel` 枚举 (例如 "easy", "hybrid", "hard")。
    -   `num_questions` (integer, 可选, 1-200): 请求的题目数量，覆盖该难度默认题量。
-   **响应**:
    -   **200 OK**: 成功创建试卷
        ```json
        // ExamPaperResponse 模型
        {
            "paper_id": "string (试卷的唯一标识符, UUID字符串)",
            "difficulty": "string (试卷的难度级别, DifficultyLevel 枚举值)",
            "paper": [ // 试卷题目列表
                {
                    "body": "string (问题题干)",
                    "choices": { // 选择题的选项 (ID到文本的映射，已打乱)
                        "random_choice_id_1": "string (选项文本1)",
                        "random_choice_id_2": "string (选项文本2)",
                        // ...
                    }
                    // "question_type": "string (题目类型, 如果返回)"
                }
                // ...
            ]
            // "finished": null (此接口不返回已完成答案)
        }
        ```
    -   **400 Bad Request**: 请求参数无效或业务逻辑错误 (例如题库题目不足)。
        ```json
        { "detail": "string (错误描述)" }
        ```
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。
    -   **429 Too Many Requests**: 请求过于频繁。
        ```json
        { "detail": "Too many requests for new exam." }
        ```
    -   **500 Internal Server Error**: 创建新试卷时发生意外错误。

### 3.2 更新未完成试卷的答题进度

-   **路径**: `/update`
-   **方法**: `POST`
-   **摘要**: 更新未完成试卷的答题进度。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 用户访问 Token。
-   **请求体**: `application/json`
    ```json
    // PaperSubmissionPayload 模型
    {
        "paper_id": "string (试卷的唯一标识符, UUID)",
        "result": ["string (所选选项ID的列表，未答题目为 null 或空字符串)"]
    }
    ```
-   **响应**:
    -   **200 OK**: 进度保存成功
        ```json
        // UpdateProgressResponse 模型
        {
            "code": 200, // 或其他业务码
            "status_code": "PROGRESS_SAVED",
            "message": "Paper progress saved successfully.",
            "paper_id": "string (相关的试卷ID)",
            "last_update_time_utc": "string (最后更新时间的ISO格式字符串)"
        }
        ```
    -   **400 Bad Request**: 答案数量错误等。
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 试卷已完成或用户账户被封禁。
    -   **404 Not Found**: 试卷未找到或权限不足。
    -   **422 Unprocessable Entity**: 请求体验证失败。
    -   **500 Internal Server Error**: 更新进度时发生意外错误。

### 3.3 提交试卷答案进行批改

-   **路径**: `/finish`
-   **方法**: `POST`
-   **摘要**: 提交试卷答案进行批改。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 用户访问 Token。
-   **请求体**: `application/json`
    ```json
    // PaperSubmissionPayload 模型
    {
        "paper_id": "string (试卷的唯一标识符, UUID)",
        "result": ["string (所选选项ID的列表，列表长度应与题目数一致)"]
    }
    ```
-   **响应**:
    -   **200 OK**: 批改完成 (无论通过与否)
        ```json
        // GradingResultResponse 模型
        {
            "code": 200, // 或其他业务码
            "status_code": "string (例如 'PASSED', 'FAILED', 'ALREADY_GRADED')",
            "message": "string (可选, 附带的操作结果消息)",
            "passcode": "string (可选, 如果通过考试，生成的通行码)",
            "score": "integer (可选, 原始得分)",
            "score_percentage": "float (可选, 百分制得分)",
            "previous_result": "string (可选, 如果试卷之前已被批改，此字段表示之前的状态)"
        }
        ```
    -   **400 Bad Request**: 提交数据无效 (例如答案数量不匹配)。
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。
    -   **404 Not Found**: 试卷未找到或权限不足。
    -   **422 Unprocessable Entity**: 请求体验证失败。
    -   **500 Internal Server Error**: 处理提交时发生意外错误。

### 3.4 获取当前用户的答题历史记录

-   **路径**: `/history`
-   **方法**: `GET`
-   **摘要**: 获取当前用户的答题历史记录。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 用户访问 Token。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // List[HistoryItem] 模型
        [
            {
                "paper_id": "string (试卷的唯一标识符, UUID字符串)",
                "difficulty": "string (试卷难度, DifficultyLevel 枚举值)",
                "score": "integer (可选, 原始得分)",
                "score_percentage": "float (可选, 百分制得分)",
                "pass_status": "string (可选, 'PASSED', 'FAILED', 或 null)",
                "submission_time_utc": "string (可选, 提交时间的ISO格式字符串)"
            }
            // ...
        ]
        ```
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。

### 3.5 获取指定历史试卷的详细信息

-   **路径**: `/history_paper`
-   **方法**: `GET`
-   **摘要**: 获取指定历史试卷的详细信息。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 用户访问 Token。
    -   `paper_id` (string, 必需, UUID): 要获取详情的历史试卷ID。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // HistoryPaperDetailResponse 模型
        {
            "paper_id": "string (试卷的唯一标识符, UUID字符串)",
            "difficulty": "string (试卷难度, DifficultyLevel 枚举值)",
            "user_uid": "string (进行此试卷的用户的UID)",
            "paper_questions": [ // 试卷题目列表及其用户作答情况
                { // HistoryPaperQuestionClientView 模型
                    "body": "string (问题题干)",
                    "question_type": "string (题目类型)",
                    "choices": { // 可选, 选择题的选项 (ID到文本的映射，已打乱)
                        "random_choice_id_1": "string (选项文本1)"
                    },
                    "submitted_answer": "string | array[string] (可选, 用户对此题提交的答案)"
                }
                // ...
            ],
            "score": "integer (可选, 原始总得分)",
            "score_percentage": "float (可选, 百分制总得分)",
            "submitted_answers_card": ["string (可选, 用户提交的完整原始答案卡, 未答为null)"],
            "pass_status": "string (可选, 最终通过状态)",
            "passcode": "string (可选, 通行码)",
            "submission_time_utc": "string (可选, 试卷提交时间)"
        }
        ```
    -   **401 Unauthorized**: Token 无效或过期。
    -   **403 Forbidden**: 用户账户被封禁。
    -   **404 Not Found**: 指定的历史试卷未找到或用户无权查看。

---

## 4. 题库元数据接口 (Public)

### 4.1 获取所有可用题库的元数据列表

-   **路径**: `/difficulties`
-   **方法**: `GET`
-   **摘要**: 获取系统中所有已定义的题库难度及其元数据信息。
-   **认证**: 无需认证。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // List[LibraryIndexItem] 模型
        [
            {
                "id": "string (题库的唯一ID, 例如 'easy')",
                "name": "string (题库的显示名称, 例如 '简单难度')",
                "description": "string (可选, 题库的详细描述)",
                "default_questions": "integer (从此题库出题时的默认题目数量)",
                "total_questions": "integer (此题库中实际的总题目数量)"
            }
            // ...
        ]
        ```
    -   **500 Internal Server Error**: 获取题库元数据时发生意外错误。

---

## 5. 管理员接口 (Admin API)

基础路径: `/admin`
认证: 所有接口都需要管理员 Token (`?token={ADMIN_ACCESS_TOKEN}`) 并且用户拥有 `admin` 标签。

### 5.1 系统配置管理

#### 5.1.1 获取当前应用配置

-   **路径**: `/settings`
-   **方法**: `GET`
-   **摘要**: 获取当前应用的配置信息 (settings.json 的内容)。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // SettingsResponseModel 模型 (字段与 app.core.config.Settings 中可配置项对应)
        {
            "app_name": "string (可选)",
            "token_expiry_hours": "integer (可选)",
            "token_length_bytes": "integer (可选)",
            "num_questions_per_paper_default": "integer (可选)",
            "num_correct_choices_to_select": "integer (可选)",
            "num_incorrect_choices_to_select": "integer (可选)",
            "generated_code_length_bytes": "integer (可选)",
            "passing_score_percentage": "float (可选)",
            "db_persist_interval_seconds": "integer (可选)",
            "rate_limits": { // 可选
                "default_user": { // UserTypeRateLimitsPayload
                    "get_exam": { "limit": "integer", "window": "integer" }, // RateLimitConfigPayload
                    "auth_attempts": { "limit": "integer", "window": "integer" }
                },
                "limited_user": { /* ... */ }
            },
            "cloudflare_ips": { // CloudflareIPsConfigPayload, 可选
                "v4_url": "string",
                "v6_url": "string",
                "fetch_interval_seconds": "integer"
            },
            "log_file_name": "string (可选)",
            "database_files": { // DatabaseFilesConfigPayload, 可选
                "papers": "string",
                "users": "string"
            },
            "question_library_path": "string (可选)",
            "question_library_index_file": "string (可选)",
            "user_config": { // UserValidationConfigPayload, 可选
                "uid_min_len": "integer",
                "uid_max_len": "integer",
                "password_min_len": "integer",
                "password_max_len": "integer",
                "uid_regex": "string"
            }
        }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。

#### 5.1.2 更新应用配置

-   **路径**: `/settings`
-   **方法**: `POST`
-   **摘要**: 更新应用的配置项 (写入 settings.json 并重新加载全局配置)。
-   **请求体**: `application/json`
    ```json
    // SettingsUpdatePayload 模型 (所有字段可选，用于部分更新)
    // 结构与 SettingsResponseModel 类似，但用于请求。
    // 例如:
    {
        "token_expiry_hours": 48,
        "app_name": "新考试系统名称"
    }
    ```
-   **响应**:
    -   **200 OK**: 更新成功，返回更新后的配置 (settings.json 的目标状态)
        ```json
        // SettingsResponseModel 模型
        { /* ... 同 GET /admin/settings 响应 ... */ }
        ```
    -   **400 Bad Request**: 提供的配置数据无效。
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **422 Unprocessable Entity**: 请求体验证失败。
    -   **500 Internal Server Error**: 文件写入错误或更新时发生未知错误。

### 5.2 用户管理

#### 5.2.1 获取所有用户列表

-   **路径**: `/users`
-   **方法**: `GET`
-   **摘要**: 管理员获取系统中的所有用户列表（分页）。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `skip` (integer, 可选, 默认: 0): 跳过的记录数。
    -   `limit` (integer, 可选, 默认: 100): 返回的最大记录数。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // List[UserPublicProfile] 模型
        [
            { /* ... UserPublicProfile 结构 ... */ }
        ]
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。

#### 5.2.2 获取特定用户详情

-   **路径**: `/users/{user_uid}`
-   **方法**: `GET`
-   **摘要**: 管理员获取指定 UID 用户的详细信息。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
-   **路径参数**:
    -   `user_uid` (string, 必需): 要获取详情的用户的 UID。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // UserPublicProfile 模型
        { /* ... UserPublicProfile 结构 ... */ }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **404 Not Found**: 用户未找到。

#### 5.2.3 更新特定用户信息

-   **路径**: `/users/{user_uid}`
-   **方法**: `PUT`
-   **摘要**: 管理员更新指定 UID 用户的信息，包括昵称、邮箱、QQ、标签和可选的密码重置。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
-   **路径参数**:
    -   `user_uid` (string, 必需): 要更新的用户的 UID。
-   **请求体**: `application/json`
    ```json
    // AdminUserUpdate 模型 (所有字段可选)
    {
        "nickname": "string (新的用户昵称)",
        "email": "string (新的电子邮箱, EmailStr)",
        "qq": "string (新的QQ号码)",
        "tags": ["string (新的用户标签列表, UserTag 枚举值, 例如 ['user', 'limited'])"],
        "new_password": "string (可选, 为用户设置新密码, 8-48 位)"
    }
    ```
-   **响应**:
    -   **200 OK**: 更新成功
        ```json
        // UserPublicProfile 模型 (更新后的用户信息)
        { /* ... UserPublicProfile 结构 ... */ }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **404 Not Found**: 用户未找到或更新失败。
    -   **422 Unprocessable Entity**: 请求体验证失败。

### 5.3 试卷管理

#### 5.3.1 获取所有试卷摘要

-   **路径**: `/paper/all`
-   **方法**: `GET`
-   **摘要**: 获取内存中所有试卷的摘要信息列表，按创建时间倒序排列。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `skip` (integer, 可选, 默认: 0): 跳过的记录数。
    -   `limit` (integer, 可选, 默认: 100): 返回的最大记录数。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // List[PaperAdminView] 模型
        [
            {
                "paper_id": "string",
                "user_uid": "string (可选)",
                "creation_time_utc": "string (ISO格式)",
                "creation_ip": "string",
                "difficulty": "string (可选)",
                "count": "integer (总题数)",
                "finished_count": "integer (可选, 已作答题数)",
                "correct_count": "integer (可选, 正确题数/得分)",
                "score": "integer (可选, 原始得分)",
                "score_percentage": "float (可选, 百分制得分)",
                "submission_time_utc": "string (可选, ISO格式)",
                "submission_ip": "string (可选)",
                "pass_status": "string (可选)",
                "passcode": "string (可选)",
                "last_update_time_utc": "string (可选, ISO格式)",
                "last_update_ip": "string (可选)"
            }
            // ...
        ]
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **500 Internal Server Error**: 获取试卷列表时发生错误。

#### 5.3.2 获取指定试卷的详细信息

-   **路径**: `/paper/`
-   **方法**: `GET`
-   **摘要**: 获取内存中指定 `paper_id` 的试卷的完整详细信息。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `paper_id` (string, 必需): 要获取详情的试卷ID。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // PaperFullDetailModel 模型
        {
            "paper_id": "string",
            "user_uid": "string (可选)",
            "creation_time_utc": "string (ISO格式)",
            "creation_ip": "string",
            "difficulty": "string (可选)",
            "paper_questions": [ // 试卷的原始问题列表（含答案映射）
                { // PaperQuestionInternalDetail 模型
                    "body": "string",
                    // "question_type": "string",
                    "correct_choices_map": { "choice_id": "choice_text" }, // 可选
                    "incorrect_choices_map": { "choice_id": "choice_text" } // 可选
                }
                // ...
            ],
            "score": "integer (可选)",
            "score_percentage": "float (可选)",
            "submitted_answers_card": ["string (可选, 用户提交的答案卡, 未答为null)"],
            "submission_time_utc": "string (可选, ISO格式)",
            "submission_ip": "string (可选)",
            "pass_status": "string (可选)",
            "passcode": "string (可选)",
            "last_update_time_utc": "string (可选, ISO格式)",
            "last_update_ip": "string (可选)"
        }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **404 Not Found**: 试卷 ID 未找到。
    -   **500 Internal Server Error**: 试卷数据格式错误。

#### 5.3.3 删除指定的试卷

-   **路径**: `/paper/`
-   **方法**: `DELETE`
-   **摘要**: 从内存中删除指定 `paper_id` 的试卷记录。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `paper_id` (string, 必需): 要删除的试卷ID。
-   **响应**:
    -   **200 OK**: 删除成功
        ```json
        {
            "message": "Paper {paper_id} successfully deleted from memory."
        }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **404 Not Found**: 试卷 ID 未找到，无法删除。

### 5.4 题库管理

#### 5.4.1 获取指定难度的题库

-   **路径**: `/question/`
-   **方法**: `GET`
-   **摘要**: 获取指定难度题库的所有题目。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `difficulty` (string, 必需): 题库难度 (例如 "easy", "hybrid", "hard")。
-   **响应**:
    -   **200 OK**: 成功
        ```json
        // List[QuestionModel] 模型
        [
            {
                "body": "string (问题题干)",
                "question_type": "string (题目类型)",
                "correct_choices": ["string (可选, 正确答案列表)"],
                "incorrect_choices": ["string (可选, 错误答案列表)"],
                "num_correct_to_select": "integer (可选)",
                "correct_fillings": ["string (可选, 填空题答案)"],
                "ref": "string (可选, 答案解释)"
            }
            // ...
        ]
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **404 Not Found**: 指定难度的题库未加载或不存在。
    -   **500 Internal Server Error**: 题库数据格式错误。

#### 5.4.2 为指定难度的题库添加题目

-   **路径**: `/question/`
-   **方法**: `POST`
-   **摘要**: 向指定难度的题库 JSON 文件添加一个新题目，并触发内存中题库的重新加载。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `difficulty` (string, 必需): 题库难度。
-   **请求体**: `application/json`
    ```json
    // QuestionModel 模型
    {
        "body": "string (问题题干)",
        "question_type": "string (题目类型, 例如 'single_choice')",
        "correct_choices": ["string (正确答案列表)"], // 对于选择题
        "incorrect_choices": ["string (错误答案列表)"], // 对于选择题
        "num_correct_to_select": "integer (可选, 多选题需选正确答案数)",
        "correct_fillings": ["string (填空题答案)"], // 对于填空题
        "ref": "string (可选, 答案解释或参考)"
    }
    ```
-   **响应**:
    -   **201 Created**: 题目添加成功
        ```json
        // QuestionModel 模型 (已添加的题目)
        { /* ... 同请求体 ... */ }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **422 Unprocessable Entity**: 请求体验证失败。
    -   **500 Internal Server Error**: 添加题目失败 (例如文件操作错误)。

#### 5.4.3 删除指定题库的指定题目

-   **路径**: `/question/`
-   **方法**: `DELETE`
-   **摘要**: 根据索引从指定难度的题库 JSON 文件中删除一个题目，并触发内存中题库的重新加载。
-   **请求参数 (Query)**:
    -   `token` (string, 必需): 管理员访问 Token。
    -   `difficulty` (string, 必需): 题库难度。
    -   `index` (integer, 必需, 别名 `_index`): 要删除的题目索引 (从0开始)。
-   **响应**:
    -   **200 OK**: 删除成功
        ```json
        {
            "message": "Successfully deleted question at index {_index} from bank '{difficulty_value}'.",
            "deleted_question_body": "string (被删除题目的题干)"
        }
        ```
    -   **401 Unauthorized / 403 Forbidden**: 认证或权限不足。
    -   **404 Not Found**: 题库文件未找到或题目索引无效。
    -   **500 Internal Server Error**: 删除题目失败 (例如文件操作错误)。

---

## 附录: 枚举类型

### DifficultyLevel (难度级别)

系统通过读取 `data/library/index.json` 文件动态生成此枚举。通常可能包含：

-   `easy`
-   `hybrid`
-   `hard`
-   ... (其他在 `index.json` 中定义的 `id`)

### UserTag (用户标签)

-   `admin`: 管理员
-   `user`: 普通用户
-   `banned`: 禁用用户
-   `limited`: 受限用户
-   `grader`: 批阅者
-   `examiner`: 出题者/题库管理员
-   `manager`: 运营管理员

---

## 错误码与状态说明

除了标准的 HTTP 状态码外，部分接口可能在响应体中包含自定义的 `status_code` (文本) 和 `code` (数字) 字段来提供更具体的业务状态信息。

-   **HTTP 200 OK**: 请求成功。
-   **HTTP 201 Created**: 资源创建成功。
-   **HTTP 204 No Content**: 请求成功，但无内容返回 (例如密码修改成功)。
-   **HTTP 400 Bad Request**: 请求无效，例如参数错误、业务逻辑不满足 (如题目不足)。响应体中的 `detail` 字段通常包含错误描述。
-   **HTTP 401 Unauthorized**: 未认证或认证失败。通常由于 Token 无效、过期或缺失。响应头可能包含 `WWW-Authenticate`。
-   **HTTP 403 Forbidden**: 已认证，但无权访问资源。例如用户被封禁，或非管理员尝试访问管理员接口。
-   **HTTP 404 Not Found**: 请求的资源不存在。
-   **HTTP 409 Conflict**: 资源冲突，例如尝试创建已存在的用户。
-   **HTTP 422 Unprocessable Entity**: 请求体数据无法通过 Pydantic 模型验证。响应体通常包含详细的验证错误信息。
-   **HTTP 429 Too Many Requests**: 请求频率超过速率限制。
-   **HTTP 500 Internal Server Error**: 服务器内部发生未预期的错误。

**自定义业务状态码示例 (在响应体中):**

-   `AuthStatusResponse.status_code`:
    -   `"WRONG"`: 用户名或密码错误，或旧 Token 无效。
    -   `"DUPLICATE"`: 用户名已存在。
-   `GradingResultResponse.status_code` / `UpdateProgressResponse.status_code`:
    -   `"PASSED"`: 考试通过。
    -   `"FAILED"`: 考试未通过。
    -   `"ALREADY_GRADED"`: 试卷已被批改。
    -   `"ALREADY_COMPLETED"`: 试卷已完成 (不能再更新)。
    -   `"PROGRESS_SAVED"`: 进度已保存。
    -   `"NOT_FOUND"`: 试卷未找到。
    -   `"INVALID_SUBMISSION"` / `"INVALID_ANSWERS_LENGTH"`: 提交的答案无效。
    -   `"INVALID_PAPER_STRUCTURE"`: 试卷内部结构错误。
