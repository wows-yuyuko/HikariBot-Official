"""文件处理插件示例：接收 -> 校验 -> 下载 -> 落盘去重 -> 回执

复制到 hikari_bot/plugins/hikari_bot_qq_official/bot/file_listener/ 下面（和 file.py 放一起），
文件名保持 file_handler- 前缀，再在 .env.prod 里设置 BOT_ENABLE_FILE_LISTEN=true 即可生效。
业务逻辑写在 on_file_saved 里，其余流程一般不用动。
"""

import hashlib
import re
import traceback
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from hikari_core import get_cache_file
from nonebot import logger
from nonebot.internal.matcher import Matcher

from hikari_bot.plugins.hikari_bot_qq_official.adapters import (
    MessageEvent,
    get_scene,
    iter_file_urls,
    scene_label,
)

# ============ 配置 ============
SAVE_DIR = get_cache_file() / 'file_cache'  # 落盘目录
ALLOWED_EXT: set[str] = set()  # 扩展名白名单，空集合表示不限制，例如 {'.wowsreplay', '.zip'}
MAX_FILE_SIZE = 32 * 1024 * 1024  # 单个文件大小上限
MAX_FILES_PER_MESSAGE = 5  # 一条消息最多处理几个文件
DOWNLOAD_TIMEOUT = 60.0
CHUNK_SIZE = 64 * 1024
REPLY_TO_USER = True  # 纯后台入库可以关掉回执

_UNSAFE_NAME_RE = re.compile(r'[^\w.\-]+')  # \w 在 Python3 里包含中文


class FileTooLargeError(Exception):
    """文件超过 MAX_FILE_SIZE，属于可预期的拒绝"""

    def __init__(self, size: int):
        super().__init__(f'文件过大（{format_size(size)}），上限 {format_size(MAX_FILE_SIZE)}')


async def process_file(bot_matcher: Matcher, ev: MessageEvent):
    """处理文件（必须实现的函数）"""
    try:
        files = iter_file_urls(ev)
        if not files:
            return
        names = attachment_names(ev)

        results = []
        if len(files) > MAX_FILES_PER_MESSAGE:
            results.append(f'本次收到 {len(files)} 个文件，只处理前 {MAX_FILES_PER_MESSAGE} 个')
            files = files[:MAX_FILES_PER_MESSAGE]
        for raw_url in files:
            results.append(await handle_single_file(bot_matcher, ev, raw_url, names.get(raw_url, '')))

        # 官方对被动消息的回复次数有限制，多个文件合成一条发
        if REPLY_TO_USER and results:
            await bot_matcher.send('\n'.join(results))
    except Exception:
        logger.error(traceback.format_exc())
        if REPLY_TO_USER:
            await bot_matcher.send('文件处理失败')


async def handle_single_file(bot_matcher: Matcher, ev: MessageEvent, raw_url: str, original_name: str = '') -> str:
    """处理单个文件，返回一行回执文案，异常不外抛，单个失败不影响同消息里的其他文件"""
    url = normalize_url(raw_url)
    if not url:
        return '收到文件，但没拿到下载地址'

    scene = get_scene(ev)
    user_id = ev.get_user_id()
    name, ext = resolve_file_name(url, original_name)
    logger.info(f'收到文件 场景={scene_label(scene)} 用户={user_id} 文件名={name} url={url}')
    if ALLOWED_EXT and ext not in ALLOWED_EXT:
        return f'{name}：不支持的文件类型，只接受 {"/".join(sorted(ALLOWED_EXT))}'

    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = SAVE_DIR / f'{uuid4().hex}.part'  # 先写临时文件，避免下载中断留下半截文件
    try:
        size, md5 = await download_file(url, temp_path)
    except FileTooLargeError as e:
        temp_path.unlink(missing_ok=True)
        return f'{name}：{e}'
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        logger.error(f'文件下载失败 文件名={name} url={url}\n{traceback.format_exc()}')
        return f'{name}：下载失败（{type(e).__name__}）'

    # md5 前 8 位做后缀，保留原始文件名的同时天然去重
    final_path = SAVE_DIR / f'{Path(name).stem if ext else name}_{md5[:8]}{ext}'
    reused = final_path.exists()
    if reused:
        temp_path.unlink(missing_ok=True)
    else:
        temp_path.replace(final_path)
    logger.info(f'文件{"已存在" if reused else "已保存"} {final_path.name} 大小={size} md5={md5}')

    meta = {'name': name, 'size': size, 'md5': md5, 'url': url, 'scene': scene, 'user_id': user_id, 'reused': reused}
    try:
        await on_file_saved(bot_matcher, ev, final_path, meta)
    except Exception:
        logger.error(f'文件业务处理失败 文件名={name}\n{traceback.format_exc()}')
        return f'{name}（{format_size(size)}）：已保存，但业务处理失败'
    return f'{name}（{format_size(size)}）已收到'


