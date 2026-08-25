
import traceback

from nonebot import logger
from nonebot.adapters.qq import MessageEvent
from nonebot.internal.matcher import Matcher

from hikari_bot.plugins.hikari_bot_qq_official.utils import get_message_event_type


async def process_file(bot_matcher: Matcher, ev: MessageEvent):
    """
    处理文件（必须实现的函数）
    """
    try:
        files = [seg for seg in ev.get_message() if seg.type == 'file']
        for seg in files:
            url = seg.data.get('url', '')
            logger.info(f'收到文件 事件类型={get_message_event_type(ev)} 用户={ev.get_user_id()} url={url}')
            # TODO: 文件业务处理（下载/转发/入库等）
            await bot_matcher.send(f'收到文件：{url or "(无地址)"}')
    except Exception:
        logger.error(traceback.format_exc())
        await bot_matcher.send("文件处理失败")
