# 贡献指南

我们非常欢迎您为本项目做出贡献！无论是报告错误、提出改进建议，还是直接贡献代码，您的参与都对项目至关重要。

## 如何贡献

###报告问题 (Issues)

-   如果您在项目中发现了错误 (Bug)、有功能建议或任何疑问，请通过提交 Issue 来告诉我们。
-   在提交 Issue 前，请先搜索现有的 Issues，看是否已有类似内容。
-   提交 Issue 时，请尽可能详细地描述问题或建议，包括：
    -   **错误报告**: 复现步骤、期望行为、实际行为、错误信息、相关截图、您的环境信息（操作系统、Python版本等）。
    -   **功能建议**: 清晰描述建议的功能、它能解决什么问题、以及可能的实现思路。

### 贡献代码 (Pull Requests)

1.  **Fork 本仓库**: 点击仓库右上角的 "Fork" 按钮，将项目复刻到您自己的 GitHub 账户下。
2.  **克隆您的 Fork**: `git clone https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git`
3.  **创建新分支**: `git checkout -b feature/your-feature-name` 或 `bugfix/issue-number`。请为您的分支选择一个描述性的名称。
4.  **进行修改**:
    *   确保您的代码风格与项目现有代码保持一致 (遵循 PEP8，使用 Black 和 Ruff 进行格式化与检查)。
    *   为新增的功能或重要的代码段添加清晰的中文文档字符串和注释。
    *   如果您添加了新功能，请考虑添加相应的单元测试。
5.  **代码格式化与检查**: 在提交前，请运行：
    ```bash
    python -m black .
    python -m ruff format .
    python -m ruff check . --fix
    ```
6.  **提交您的更改**: `git commit -m "feat: 添加了 XXX 功能"` 或 `fix: 修复了 YYY 问题 (#issue_number)`。请遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范编写提交信息。
7.  **推送代码到您的 Fork**: `git push origin feature/your-feature-name`
8.  **创建 Pull Request**: 返回原始仓库页面，点击 "New pull request" 按钮，选择您的分支与目标分支 (通常是 `main` 或 `develop`)。
    *   在 Pull Request 描述中，清晰说明您所做的更改、解决的问题等。如果关联到某个 Issue，请使用 `Closes #issue_number`。

## 开发环境设置

请参考项目主 `README.md` 中的“快速开始”部分，使用 `install.sh` 脚本来设置您的本地开发环境。

## 文档预览与构建 (Previewing and Building Documentation)

本项目使用 MkDocs 和 Material for MkDocs 主题来生成文档网站。

-   **安装依赖**:
    确保您已安装项目依赖，特别是 `mkdocs` 和 `mkdocs-material`。可以运行 `pip install -r requirements.txt` 来安装或更新。

-   **本地预览文档**:
    在项目根目录下运行以下命令，可以在本地启动一个实时预览服务器，通常访问 `http://127.0.0.1:8000` 即可查看：
    ```bash
    python -m mkdocs serve
    ```
    当您修改 `docs/` 目录下的 Markdown 文件或 `mkdocs.yml` 配置文件时，网页会自动刷新。

-   **构建静态文档**:
    要生成静态的 HTML 文档网站（通常用于部署），请在项目根目录下运行：
    ```bash
    python -m mkdocs build --clean
    ```
    构建后的文件将默认输出到项目根目录下的 `site/` 文件夹中。`--clean` 参数表示在构建前清除旧的构建文件。

## 行为准则

我们期望所有贡献者都能遵守友好和互相尊重的社区行为准则。

感谢您的贡献！
