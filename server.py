"""启动入口：自己读取 PORT 环境变量，兼容各类托管环境。

用法：
    python server.py              # 默认 3000 端口
    PORT=8701 python server.py    # 指定端口
"""

import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
