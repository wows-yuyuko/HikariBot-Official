import sys
from pathlib import Path

# hikari_core 以 git 子模块形式随仓库同步，包位于 hikari_core/hikari_core
# 将子模块根目录加入 sys.path，保证 `from hikari_core import ...` 可导入
_hikari_core_path = str(Path(__file__).resolve().parents[3] / "hikari_core")
if _hikari_core_path not in sys.path:
    sys.path.insert(0, _hikari_core_path)

from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="hikari_bot_qq_official",
    description="",
    usage="",
    config=Config,
)

config = get_plugin_config(Config)

# 启动配置（set_hikari_config 与适配器能力告警）
from . import start  # noqa: F401
# 机器人消息处理（wws 指令业务）
from hikari_bot.plugins.hikari_bot_qq_official.bot.bot import main, wws
from hikari_bot.plugins.hikari_bot_qq_official.bot.file_listener.file import file_listen
from hikari_bot.plugins.hikari_bot_qq_official.select_state import bot_listen