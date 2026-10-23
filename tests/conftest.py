"""测试环境隔离：强制 mock 模式，保证测试套件不依赖 .env 与外网。"""

import os

os.environ["LLM_MODE"] = "mock"
