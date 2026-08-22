import os
import shutil
import traceback
from typing import List

import nonebot
from fastapi import FastAPI
from fastapi.responses import FileResponse
from hikari_core import callback_hikari, init_hikari, init_hikari_no_output, output_hikari
from hikari_core import get_cache_file,set_hikari_config

from hikari_core.core.model import Func, Hikari_Model
from nonebot import get_driver, on_command, on_message, Bot
from nonebot.adapters.qq import (
    ActionFailed,
    GuildMessageEvent,
    Message,
    MessageEvent,
    MessageSegment, )
from nonebot.exception import FinishedException
from nonebot.log import logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER


from hikari_bot.plugins.hikari_bot_qq_official.select_state import wait_to_select
from hikari_bot.plugins.hikari_bot_qq_official.template import select_template
from hikari_bot.plugins.hikari_bot_qq_official.utils import upload_image, check_rule, image_path

bot_get_random_pic = on_command('wws 随机表情包', block=True, priority=5)
delete_image_cache = on_command('wws 清除本地缓存', priority=5, block=True, permission=SUPERUSER)
wws = on_command('wws', block=False, aliases={'WWS'}, priority=10)
bot_pupu = on_command('噗噗', block=False, priority=5)
bot_listen = on_message(priority=5, block=False)

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




async def _send_output(ev: MessageEvent, sender, hikari: Hikari_Model):
    hikari = await output_hikari(hikari)
    data = hikari.Output.Data
    """发送 Hikari 输出数据，自动处理 bytes（图片）和 str（文本）。"""
    if isinstance(data, bytes):
        if isinstance(ev, GuildMessageEvent):
            await sender.send(MessageSegment.file_image(data))
        else:
            url = await upload_image(data)
            logger.success(url)
            await sender.send(MessageSegment.image(url))
    elif isinstance(data, str):
        await sender.send(data)


def _build_select_list(type: int, select_data):
    """从 Select_Data 构建 SelectClan 列表。"""
    data_list = []
    if type == 1:
        for index, club in enumerate(select_data[:10], start=1):
            data_list.append(
                select_template.SelectShip(index=index, level_str=club.get('levelStr') or '0', ship_type_url=club.get('shipTypeImage') or '', ship_type=club.get('shipType') or 'Battleship',
                                           name_cn=club.get('nameCn') or '', name_cn360=club.get('nameCn360') or '', name_en=club.get('nameEnglish') or '')
            )
    elif type == 2:
        for index, club in enumerate(select_data[:10], start=1):
            data_list.append(
                select_template.SelectClan(index=index, tag=club.get('tag') or '', name=club.get('name') or '', ))

    return data_list


@wws.handle()
async def main(ev: MessageEvent, bot: Bot, message: Message = CommandArg()):  # noqa: B008, PLR0915
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
            # 展示选择界面
            if bot.self_id not in get_driver().config.bot_is_md_file_list:
                if hikari.Output.Template in ('select-ship-v3.html', 'select-clan.html'):
                    if hikari.Output.Template == 'select-ship-v3.html':
                        await wws.send(select_template.get_ship_markdown(_build_select_list(1, hikari.Input.Select_Data)))
                    else:
                        await wws.send(select_template.get_clan_markdown(_build_select_list(2, hikari.Input.Select_Data)))
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
    except Exception:
        logger.error(traceback.format_exc())
        await wws.send('呜呜呜发生了错误，可能是网络问题，如果过段时间不能恢复请联系麻麻哦~')


@driver.on_startup
def web_run():
    if get_driver().config.upload_image == 'local':
        app: FastAPI = nonebot.get_app()
        if not os.path.exists(image_path):
            os.mkdir(image_path)
        logger.success(f'本地文件服务器启动成功 path={image_path}，请确认是否放行对应端口，如果没有公网ip请将配置项UPLOAD_IMAGE改为smms或oss')

        @app.get('/images/{filename}')
        async def get_file(filename):
            return FileResponse(image_path / filename)


@delete_image_cache.handle()
async def delete_image(ev: MessageEvent):
    try:
        shutil.rmtree(image_path, ignore_errors=True)
        if not os.path.exists(image_path):
            os.mkdir(image_path)
        await delete_image_cache.send('清除缓存成功')
    except Exception:
        logger.error(traceback.format_exc())
        await delete_image_cache.send('清除缓存失败')
