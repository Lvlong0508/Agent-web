# AgentWeb 项目规则

## 环境
本项目专用的 conda 环境名为 `agent-web`，所有 Python 依赖安装在此环境中。
后端启动脚本 `scripts/start_backend.py` 会自动激活该环境。

## 用户角色
本项目用户是 **Python/Web 学习者**。编写的每一行代码都应当帮助理解，不得默认读者有专业背景。

## 编码规范

### 职责分类
参考 backend.md/frontend.md

### 注释要求
所有新增和修改的代码必须带中文注释，说明"做什么、为什么这么做"。包括但不限于：

- 每个函数/方法的用途说明
- 关键逻辑步骤的说明
- 非常见语法或设计模式的解释
- 配置项的含义

### 注释风格
```python
# 简短说明写行内
class AuthService:
    """认证业务逻辑层：串联数据访问、密码加密、令牌生成"""
    pass

    async def register(self, ...):
        """注册流程：检查重复 -> 哈希密码 -> 创建用户"""
        # 先检查用户名是否已被注册
        existing_user = await self.dao.get_by_username(username)
        if existing_user:
            raise UserExistsError("Username")
```

```vue
<!-- 导航栏组件：登录后显示，包含 Logo 和用户头像按钮 -->
```

### 禁止事项
- 不得删除或覆盖现有中文注释
- 不得使用纯英文注释
- 不得使用无意义的注释（如 `# 设置变量 x = 1`）

## 代码知识图谱（codebase-memory-mcp）

本项目使用 codebase-memory-mcp 维护代码库知识图谱（函数/类/路由/调用关系）。
涉及代码发现与定位时，优先用图谱工具，而不是盲目 grep/glob 全库搜索。

### 工具
- `search_graph`：按名字/模式找函数、类、路由、变量
- `trace_path`：追踪谁调用某函数、它内部又调用了谁（调用链）
- `get_code_snippet`：读指定函数/类的源码片段
- `query_graph`：跑 Cypher 查复杂关系（如多跳调用、模块依赖）
- `get_architecture`：项目整体架构摘要
- `check_index_coverage`：校验某路径是否已建索引、有无覆盖缺口
- `list_projects` / `index_status`：确认图谱项目与索引状态

### 使用时机（按证据强度分级）
- **Scout（快速粗查）**：目标明确、只需少量查询定位时用；结论标记为"待确认"
- **Verify（常规，默认）**：任务需要得出可信结论时，用图谱查调用链/源码片段验证
- **Auditor（严格核验）**：对材料性断言做完整核验时，双向追踪 + 完整分页 + 披露限制

### 何时回退到 grep/glob
- 搜字符串字面量、错误消息、配置值
- 搜非代码文件（Dockerfile、shell 脚本、配置文件）
- 图谱返回不足或覆盖不全时

### 注意事项
- 使用前先 `index_status` 确认图谱新鲜度；会话重置或压缩后重新确认
- 图谱结果不能证明"不存在"（clean 只是没记录缺口，不代表完备）
- 派子代理前先在父会话查好图谱与覆盖证据，把结论传给子代理（子代理未必有 MCP 工具）


