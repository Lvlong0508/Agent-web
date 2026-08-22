# Agent Web（AI 赋能个人智能助理系统）

> **持续迭代声明**：本项目是作者的个人全栈学习项目，功能处于持续迭代中，本文档描述可能与实际实现存在出入，请以代码为准。

## 项目简介

该系统在 AI 工具辅助下全栈开发，是面向个人消费场景的 AI 智能记账助手，采用前后端分离架构，将自然语言对话与账单数据管理整合于统一体系。以智能对话和 Tool-Calling 为核心特色，用 AI 降低记账、查询与分析成本，并通过质检重写机制防止模型编造数据，确保数据类回答有据可依。

### 核心业务功能

- **对话式记账闭环**：自然语言完成账单增删改查，支持流式回复、多会话回溯。
- **AI 智能助手**：基于 LangChain/LangGraph 编排 Agent，通过 Tool-Calling 自主调用账单、时间、计算等工具；支持本地 Ollama 与通义千问双模型路由及"深度思考"模式。
- **回复质量保障**：verifier 质检节点结构化判定候选回复（数据须有本轮工具结果来源），不准确进入重写轮修正（上限防死循环），配全链路追踪（trace_id）复盘调优。

## 技术栈

| 端 | 技术 |
|----|------|
| 后端 | Python · FastAPI · LangChain/LangGraph · MongoDB（motor）· MySQL（SQLAlchemy） |
| 前端 | Vue 3 · Vite · TypeScript · Vue Router · Axios |
| AI 模型 | Ollama 本地模型（默认）· 通义千问（DashScope，可选） |
| 通信 | SSE 流式回复 |

## 本地运行方式

### 手动启动

```bash
# 后端（conda 环境 agent-web）
conda activate agent-web
cd backend
pip install -r requirements.txt   # 仅首次
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 前端（另开终端）
cd frontend/AgentWeb-user
npm install   # 仅首次
npm run dev -- --host 0.0.0.0 --port 5173 --strictPort
```

### 环境配置

复制 `backend/.env.example` 为 `backend/.env`，按需配置 MongoDB、MySQL、Ollama 与通义千问（DashScope 可选）。

### 运行测试

```bash
cd backend
python -m pytest
```

## 其他页面URL
```
全链路记录URL：http://localhost:5173/runs
```
