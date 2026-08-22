import re
import time
import traceback
from zoneinfo import ZoneInfo

import nonebot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from hikari_core import callback_hikari, init_hikari, init_hikari_no_output, output_hikari
from hikari_core import get_cache_file, set_hikari_config

from hikari_core.core.model import Func, Hikari_Model
from nonebot import get_driver, get_plugin_config, on_command
from nonebot.adapters.qq import (
    ActionFailed,
    GuildMessageEvent,
    Message,
    MessageEvent,
    MessageSegment, )
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER


from hikari_bot.plugins.hikari_bot_qq_official.config import Config
from hikari_bot.plugins.hikari_bot_qq_official.select_state import wait_to_select
from hikari_bot.plugins.hikari_bot_qq_official.template import select_template
from hikari_bot.plugins.hikari_bot_qq_official.utils import upload_image, check_rule, image_path, byte2md5

bot_get_random_pic = on_command('wws 随机表情包', block=True, priority=5)
delete_image_cache = on_command('wws 清除本地缓存', priority=5, block=True, permission=SUPERUSER)
wws = on_command('wws', block=False, aliases={'WWS'}, priority=10)
bot_pupu = on_command('噗噗', block=False, priority=5)

plugin_config = get_plugin_config(Config)

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




async def _send_output(ev: MessageEvent, sender, hikari: Hikari_Model):
    hikari = await output_hikari(hikari)
    data = hikari.Output.Data
    """发送 Hikari 输出数据，自动处理 bytes（图片）和 str（文本）。"""
    if isinstance(data, bytes):
        if isinstance(ev, GuildMessageEvent):
            await sender.send(MessageSegment.file_image(data))
        else:
            url = await upload_image(data)
            if url is None:
                await sender.send('呜呜呜，图片上传失败，请检查 UPLOAD_IMAGE 配置~')
                return
            logger.success(f'图片上传成功 md5={byte2md5(data)}')
            await sender.send(MessageSegment.image(url))
    elif isinstance(data, str):
        await sender.send(data)
    else:
        # Data 为 None 或未渲染的数据类型：给出兜底提示，避免静默丢失
        logger.warning(f'输出数据为空或类型不支持: type={type(data).__name__}')
        await sender.send('呜呜呜，没有拿到可展示的内容，请稍后再试~')


def _build_select_list(type: int, select_data, max_size: int = 10):
    """从 Select_Data 构建 SelectClan 列表，最多展示 max_size 条。"""
    data_list = []
    if type == 1:
        for index, club in enumerate(select_data[:max_size], start=1):
            data_list.append(
                select_template.SelectShip(index=index, level_str=club.get('levelStr') or '0', ship_type_url=club.get('shipTypeImage') or '', ship_type=club.get('shipType') or 'Battleship',
                                           name_cn=club.get('nameCn') or '', name_cn360=club.get('nameCn360') or '', name_en=club.get('nameEnglish') or '')
            )
    elif type == 2:
        for index, club in enumerate(select_data[:max_size], start=1):
            data_list.append(
                select_template.SelectClan(index=index, tag=club.get('tag') or '', name=club.get('name') or '', ))

    return data_list


@wws.handle()
async def main(ev: MessageEvent, message: Message = CommandArg()):  # noqa: B008, PLR0915
    try:
        if not check_rule(ev):
            await wws.finish('该功能已禁用')
        server_type = driver.config.platform
        qq_id = ev.get_user_id()
        group_id = None
        hikari = await init_hikari_no_output(
            platform=server_type,
            PlatformId=str(qq_id),
            command_text=str(message),
            GroupId=group_id,
        )
        # ========== 状态判断 ==========
        if hikari.Status == 'success':
            await _send_output(ev, wws, hikari)
        elif hikari.Status == 'wait':
            # 展示选择界面：开启 md 时选择类模板走 markdown，否则走渲染图片
            if plugin_config.bot_select_msg_is_md:
                if hikari.Output.Template in ('select-ship-v3.html', 'select-clan.html'):
                    max_size = plugin_config.bot_select_msg_is_md_max_size
                    if hikari.Output.Template == 'select-ship-v3.html':
                        await wws.send(select_template.get_ship_markdown(_build_select_list(1, hikari.Input.Select_Data, max_size)))
                    else:
                        await wws.send(select_template.get_clan_markdown(_build_select_list(2, hikari.Input.Select_Data, max_size)))
                else:
                    await _send_output(ev, wws, hikari)
            else:
                await _send_output(ev, wws, hikari)
            hikari = await wait_to_select(hikari)
            if hikari.Status == 'error':
                await wws.send(str(hikari.Output.Data))
                return
            hikari = await callback_hikari(hikari)  # callback_hikari 内部已调用 output_hikari
            await _send_output(ev, wws, hikari)
        else:
            await wws.send(str(hikari.Output.Data))
    except ActionFailed as e:
        logger.error(traceback.format_exc())
        try:
            await wws.send(f'发不出图片，可能撞限速了QAQ，请在频道重新尝试\n{e}')
        except Exception:
            logger.error(traceback.format_exc())
    except Exception as e:
        logger.error(traceback.format_exc())
        if isinstance(e, (ValueError, TypeError)):
            await wws.send('呜呜呜参数似乎有问题，请检查指令格式~')
        else:
            await wws.send('呜呜呜发生了错误，可能是网络问题，如果过段时间不能恢复请联系麻麻哦~')


@driver.on_startup
def web_run():
    if get_driver().config.upload_image == 'local':
        app: FastAPI = nonebot.get_app()
        image_path.mkdir(parents=True, exist_ok=True)
        logger.success(f'本地文件服务器启动成功 path={image_path}，请确认是否放行对应端口，如果没有公网ip请将配置项UPLOAD_IMAGE改为smms或oss')

        @app.get('/images/{filename}')
        async def get_file(filename: str):
            # 防路径穿越：仅允许本地图片缓存中的 md5 文件名（upload_local 的命名规则）
            if not re.fullmatch(r'[0-9a-f]{32}\.(?:jpg|png|gif|webp)', filename):
                return JSONResponse(status_code=400, content={'detail': 'invalid filename'})
            file = image_path / filename
            if not file.is_file():
                return JSONResponse(status_code=404, content={'detail': 'not found'})
            return FileResponse(file)


@delete_image_cache.handle()
async def delete_image(ev: MessageEvent):
    try:
        removed = _cleanup_old_images()
        await delete_image_cache.send(f'清理完成，已删除 {removed} 个 1 小时前的图片')
    except Exception:
        logger.error(traceback.format_exc())
        await delete_image_cache.send('清除缓存失败')
