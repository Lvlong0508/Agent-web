"""提示词集中管理模块测试：验证模板拼装与系统提示词内容"""

from app.services.agent.prompts import (
    REPLY_ON_VERIFY_FAILED,
    SYSTEM_PROMPT,
    TITLE_GENERATION_TEMPLATE,
    VERIFY_PROMPT,
    build_rewrite_prompt,
    build_system_prompt,
    build_title_prompt,
)


def test_build_system_prompt_injects_today():
    """系统提示词必须拼接当前日期：agent 构造日期类工具参数（如"8月14日"账单）
    时需要知道今天是哪年，否则会幻觉成往年（实测用 2023 年查询当月账单）"""
    prompt = build_system_prompt("2026-08-15")
    # 基础系统提示词完整保留
    assert SYSTEM_PROMPT in prompt
    # 当前日期注入其中
    assert "2026-08-15" in prompt
    assert "今天" in prompt


def test_build_title_prompt_injects_messages():
    """测试标题提示词模板能拼入对话内容"""
    prompt = build_title_prompt("human: 你好")
    assert "human: 你好" in prompt
    # 模板占位符已被替换，不再残留花括号
    assert "{messages_text}" not in prompt


def test_title_template_mentions_short_title():
    """测试标题模板要求生成简短标题（不超过20字）"""
    assert "不超过20个字" in TITLE_GENERATION_TEMPLATE


def test_system_prompt_defines_role():
    """测试系统提示词包含角色名"小励"并承诺耐心的友好态度"""
    assert "小励" in SYSTEM_PROMPT
    assert "耐心" in SYSTEM_PROMPT
    assert "友好" in SYSTEM_PROMPT


def test_system_prompt_keeps_clarification_requirement():
    """合并沟通准则后必须保留"信息不足时先追问确认"：多轮对话中避免助手
    在模糊场景下硬答或猜测数据，间接踩中"未经工具核实"的红线"""
    assert "追问确认" in SYSTEM_PROMPT


def test_system_prompt_requires_tool_for_non_chat_questions():
    """系统提示词必须约束：非纯聊天问题（查账单/时间等）应先调用工具、
    结合工具结果回答，不得凭记忆或猜测编造数据（用户实测：agent 不调用
    工具就编造"3笔/320元"等幻觉数据，导致质检拦截）。
    且需给出具体示例（查询账单/统计金额/获取时间等），降低模型自行界定
    "非纯聊天问题"范围的风险"""
    assert "调用工具" in SYSTEM_PROMPT
    assert "结合工具结果回答" in SYSTEM_PROMPT
    assert "编造数据" in SYSTEM_PROMPT
    assert "查询账单" in SYSTEM_PROMPT
    assert "统计金额" in SYSTEM_PROMPT
    assert "获取时间" in SYSTEM_PROMPT


def test_verify_prompt_exists_and_instructs():
    """验证提示词存在且包含判定指令"""
    assert "is_accurate" in VERIFY_PROMPT
    assert "工具" in VERIFY_PROMPT


def test_verify_prompt_explicitly_targets_last_assistant():
    """质检提示词必须明确校验对象是最后一条 assistant 回复，避免质检员把
    角色设定/用户消息当成交互对象（用户实测：质检员把"你是小励"当成了对话方）"""
    assert "最后一条" in VERIFY_PROMPT
    assert "assistant" in VERIFY_PROMPT


def test_verify_prompt_correcting_user_is_not_inaccurate():
    """质检提示词必须明确：用户可能陈述错误前提（如"我记了3笔"），
    工具返回数据才是唯一事实依据；回复基于工具数据纠正用户是正确行为，
    不能判为不准确（用户实测：agent 答对6笔仍被连续拦截）"""
    assert "错误前提" in VERIFY_PROMPT
    assert "纠正为6笔" in VERIFY_PROMPT
    assert "唯一事实依据" in VERIFY_PROMPT
    assert "不算不准确" in VERIFY_PROMPT


def test_verify_prompt_history_reference_only_context():
    """质检提示词必须明确：历史会话仅供参考（理解背景如用户名），
    不能因助手依据历史背景作答而判不准确"""
    assert "历史会话" in VERIFY_PROMPT
    assert "仅供参考" in VERIFY_PROMPT


def test_system_prompt_requires_fresh_tool_call_each_round():
    """系统提示词必须约束：每一轮数据类问题都必须重新调用工具核实，
    即使之前查询过同一主题，也不能凭记忆沿用旧结论（用户实测：第二轮
    "我有4个账单"助手没调工具，凭第一轮印象编造出5条/金额全错的回复）"""
    assert "每一轮" in SYSTEM_PROMPT or "每轮" in SYSTEM_PROMPT
    assert "重新" in SYSTEM_PROMPT
    assert "记忆" in SYSTEM_PROMPT


