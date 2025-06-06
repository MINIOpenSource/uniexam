# API 文档 - 在线考试系统

版本: 3.0.0

## 简介

本文档详细描述了在线考试系统的 API 接口。系统功能包括用户认证、试卷获取、答题、进度保存、历史记录查看以及管理员后台管理等。

本 API 文档分为以下几个主要部分：

-   [用户、认证与核心考试功能](./user_exam.md)
-   [管理员接口](./admin.md)

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

## 错误处理与HTTP状态码

本API力求遵循标准的HTTP状态码来指示请求的结果。

-   **`200 OK`**: 请求成功执行，响应体中通常包含所请求的数据。
-   **`201 Created`**: 资源成功创建（例如，用户注册成功后），响应体中可能包含新创建的资源或相关信息（如Token）。
-   **`204 No Content`**: 请求成功执行，但响应体中无内容返回（例如，用户成功修改密码后）。
-   **`400 Bad Request`**: 客户端请求无效。这可能因为参数错误、业务逻辑不满足（如请求的题目数量不足以出题）、或提交的数据格式不正确但不符合特定验证错误类型。响应体的 `detail` 字段通常包含具体的错误描述。
-   **`401 Unauthorized`**: 未认证或认证失败。通常由于Token无效、过期、缺失，或凭证不正确。响应头可能包含 `WWW-Authenticate`。
-   **`403 Forbidden`**: 用户已认证，但无权访问所请求的资源。例如，用户账户被封禁，或普通用户尝试访问管理员专属接口。
-   **`404 Not Found`**: 请求的资源不存在。例如，查询一个不存在的试卷ID或用户UID。
-   **`409 Conflict`**: 请求与服务器当前状态冲突，无法完成。例如，尝试创建已存在的用户，或提交已被批改的试卷。
-   **`422 Unprocessable Entity`**: 请求体数据虽然格式正确（例如是合法的JSON），但无法通过Pydantic模型的验证规则（如类型错误、必填字段缺失、值不符合约束等）。响应体通常包含详细的字段级验证错误信息。
-   **`429 Too Many Requests`**: 客户端在给定时间内发送的请求过多，已超出速率限制。
-   **`500 Internal Server Error`**: 服务器内部发生未预期的错误，导致无法完成请求。

**关于响应体中的业务状态字段：**
在部分成功响应（如 `200 OK`）的场景下，响应体内的特定字段（例如 `GradingResultResponse` 中的 `status_code` 字段，其值为 `PaperPassStatusEnum` 枚举的成员如 "PASSED" 或 "FAILED"）会提供更细致的业务处理结果。这些字段用于区分业务逻辑上的不同成功状态，而非HTTP层面的错误。对于API错误，应优先参考HTTP状态码和 `HTTPException` 返回的 `detail` 信息。

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
