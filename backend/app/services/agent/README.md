# agent 包职责划分手册

> 目的：明确 agent 包各层职责，防止再出现"职责混杂"（如 planner 曾把 prompt 素材、
> content 组装、输出清洗全塞进能力包）。新增代码前先查本手册确定归属。

## 一、顶层包职责

| 包 | 职责 | 放什么 | 不放什么 |
|---|---|---|---|
| `prompts/` | 提示词素材（静态） | 提示词模板、示例库数据、关键词表 | 拼接逻辑、LLM 调用 |
| `context/` | content 组装 | 把提示词+工具+skill+历史+用户对话组装成消息列表 | 静态素材、节点编排 |
| `skills/` | 技能机制 | loader 扫描、read_skill 工具、检索装配 | 其他能力的提示词 |
| `capabilities/` | 能力编排 | 节点注册/连线、LLM 调用、降级、输出清洗 | prompt 素材、content 组装 |
| `events.py` | 事件契约 | 事件常量 + emit | 业务逻辑 |

## 二、能力包内部规则

每个能力包（`capabilities/<name>/`）只允许放四类文件：

```
capabilities/<name>/
├── node.py        # 编排：LLM 调用 + 降级 + 状态组装 + 输出清洗
├── schema.py      # 数据结构（LLM 输入/输出模型）
├── events.py      # 事件常量
└── __init__.py    # 能力注册（AgentCapability 子类）
```

**禁止**在能力包里放：提示词模板、示例数据、上下文组装函数。

## 三、分层速查表（新增代码时查这里）

| 我要写什么 | 放哪里 |
|---|---|
| 提示词模板 / few-shot 示例 / 关键词表 | `prompts/<name>.py` |
| 把提示词+工具+skill+历史+用户对话拼成消息列表 | `context/<name>.py` |
| 节点逻辑（调 LLM、降级、状态组装） | `capabilities/<name>/node.py` |
| LLM 输出的工具名清洗等后处理 | `capabilities/<name>/node.py` |
| LLM 输入/输出的数据结构 | `capabilities/<name>/schema.py` |
| 事件常量 | `capabilities/<name>/events.py` |

## 四、import 边界

- 编排层（node.py）**只能从包级 `__init__` 导入**：`from app.services.agent.context import ...`
- 禁止 `from app.services.agent.context.planner import ...`（深层 import 越过 init）
- 素材（prompts）与组装（context）之间的引用也经 `__init__` 导出

## 五、反模式清单（不要这样做）

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| node.py 里内联拼提示词 | 提示词散落、难统一维护 | 提示词放 prompts/，node 只调 context |
| 把 few-shot 数据和组装函数放一个文件 | 素材与逻辑混杂 | 素材 prompts/，组装 context/ |
| 复制 build_agent_messages 的组装逻辑到节点 | 重复 + 不一致 | 统一走 context/ 的组装函数 |
| 能力包放 schema 之外的业务文件 | 包职责膨胀 | 按速查表归位 |
| 深层 import 越过包 init | import 边界失守 | 先在本包 __init__ 导出再 import |

## 六、已知待清理项

- `capabilities/verifier/context/rewrite.py:6`、`verdict.py:8` 深层 import
  `HISTORY_REFERENCE_MARKER`（应经 `agent.context` 包级导出）——后续独立任务清理
