#!/bin/bash

echo "开始安装脚本..."

# Function to prompt for user input
ask_yes_no() {
    while true; do
        read -p "$1 (y/n): " yn
        case $yn in
            [Yy]* ) return 0;;
            [Nn]* ) return 1;;
            * ) echo "请输入 y 或 n.";;
        esac
    done
}

# Function to prompt for variable input
ask_for_var() {
    local var_name="$1"
    local current_value="$2"
    local prompt_message="$3"
    local default_value="$4"

    if [ -n "$current_value" ]; then
        read -p "$prompt_message (当前值: $current_value, 直接回车跳过): " new_value
    else
        if [ -n "$default_value" ]; then
             read -p "$prompt_message (默认值: $default_value, 直接回车使用默认值): " new_value
        else
             read -p "$prompt_message (直接回车跳过): " new_value
        fi
    fi

    if [ -z "$new_value" ]; then
        if [ -n "$current_value" ]; then
            echo "$current_value"
        else
            echo "$default_value"
        fi
    else
        echo "$new_value"
    fi
}

# Function to setup systemd service
setup_systemd_service() {
    echo ""
    echo "步骤 5: 设置 systemd 服务 (可选)..."
    if ask_yes_no "您想设置 systemd 服务以便在后台运行应用吗？"; then
        echo "设置 systemd 服务需要 sudo 权限来复制服务文件。"
        local service_name="yourapp" # Default service name, can be customized
        # Consider prompting for service_name if needed:
        # read -p "请输入服务名称 (默认: yourapp): " custom_service_name
        # if [ -n "$custom_service_name" ]; then
        #    service_name="$custom_service_name"
        # fi
        local service_file_tmp="${service_name}.service.tmp"
        local service_file_target="/etc/systemd/system/${service_name}.service"
        local app_dir=$(pwd)
        local python_exec="$app_dir/$VENV_DIR/bin/python"
        local app_main_script="$app_dir/app/main.py"
        local env_file_abs="$app_dir/.env"
        local current_user=$(whoami)

        echo "正在生成服务文件内容到 '$service_file_tmp'..."

        cat > "$service_file_tmp" << EOF
[Unit]
Description=My Application Service
After=network.target

[Service]
User=$current_user
WorkingDirectory=$app_dir
EnvironmentFile=$env_file_abs
ExecStart=$python_exec $app_main_script
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
        echo "成功: 服务文件内容已生成到 '$service_file_tmp'."
        echo ""
        echo "请执行以下命令来安装和启动服务:"
        echo "---------------------------------------------------------------------"
        echo "1. 复制服务文件:"
        echo "   sudo cp \"$service_file_tmp\" \"$service_file_target\""
        echo ""
        echo "2. 重新加载 systemd 管理器配置:"
        echo "   sudo systemctl daemon-reload"
        echo ""
        echo "3. 启用服务 (开机自启):"
        echo "   sudo systemctl enable \"${service_name}.service\""
        echo ""
        echo "4. 启动服务:"
        echo "   sudo systemctl start \"${service_name}.service\""
        echo ""
        echo "5. 检查服务状态:"
        echo "   sudo systemctl status \"${service_name}.service\""
        echo ""
        echo "6. (可选) 清理临时服务文件:"
        echo "   rm \"$service_file_tmp\""
        echo "---------------------------------------------------------------------"
        echo "注意: 如果您更改了应用路径、虚拟环境位置或 .env 文件路径，"
        echo "您需要更新服务文件 ($service_file_target) 并重新加载/重启服务。"
    else
        echo "跳过 systemd 服务设置。"
    fi
}

# 1. Check for Python 3.8+
echo ""
echo "步骤 1: 检查 Python 版本..."
python3 -c 'import sys; sys.exit(not (sys.version_info.major == 3 and sys.version_info.minor >= 8))'
if [ $? -ne 0 ]; then
    echo "错误: 需要 Python 3.8 或更高版本。请安装后重试。"
    exit 1
fi
echo "成功: Python 3.8+ 已找到。"

