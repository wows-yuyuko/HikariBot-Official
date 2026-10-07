"""回放渲染插件：收到 .wowsreplay 后调外部渲染服务生成小地图 MP4 并发回

复制到 hikari_bot/plugins/hikari_bot_qq_official/bot/file_listener/ 下面（和 file.py 放一起），
文件名保持 file_handler- 前缀，再在 .env.prod 里设置 BOT_ENABLE_FILE_LISTEN=true。
另外必须配 REPLAY_RENDER_URL / REPLAY_RENDER_TOKEN 指向渲染服务，不配则本插件直接跳过。
只支持 BOT_ADAPTER=qq_official：发视频靠 QQ 官方的富媒体字节直传，OneBot 下本插件不工作。

渲染很重（吃满 1 核、峰值 2-4GB 内存，h264 一局约 30 秒），所以渲染跑在独立的渲染服务上，
本插件只做：下载 → 本地体检 → 提交 → 轮询 → 取回 MP4 → 发送。
QQ 官方被动回复群聊只有 5 分钟有效期、单聊 60 分钟，因此接单前按渲染服务的平均耗时和当前排队数
估算能否在时限内发出，估不上或队列已满就当场拒收，不让用户白等。
"""

import asyncio
import hashlib
import json
import re
import struct
import time
import traceback
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

import httpx
from hikari_core import get_cache_file
from nonebot import get_driver, logger
from nonebot.internal.matcher import Matcher

from hikari_bot.adapter_registry import get_adapter_name
from hikari_bot.plugins.hikari_bot_qq_official.adapters import (
    MessageEvent,
    Scene,
    get_group_id,
    get_scene,
    iter_file_urls,
    scene_label,
)

_config = get_driver().config

# ============ 配置 ============
RENDER_URL = ''.rstrip('/')  # 渲染服务地址，空则本插件不工作
RENDER_TOKEN = ''  # 渲染服务 Bearer Token
ENABLED = bool(RENDER_URL) and get_adapter_name() == 'qq_official'
if RENDER_URL and not ENABLED:
    logger.warning('回放渲染插件只支持 BOT_ADAPTER=qq_official，当前适配器下不工作')

CACHE_DIR = get_cache_file() / 'replay_cache'
MAX_REPLAY_SIZE = 20 * 1024 * 1024  # 回放文件大小上限
MAX_SLOTS = 3  # 同时在处理的任务数，满了当场拒绝（不排队等）
USER_QUOTA_PER_HOUR = 3
GROUP_QUOTA_PER_HOUR = 10
MP4_CACHE_TTL = 24 * 3600  # 结果缓存，超窗后用户重发能秒回，是唯一兜底
NEG_CACHE_TTL = {'unsupported_build': 6 * 3600, 'version_mismatch': 6 * 3600}
NEG_CACHE_TTL_DEFAULT = 1800
CAPS_TTL = 600  # 渲染服务临时查不到时，上一份 /capabilities 最多沿用多久
SWEEP_INTERVAL = 3600  # 机会式清理间隔

DOWNLOAD_TIMEOUT = 60.0
SUBMIT_TIMEOUT = 120.0
POLL_TIMEOUT = 10.0
ARTIFACT_TIMEOUT = 180.0
STALL_LIMIT = 180  # 进度连续多少秒不动就当卡死
CHUNK_SIZE = 64 * 1024

# 被动回复窗口：群聊 5 分钟 / 单聊 60 分钟。MARGIN 是留给「取回 MP4 + 富媒体上传」的余量
WINDOW = {Scene.PRIVATE: 3600, Scene.GROUP: 300, Scene.GROUP_AT: 300}
MARGIN = {Scene.PRIVATE: 120, Scene.GROUP: 45, Scene.GROUP_AT: 45}

REPLAY_SIGNATURE = b'\x12\x32\x34\x11'
REPLAY_HEADER_LEN = 12
MAX_META_LEN = 1024 * 1024
_UNSAFE_NAME_RE = re.compile(r'[^\w.\-]+')

