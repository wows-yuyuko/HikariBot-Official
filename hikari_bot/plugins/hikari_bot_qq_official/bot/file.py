import importlib.util
import inspect
import traceback
from pathlib import Path
from typing import Optional, Any, Callable

from nonebot import get_driver, get_plugin_config, on_message
from nonebot.internal.matcher import Matcher
from nonebot.log import logger

from hikari_bot.plugins.hikari_bot_qq_official.adapters import MessageEvent, has_file_segment
from hikari_bot.plugins.hikari_bot_qq_official.config import Config

plugin_config = get_plugin_config(Config)

driver = get_driver()

# ============ 配置 ============
SCRIPT_FILE_NAME = "file_handler-*"  # 目录内脚本文件名
FUNCTION_NAME = "process_file"  # 处理函数名
LISTEN_DIR_NAME = "bot_file_listener"  # 外部脚本目录名（位于项目根目录下）


def listen_dir() -> Path:
    """外部脚本目录：项目根目录下的 bot_file_listener/（随包升级不会被覆盖）"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent / LISTEN_DIR_NAME
    # 打包/异常场景下退回当前工作目录
    return Path.cwd() / LISTEN_DIR_NAME


# ============ 脚本加载器 ============
class ScriptLoader:
    """启动时加载外部脚本（支持多个脚本文件）"""

    def __init__(self, script_dir: Path, file_pattern: str, func_name: str):
        self.script_dir = script_dir
        self.file_pattern = file_pattern
        self.func_name = func_name
        self.handler_funcs: list[Callable] = []  # 改为列表存储多个函数

        # 启动时加载所有匹配的脚本
        self._load_all_scripts()

    def _load_all_scripts(self) -> bool:
        """加载所有匹配的脚本文件（仅启动时执行一次）"""
        # 目录不存在则按需创建，方便用户直接把脚本丢进去
        if not self.script_dir.exists():
            try:
                self.script_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"📁 已创建脚本目录: {self.script_dir}")
            except OSError as e:
                logger.error(f"❌ 无法创建脚本目录 {self.script_dir}: {e}")

        # 查找所有匹配的脚本文件（排序保证加载顺序稳定）
        script_files = sorted(self.script_dir.glob(self.file_pattern))

        if not script_files:
            logger.info(f"ℹ️ 未找到匹配的file_handler脚本: {self.script_dir}/{self.file_pattern}，使用默认处理逻辑")
            self.handler_funcs = []
            return False

        loaded_count = 0
        for script_path in script_files:
            if self._load_single_script(script_path):
                loaded_count += 1

        logger.info(f"✅ 成功加载 {loaded_count}/{len(script_files)} 个file_handler脚本")
        return loaded_count > 0

    def _load_single_script(self, script_path: Path) -> bool:
        """加载单个脚本文件"""
        try:
            # 动态加载模块（使用唯一模块名避免冲突）
            module_name = f"external_handler_{script_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, script_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载file_handler脚本: {script_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 获取处理函数
            if hasattr(module, self.func_name):
                handler_func = getattr(module, self.func_name)
                self.handler_funcs.append(handler_func)
                logger.info(f"✅ file_handler脚本加载成功: {script_path.name}")
                return True
            else:
                logger.error(f"❌ file_handler脚本中未找到函数: {self.func_name} in {script_path.name}")
                return False

        except Exception as e:
            logger.error(f"❌ 加载file_handler脚本失败 {script_path.name}: {e}\n{traceback.format_exc()}")
            return False

    async def call_all(self, *args, **kwargs) -> Any:
        """依次调用所有外部处理函数"""
        if not self.handler_funcs:
            return await self._default_handler(*args, **kwargs)

        results = []
        for handler_func in self.handler_funcs:
            try:
                if inspect.iscoroutinefunction(handler_func):
                    result = await handler_func(*args, **kwargs)
                else:
                    result = handler_func(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ file_handler脚本执行失败: {e}\n{traceback.format_exc()}")
                # 继续执行下一个脚本
                continue

        return results  # 返回所有脚本的执行结果

    async def _default_handler(self, bot_matcher: Matcher, ev: MessageEvent):
        """默认处理逻辑（外部脚本不存在时的降级方案）"""
        pass


# ============ 初始化 ============
script_loader: Optional[ScriptLoader] = None

@driver.on_startup
async def init_script_loader():
    """启动时初始化脚本加载器（加载所有匹配的脚本）"""
    global script_loader

    # 固定扫描项目根目录下的 bot_file_listener/
    script_dir = listen_dir()

    logger.info(f"🔍 检查外部脚本目录: {script_dir}/{SCRIPT_FILE_NAME}")
    script_loader = ScriptLoader(script_dir, SCRIPT_FILE_NAME, FUNCTION_NAME)


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
            await script_loader.call_all(file_listen, ev)
    except Exception:
        logger.error(traceback.format_exc())
