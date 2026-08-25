import importlib.util
import traceback
from pathlib import Path
from typing import Optional, Any, Callable

from nonebot import get_driver, get_plugin_config, on_message
from nonebot.adapters.qq import (
    MessageEvent, )
from nonebot.internal.matcher import Matcher
from nonebot.log import logger

from hikari_bot.plugins.hikari_bot_qq_official.config import Config
from hikari_bot.plugins.hikari_bot_qq_official.utils import (
    has_file_segment,get_message_event_type
)

plugin_config = get_plugin_config(Config)

driver = get_driver()

# ============ 配置 ============
SCRIPT_FILE_NAME = "file_handler.py"  # 同级目录脚本文件名
FUNCTION_NAME = "process_file"  # 处理函数名


# ============ 脚本加载器 ============
class ScriptLoader:
    """启动时加载外部脚本"""

    def __init__(self, script_path: Path, func_name: str):
        self.script_path = script_path
        self.func_name = func_name
        self.handler_func: Optional[Callable] = None

        # 启动时加载一次
        self._load_script()

    def _load_script(self) -> bool:
        """加载脚本文件（仅启动时执行一次）"""
        if not self.script_path.exists():
            logger.info(f"ℹ️ file_handler 脚本不存在: {self.script_path.name}，使用默认处理逻辑")
            self.handler_func = None
            return False

        try:
            # 动态加载模块
            spec = importlib.util.spec_from_file_location("external_handler", self.script_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载file_handler脚本: {self.script_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 获取处理函数
            if hasattr(module, self.func_name):
                self.handler_func = getattr(module, self.func_name)
                logger.info(f"✅ file_handler脚本加载成功: {self.script_path.name}")
                return True
            else:
                logger.error(f"❌ file_handler脚本中未找到函数: {self.func_name}")
                self.handler_func = None
                return False

        except Exception as e:
            logger.error(f"❌ 加载file_handler脚本失败: {e}\n{traceback.format_exc()}")
            self.handler_func = None
            return False

    async def call(self, *args, **kwargs) -> Any:
        """调用外部处理函数"""
        if self.handler_func is None:
            return await self._default_handler(*args, **kwargs)
        try:
            import inspect
            if inspect.iscoroutinefunction(self.handler_func):
                return await self.handler_func(*args, **kwargs)
            else:
                return self.handler_func(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ file_handler脚本执行失败: {e}\n{traceback.format_exc()}")
            return await self._default_handler(*args, **kwargs)

    async def _default_handler(self, bot_matcher: Matcher, ev: MessageEvent):
        """默认处理逻辑（外部脚本不存在时的降级方案）"""

# ============ 初始化 ============
script_loader: Optional[ScriptLoader] = None


@driver.on_startup
async def init_script_loader():
    """启动时初始化脚本加载器（仅执行一次）"""
    global script_loader

    # 获取插件所在目录
    plugin_dir = Path(__file__).parent
    script_path = plugin_dir / SCRIPT_FILE_NAME

    logger.info(f"🔍 检查外部脚本: {script_path}")
    script_loader = ScriptLoader(script_path, FUNCTION_NAME)


# ============ 消息处理器 ============
# 文件消息监听：私聊/群/频道消息中携带文件附件时触发
file_listen = on_message(priority=5, block=False, rule=has_file_segment)


@file_listen.handle()
async def handle_file_message(ev: MessageEvent):
    """专门处理收到的文件消息（文件附件由适配器解析为 file 段，data 仅含 url）"""
    if not plugin_config.bot_enable_file_listen:
        return
    try:
        # 调用脚本处理
        if script_loader is not None:
            await script_loader.call(file_listen, ev)
    except Exception:
        logger.error(traceback.format_exc())
