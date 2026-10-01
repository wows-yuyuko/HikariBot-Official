"""适配层公共定义：业务代码与具体适配器实现之间的契约。

各实现模块（``qq_impl`` / ``onebot11_impl``）必须提供以下**同名**接口：

    MessageEvent                                                  该适配器的事件基类（类型标注用）
    get_scene(ev) -> Scene                                        事件 -> 统一场景
    is_text_or_at_message(ev) -> bool                             是否纯文本/@ 消息
    has_file_segment(ev) -> bool                                  是否含文件附件
    iter_file_urls(ev) -> list[str]                               取出文件附件地址
    parse_mentions(message, bot_self_id) -> ParsedMentions        @ 提及解析
    get_group_id(ev) -> str | None                                取群号
    supports_markdown() -> bool                                   该适配器是否支持 markdown 消息
    build_markdown_segment(content) -> MessageSegment | None      构造 markdown 消息段
    async send_image(matcher, data) -> None                       发图（失败时抛异常，由业务层兜底分支处理）

业务代码只 import ``adapters`` 包，不直接 import 任何 ``nonebot.adapters.*``，
这样新增适配器时改动范围就锁在 adapters 包内。
"""
from dataclasses import dataclass, field
from enum import StrEnum


class Scene(StrEnum):
    """统一消息场景。

    频道类场景（CHANNEL / CHANNEL_DIRECT）是 QQ 官方独有的，
    OneBot 不会产生它们 —— 业务代码里针对频道的分支在 OneBot 下自然走不到。
    """

    PRIVATE = 'private'                # C2C 私聊
    GROUP = 'group'                    # 群普通消息
    GROUP_AT = 'group_at'              # 群 @ 机器人
    CHANNEL = 'channel'                # 频道消息
    CHANNEL_DIRECT = 'channel_direct'  # 频道私信
    UNKNOWN = 'unknown'                # 兜底


def scene_label(scene: Scene) -> str:
    """场景的中文标签，仅用于日志。

    UNKNOWN 与 CHANNEL 同标签 —— 保持与改造前一致（改造前 else 分支即「频道」）。
    """
    if scene in (Scene.GROUP, Scene.GROUP_AT):
        return '群聊'
    if scene in (Scene.PRIVATE, Scene.CHANNEL_DIRECT):
        return '私信'
    return '频道'


@dataclass
class ParsedMentions:
    """@ 提及解析结果。

    parts: 已按既有语义处理过的消息片段 —— @机器人 整段丢弃，@其他用户 替换为 'me'
    mentioned_user_id: 被 @ 的那个非机器人用户 id（没有则为 None）
    at_count: 非机器人 @ 的数量（业务层据此判断「仅允许@一个用户」）
    """

    parts: list[str] = field(default_factory=list)
    mentioned_user_id: str | None = None
    at_count: int = 0
