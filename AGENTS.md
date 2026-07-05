# AgentWeb 项目规则

## 用户角色
本项目用户是 **Python/Web 学习者**。编写的每一行代码都应当帮助理解，不得默认读者有专业背景。

## 编码规范

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
