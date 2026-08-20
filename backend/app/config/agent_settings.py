"""Agent 模块专用配置：模型注册表 + planner 规划节点 + skill 机制（agent 模块唯一配置源）。

背景：原 settings.py 职责过重（MongoDB/MySQL/LLM/skills 混在一处），且模型分发
硬编码在选择名白名单里，每加一个模型就要改代码。拆出本类后：
- agent 模块自己的配置（模型注册表、规划参数、技能目录）只在此维护
- 模型注册表配置驱动：新增模型 = 改 models.yaml（或内置默认字典），工厂零改动
"""

from pathlib import Path
from typing import ClassVar, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """模型定义：一个注册条目 = 一份完整可构造的模型配置。

    base_url/api_key 不放在模型层（YAGNI）：当前全部走 settings.py 的厂商凭据，
    未来出现多端点/多实例需求时再给 ModelConfig 扩展这两个字段。
    """

    provider: Literal["dashscope", "ollama"] = Field(description="厂商，决定走哪个子包构造")
    model: str = Field(description="真实 API 模型名")
    enable_thinking: bool = True      # 默认思考开关（dashscope 用）
    streaming: bool = True            # 默认流式（节点可运行时覆盖）
    max_tokens: int | None = None     # 默认输出上限（节点可覆盖）
    temperature: float | None = None  # 默认采样温度（None=用 ChatOpenAI 默认）


# 内置默认注册表：models.yaml 缺省时兜底，保证零配置可跑。
# 新增模型建议写在 models.yaml（声明式、可注释），此字典只作兜底
_BUILTIN_REGISTRY: dict[str, ModelConfig] = {
    # 前端可选 · 本地 Ollama
    "ollama-qwen3.5": ModelConfig(provider="ollama", model="qwen3.5:9b", streaming=True),
    # 前端可选 · 通义千问主模型（思考默认开，与现状一致）
    "qwen3.7-flash": ModelConfig(provider="dashscope", model="qwen3.7-flash", enable_thinking=True, streaming=True),
    # 内部 · planner 规划模型（独立版本号，思考开、非流式）
    "planner": ModelConfig(provider="dashscope", model="qwen3.7-flash-2026-07-15", enable_thinking=True, streaming=False),
}


class AgentSettings(BaseSettings):
    # ---- 模型注册表：alias -> ModelConfig（models.yaml 为准，缺省用内置默认）----
    MODEL_REGISTRY: dict[str, ModelConfig] = Field(default_factory=lambda: dict(_BUILTIN_REGISTRY))

    # ---- 前端选择名常量（= 注册表 key，前端下拉值与后端保持一致）----
    MODEL_OLLAMA: ClassVar[str] = "ollama-qwen3.5"
    MODEL_DASHSCOPE_QWEN: ClassVar[str] = "qwen3.7-flash"

    # ---- planner 规划节点配置 ----
    PLANNER_MODEL_ALIAS: str = "planner"       # 用注册表里的哪个模型做规划
    PLANNER_THINKING: bool = True              # 思考模式：意图识别需推理，代价是更慢，故超时上调
    PLANNER_TIMEOUT: float = 60.0              # 规划超时（秒）。思考模式非流式要等全部思考完成（实测十几秒+），20s 不够实测触发降级，上调至 60s
    PLANNER_CONFIDENCE_THRESHOLD: float = 0.7  # 置信度阈值：低于此值标注低置信度

    # ---- skill 机制（从原 settings 迁入）----
    SKILLS_DIR: str = "skills"                 # 相对 BASE_DIR 或绝对路径

    BASE_DIR: ClassVar[Path] = Path(__file__).resolve().parents[2]  # backend/

    # extra="ignore"：忽略 .env 中属于 settings.py 的基础设施变量（MONGODB_* 等），
    # AgentSettings 只认领自己的字段；需要覆盖时用 AGENT_ 前缀的环境变量
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def load(cls, yaml_path: Path | None = None) -> "AgentSettings":
        """加载配置：模型注册表优先读 models.yaml，缺省用内置默认（零配置可跑）。

        yaml_path：显式指定注册表文件（测试注入用）；None 时默认 backend/models.yaml。
        yaml 只放非敏感模型定义；厂商凭据/base_url 仍在 settings.py（全局单一来源）。
        """
        if yaml_path is None:
            yaml_path = Path(__file__).resolve().parents[2] / "models.yaml"
        registry = dict(_BUILTIN_REGISTRY)
        if yaml_path.exists():
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            raw = data.get("model_registry") or {}
            registry = {name: ModelConfig(**cfg) for name, cfg in raw.items()}
        return cls(MODEL_REGISTRY=registry)


# 全局单例配置对象（导入即加载；models.yaml 存在则以文件为准）
agent_settings = AgentSettings.load()