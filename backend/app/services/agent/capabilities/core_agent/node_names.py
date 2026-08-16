"""核心节点名常量：能力 connect() 引用它们挂接主循环，避免裸字符串（规格 4.1）。

connect() 引用的节点必须已注册，真实存在性校验由 LangGraph compile() 兜底
（编译时会报缺失节点）；本常量只统一节点名来源，便于检索与修改。
"""

CORE_NODE_AGENT = "agent"          # Agent 推理节点（主循环核心锚点）
CORE_NODE_TOOLS = "tools"          # 工具执行节点
CORE_NODE_VERIFIER = "verifier"    # 质检节点
