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

from .start import *
from hikari_bot.plugins.hikari_bot_qq_official.select_state import bot_listen