# 服务端 code / reason -> 给用户看的中文。渲染器原始输出一律不进 QQ 消息，只进日志
MESSAGES = {
    'invalid_replay': '这不是有效的 .wowsreplay 回放文件',
    'unsupported_build': '暂不支持这个游戏版本（build {build}）的回放，渲染数据还没更新，请等管理员补充后再试',
    'version_mismatch': '暂不支持这个游戏版本的回放，渲染数据还没更新，请等管理员补充后再试',
    'deserialize_failed': '这份回放解析失败了，可能是录制不完整，换一份试试',
    'queue_full': '渲染队列忙着，请过几分钟再发一次',
    'rate_limited': '渲染服务正忙，请过几分钟再发一次',
    'payload_too_large': '回放文件太大了',
    'timeout': '渲染超时了。稍后把这个文件再发一次，我会立刻返回结果（已缓存）',
    'artifact_too_large': '渲染结果太大，QQ 发不出去，请联系管理员调整渲染参数',
    'renderer_missing': '渲染服务没配置好，请联系管理员',
    'unavailable': '渲染服务暂时联系不上，请稍后再试',
}
FALLBACK_MESSAGE = '渲染失败了，已记录日志，请稍后再试（错误码 {reason}）'

# ============ 进程内状态，全部由 _lock 保护 ============
_lock = asyncio.Lock()
_slots = 0
_inflight: dict[str, float] = {}  # md5 -> 开始时间
_user_hits: dict[str, list[float]] = {}
_group_hits: dict[str, list[float]] = {}
_neg_cache: dict[str, tuple[str, dict, float]] = {}  # md5 -> (reason, detail, 记录时间)
_caps_cache: tuple[float, dict] = (0.0, {})
_last_sweep = 0.0


class Rejected(Exception):
    """可预期的拒绝，message 直接发给用户"""

    def __init__(self, message: str, reason: str = ''):
        self.user_message = message
        self.reason = reason
        super().__init__(message)


async def process_file(bot_matcher: Matcher, ev: MessageEvent):
    """处理文件（必须实现的函数）"""
    if not ENABLED:
        return
    t0 = time.monotonic()  # 事件刚到，用当前时刻当被动回复窗口的起点
    try:
        url = _pick_replay_url(ev)
        if url is None:
            return

        scene = get_scene(ev)
        if scene in (Scene.CHANNEL, Scene.CHANNEL_DIRECT):
            # 适配器发不了频道视频（_extract_guild_image 只认 image 段），提前用人话拒掉
            await bot_matcher.send('频道内暂不支持回放渲染，请在 QQ 群 @我 或和我私聊发送回放文件')
            return

        await _handle(bot_matcher, ev, url, scene, t0)
    except Rejected as e:
        logger.info(f'回放渲染已拒绝 原因={e.reason or "-"} 用户={_safe_user(ev)}')
        await _try_send(bot_matcher, e.user_message)
    except Exception:
        logger.error(traceback.format_exc())
        await _try_send(bot_matcher, '回放处理失败了，已记录日志')


async def _handle(bot_matcher: Matcher, ev: MessageEvent, url: str, scene: Scene, t0: float) -> None:
    """主流程，异常统一由 process_file 兜"""
    user_id = ev.get_user_id()
    group_id = str(get_group_id(ev) or '')
    deadline = t0 + WINDOW.get(scene, 300) - MARGIN.get(scene, 45)

    caps = await _capabilities()
    due = await _acquire_slot(user_id, group_id, caps, deadline - time.monotonic())

    md5 = ''
    claimed = False  # 只有真占到 _inflight 名额才在 finally 里释放，否则会误删别人的
    inbox = None
    try:
        CACHE_DIR.joinpath('inbox').mkdir(parents=True, exist_ok=True)
        CACHE_DIR.joinpath('mp4').mkdir(parents=True, exist_ok=True)
        inbox = CACHE_DIR / 'inbox' / f'{uuid4().hex}.part'
        size, md5 = await _download(url, inbox)

        build = _inspect_replay(inbox, caps)
        logger.info(f'收到回放 场景={scene_label(scene)} 用户={user_id} 大小={size} build={build} md5={md5[:8]}')

        cached = await _claim(md5)
        if cached is not None:
            # 缓存命中：不发回执，直接把视频发出去，省一格被动回复额度
            await _send_video(bot_matcher, cached.read_bytes(), md5)
            return
        claimed = True

        job = await _submit(inbox, md5)
        _discard(inbox)
        inbox = None

        eta = int(job.get('eta_seconds') or 0)
        if not job.get('reused'):
            await bot_matcher.send(f'已收到回放（{_fmt_size(size)}），正在渲染，约 {max(1, round(eta / 60))} 分钟后发出')

        state = await _poll(job['job_id'], deadline)
        data = await _fetch_artifact(job['job_id'], state)
        _store_mp4(md5, data)
        await _send_video(bot_matcher, data, md5)
    finally:
        if inbox is not None:
            _discard(inbox)
        await _release_slot(md5 if claimed else '')
        if due:
            _sweep_files()  # 扫文件系统放在锁外，不卡事件循环