# 2. Create or manage virtual environment
echo ""
echo "步骤 2: 设置 Python 虚拟环境..."
VENV_DIR=".venv"
if [ -d "$VENV_DIR" ]; then
    echo "虚拟环境目录 '$VENV_DIR' 已存在。"
    if ask_yes_no "您想重新创建虚拟环境吗？这将删除现有环境。"; then
        echo "正在删除现有的虚拟环境..."
        rm -rf "$VENV_DIR"
        echo "正在创建新的虚拟环境..."
        virtualenv "$VENV_DIR"
        if [ $? -ne 0 ]; then
            echo "错误: 创建虚拟环境失败。"
            exit 1
        fi
        echo "成功: 新的虚拟环境已创建。"
    else
        echo "使用现有的虚拟环境。"
    fi
else
    echo "正在创建虚拟环境 '$VENV_DIR'..."
    virtualenv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "错误: 创建虚拟环境失败。"
        exit 1
    fi
    echo "成功: 虚拟环境已创建。"
fi

# Activate virtual environment (hint for user for manual activation later)
PIP_CMD="$VENV_DIR/bin/pip"
PYTHON_CMD="$VENV_DIR/bin/python"

# 3. Dependency Installation Confirmation
echo ""
echo "步骤 3: 安装项目依赖..."
if ask_yes_no "是否要安装/更新项目的依赖项 (包括 dev 和 docs extras)？"; then
    echo "正在安装依赖项... 这可能需要一些时间。"
    if [ -f "$PIP_CMD" ]; then
        "$PIP_CMD" install .[dev,docs]
        if [ $? -ne 0 ]; then
            echo "错误: 依赖安装失败。"
            exit 1
        fi
        echo "成功: 依赖项已成功安装。"
    else
        echo "错误: Pip 未在 '$VENV_DIR/bin' 中找到。请确保虚拟环境已正确创建。"
        exit 1
    fi
else
    echo "跳过依赖安装。"
fi

# 4. Guide .env file creation
echo ""
echo "步骤 4: 配置 .env 文件..." # This line is just for context, no change here
ENV_FILE=".env"
ENV_EXAMPLE_FILE=".env.example"

update_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"
    # Escape special characters for sed
    local escaped_value=$(printf '%s\n' "$value" | sed -e 's/[\/&]/\\&/g')
    if grep -q "^$key=" "$file"; then
        sed -i "s/^$key=.*/$key=$escaped_value/" "$file"
    else
        echo "$key=$escaped_value" >> "$file"
    fi
}

env_vars_to_manage=(
    "APP_DOMAIN"
    "FRONTEND_DOMAIN"
    "LISTENING_PORT"
    "INITIAL_ADMIN_PASSWORD"
    "DB_TYPE"
    "DB_JSON_PATH"
    "SQLITE_DB_PATH"
    "POSTGRES_USER"
    "POSTGRES_PASSWORD"
    "POSTGRES_SERVER"
    "POSTGRES_PORT"
    "POSTGRES_DB"
    "MYSQL_USER"
    "MYSQL_PASSWORD"
    "MYSQL_SERVER"
    "MYSQL_PORT"
    "MYSQL_DB"
    "REDIS_HOST"
    "REDIS_PORT"
    "REDIS_DB"
    "REDIS_PASSWORD"
)
default_values=(
    "localhost"
    "http://localhost:3000"
    "17071"
    "admin"
    "sqlite"
    "data/db.json"
    "data/sqlite.db"
    "user"
    "password"
    "localhost"
    "5432"
    "mydb"
    "user"
    "password"
    "localhost"
    "3306"
    "mydb"
    "localhost"
    "6379"
    "0"
    ""
)


