# run.py (在项目根目录)
import uvicorn
from app.main import app # 从 app 包的 main 模块导入 app 实例
from app.core.config import settings # 导入配置

if __name__ == "__main__":
    uvicorn.run(
        app, # 或者 "app.main:app" 字符串形式，如果 uvicorn 从项目根目录运行
        host="0.0.0.0",
        port=settings.listening_port, # 从配置获取端口
        log_level=settings.log_level.lower(), # 从配置获取日志级别 (Uvicorn需要小写)
        access_log=False, # 通常在生产中禁用Uvicorn的访问日志，如果应用自己记录的话
        # reload=True # 开发时可以启用，生产环境应禁用
    )