async def _acquire_slot(user_id: str, group_id: str, caps: dict, budget: float) -> bool:
    """准入门：限流、名额、排队预估是否赶得上被动回复窗口；返回是否该顺带扫一遍文件系统"""
    global _slots
    async with _lock:
        due = _sweep_memory_locked()
        _check_quota_locked(_user_hits, user_id, USER_QUOTA_PER_HOUR, f'你渲染得太频繁了，每小时最多 {USER_QUOTA_PER_HOUR} 次')
        if group_id:
            _check_quota_locked(_group_hits, group_id, GROUP_QUOTA_PER_HOUR, f'本群渲染太频繁了，每小时最多 {GROUP_QUOTA_PER_HOUR} 次')
        if _slots >= MAX_SLOTS:
            raise Rejected('渲染队列忙着，请过几分钟再发一次', 'no_slot')

        # 被动回复过期就发不出去了，所以接单前先估一遍：前面几个 + 自己这一个能不能跑完。
        # avg_render_seconds 是渲染服务用最近几次真实耗时算的，会跟着机器实际速度走。
        avg = int(caps.get('avg_render_seconds') or 165)
        ahead = int(caps.get('queue_depth') or 0) + (1 if caps.get('busy') else 0)
        estimate = avg * (ahead + 1)
        if estimate > budget:
            raise Rejected(f'当前排队较多，预计要等 {max(1, round(estimate / 60))} 分钟，'
                           f'赶不上 QQ 的回复时限，请稍后再发一次', 'eta_exceeds_window')
        _slots += 1
        return due


async def _release_slot(claimed_md5: str) -> None:
    """归还名额；claimed_md5 非空时同时释放去重锁"""
    global _slots
    async with _lock:
        _slots -= 1
        if claimed_md5:
            _inflight.pop(claimed_md5, None)


# ============ 取段与校验 ============

def _pick_replay_url(ev: MessageEvent) -> str | None:
    """只取第一个 .wowsreplay 文件的地址，其它扩展名静默跳过（别人可能有其它 file_handler）"""
    names = _attachment_names(ev)
    for raw in iter_file_urls(ev):
        url = _normalize_url(raw)
        _, ext = _resolve_file_name(url, names.get(raw, ''))
        if ext == '.wowsreplay':
            return url
    return None


def _inspect_replay(path: Path, caps: dict) -> int | None:
    """本地体检：签名、meta 长度、JSON、build 号。宽容处理，取不到 build 就交给服务端判"""
    with path.open('rb') as f:
        head = f.read(64 * 1024)
    if len(head) < REPLAY_HEADER_LEN or head[:4] != REPLAY_SIGNATURE:
        raise Rejected(MESSAGES['invalid_replay'], 'bad_magic')

    meta_len = struct.unpack_from('<I', head, 8)[0]
    if not 0 < meta_len <= MAX_META_LEN:
        raise Rejected(MESSAGES['invalid_replay'], 'bad_meta_len')
    if len(head) < REPLAY_HEADER_LEN + meta_len:
        with path.open('rb') as f:
            head = f.read(REPLAY_HEADER_LEN + meta_len)
    try:
        meta = json.loads(head[REPLAY_HEADER_LEN:REPLAY_HEADER_LEN + meta_len])
    except Exception:
        raise Rejected(MESSAGES['invalid_replay'], 'bad_meta_json') from None

    parts = [p.strip() for p in str(meta.get('clientVersionFromExe') or '').split(',')]
    build = int(parts[3]) if len(parts) >= 4 and parts[3].isdigit() else None
    supported = caps.get('supported_builds') or []
    if build is not None and supported and build not in supported:
        raise Rejected(MESSAGES['unsupported_build'].format(build=build), 'unsupported_build')
    return build


# ============ 准入、去重、缓存（都在 _lock 内调用） ============

