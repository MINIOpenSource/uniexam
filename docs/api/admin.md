# 管理员接口 (Admin API)

本文档描述了仅供管理员使用的API端点。所有这些端点都需要有效的管理员Token进行认证（通过请求参数 `?token={ADMIN_ACCESS_TOKEN}` 传递），并且通常以 `/admin` 作为路径前缀。

## 1. 系统配置管理 API (System Configuration Management API)

基础路径: `/admin/settings`

这些端点允许管理员查看和修改应用的核心配置。

### 1.1 获取当前系统配置 (`GET /settings`)

-   **摘要**: 获取当前系统配置
-   **描述**: 管理员获取当前应用的主要配置项信息。注意：此接口返回的配置主要反映 `settings.json` 文件的内容，可能不完全包含通过环境变量最终生效的配置值。敏感信息（如数据库密码）不会在此接口返回。
-   **认证**: 需要管理员权限。
-   **响应**:
    -   **`200 OK`**: 成功获取配置信息。返回 `SettingsResponseModel`。
        ```json
        // SettingsResponseModel 示例 (部分字段)
        {
            "app_name": "在线考试系统",
            "token_expiry_hours": 24,
            "log_level": "INFO",
            // ... 其他配置项
        }
        ```
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员或无权访问。
    -   **`500 Internal Server Error`**: 服务器内部错误导致无法获取配置。

### 1.2 更新系统配置 (`POST /settings`)

-   **摘要**: 更新系统配置
-   **描述**: 管理员更新应用的部分或全部可配置项。请求体中仅需包含需要修改的字段及其新值。更新操作会写入 `settings.json` 文件并尝试动态重新加载配置到应用内存。注意：通过环境变量设置的配置项具有最高优先级，其在内存中的值不会被此API调用修改，但 `settings.json` 文件中的对应值会被更新。
-   **认证**: 需要管理员权限。
-   **请求体** (`application/json`): `SettingsUpdatePayload` 模型
    ```json
    // SettingsUpdatePayload 示例
    {
        "app_name": "新版在线考试平台",
        "token_expiry_hours": 48
    }
    ```
-   **响应**:
    -   **`200 OK`**: 配置成功更新并已重新加载。返回更新后的 `SettingsResponseModel`。
    -   **`400 Bad Request`**: 提供的配置数据无效或不符合约束。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`422 Unprocessable Entity`**: 请求体验证失败。
    -   **`500 Internal Server Error`**: 配置文件写入失败或更新时发生未知服务器错误。

---

## 2. 用户账户管理 API (User Account Management API)

基础路径: `/admin/users`

这些端点允许管理员管理用户账户。

### 2.1 管理员获取用户列表 (`GET /users`)

-   **摘要**: 管理员获取用户列表
-   **描述**: 获取系统中的用户账户列表，支持分页查询。返回的用户信息不包含敏感数据（如哈希密码）。
-   **认证**: 需要管理员权限。
-   **请求参数 (Query Parameters)**:
    -   `skip` (integer, 可选, 默认: 0): 跳过的记录数，用于分页 (最小值为0)。
    -   `limit` (integer, 可选, 默认: 100): 返回的最大记录数 (最小值为1，最大值为200)。
-   **响应**:
    -   **`200 OK`**: 成功获取用户列表。返回 `List[UserPublicProfile]`。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`500 Internal Server Error`**: 获取用户列表时发生服务器内部错误。

### 2.2 管理员获取特定用户信息 (`GET /users/{user_uid}`)

-   **摘要**: 管理员获取特定用户信息
-   **描述**: 根据用户UID（用户名）获取其公开的详细信息，不包括密码等敏感内容。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `user_uid` (string, 必需): 要获取详情的用户的UID。
-   **响应**:
    -   **`200 OK`**: 成功获取用户信息。返回 `UserPublicProfile` 模型。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定UID的用户未找到。

### 2.3 管理员更新特定用户信息 (`PUT /users/{user_uid}`)

-   **摘要**: 管理员更新特定用户信息
-   **描述**: 管理员修改用户的昵称、邮箱、QQ、用户标签，或为其重置密码。请求体中仅需包含需要修改的字段。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `user_uid` (string, 必需): 要更新信息的用户的UID。
-   **请求体** (`application/json`): `AdminUserUpdate` 模型
-   **响应**:
    -   **`200 OK`**: 用户信息成功更新。返回更新后的 `UserPublicProfile` 模型。
    -   **`400 Bad Request`**: 提供的更新数据无效（例如，无效的标签值）。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定UID的用户未找到。
    -   **`422 Unprocessable Entity`**: 请求体验证失败。

