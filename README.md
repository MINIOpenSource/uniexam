# 在线考试系统后端 API

欢迎使用在线考试系统后端 API 项目！这是一个基于 Python 和 FastAPI 构建的 RESTful API 服务，旨在为在线考试应用提供核心后端支持。

## 项目概述

本项目提供了一套完整的 API 接口，用于实现在线考试的各项功能，包括用户管理、试卷生成、答题、自动批改、历史记录查询以及管理员后台管理等。系统设计注重模块化和可扩展性，方便后续的功能迭代和维护。

## 主要功能

-   **用户认证**:
    -   用户注册与登录
    -   Token 刷新机制
-   **用户管理**:
    -   查看和修改个人资料
    -   修改密码
-   **考试流程**:
    -   根据难度动态生成试卷
    -   保存答题进度
    -   提交试卷并自动批改
    -   查看考试历史和试卷详情
-   **题库管理**:
    -   动态加载不同难度的题库
    -   管理员可查看、添加、删除题目
-   **系统配置**:
    -   管理员可查看和修改应用配置
-   **管理员后台**:
    -   用户管理 (查看、修改用户属性、重置密码)
    -   试卷管理 (查看所有试卷摘要、详情、删除试卷)
    -   题库管理
    -   系统配置管理
-   **安全性**:
    -   密码哈希存储
    -   API 速率限制
    -   基于角色的访问控制 (用户标签)
-   **日志记录**:
    -   详细的应用运行日志，支持文件和控制台输出
    -   可配置的日志级别
-   **命令行工具 (`examctl.py`)**:
    -   方便管理员进行用户添加、属性修改、密码重置等操作

## 技术栈

-   **后端框架**: FastAPI - 高性能、易于学习、快速编码的现代 Python Web 框架。
-   **数据验证**: Pydantic - 基于 Python 类型提示的数据验证和设置管理。
-   **Web 服务器**: Uvicorn - ASGI 服务器，用于运行 FastAPI 应用。
-   **密码哈希**: Passlib - 强大的密码哈希库。
-   **环境变量管理**: python-dotenv - 从 `.env` 文件加载环境变量。
-   **数据库**: 基于 JSON 文件的简单数据持久化 (用户数据、试卷数据、题库)。
-   **开发语言**: Python 3.10+

## 项目结构

```
backend/
├── app/                     # FastAPI 应用核心代码
│   ├── core/                # 核心逻辑 (配置, 安全, 速率限制等)
│   ├── crud/                # 数据增删改查操作 (CRUD)
│   ├── models/              # Pydantic 数据模型
│   ├── utils/               # 工具函数
│   ├── admin_routes.py      # 管理员 API 路由
│   ├── main.py              # FastAPI 应用主入口
│   └── __init__.py
├── data/                    # 应用数据存储目录 (自动创建)
│   ├── library/             # 题库文件目录
│   │   └── index.json       # 题库索引文件
│   ├── users.json           # 用户数据文件
│   ├── papers.json          # 试卷数据文件
│   └── settings.json        # 应用配置文件
├── venv/                    # Python 虚拟环境 (建议)
├── .env                     # 环境变量配置文件 (需手动创建)
├── APIDocument.md           # API 接口文档
├── examctl.py               # 命令行管理工具
├── requirements.txt         # Python 依赖包列表
├── run.py                   # Uvicorn 启动脚本
└── README.md                # 本文档
```

## 安装与启动

### 1. 环境准备

-   Python 3.10 或更高版本
-   pip (Python 包安装器)
-   (推荐) Python 虚拟环境工具 (如 `venv`)

### 2. 克隆项目 (如果适用)

```bash
git clone <your_repository_url>
cd backend # 进入项目后端目录
```

### 3. 创建并激活虚拟环境 (推荐)

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置环境变量

在项目根目录 (例如 `/www/ciexam/backend/`) 创建一个名为 `.env` 的文件，并根据需要配置以下内容。可以参考提供的 `/www/ciexam/backend/.env` 文件示例：

```properties
# 应用基本配置
APP_DOMAIN="http://localhost:17071" # API 访问域名/IP和端口
FRONTEND_DOMAIN="http://localhost:3000" # 前端应用的访问地址，用于CORS配置
LISTENING_PORT="17071" # API 服务监听端口

# 初始Admin密码 (可选)
# 如果不设置，且 settings.json 中也未设置，首次运行会随机生成一个admin密码并打印到日志
# INITIAL_ADMIN_PASSWORD="yoursecureadminpassword"
```

**注意**: `APP_DOMAIN` 和 `FRONTEND_DOMAIN` 对于本地开发可能不是必需的，但对于部署和 CORS 配置非常重要。`LISTENING_PORT` 应与您希望服务运行的端口一致。

### 6. 初始化数据与管理员账户

首次运行应用时，系统会自动在 `data/` 目录下创建所需的数据文件 (`users.json`, `papers.json`, `settings.json`) 和题库目录。

**管理员账户**:
-   默认管理员用户名为 `admin`。
-   如果 `.env` 文件中设置了 `INITIAL_ADMIN_PASSWORD`，则该密码将用于 `admin` 用户。
-   如果未设置 `INITIAL_ADMIN_PASSWORD`，且 `data/settings.json` 中也未指定，系统会在首次启动时为 `admin` 用户生成一个随机密码，并将其打印到控制台日志中。请务必记录此密码。
-   您也可以使用 `examctl.py` 工具手动添加或修改管理员账户。

### 7. 运行应用

在项目根目录 (例如 `/www/ciexam/backend/`) 执行：

```bash
./venv/bin/python run.py
# 或者 (如果虚拟环境已激活)
python run.py
```

服务启动后，默认会在 `0.0.0.0` 上监听 `.env` 文件中 `LISTENING_PORT` 指定的端口 (例如 `17071`)。

API 文档 (Swagger UI) 通常可在 `http://localhost:17071/docs` 访问。

## API 文档

详细的 API 接口说明、请求格式和响应格式，请参阅项目根目录下的 APIDocument.md 文件。

## 命令行管理工具 (`examctl.py`)

项目提供了一个命令行工具 `examctl.py` 用于执行一些管理操作，例如：

-   **添加用户**:
    ```bash
    python examctl.py add-user --uid <username> --password <password> [--nickname <nickname>] [--email <email>] [--qq <qq>]
    ```
-   **更新用户属性**:
    ```bash
    python examctl.py update-user --uid <username> [--nickname <nickname>] [--email <email>] [--qq <qq>] [--tags <tag1,tag2>]
    ```
-   **修改用户密码**:
    ```bash
    python examctl.py change-password --uid <username> --new-password <new_password>
    ```

使用 `--help` 查看更多命令和选项：
```bash
python examctl.py --help
python examctl.py add-user --help
```

## 配置

应用的主要配置通过以下方式管理：

-   **`.env` 文件**: 用于存储敏感信息和特定于环境的配置 (如端口、域名、初始密码)。
-   **`data/settings.json` 文件**: 存储应用的大部分可配置参数 (如 Token 有效期、默认题目数量、速率限制等)。此文件由应用自动创建和管理，管理员也可以通过 API 修改。

配置加载优先级：环境变量 (`.env`) > `settings.json` > Pydantic 模型默认值。

## 贡献

欢迎对本项目进行贡献！如果您有任何建议、发现 Bug 或希望添加新功能，请随时通过 Issue 或 Pull Request 的方式参与。

## 许可证

本项目采用 GPLv3 许可证

---

感谢您的使用！