def _check_quota_locked(table: dict[str, list[float]], key: str, quota: int, message: str) -> None:
    """滑动窗口限流，超了抛 Rejected"""
    now = time.time()
    hits = [t for t in table.get(key, []) if now - t < 3600]
    if len(hits) >= quota:
        table[key] = hits
        raise Rejected(message, 'rate_limited')
    hits.append(now)
    table[key] = hits


async def _claim(md5: str) -> Path | None:
    """占位并检查三层去重：结果缓存命中返回路径，负缓存/重复渲染抛 Rejected"""
    async with _lock:
        cached = _cached_mp4(md5)
        if cached is not None:
            return cached
        entry = _neg_cache.get(md5)
        if entry is not None:
            reason, detail, ts = entry
            if time.time() - ts < NEG_CACHE_TTL.get(reason, NEG_CACHE_TTL_DEFAULT):
                raise Rejected(_message_for(reason, detail), reason)
            _neg_cache.pop(md5, None)
        if md5 in _inflight:
            raise Rejected('这份回放正在渲染中，请等上一次的结果', 'duplicate')
        _inflight[md5] = time.time()
    return None


def _cached_mp4(md5: str) -> Path | None:
    """结果缓存命中且未过期则返回路径"""
    path = CACHE_DIR / 'mp4' / f'{md5}.mp4'
    try:
        if path.is_file() and time.time() - path.stat().st_mtime < MP4_CACHE_TTL:
            return path
    except OSError:
        pass
    return None


def _store_mp4(md5: str, data: bytes) -> None:
    """原子写入结果缓存，超窗发不出去时用户重发能秒回。
    缓存只是加速，写失败（如 Windows 上杀毒软件短暂锁住文件）不能耽误把视频发出去"""
    target = CACHE_DIR / 'mp4' / f'{md5}.mp4'
    tmp = target.with_suffix('.mp4.part')
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        tmp.replace(target)
    except OSError as e:
        # 残留的 .part 不在这里删（同样可能被锁），_sweep_files 过期后会清掉
        logger.warning(f'写结果缓存失败（不影响本次发送）：{type(e).__name__} {e}')


def _discard(path: Path) -> None:
    """尽力删临时文件。Windows 上文件被占用（如杀毒软件正在扫刚下载的文件）时删除会抛异常，
    而 Unix 上不会；删不掉就留给 _sweep_files 过期清理，绝不能让它打断后面的名额归还"""
    try:
        path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning(f'删除临时文件失败，稍后由定期清理处理：{path.name} {type(e).__name__}')


async def _remember_failure(md5: str, reason: str, detail: dict) -> None:
    async with _lock:
        _neg_cache[md5] = (reason, detail, time.time())


def _sweep_memory_locked() -> bool:
    """机会式清理的内存部分；返回是否该顺带扫一遍文件系统（扫盘放锁外做）"""
    global _last_sweep
    now = time.time()
    if now - _last_sweep < SWEEP_INTERVAL:
        return False
    _last_sweep = now
    for key in [k for k, (_, _, ts) in _neg_cache.items() if now - ts > max(NEG_CACHE_TTL.values())]:
        _neg_cache.pop(key, None)
    for table in (_user_hits, _group_hits):
        for key in [k for k, v in table.items() if not any(now - t < 3600 for t in v)]:
            table.pop(key, None)
    return True


def _sweep_files() -> None:
    """删过期的结果缓存和 inbox 里的孤儿临时文件，不持锁"""
    now = time.time()
    for sub, ttl in (('mp4', MP4_CACHE_TTL), ('inbox', 3600)):
        folder = CACHE_DIR / sub
        if not folder.is_dir():
            continue
        try:
            children = list(folder.iterdir())
        except OSError:
            continue
        for child in children:
            try:
                if now - child.stat().st_mtime > ttl:
                    child.unlink(missing_ok=True)
            except OSError:
                pass


# ============ 渲染服务客户端 ============

def _client(timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers={'Authorization': f'Bearer {RENDER_TOKEN}'})


async def _capabilities() -> dict:
    """拿渲染服务能力。每次接单都现查：排队数和是否在渲染决定了能不能赶上回复时限，不能用旧值。
    查不到时退回 CAPS_TTL 内的上一份（支持的版本、各项上限很少变），再没有就抛 Rejected"""
    global _caps_cache
    ts, cached = _caps_cache
    if cached and time.time() - ts >= CAPS_TTL:
        cached = {}
    try:
        async with _client(POLL_TIMEOUT) as client:
            resp = await client.get(f'{RENDER_URL}/capabilities')
            resp.raise_for_status()
            caps = resp.json()
    except Exception as e:
        logger.error(f'渲染服务 /capabilities 失败：{type(e).__name__} {e}')
        if cached:
            return cached
        raise Rejected(MESSAGES['unavailable'], 'unavailable') from None
    _caps_cache = (time.time(), caps)
    return caps