---

## 3. 试卷管理 API (Paper Management API)

基础路径: `/admin/papers`

这些端点允许管理员管理用户生成的试卷。

### 3.1 管理员获取所有试卷摘要列表 (`GET /papers`)

-   **摘要**: 管理员获取所有试卷摘要列表
-   **描述**: 获取系统生成的所有试卷的摘要信息列表，支持分页。
-   **认证**: 需要管理员权限。
-   **请求参数 (Query Parameters)**:
    -   `skip` (integer, 可选, 默认: 0): 跳过的记录数。
    -   `limit` (integer, 可选, 默认: 100): 返回的最大记录数。
-   **响应**:
    -   **`200 OK`**: 成功获取试卷摘要列表。返回 `List[PaperAdminView]`。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`500 Internal Server Error`**: 获取试卷列表时发生服务器内部错误。

### 3.2 管理员获取特定试卷的完整信息 (`GET /papers/{paper_id}`)</h3>

-   **摘要**: 管理员获取特定试卷的完整信息
-   **描述**: 根据试卷ID获取其完整详细信息。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `paper_id` (string, 必需, UUID格式): 要获取详情的试卷ID。
-   **响应**:
    -   **`200 OK`**: 成功获取试卷详细信息。返回 `PaperFullDetailModel`。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定ID的试卷未找到。
    -   **`500 Internal Server Error`**: 获取试卷详情时发生服务器内部错误。

### 3.3 管理员删除特定试卷 (`DELETE /papers/{paper_id}`)</h3>

-   **摘要**: 管理员删除特定试卷
-   **描述**: 根据试卷ID永久删除一份试卷。此操作需谨慎。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `paper_id` (string, 必需, UUID格式): 要删除的试卷ID。
-   **响应**:
    -   **`204 No Content`**: 试卷成功删除。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定ID的试卷未找到。
    -   **`500 Internal Server Error`**: 删除试卷时发生服务器内部错误。

---

## 4. 题库管理 API (Question Bank Management API)

基础路径: `/admin/question-banks`

这些端点允许管理员管理题库的元数据和题目内容。

### 4.1 管理员获取所有题库的元数据列表 (`GET /question-banks`)</h3>

-   **摘要**: 管理员获取所有题库的元数据列表
-   **描述**: 获取系统中所有题库的元数据信息列表。
-   **认证**: 需要管理员权限。
-   **响应**:
    -   **`200 OK`**: 成功获取题库元数据列表。返回 `List[LibraryIndexItem]`。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`500 Internal Server Error`**: 获取题库元数据时发生服务器内部错误。

### 4.2 管理员获取特定难度题库的完整内容 (`GET /question-banks/{difficulty_id}/content`)</h3>

-   **摘要**: 管理员获取特定难度题库的完整内容
-   **描述**: 根据难度ID获取指定题库的元数据及其包含的所有题目详情。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `difficulty_id` (string, 必需): 要获取内容的题库难度ID (例如: "easy", "hybrid")。
-   **响应**:
    -   **`200 OK`**: 成功获取题库内容。返回 `QuestionBank` 模型。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定难度的题库未找到。
    -   **`500 Internal Server Error`**: 获取题库内容时发生服务器内部错误。

### 4.3 管理员向特定题库添加新题目 (`POST /question-banks/{difficulty_id}/questions`)</h3>

-   **摘要**: 管理员向特定题库添加新题目
-   **描述**: 向指定难度的题库中添加一道新的题目。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `difficulty_id` (string, 必需): 要添加题目的题库难度ID。
-   **请求体** (`application/json`): `QuestionModel` 模型
-   **响应**:
    -   **`201 Created`**: 题目成功添加到题库。返回已添加的 `QuestionModel`。
    -   **`400 Bad Request`**: 提供的题目数据无效。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定难度的题库未找到。
    -   **`422 Unprocessable Entity`**: 请求体验证失败。
    -   **`500 Internal Server Error`**: 添加题目到题库时发生服务器内部错误。

### 4.4 管理员从特定题库删除题目 (`DELETE /question-banks/{difficulty_id}/questions`)</h3>

-   **摘要**: 管理员从特定题库删除题目
-   **描述**: 根据题目在题库列表中的索引，从指定难度的题库中删除一道题目。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `difficulty_id` (string, 必需): 要删除题目的题库难度ID。
-   **请求参数 (Query Parameters)**:
    -   `index` (integer, 必需, ge=0): 要删除的题目在列表中的索引 (从0开始)。
