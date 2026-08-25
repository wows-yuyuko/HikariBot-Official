"""机器人消息处理：wws 指令的完整业务（@处理、输出发送、选择流程）"""
import traceback

from nonebot import get_driver, get_plugin_config, on_command, on_message
from nonebot.adapters.qq import (
    ActionFailed,
    Message,
    MessageEvent,
    MessageSegment, )
from nonebot.log import logger
from nonebot.params import CommandArg

from hikari_bot.plugins.hikari_bot_qq_official.config import Config
from hikari_bot.plugins.hikari_bot_qq_official.select_state import wait_to_select
from hikari_bot.plugins.hikari_bot_qq_official.template import select_template
from hikari_bot.plugins.hikari_bot_qq_official.utils import (
    byte2md5,
    get_message_event_type,
    has_file_segment,
    is_text_or_at_message,
    upload_image,
)
from hikari_core import callback_hikari, init_hikari_no_output, output_hikari
from hikari_core.core.model import Hikari_Model

plugin_config = get_plugin_config(Config)

driver = get_driver()

wws = on_command('wws', block=False, aliases={'WWS'}, priority=10, rule=is_text_or_at_message)


async def _send_output(ev: MessageEvent, sender, hikari: Hikari_Model):
    """发送 Hikari 输出数据，自动处理 bytes（图片）和 str（文本）。"""
    hikari = await output_hikari(hikari)
    data = hikari.Output.Data
    if isinstance(data, bytes):
        if get_message_event_type(ev) in ('CHANNEL', 'CHANNEL_DIRECT'):
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


async def init_hikari_process(ev: MessageEvent, message: Message) -> Hikari_Model:
    """处理 @提及 并初始化 Hikari 请求

    - @到机器人：整段移除（提示机器人，不代表查询目标）
    - @到其他用户：替换为文本 'me'，并将查询身份切换为被@用户（等价于其本人执行 me）
    - 仅允许 @ 一个非机器人用户，多个直接返回错误
    """
    parts = []
    platform_id = None
    at_count = 0
    for seg in message:
        if seg.type == 'mention_user':
            if seg.data.get('is_bot', False):
                continue
            at_count += 1
            if at_count > 1:
                return Hikari_Model().error('仅允许@一个用户')
            parts.append("me")
            platform_id = seg.data.get('user_id')
        else:
            parts.append(str(seg))
    if platform_id is None:
        platform_id = ev.get_user_id()
    server_type = driver.config.platform
    group_id = None
    command_text = ' '.join(p.strip() for p in parts if p.strip())
    str_platform_id = str(platform_id)
    logger.success(f'init_hikari 传递参数 platform={server_type} PlatformId={str_platform_id} 命令={command_text}')
    return await init_hikari_no_output(
        platform=server_type,
        PlatformId=str_platform_id,
        command_text=command_text,
        GroupId=group_id,
    )


@wws.handle()
async def main(ev: MessageEvent, message: Message = CommandArg()):  # noqa: B008, PLR0915
    try:
        # logger.info(f'收到 wws 指令 事件类型={get_message_event_type(ev)} 用户={ev.get_user_id()}')
        hikari = await init_hikari_process(ev, message)
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
            hikari = await wait_to_select(hikari, ev.get_user_id())
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