async def _submit(path: Path, md5: str) -> dict:
    """提交渲染任务，返回 job dict；被服务端拒绝时抛 Rejected"""
    data = {'client_job_key': md5}  # 幂等键，服务端据此避免同一份回放重复烧 CPU
    try:
        async with _client(SUBMIT_TIMEOUT) as client:
            resp = await client.post(
                f'{RENDER_URL}/jobs',
                files={'replay': ('replay.wowsreplay', path.read_bytes(), 'application/octet-stream')},
                data=data,
            )
    except Exception as e:
        logger.error(f'提交渲染任务失败：{type(e).__name__} {e}')
        raise Rejected(MESSAGES['unavailable'], 'unavailable') from None

    if resp.status_code in (200, 201):
        return resp.json()
    reason, detail = _error_of(resp)
    await _remember_failure(md5, reason, detail)
    logger.warning(f'渲染服务拒绝提交 status={resp.status_code} reason={reason} detail={detail}')
    raise Rejected(_message_for(reason, detail), reason)


async def _poll(job_id: str, deadline: float) -> dict:
    """轮询到终态；超出被动回复窗口或卡死则放弃并让服务端释放任务"""
    last_frame = -1
    last_move = time.monotonic()
    while True:
        if time.monotonic() > deadline:
            await _abandon(job_id)
            raise Rejected(MESSAGES['timeout'], 'window_exceeded')

        try:
            async with _client(POLL_TIMEOUT) as client:
                resp = await client.get(f'{RENDER_URL}/jobs/{job_id}')
        except Exception as e:
            logger.warning(f'轮询失败，稍后重试：{type(e).__name__} {e}')
            await asyncio.sleep(5)
            continue

        if resp.status_code == 404:
            raise Rejected(MESSAGES['timeout'], 'job_gone')
        if resp.status_code >= 400:
            raise Rejected(MESSAGES['unavailable'], 'unavailable')

        state = resp.json()
        status = state.get('state')
        if status == 'done':
            return state
        if status in ('failed', 'cancelled', 'expired'):
            reason = ((state.get('error') or {}).get('reason')) or 'unknown'
            logger.warning(f'渲染任务失败 job={job_id} state={status} reason={reason}')
            raise Rejected(_message_for(reason, {}), reason)

        frame = ((state.get('progress') or {}).get('frame')) or 0
        if frame != last_frame:
            last_frame, last_move = frame, time.monotonic()
        elif time.monotonic() - last_move > STALL_LIMIT:
            await _abandon(job_id)
            raise Rejected(MESSAGES['timeout'], 'stalled')

        await asyncio.sleep(max(1, int(state.get('poll_after_seconds') or 3)))


async def _fetch_artifact(job_id: str, state: dict) -> bytes:
    """取回 MP4 并校验 sha256，取完让服务端释放产物"""
    try:
        async with _client(ARTIFACT_TIMEOUT) as client:
            resp = await client.get(f'{RENDER_URL}/jobs/{job_id}/artifact')
            resp.raise_for_status()
            data = resp.content
    except Exception as e:
        logger.error(f'取回 MP4 失败：{type(e).__name__} {e}')
        raise Rejected(MESSAGES['unavailable'], 'artifact_failed') from None

    expect = (state.get('artifact') or {}).get('sha256') or ''
    if expect and hashlib.sha256(data).hexdigest() != expect:
        logger.error(f'MP4 校验不一致 job={job_id}')
        raise Rejected('视频下载校验失败，请稍后再试', 'checksum')
    await _abandon(job_id)
    return data


async def _abandon(job_id: str) -> None:
    """让渲染服务提前释放任务与产物，失败不影响主流程"""
    try:
        async with _client(POLL_TIMEOUT) as client:
            await client.delete(f'{RENDER_URL}/jobs/{job_id}')
    except Exception as e:
        logger.warning(f'DELETE job 失败 job={job_id}：{type(e).__name__} {e}')


