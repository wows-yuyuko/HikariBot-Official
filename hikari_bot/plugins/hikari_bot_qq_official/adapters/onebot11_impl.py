"""OneBot V11 适配器实现。

连接方式**只支持 WebSocket**（正/反皆可，由 nonebot-adapter-onebot 自身提供）：
- 反向 WS：机器人提供 ``/onebot/v11/ws``，实现端（NapCat / Lagrange 等）主动连入，
  要求 driver 具备 ASGI 能力（本项目 DRIVER 含 ``~fastapi``）
- 正向 WS：机器人主动连实现端，配置 ``ONEBOT_WS_URLS``，
  要求 driver 具备 WebSocketClient 能力（本项目 DRIVER 含 ``~websockets``）

注意：适配器还会顺带注册 ``/onebot/v11/http`` 之类的 HTTP POST 端点，这是它自身行为，
我们不用也不保证；本项目对外承诺的接入方式只有上面两种 WebSocket。

与 QQ 官方实现的差异（业务代码无需感知，均由本文件消化）：
- 事件只有「私聊 / 群聊」两类，没有频道概念，因此不会产生 CHANNEL / CHANNEL_DIRECT
- ``at`` 段没有 ``is_bot`` 标记，识别「@的是不是机器人」要靠与 ``bot.self_id`` 比对
- ``image`` 段可直接吃 bytes（适配器转 ``base64://``），**不需要图床上传**
- 协议没有 markdown 消息段，``supports_markdown()`` 返回 False
"""
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)

# 显式再导出：业务层靠它区分「消息发不出去（限速等）」与普通异常
from nonebot.adapters.onebot.v11.exception import ActionFailed as ActionFailed  # noqa: PLC0414

from .base import ParsedMentions, Scene
from .base import scene_label as scene_label  # noqa: PLC0414 显式再导出，满足适配层的同名接口约定

TEXT_SEG = 'text'
AT_SEG = 'at'
FILE_SEG = 'file'
MENTION_ALL = 'all'  # at 段的 qq 取该值表示 @全体


def get_scene(ev: MessageEvent) -> Scene:
    """区分消息场景。

    OneBot 没有「群@机器人」这个独立事件类型，群消息统一走 GroupMessageEvent，
    这里用 ``to_me``（消息里 @ 了机器人）再细分成 GROUP_AT 与 GROUP，
    让日志与场景语义保持准确 —— 两者在业务上的处理完全一致。
    """
    if isinstance(ev, PrivateMessageEvent):
        return Scene.PRIVATE
    if isinstance(ev, GroupMessageEvent):
        return Scene.GROUP_AT if getattr(ev, 'to_me', False) else Scene.GROUP
    return Scene.UNKNOWN


def is_text_or_at_message(ev: MessageEvent) -> bool:
    """仅当消息只含 纯文本 和 @用户 段时返回 True。

    ``at`` 段里的 @全体 不算「@用户」—— 与 QQ 侧把 ``mention_everyone`` 排除在外保持一致，
    否则群里随便一条 @全体 消息都会触发查询。
    """
    for seg in ev.get_message():
        if seg.type == TEXT_SEG:
            continue
        if seg.type == AT_SEG and str(seg.data.get('qq')) != MENTION_ALL:
            continue
        return False
    return True


def has_file_segment(ev: MessageEvent) -> bool:
    """消息中是否包含 文件 段。

    OneBot V11 协议本身没有定义「收到文件」的消息段，能否收到取决于实现端
    （部分实现会下发 ``file`` 段）。这里按段名做鸭子判断：实现端不下发就永远为 False。
    """
    return any(seg.type == FILE_SEG for seg in ev.get_message())


def iter_file_urls(ev: MessageEvent) -> list[str]:
    """取出文件段里的地址。

    各实现端填的字段不一致：有的给下载地址 ``url``，有的给 ``file``（路径或 URL），
    两个都取不到时给空串，交由调用方决定怎么提示。
    """
    return [seg.data.get('url') or seg.data.get('file') or '' for seg in ev.get_message() if seg.type == FILE_SEG]


def parse_mentions(message: Message, bot_self_id: str) -> ParsedMentions:
    """解析 @ 提及：@机器人 与 @全体 整段移除，@其他用户 替换为 'me' 并记下其 id。

    V11 的 at 段只有 ``qq`` 字段，没有 is_bot 标记，所以「@的是不是机器人」
    必须靠与 ``bot_self_id`` 比对得出 —— 这正是适配层签名里带 bot_self_id 的原因。
    """
    parsed = ParsedMentions()
    self_id = str(bot_self_id)
    for seg in message:
        if seg.type == AT_SEG:
            target = str(seg.data.get('qq', ''))
            if target == self_id or target == MENTION_ALL:
                continue
            parsed.at_count += 1
            if parsed.at_count > 1:
                return parsed
            parsed.parts.append('me')
            # 取不到 qq 时留 None，让业务层回退到发送者，避免用空串当身份去查
            parsed.mentioned_user_id = target or None
        else:
            parsed.parts.append(str(seg))
    return parsed


def get_group_id(ev: MessageEvent) -> str | None:
    """取群号。V11 的 group_id 是 int，这里统一转成字符串（框架内身份一律按 str 处理）"""
    group_id = getattr(ev, 'group_id', None)
    return str(group_id) if group_id is not None else None


def supports_markdown() -> bool:
    """OneBot 协议没有 markdown 消息段"""
    return False


def build_markdown_segment(content: str) -> None:
    """不支持 markdown：返回 None。

    业务层会先用 supports_markdown() 判断，这里返回 None 只是把契约补齐，
    保证「不支持时不要构造出半成品消息段」。
    """
    return None


async def send_image(matcher, data: bytes) -> None:
    """发送图片。V11 的 image 段直接接受 bytes（适配器转 base64:// 下发），
    不需要图床，也就无所谓场景差异。"""
    await matcher.send(MessageSegment.image(data))
