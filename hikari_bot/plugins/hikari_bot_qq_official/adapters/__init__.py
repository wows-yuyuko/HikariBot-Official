"""适配层出口：业务代码只 import 本包，不直接依赖任何 nonebot.adapters.*。

按 BOT_ADAPTER 选择唯一一个实现模块，并把它的接口平铺到本包命名空间，
这样业务代码写 ``from ...adapters import get_scene`` 即可，换适配器时不用改业务代码。
"""
from hikari_bot.adapter_registry import get_adapter_name

from .base import ParsedMentions, Scene, scene_label  # noqa: F401

_ADAPTER_NAME = get_adapter_name()

if _ADAPTER_NAME == 'qq_official':
    from . import qq_impl as _impl
elif _ADAPTER_NAME == 'onebot11':
    from . import onebot11_impl as _impl
else:
    # 走到这里说明 bot.py 的注册环节没拦住，明确报错而不是静默降级
    raise ValueError(f'BOT_ADAPTER={_ADAPTER_NAME!r} 没有对应的适配层实现')

ActionFailed = _impl.ActionFailed
Message = _impl.Message
MessageEvent = _impl.MessageEvent
build_markdown_segment = _impl.build_markdown_segment
get_group_id = _impl.get_group_id
get_scene = _impl.get_scene
has_file_segment = _impl.has_file_segment
is_text_or_at_message = _impl.is_text_or_at_message
iter_file_urls = _impl.iter_file_urls
parse_mentions = _impl.parse_mentions
send_image = _impl.send_image
supports_markdown = _impl.supports_markdown

__all__ = [
    'ActionFailed',
    'Message',
    'MessageEvent',
    'ParsedMentions',
    'Scene',
    'build_markdown_segment',
    'get_adapter_name',
    'get_group_id',
    'get_scene',
    'has_file_segment',
    'is_text_or_at_message',
    'iter_file_urls',
    'parse_mentions',
    'scene_label',
    'send_image',
    'supports_markdown',
]