if [ ! -f "$ENV_FILE" ]; then
    echo ".env 文件不存在。"
    if [ -f "$ENV_EXAMPLE_FILE" ]; then
        if ask_yes_no "是否要从 '$ENV_EXAMPLE_FILE' 复制并创建新的 '.env' 文件？"; then
            cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
            echo "成功: '$ENV_FILE' 已从 '$ENV_EXAMPLE_FILE' 创建。"
        else
            echo "选择不从 '$ENV_EXAMPLE_FILE' 创建。将创建一个空的 '.env' 文件 (如果需要设置变量)。"
            touch "$ENV_FILE" # Create empty if user declines copy but wants to set vars later
        fi
    else
        echo "'$ENV_EXAMPLE_FILE' 未找到。将创建一个空的 '.env' 文件 (如果需要设置变量)。"
        touch "$ENV_FILE"
    fi

    if ask_yes_no "是否要现在配置 '.env' 文件中的环境变量？"; then
        echo "请输入以下环境变量的值。直接回车将使用默认值 (如果提供) 或留空。"
        for i in "${!env_vars_to_manage[@]}"; do
            var_name="${env_vars_to_manage[$i]}"
            default_val="${default_values[$i]}"
            user_input=$(ask_for_var "$var_name" "" "请输入 $var_name" "$default_val")
            if [ -n "$user_input" ]; then # Only write if user provided or default existed
                update_env_var "$ENV_FILE" "$var_name" "$user_input"
                echo "$var_name 已设置为: $user_input"
            elif [ -n "$default_val" ]; then # Write default if user skipped but default exists
                 update_env_var "$ENV_FILE" "$var_name" "$default_val"
                 echo "$var_name 已设置为默认值: $default_val"
            else
                echo "跳过 $var_name (无输入且无默认值)。"
            fi
        done
        echo "成功: .env 文件配置完成。"
    else
        echo "跳过 .env 文件配置。如果需要，请稍后手动配置 '$ENV_FILE'。"
    fi
else
    echo ".env 文件已存在。"
    if ask_yes_no "是否要检查并更新现有的 '$ENV_FILE' 文件中的环境变量？"; then
        echo "将逐个提示您更新环境变量。直接回车将保留当前值。"
        for i in "${!env_vars_to_manage[@]}"; do
            var_name="${env_vars_to_manage[$i]}"
            current_value=$(grep "^$var_name=" "$ENV_FILE" | cut -d'=' -f2-)
            default_val="${default_values[$i]}" # For display if current is empty

            prompt_msg="更新 $var_name"
            if [ -z "$current_value" ] && [ -n "$default_val" ]; then
                prompt_msg="$prompt_msg (当前未设置, 默认: $default_val)"
            fi

            user_input=$(ask_for_var "$var_name" "$current_value" "$prompt_msg" "$default_val")

            if [ "$user_input" != "$current_value" ] || ([ -z "$current_value" ] && [ -n "$user_input" ]); then
                 if [ -n "$user_input" ]; then
                    update_env_var "$ENV_FILE" "$var_name" "$user_input"
                    echo "$var_name 已更新为: $user_input"
                 else # User cleared the value
                    update_env_var "$ENV_FILE" "$var_name" ""
                    echo "$var_name 已清空。"
                 fi
            else
                echo "$var_name 未更改。"
            fi
        done
        echo "成功: .env 文件检查/更新完成。"
    else
        echo "跳过 .env 文件检查/更新。"
    fi
fi

# Call systemd setup function
setup_systemd_service

# 6. Final Instructions (renumbered from 5)
echo ""
echo "---------------------------------------------------------------------"
echo "安装脚本执行完毕！"
echo ""
echo "重要后续步骤:"
echo ""
echo "1. 激活虚拟环境:"
echo "   为了确保应用能够正确运行，请务必激活 Python 虚拟环境。"
echo "   请运行以下命令:"
echo "   source $VENV_DIR/bin/activate"
echo ""
echo "2. (如果尚未配置或需要修改) 编辑 .env 文件:"
echo "   nano .env  (或其他文本编辑器)"
echo "   确保所有的配置 (如数据库连接、域名等) 都已根据您的环境正确设置。"
echo ""
echo "3. 手动运行应用 (如果未设置 systemd 服务):"
echo "   如果您选择不设置 systemd 服务，或者想要在前台手动运行应用，"
echo "   请在激活虚拟环境后，使用以下命令:"
echo "   $PYTHON_CMD app/main.py"
echo ""
echo "4. 如果您设置了 systemd 服务:"
echo "   请按照上面 步骤 5 中提供的 'sudo systemctl' 系列命令来管理服务。"
echo "   服务启动后，应用将在后台运行。"
echo ""
echo "如果您修改了 Python 代码或依赖，请记得重新激活虚拟环境 (如果已退出)，"
echo "并可能需要重新安装依赖 (参照步骤 3 中的依赖安装说明)。"
echo "如果更改了 .env 文件，并且应用正在作为 systemd 服务运行，请重启服务:"
echo "   sudo systemctl restart yourapp.service  (将 'yourapp.service' 替换为您的服务名)"
echo "---------------------------------------------------------------------"

exit 0
