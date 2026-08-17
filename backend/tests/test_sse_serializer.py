"""SSESerializer 单元测试：SSE 输出逐字节比对（协议保真的关键防线）"""
from app.services.chat.sse_serializer import SSEEvent, SSESerializer


def test_serialize_title_event():
    """标题事件：中文原样输出（ensure_ascii=False），与前端协议一致"""
    serializer = SSESerializer()
    event = SSEEvent(type="title", data={"title": "新标题"})
    assert serializer.serialize(event) == 'data: {"title": "新标题"}\n\n'


def test_serialize_rewriting_event():
    """重写中事件：布尔值原样序列化"""
    serializer = SSESerializer()
    event = SSEEvent(type="rewriting", data={"rewriting": True})
    assert serializer.serialize(event) == 'data: {"rewriting": true}\n\n'


def test_serialize_final_event():
    """最终版事件：内容完整透传"""
    serializer = SSESerializer()
    event = SSEEvent(type="final", data={"final": "你好"})
    assert serializer.serialize(event) == 'data: {"final": "你好"}\n\n'


def test_serialize_error():
    """错误事件：固定友好文案，不泄漏内部细节"""
    serializer = SSESerializer()
    assert serializer.serialize_error("小励出了点问题，请稍后再试吧") == \
        'data: {"error": "小励出了点问题，请稍后再试吧"}\n\n'


def test_serialize_done():
    """流结束标志：[DONE] 必须无空格差异"""
    serializer = SSESerializer()
    assert serializer.serialize_done() == "data: [DONE]\n\n"


def test_serialize_multiple_fields_keeps_default_separators():
    """多字段 dict 保留 json.dumps 默认分隔符（', ' 与 ': '），逐字节锁定协议"""
    serializer = SSESerializer()
    event = SSEEvent(type="final", data={"final": "你好", "extra": 1})
    assert serializer.serialize(event) == 'data: {"final": "你好", "extra": 1}\n\n'