def test_verify_prompt_requires_tool_evidence_for_data_questions():
    """质检提示词必须明确：数据类问题（条数/金额/日期/明细）本轮若无 tool
    结果，说明助手没调用工具核实，直接判不准确（用户实测：助手没调工具
    编造回复，质检员因无 tool 依据而漏判）"""
    assert "数据" in VERIFY_PROMPT
    assert "没有" in VERIFY_PROMPT or "无" in VERIFY_PROMPT
    assert "调用工具" in VERIFY_PROMPT


def test_verify_prompt_checks_internal_consistency():
    """质检提示词必须要求做内部一致性检查：列出的明细条数必须等于宣称
    条数、明细金额之和必须等于宣称总额（用户实测：5条明细相加90元却宣称
    70元，质检员没发现仍判准确）"""
    assert "明细" in VERIFY_PROMPT
    assert "条数" in VERIFY_PROMPT
    assert "金额之和" in VERIFY_PROMPT or "总额" in VERIFY_PROMPT
    assert "一致" in VERIFY_PROMPT


def test_verify_prompt_allows_correct_summary():
    """质检提示词必须允许合理汇总：助手把多条明细汇总成类别金额（如早餐5元+
    午饭15元=餐饮20元）是正常行为，不能因未逐项罗列而误判；但汇总必须正确。
    需覆盖两层汇总：每个分类汇总=该类明细之和、总汇总=全部明细之和"""
    assert "汇总" in VERIFY_PROMPT
    assert "允许" in VERIFY_PROMPT
    assert "之和" in VERIFY_PROMPT
    assert "每个分类汇总金额" in VERIFY_PROMPT
    assert "总汇总金额" in VERIFY_PROMPT


def test_verify_prompt_honest_no_tool_is_exception():
    """质检提示词必须允许例外：助手确实没有可用工具、在回复中明确说明无法
    查询且未编造数据时，不算不准确；但必须限定为"回复里白纸黑字明说没有
    可用工具"，防止 agent 偷懒不调工具还含糊带过"""
    assert "如实说明" in VERIFY_PROMPT or "明确说明" in VERIFY_PROMPT
    assert "可用的查询工具" in VERIFY_PROMPT or "无法查询" in VERIFY_PROMPT
    assert "不算不准确" in VERIFY_PROMPT


def test_verify_prompt_uses_available_tools_for_no_tool_exception():
    """质检提示词必须说明：可用工具清单随输入提供，质检员以此判断"没有可用工具"
    的说法真伪——工具清单里明明有对应工具却说没有，判不准确（用户担忧：助手
    可谎称无工具骗过质检）"""
    assert "可用工具" in VERIFY_PROMPT
    assert "清单" in VERIFY_PROMPT or "列表" in VERIFY_PROMPT


def test_verify_prompt_defines_current_round():
    """质检提示词必须明确"本轮"定义：判定依据只认本轮 tool 结果，历史 tool
    结果仅供参考、不作为判定依据，避免历史数据干扰校验"""
    assert "本轮" in VERIFY_PROMPT
    assert "历史" in VERIFY_PROMPT
    assert "不作为判定依据" in VERIFY_PROMPT


def test_verify_prompt_hides_tool_limits_penalty():
    """质检提示词必须明确：工具结果不含用户要的时段时，助手若不告知工具限制、
    直接拿不匹配数据硬答，判不准确（堵住"闷头用错数据"的漏洞）"""
    assert "不匹配" in VERIFY_PROMPT
    assert "判不准确" in VERIFY_PROMPT


def test_verify_prompt_each_data_needs_tool_origin():
    """质检提示词必须要求：候选回复中的每个数据（金额/日期/条数/明细）都必须
    能在本轮工具结果中找到对应来源；若涉及某类数据但本轮无该类数据的工具结果，
    视为无依据，按规则4处理。堵住"调无关工具（如 get_now_time）制造有 tool
    结果假象、再凭记忆编造账单数据"的漏洞（用户对抗式审查发现）"""
    assert "找到来源" in VERIFY_PROMPT
    assert "无依据" in VERIFY_PROMPT or "无有效工具依据" in VERIFY_PROMPT


def test_verify_prompt_irrelevant_tool_is_not_valid_evidence():
    """质检提示词规则4必须明确：无关工具调用不算有效工具依据——用户问账单
    却只调了获取时间的工具，视同无有效工具调用，判 false"""
    assert "无关" in VERIFY_PROMPT
    assert "获取时间" in VERIFY_PROMPT
    assert "无有效工具" in VERIFY_PROMPT or "无依据" in VERIFY_PROMPT


