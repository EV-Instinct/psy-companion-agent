# 小树洞 · 六年级心事陪伴智能体

面向小学六年级学生的心理陪伴 Agent：围绕**考试压力**与**升学焦虑**，提供文字、语音识别、图片讨论三种对话方式。设计依据《中小学心理健康教育指导纲要（2012 年修订）》《进一步加强中小学生心理健康工作十条措施》《健康中国行动——儿童青少年心理健康行动方案（2019—2022 年）》。

> 我是 AI 伙伴，不能替代心理老师、医生和家长。紧急情况请拨 12356（24 小时心理援助热线）或 12355（青少年服务台）。

## 核心设计

| 设计点 | 说明 |
|---|---|
| 单一对话内核 | 文字 / 语音 / 图片三种入口归一为同一种 `Message`，后端只有一条对话管线 |
| 三级危机预警 | 关键词快筛（毫秒级）→ LLM 语义分级（绿 / 黄 / 红）→ 红线固定安全脚本 + 热线卡片 + 审计日志 |
| 输出四不护栏 | 不诊断、不开药、不承诺、不评判；提示词（软约束）+ 句级后置过滤（硬约束）双保险 |
| 知识库 | 66 篇 Markdown（政策原文要点 + 心理科普 + 方法库），jieba + BM25 内存检索 |
| 界面配置 Key | 顶栏小按钮打开配置弹层，Key 只存本机浏览器（服务端不落盘）；不填则用服务端 `.env` 默认配置 |
| 隐私最小化 | 匿名会话、不收集身份信息、审计日志只记事件不记对话原文 |

## 快速开始

```bash
# 1. 安装依赖（Python 3.11+）
python -m venv .venv
.venv/Scripts/python.exe -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY（不填则自动进入 mock 演示模式）
# 默认走智谱 GLM；换阿里云百炼见 .env.example 内的注释

# 3. 启动（前后端同端口）
.venv/Scripts/python.exe server.py            # 默认 3000 端口
# 或指定端口：PORT=8701 .venv/Scripts/python.exe server.py
# 开发热重载：.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8701 --reload
```

浏览器打开 http://127.0.0.1:8701

- **真实模式**：`.env` 中配置 `LLM_API_KEY`，`LLM_MODE=auto`（默认智谱 GLM：glm-5 文本 + glm-4v-plus 图片）
- **演示模式**：无 Key 自动降级为 `mock`，界面与全链路可跑通，回复为预置安全话术（页面右上角显示「演示模式」）

## 目录结构

```
psy-companion/
├─ app/
│  ├─ main.py              # FastAPI 入口 + 静态前端托管
│  ├─ config.py            # 环境变量配置
│  ├─ models.py            # Pydantic 数据模型
│  ├─ api/chat.py          # SSE 流式对话 + 安全管线编排
│  ├─ core/
│  │  ├─ prompts.py        # 人格提示词 / 分级提示词 / 危机脚本
│  │  ├─ lexicon.py        # 危机词库 + 关键词快筛
│  │  ├─ safety.py         # 三级分级 + 输出护栏（句级）
│  │  ├─ sessions.py       # 会话与上下文窗口
│  │  └─ audit.py          # 审计日志（不记原文）
│  ├─ services/llm.py      # 百炼 OpenAI 兼容客户端 + mock
│  └─ knowledge/           # BM25 检索 + docs/（66 篇）
├─ frontend/               # 原生 ES Modules + 手写 CSS，零构建
│  └─ js/                  # app / api / ui / voice / image / settings
├─ tests/                  # 54 条回归用例
└─ scripts/                # 知识库生成、浏览器端到端验证
```

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests -q
```

浏览器端到端（需要本机 Edge）：

```bash
node scripts/functional.js   # 文字/图片/历史/快捷入口
node scripts/voice-test.js   # 语音降级 + 转写 + 发送
node scripts/qa.js           # 窄屏/黄线条/新对话/弹层
```

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查（返回 mock/real 模式、知识库篇数） |
| POST | `/api/chat` | SSE 流式对话：`meta → risk → delta* → suggestions? → done` |
| GET | `/api/history` | 会话历史（页面刷新恢复） |

## 政策依据 → 设计映射

| 政策 | 设计体现 |
|---|---|
| 纲要：发展、预防和危机干预相结合 | 三级预警 + 微行动建议 |
| 纲要：小学高年级「正确对待成绩、学会表达情绪、为初中做准备」 | 五大话题体系 + 情绪命名训练 |
| 纲要：知情自愿、保密及保密例外、及时转介、防医学化 | 会话约定 + 红线转介 + 四不护栏 |
| 十条措施：缓解考试焦虑、监测预警分级响应、家校协同 | 考试专项话术 + 三级分级 + 「告诉信任的大人」 |
| 行动方案：心理援助热线、对升学压力学生开展辅导 | 12355 / 12356 资源卡 + 升学焦虑核心场景 |

## 生产化差距（已知限制）

- 会话存于进程内存（重启丢失），生产需 Postgres；
- 单实例部署，未做多租户与配额；
- 图片内容审核依赖模型自身判断，生产建议接入内容安全服务；
- 语音输入：浏览器 MediaRecorder 录音 → 服务端 `Qwen/Qwen3-ASR-1.7B` 识别（硅基流动，实测约 1 秒），不再依赖浏览器/微软识别引擎；朗读同理走 `CosyVoice2`。
