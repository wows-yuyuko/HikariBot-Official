import os
import shutil
import traceback
from typing import List

import nonebot
from fastapi import FastAPI
from fastapi.responses import FileResponse
from hikari_core import callback_hikari, init_hikari, init_hikari_no_output
from hikari_core.cache_utils import get_cache_file
from hikari_core.config import set_hikari_config
from hikari_core.model import Func
from hikari_core.moudle.wws_real_game import (
    add_listen_list,
    delete_listen_list,
    get_diff_ship,
    get_listen_list,
)
from nonebot import get_driver, on_command, on_message
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

from hikari_bot.plugins.hikari_bot_qq_official.game.ocr import get_Random_Ocr_Pic
from hikari_bot.plugins.hikari_bot_qq_official.game.pupu import get_pupu_msg
from hikari_bot.plugins.hikari_bot_qq_official.select_state import wait_to_select
from hikari_bot.plugins.hikari_bot_qq_official.template import select_template
from hikari_bot.plugins.hikari_bot_qq_official.utils import upload_image, check_rule

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
    game_path=str(get_cache_file())
)

ignore_list = [add_listen_list, delete_listen_list, get_diff_ship, get_listen_list, ]

image_path = get_cache_file() / 'image_cache'


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
            GroupId=group_id, Ignore_List=ignore_list)
        if hikari.Status == 'success':
            if isinstance(hikari.Output.Data, bytes):
                if isinstance(ev, GuildMessageEvent):
                    await wws.send(MessageSegment.file_image(hikari.Output.Data))
                else:
                    url = await upload_image(hikari.Output.Data)
                    logger.success(url)
                    await wws.send(MessageSegment.image(url))
            elif isinstance(hikari.Output.Data, str):
                await wws.send(hikari.Output.Data)
        elif hikari.Status == 'wait':
            if hikari.Output.Template in 'select-ship-v3.html':
                data_list = []
                index = 1
                for club in hikari.Input.Select_Data[:10]:
                    data_list.append(select_template.SelectClan(index=index, tag=club.get('tag', ''), name=club.get('name', ''), ))
                    index += 1
                    await wws.send(select_template.get_clan_markdown(data_list))
            elif hikari.Output.Template in 'select-clan.html':
                data_list = []
                index = 1
                for club in hikari.Input.Select_Data[:10]:
                    data_list.append(select_template.SelectClan(index=index, tag=club.get('tag', ''), name=club.get('name', ''), ))
                    index += 1
                await wws.send(select_template.get_clan_markdown(data_list))
            elif isinstance(ev, GuildMessageEvent):
                await wws.send(MessageSegment.file_image(hikari.Output.Data))
            else:
                url = await upload_image(hikari.Output.Data)
                logger.success(url)
                await wws.send(MessageSegment.image(url))
            hikari = await wait_to_select(hikari)
            if hikari.Status == 'error':
                await wws.send(str(hikari.Output.Data))
                return
            hikari = await callback_hikari(hikari)
            if isinstance(hikari.Output.Data, bytes):
                if isinstance(ev, GuildMessageEvent):
                    await wws.send(MessageSegment.file_image(hikari.Output.Data))
                else:
                    url = await upload_image(hikari.Output.Data)
                    logger.success(url)
                    await wws.send(MessageSegment.image(url))
            elif isinstance(hikari.Output.Data, str):
                await wws.send(str(hikari.Output.Data))
        else:
            await wws.send(str(hikari.Output.Data))
    except FinishedException:
        return
    except ActionFailed as e:
        logger.error(traceback.format_exc())
        try:
            await wws.send(f'发不出图片，可能撞限速了QAQ，请在频道重新尝试\n{e}')
            return True
        except Exception:
            logger.error(traceback.format_exc())
            pass
        return False
    except Exception:
        logger.error(traceback.format_exc())
        await wws.send('呜呜呜发生了错误，可能是网络问题，如果过段时间不能恢复请联系麻麻哦~')


@bot_get_random_pic.handle()
async def send_random_ocr_image(ev: MessageEvent):
    try:
        img = await get_Random_Ocr_Pic()
        if isinstance(img, bytes):
            if isinstance(ev, GuildMessageEvent):
                await wws.send(MessageSegment.file_image(img))
            else:
                url = await upload_image(img)
                logger.success(url)
                await wws.send(MessageSegment.image(url))
        elif isinstance(img, str):
            await bot_get_random_pic.send(str(img))
    except Exception:
        logger.error(traceback.format_exc())
        await bot_get_random_pic.send('呜呜呜发生了错误，可能是网络问题，如果过段时间不能恢复请联系麻麻哦~')
        return


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


@bot_pupu.handle()
async def send_pupu_msg(ev: MessageEvent):
    try:
        if check_rule(ev):
            msg = await get_pupu_msg()
            await bot_pupu.send(msg)
    except ActionFailed:
        logger.warning(traceback.format_exc())
        try:
            await bot_pupu.send('噗噗寄了>_<可能被风控了QAQ')
        except Exception:
            pass
        return


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
