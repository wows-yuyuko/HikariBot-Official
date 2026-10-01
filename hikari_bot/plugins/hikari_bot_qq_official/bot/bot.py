"""机器人消息处理：wws 指令的完整业务（@处理、输出发送、选择流程）

本模块不直接依赖任何具体适配器 —— 事件判定、@ 解析、发图都经 adapters 层。
"""
import traceback

from nonebot import Bot, get_plugin_config, on_command
from nonebot.internal.rule import Rule
from nonebot.log import logger
from nonebot.params import CommandArg

from hikari_bot.adapter_registry import resolve_platform
from hikari_bot.plugins.hikari_bot_qq_official.adapters import (
    ActionFailed,
    Message,
    MessageEvent,
    Scene,
    build_markdown_segment,
    get_group_id,
    get_scene,
    is_text_or_at_message,
    parse_mentions,
    scene_label,
    send_image,
    supports_markdown,
)
from hikari_bot.plugins.hikari_bot_qq_official.config import Config
from hikari_bot.plugins.hikari_bot_qq_official.select_state import wait_to_select
from hikari_bot.plugins.hikari_bot_qq_official.template import select_template
from hikari_core import callback_hikari, init_hikari_no_output, output_hikari
from hikari_core.core.model import Hikari_Model

plugin_config = get_plugin_config(Config)

wws = on_command('wws', block=False, aliases={'WWS'}, priority=10, rule=Rule(is_text_or_at_message))


async def _send_output(ev: MessageEvent, sender, hikari: Hikari_Model):
    """发送 Hikari 输出数据，自动处理 bytes（图片）和 str（文本）。"""
    hikari = await output_hikari(hikari)
    data = hikari.Output.Data
    if isinstance(data, bytes):
        # 各适配器都有自己的原生发图通道（QQ 富媒体 / OneBot base64），均不需要图床
        await send_image(sender, data)
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


async def init_hikari_process(bot: Bot, ev: MessageEvent, message: Message) -> Hikari_Model:
    """处理 @提及 并初始化 Hikari 请求

    - @到机器人：整段移除（提示机器人，不代表查询目标）
    - @到其他用户：替换为文本 'me'，并将查询身份切换为被@用户（等价于其本人执行 me）
    - 仅允许 @ 一个非机器人用户，多个直接返回错误
    """
    parsed = parse_mentions(message, bot.self_id)
    if parsed.at_count > 1:
        return Hikari_Model().error('仅允许@一个用户')

    # 用 is None 判断而非 or：旧实现是「@到的用户 id 为 None 才回退到发送者」，
    # 空串同样视为已取到值，保持与改造前逐字一致
    platform_id = parsed.mentioned_user_id if parsed.mentioned_user_id is not None else ev.get_user_id()
    server_type = resolve_platform()
    command_text = ' '.join(p.strip() for p in parsed.parts if p.strip())
    str_platform_id = str(platform_id)

    # 私信 / 群聊场景判断：群聊（群@机器人、群普通消息）需要给 GroupId 赋值，供分群功能使用
    scene = get_scene(ev)
    if scene in (Scene.GROUP, Scene.GROUP_AT):
        group_id = get_group_id(ev)
    else:
        group_id = None

    logger.success(f'init_hikari 场景={scene_label(scene)} 传递参数 platform={server_type} PlatformId={str_platform_id} GroupId={group_id} 命令={command_text}')
    return await init_hikari_no_output(
        platform=server_type,
        PlatformId=str_platform_id,
        BotId=bot.self_id,
        command_text=command_text,
        GroupId=group_id,
    )


@wws.handle()
async def main(ev: MessageEvent, bot: Bot, message: Message = CommandArg()):  # noqa: B008, PLR0915
    try:
        hikari = await init_hikari_process(bot, ev, message)
        # ========== 状态判断 ==========
        if hikari.Status == 'success':
            await _send_output(ev, wws, hikari)
        elif hikari.Status == 'wait':
            # 展示选择界面：适配器支持 markdown 且开启 md 时，选择类模板走 markdown，否则走渲染图片
            if plugin_config.bot_select_msg_is_md and supports_markdown():
                if hikari.Output.Template in ('select-ship-v3.html', 'select-clan.html'):
                    max_size = plugin_config.bot_select_msg_is_md_max_size
                    if hikari.Output.Template == 'select-ship-v3.html':
                        content = select_template.get_ship_markdown(_build_select_list(1, hikari.Input.Select_Data, max_size))
                    else:
                        content = select_template.get_clan_markdown(_build_select_list(2, hikari.Input.Select_Data, max_size))
                    await wws.send(build_markdown_segment(content))
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