-   **响应**:
    -   **`204 No Content`**: 题目成功删除。
    -   **`400 Bad Request`**: 提供的索引无效。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定难度的题库或指定索引的题目未找到。
    -   **`500 Internal Server Error`**: 删除题目时发生服务器内部错误。

---

## 5. 阅卷接口 (Grading API)

基础路径: `/admin/grading`

这些端点用于管理员（或未来可能的阅卷员角色）对包含主观题的试卷进行人工批阅和管理。

### 5.1 获取待人工批阅的试卷列表 (`GET /pending-papers`)

-   **摘要**: 获取待批阅试卷列表
-   **描述**: 返回一个试卷列表，这些试卷已由用户提交，包含未完成人工批阅的主观题 (`pending_manual_grading_count > 0` 且 `pass_status` 为 `PENDING_REVIEW`)。
-   **认证**: 需要管理员权限。
-   **请求参数 (Query Parameters)**:
    -   `skip` (integer, 可选, 默认: 0): 跳过的记录数，用于分页。
    -   `limit` (integer, 可选, 默认: 100): 返回的最大记录数。
-   **响应**:
    -   **`200 OK`**: 成功获取待批阅试卷列表。返回 `List[PendingGradingPaperItem]`。
        ```json
        // PendingGradingPaperItem 示例
        [
            {
                "paper_id": "uuid-string-paper1",
                "user_uid": "user001",
                "submission_time_utc": "2024-03-15T10:30:00Z",
                "subjective_questions_count": 5,
                "pending_manual_grading_count": 3,
                "difficulty": "hybrid"
            }
            // ...更多试卷...
        ]
        ```
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`500 Internal Server Error`**: 获取列表时发生服务器内部错误。

### 5.2 获取试卷中待批阅的主观题详情 (`GET /papers/{paper_id}/subjective-questions`)

-   **摘要**: 获取试卷主观题详情（供批阅）
-   **描述**: 返回指定试卷ID中所有主观题的详细列表，供阅卷员查看题目内容、学生答案、参考答案及评分标准，并可查看或输入批阅结果。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `paper_id` (UUID, 必需): 要获取主观题详情的试卷ID。
-   **响应**:
    -   **`200 OK`**: 成功获取主观题列表。返回 `List[SubjectiveQuestionForGrading]`。
        ```json
        // SubjectiveQuestionForGrading 示例
        [
            {
                "internal_question_id": "uuid-internal-q1",
                "body": "请论述人工智能在教育领域的应用前景。",
                "question_type": "essay_question",
                "student_subjective_answer": "学生关于AI应用的回答文本...",
                "standard_answer_text": "参考答案要点：1. 个性化学习...",
                "scoring_criteria": "论点清晰5分，论据充分3分...",
                "manual_score": null, // 如果未批改
                "teacher_comment": null, // 如果未批改
                "is_graded_manually": false
            }
            // ...更多主观题...
        ]
        ```
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定的试卷ID未找到。
    -   **`500 Internal Server Error`**: 获取题目详情时发生服务器内部错误。

### 5.3 提交单个主观题的批阅结果 (`POST /papers/{paper_id}/questions/{question_internal_id}/grade`)

-   **摘要**: 提交主观题批阅结果
-   **描述**: 阅卷员提交对特定试卷中特定主观题的评分和评语。成功提交后，如果该试卷的所有主观题均已批改，系统将自动计算最终总分和通过状态。
-   **认证**: 需要管理员权限。
-   **路径参数 (Path Parameters)**:
    -   `paper_id` (UUID, 必需): 目标试卷的ID。
    -   `question_internal_id` (string, 必需): 试卷中被批阅题目的内部唯一ID。
-   **请求体** (`application/json`): `GradeSubmissionPayload` 模型
    ```json
    // GradeSubmissionPayload 示例
    {
        "manual_score": 8.5,
        "teacher_comment": "论述基本完整，但缺乏部分细节。"
    }
    ```
-   **响应**:
    -   **`204 No Content`**: 批阅结果成功保存。
    -   **`400 Bad Request`**: 请求数据无效（例如，分数超出范围，或目标题目不是主观题）。
    -   **`401 Unauthorized`**: Token缺失或无效。
    -   **`403 Forbidden`**: 当前用户非管理员。
    -   **`404 Not Found`**: 指定的试卷ID或题目内部ID未找到。
    -   **`422 Unprocessable Entity`**: 请求体验证失败。
    -   **`500 Internal Server Error`**: 保存批阅结果时发生服务器内部错误。

---