def _error_of(resp: httpx.Response) -> tuple[str, dict]:
    """从错误响应里取出 code 与 detail"""
    try:
        err = resp.json().get('error') or {}
        return str(err.get('code') or 'unknown'), dict(err.get('detail') or {})
    except Exception:
        return 'unknown', {}


def _message_for(reason: str, detail: dict) -> str:
    """把服务端的 code/reason 翻成中文，认不出就用带错误码的兜底文案"""
    text = MESSAGES.get(reason)
    if text is None:
        return FALLBACK_MESSAGE.format(reason=reason)
    return text.format(build=detail.get('replay_build', '未知')) if '{build}' in text else text


# ============ 下载与发送 ============

async def _download(url: str, dest: Path) -> tuple[int, str]:
    """流式下载回放，边下边算 md5，超上限立刻中断"""
    md5 = hashlib.md5()
    size = 0
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            async with client.stream('GET', url) as resp:
                resp.raise_for_status()
                declared = resp.headers.get('content-length', '')
                if declared.isdigit() and int(declared) > MAX_REPLAY_SIZE:
                    raise Rejected(f'回放文件太大了（{_fmt_size(int(declared))}），上限 {_fmt_size(MAX_REPLAY_SIZE)}', 'too_large')
                with dest.open('wb') as f:
                    async for chunk in resp.aiter_bytes(CHUNK_SIZE):
                        size += len(chunk)
                        if size > MAX_REPLAY_SIZE:
                            raise Rejected(f'回放文件太大了，上限 {_fmt_size(MAX_REPLAY_SIZE)}', 'too_large')
                        md5.update(chunk)
                        f.write(chunk)
    except Rejected:
        raise
    except Exception as e:
        logger.error(f'下载回放失败 url={url}：{type(e).__name__} {e}')
        raise Rejected('回放下载失败，请稍后再试', 'download_failed') from None
    return size, md5.hexdigest()


async def _send_video(bot_matcher: Matcher, data: bytes, md5: str) -> None:
    """发视频。单独一条消息，绝不和 image 段同发（适配器只取一个附件且 image 优先）"""
    # 适配层没有发视频的接口，只能直接用 QQ 官方的段；ENABLED 已保证当前就是 qq_official
    from nonebot.adapters.qq import MessageSegment  # noqa: PLC0415 OneBot 部署不该因为本插件去加载 QQ 适配器

    # file_name 必须显式给且带 .mp4，不给会变成无扩展名的 default；只用 ASCII 避免无谓风险
    segment = MessageSegment.file_video(data, file_name=f'minimap_{md5[:8]}.mp4')
    try:
        await bot_matcher.send(segment)
    except Exception as e:
        logger.error(f'发送视频失败：{type(e).__name__} {e}\n{traceback.format_exc()}')
        await _try_send(bot_matcher, '视频发不出去了（可能超时或撞限速）。把回放再发一次我就能立刻给你结果')


async def _try_send(bot_matcher: Matcher, text: str) -> None:
    """尽力发一条文本，失败只记日志"""
    try:
        await bot_matcher.send(text)
    except Exception as e:
        logger.error(f'发送消息失败：{type(e).__name__} {e}')


# ============ 工具 ============

def _normalize_url(url: str) -> str:
    """补全协议头，兼容旧版适配器和 QQ 偶尔返回的无协议地址"""
    url = (url or '').strip()
    return f'https://{url.lstrip("/")}' if url and not urlparse(url).scheme else url


def _attachment_names(ev: MessageEvent) -> dict[str, str]:
    """url -> 原始文件名。QQ 官方的 file 段只有 url（形如 /download?fileid=...，路径里没有文件名），
    原始文件名只留在事件的 attachments 上"""
    return {a.url: a.filename for a in getattr(ev, 'attachments', None) or [] if getattr(a, 'url', None) and getattr(a, 'filename', None)}


def _resolve_file_name(url: str, original_name: str = '') -> tuple[str, str]:
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


def _fmt_size(size: int) -> str:
    """字节数转成便于阅读的形式"""
    value = float(size)
    for unit in ('B', 'KB', 'MB'):
        if value < 1024:
            return f'{value:.0f}{unit}' if unit == 'B' else f'{value:.1f}{unit}'
        value /= 1024
    return f'{value:.1f}GB'


def _safe_user(ev: MessageEvent) -> str:
    try:
        return ev.get_user_id()
    except Exception:
        return '-'
