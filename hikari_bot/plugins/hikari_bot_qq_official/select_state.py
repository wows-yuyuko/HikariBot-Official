import asyncio
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional

from nonebot import get_plugin_config, on_message
from nonebot.adapters.qq import (
    MessageEvent,
)
from nonebot.log import logger

from hikari_bot.plugins.hikari_bot_qq_official.config import Config
from hikari_bot.plugins.hikari_bot_qq_official.utils import is_text_or_at_message

plugin_config = get_plugin_config(Config)

bot_listen = on_message(priority=5, block=False, rule=is_text_or_at_message)


@dataclass
class SelectState:
    state: bool = False
    select_index: Optional[int] = None
    select_list: List = field(default_factory=list)  # 默认空列表


SelectProcess = defaultdict(SelectState)

# 配置常量
SELECT_TIMEOUT = 20  # 超时时间（秒）
CHECK_INTERVAL = 0.5  # 检查间隔（秒）


@bot_listen.handle()
async def change_select_state(ev: MessageEvent):
    """处理用户的选择输入"""
    try:
        msg = str(ev.get_message()).strip()
        qq_id = str(ev.get_user_id())

        # 获取当前状态
        current_state = SelectProcess.get(qq_id)
        if not current_state or not current_state.state:
            return

        # 验证输入是否为数字
        if not msg.isdigit():
            return

        select_num = int(msg)
        select_list = current_state.select_list or []
        max_size = plugin_config.bot_select_msg_is_md_max_size

        # 验证序号范围（与展示的最大选择数保持一致）
        if 1 <= select_num <= min(len(select_list), max_size):
            # 更新选择结果
            SelectProcess[qq_id] = SelectState(
                state=False,
                select_index=select_num,
                select_list=select_list
            )
        else:
            await bot_listen.send('请选择列表中的序号哦~')

    except Exception:
        logger.error(f"选择状态处理异常: {traceback.format_exc()}")


async def wait_to_select(hikari, selector_id: Optional[str] = None):
    """使用 asyncio.wait_for 实现超时控制；选择状态以发起人（selector_id）为键"""
    platform_id = selector_id or hikari.UserInfo.PlatformId
    select_data = hikari.Input.Select_Data or []

    # 同一用户已有进行中的选择流程时，拒绝并发，避免共享状态槽竞态
    existing = SelectProcess.get(platform_id)
    if existing and existing.state:
        return hikari.error('你有一个选择操作正在进行中，请等待完成或超时后再试')

    # 初始化选择状态
    SelectProcess[platform_id] = SelectState(
        state=True,
        select_index=None,
        select_list=select_data
    )

    async def wait_for_selection():
        """等待用户选择的协程"""
        while True:
            current_state = SelectProcess.get(platform_id)
            if current_state and current_state.select_index is not None:
                return current_state.select_index
            await asyncio.sleep(CHECK_INTERVAL)

    try:
        # 设置超时等待
        select_index = await asyncio.wait_for(
            wait_for_selection(),
            timeout=SELECT_TIMEOUT
        )

        hikari.Input.Select_Index = select_index
        return hikari

    except asyncio.TimeoutError:
        return hikari.error('选择超时，请重新操作')

    finally:
        # 清理状态
        SelectProcess[platform_id] = SelectState()
