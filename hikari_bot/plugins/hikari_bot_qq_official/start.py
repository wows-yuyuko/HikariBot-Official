"""插件启动与配置：hikari_core 初始化"""
from nonebot import get_driver, get_plugin_config
from nonebot.log import logger

from hikari_bot.plugins.hikari_bot_qq_official.adapters import supports_markdown
from hikari_bot.plugins.hikari_bot_qq_official.config import Config
from hikari_core import get_cache_file, set_hikari_config

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
    image_type='webp',
    Authorization=plugin_config.bot_authorization,
    save_template_html=False
)

# markdown 选择表是 QQ 官方独有的能力：OneBot 下会静默回落成渲染图片，这里提前提示一次
if plugin_config.bot_select_msg_is_md and not supports_markdown():
    logger.warning('BOT_SELECT_MSG_IS_MD 已开启，但当前适配器不支持 markdown 消息段，选择类消息将按渲染图片发送')
