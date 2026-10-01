
import traceback

from nonebot import logger
from nonebot.internal.matcher import Matcher

from hikari_bot.plugins.hikari_bot_qq_official.adapters import (
    MessageEvent,
    get_scene,
    iter_file_urls,
    scene_label,
)


async def process_file(bot_matcher: Matcher, ev: MessageEvent):
    """
    处理文件（必须实现的函数）
    """
    try:
        scene = scene_label(get_scene(ev))
        for url in iter_file_urls(ev):
            logger.info(f'收到文件 场景={scene} 用户={ev.get_user_id()} url={url}')
            # TODO: 文件业务处理（下载/转发/入库等）
            await bot_matcher.send(f'收到文件：{url or "(无地址)"}')
    except Exception:
        logger.error(traceback.format_exc())
        await bot_matcher.send("文件处理失败")
