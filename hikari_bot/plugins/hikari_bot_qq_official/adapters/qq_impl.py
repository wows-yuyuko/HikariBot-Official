"""QQ 官方适配器实现。

QQ 专属语义集中在这里：事件分类、@ 解析、发图。
业务代码只经 adapters 包访问，不直接依赖 nonebot.adapters.qq。
"""
from nonebot.adapters.qq import (
    C2CMessageCreateEvent,
    DirectMessageCreateEvent,
    GroupAtMessageCreateEvent,
    GroupMessageCreateEvent,
    GuildMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
)
# 显式再导出：业务层靠它区分「消息发不出去（限速等）」与普通异常
from nonebot.adapters.qq import ActionFailed as ActionFailed

from .base import ParsedMentions, Scene
from .base import scene_label as scene_label  # noqa: PLC0414 显式再导出，满足适配层的同名接口约定

TEXT_SEG = 'text'
MENTION_SEG = 'mention_user'   # 适配器已把「@全体」等归一到这里（带 is_bot 标记）
FILE_SEG = 'file'


def get_scene(ev: MessageEvent) -> Scene:
    """区分消息事件类型（注意继承关系，isinstance 判断顺序不能乱）

    - C2C_MESSAGE_CREATE      -> PRIVATE（私聊）
    - GROUP_AT_MESSAGE_CREATE -> GROUP_AT（群@机器人）
    - GROUP_MESSAGE_CREATE    -> GROUP（群普通消息）
    - 频道消息 MESSAGE_CREATE -> CHANNEL
    - 频道私信                -> CHANNEL_DIRECT
    - 其他                    -> UNKNOWN
    """
    if isinstance(ev, C2CMessageCreateEvent):
        return Scene.PRIVATE
    if isinstance(ev, DirectMessageCreateEvent):    # 必须先于 GuildMessageEvent
        return Scene.CHANNEL_DIRECT
    if isinstance(ev, GroupAtMessageCreateEvent):   # 必须先于 GroupMessageCreateEvent
        return Scene.GROUP_AT
    if isinstance(ev, GroupMessageCreateEvent):
        return Scene.GROUP
    if isinstance(ev, GuildMessageEvent):
        return Scene.CHANNEL
    return Scene.UNKNOWN


def is_text_or_at_message(ev: MessageEvent) -> bool:
    """仅当消息只含 纯文本 和 @提及 段时返回 True，其余（图片/表情/文件/@全体/@频道等）一律不处理"""
    return all(seg.type in (TEXT_SEG, MENTION_SEG) for seg in ev.get_message())


def has_file_segment(ev: MessageEvent) -> bool:
    """消息中是否包含 文件 段（收到的文件附件由适配器解析为 file 段）"""
    return any(seg.type == FILE_SEG for seg in ev.get_message())


def iter_file_urls(ev: MessageEvent) -> list[str]:
    """取出消息中所有文件附件的地址（file 段的 data 里只有 url）"""
    return [seg.data.get('url', '') for seg in ev.get_message() if seg.type == FILE_SEG]


def parse_mentions(message: Message, bot_self_id: str) -> ParsedMentions:
    """解析 @ 提及：@机器人 整段移除，@其他用户 替换为 'me' 并记下其 id。

    QQ 官方适配器会在 mention_user 段上直接给出 is_bot，无需与 bot_self_id 比对；
    该参数在此实现里不使用，仅为满足适配层统一签名。
    """
    parsed = ParsedMentions()
    for seg in message:
        if seg.type == MENTION_SEG:
            if seg.data.get('is_bot', False):
                continue
            parsed.at_count += 1
            if parsed.at_count > 1:
                return parsed
            parsed.parts.append('me')
            parsed.mentioned_user_id = seg.data.get('user_id')
        else:
            parsed.parts.append(str(seg))
    return parsed


def get_group_id(ev: MessageEvent) -> str | None:
    """取群号（群场景才有意义）"""
    return getattr(ev, 'group_openid', None) or getattr(ev, 'group_id', None)


def supports_markdown() -> bool:
    """QQ 官方支持 markdown 消息段"""
    return True


def build_markdown_segment(content: str) -> MessageSegment:
    return MessageSegment.markdown(content)


async def send_image(matcher, data: bytes) -> None:
    """发送图片。

    QQ 官方统一走富媒体直发（file_image）：适配器内部把图片交给腾讯的富媒体接口，
    不需要公网 IP，也不需要任何图床 —— 因此频道与群聊、私信走的是同一条路径。
    """
    await matcher.send(MessageSegment.file_image(data))
