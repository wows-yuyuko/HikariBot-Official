"""插件启动与配置：hikari_core 初始化、每日定时清理图片缓存"""
import time
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from nonebot import get_driver
from nonebot.log import logger

from hikari_bot.plugins.hikari_bot_qq_official.utils import image_path
from hikari_core import get_cache_file, set_hikari_config

driver = get_driver()

_proxy = None
if driver.config.proxy_on:
    _proxy = driver.config.proxy

set_hikari_config(
    use_broswer=driver.config.htmlrender_browser,
    http2=driver.config.http2,
    proxy=_proxy,
    token=driver.config.api_token,
    game_path=str(get_cache_file()),
    save_template_html=False
)

# 每日 4 点（北京时间）自动清理 1 小时前的图片缓存
_scheduler = AsyncIOScheduler(timezone=ZoneInfo('Asia/Shanghai'))


def _cleanup_old_images(max_age_seconds: int = 3600) -> int:
    """删除 image_cache 中超过 max_age_seconds 的图片，返回删除数量"""
    cutoff = time.time() - max_age_seconds
    image_path.mkdir(parents=True, exist_ok=True)
    removed = 0
    for file in image_path.iterdir():
        try:
            if file.is_file() and file.stat().st_mtime < cutoff:
                file.unlink()
                removed += 1
        except OSError:
            logger.warning(f'删除图片失败，跳过: {file.name}')
    return removed


@driver.on_startup
async def start_scheduler():
    _scheduler.add_job(
        _cleanup_old_images,
        'cron',
        hour=4,
        minute=0,
        id='daily_image_cache_cleanup',
        replace_existing=True,
    )
    _scheduler.start()
    logger.success('已启动每日 4 点图片缓存清理任务')


@driver.on_shutdown
async def stop_scheduler():
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