async def on_file_saved(bot_matcher: Matcher, ev: MessageEvent, file_path: Path, meta: dict) -> None:
    """文件已落盘，在这里写自己的业务逻辑（TODO：解析回放、入库、转发等）"""
    # meta 含 name/size/md5/url/scene/user_id/reused，scene 是 adapters.Scene，reused=True 说明这个内容之前已经收过
    logger.info(f'待处理文件 {file_path} meta={meta}')


async def download_file(url: str, dest: Path) -> tuple[int, str]:
    """流式下载到 dest，边下边算 md5，超过上限立刻中断，返回 (字节数, md5)"""
    md5 = hashlib.md5()
    size = 0
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
        async with client.stream('GET', url) as resp:
            resp.raise_for_status()
            declared = resp.headers.get('content-length', '')
            if declared.isdigit() and int(declared) > MAX_FILE_SIZE:
                raise FileTooLargeError(int(declared))  # 有 Content-Length 就提前拒，省掉无谓的流量
            with dest.open('wb') as f:
                async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                    size += len(chunk)
                    if size > MAX_FILE_SIZE:
                        raise FileTooLargeError(size)
                    md5.update(chunk)
                    f.write(chunk)
    return size, md5.hexdigest()


def normalize_url(url: str) -> str:
    """补全协议头，兼容旧版适配器和 QQ 偶尔返回的无协议地址"""
    url = (url or '').strip()
    return f'https://{url.lstrip("/")}' if url and not urlparse(url).scheme else url


def attachment_names(ev: MessageEvent) -> dict[str, str]:
    """url -> 原始文件名。QQ 官方的 file 段只有 url（形如 /download?fileid=...，路径里没有文件名），
    原始文件名只留在事件的 attachments 上；其它适配器没有这个字段，返回空"""
    return {a.url: a.filename for a in getattr(ev, 'attachments', None) or [] if getattr(a, 'url', None) and getattr(a, 'filename', None)}


def resolve_file_name(url: str, original_name: str = '') -> tuple[str, str]:
    """推导安全的文件名和扩展名：优先用原始文件名，没有再从 url 路径里取"""
    raw = original_name.replace('\\', '/').rsplit('/', 1)[-1] if original_name else unquote(urlparse(url).path.rsplit('/', 1)[-1])
    cleaned = _UNSAFE_NAME_RE.sub('_', raw).strip('._')  # 取 basename 再过滤字符，双重防路径穿越
    if not cleaned:
        return 'unknown', ''
    ext = Path(cleaned).suffix.lower()
    if len(ext) > 16:
        ext = ''  # 路径里带点的随机串，不当成扩展名
    stem = (Path(cleaned).stem if ext else cleaned)[:80] or 'unknown'
    return f'{stem}{ext}', ext


def format_size(size: int) -> str:
    """字节数转成便于阅读的形式"""
    value = float(size)
    for unit in ('B', 'KB', 'MB'):
        if value < 1024:
            return f'{value:.0f}{unit}' if unit == 'B' else f'{value:.1f}{unit}'
        value /= 1024
    return f'{value:.1f}GB'