def test_verify_prompt_derivation_allows_single_value():
    """质检提示词规则0的"推导来源"必须覆盖单值推导：由日期算星期几、
    由总额与条数算平均每笔，都是基于相关工具结果的合理推导，不能被
    "多个值"限制误拦（用户审查：单个值也可推导出新数据）"""
    assert "推导来源" in VERIFY_PROMPT
    assert "一个或多个值" in VERIFY_PROMPT
    assert "计算逻辑正确" in VERIFY_PROMPT


def test_verify_prompt_no_effective_evidence_when_not_derivable():
    """质检提示词规则4必须覆盖第三种情形：虽有相关工具调用，但候选回复中的
    数据既非直接来自工具结果、也无法由相关工具结果正确推导（如调了账单工具
    却报个凭空数字）——同样判不准确（用户对抗式审查：规则0引用规则4的承接）"""
    assert "既非直接来自工具结果" in VERIFY_PROMPT
    assert "正确推导" in VERIFY_PROMPT


def test_verify_prompt_tool_failure_requires_evidence():
    """质检提示词例外必须明确："工具调用失败"必须有本轮 tool 消息作为证据——
    若本轮无 tool 消息、或 tool 消息显示调用成功，则不适用失败豁免。
    堵住"根本没调工具却谎称调用失败"的漏洞（用户对抗式审查）"""
    assert "调用失败" in VERIFY_PROMPT
    assert "tool 消息" in VERIFY_PROMPT
    assert "表明调用失败" in VERIFY_PROMPT


def test_verify_prompt_distinguishes_category_and_item_count():
    """质检提示词规则1必须区分两个"条数"：汇总按类别合并后类别数可与明细
    条数不同；但候选回复若列出明细条目，实际列出的条目数必须等于宣称的总条数。
    避免质检模型混淆两个含义（用户第一性原理审查发现）"""
    assert "类别数" in VERIFY_PROMPT
    assert "实际列出的条目数" in VERIFY_PROMPT


def test_system_prompt_exception_requires_checking_own_tools():
    """系统提示词例外条款必须要求先检查自己所拥有的工具：当且仅当确认没有
    能回答该问题的工具、或工具调用失败时，才可如实说明；不得未经检查就声称
    没有工具。与质检员侧"可用工具清单"形成闭环（用户建议）"""
    assert "检查你所拥有的工具" in SYSTEM_PROMPT
    assert "未经检查就声称没有工具" in SYSTEM_PROMPT


def test_system_prompt_no_number_gap():
    """合并沟通准则1-4后不应残留编号断层（从5.开始会让人困惑为何没有1-4），
    铁律与唯一例外直接以文字表述，不编号"""
    assert "5. 铁律" not in SYSTEM_PROMPT
    assert "6. 唯一例外" not in SYSTEM_PROMPT
    assert "铁律：" in SYSTEM_PROMPT
    assert "唯一例外：" in SYSTEM_PROMPT


def test_verify_prompt_no_tool_exception_uses_author_connector():
    """规则4例外中"无可用工具/无法查询"与"对照工具清单确实无对应工具"
    应使用"且"连接，避免顿号被误解为两个并列的动作要求（用户审查）"""
    assert "无法查询，且对照" in VERIFY_PROMPT
    assert "，且" in VERIFY_PROMPT


def test_rewrite_prompt_tells_agent_to_reorganize():
    """重写轮指令必须重置前提（回答已被清空）、声明质检员身份、禁止道歉，
    否则 agent 会暴露"上一条回复未通过校验"这类过程性话术或输出道歉（实测出现"非常抱歉"）。
    同时必须强制：涉及数据的问题先调用工具，避免重写轮再次凭记忆编造（实测第二轮没调工具）"""
    prompt = build_rewrite_prompt("金额错误")
    # 重置前提：清空回答，让 agent 全新开始，不纠结之前的错误
    assert "已被我清空" in prompt
    # 声明质检员身份与中间人角色，防止 agent 把质检员当用户
    assert "质检员" in prompt
    assert "你和用户之间" in prompt
    # 硬性禁令：不道歉（对用户也不道歉）、不提及质检过程（重写轮用户端不可见）
    assert "不要道歉" in prompt
    assert "对用户也不要道歉" in prompt
    assert "不要提及质检过程" in prompt
    assert "未通过" not in prompt
    # 强制数据类问题重新调用工具，堵住"凭记忆编造"的二次机会；
    # 且禁用直接采用反馈中的数字，必须重新调工具核实
    assert "涉及数据" in prompt
    assert "调用工具" in prompt
    assert "反馈" in prompt or "修正要求" in prompt
    # 反馈正确注入
    assert "金额错误" in prompt


def test_reply_on_verify_failed_is_fixed_message():
    """验证失败超限后返回固定文案"""
    assert REPLY_ON_VERIFY_FAILED == "小励出现了点问题，请稍后再尝试吧"