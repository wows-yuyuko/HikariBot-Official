import hashlib

import httpx
import orjson
import oss2
from hikari_core import get_cache_file
from nonebot import get_driver
from nonebot.adapters.qq import (
    C2CMessageCreateEvent,
    DirectMessageCreateEvent,
    GroupMessageCreateEvent,
    GuildMessageEvent, MessageEvent,
)
from nonebot.log import logger

driver = get_driver()
config = driver.config

image_path = get_cache_file() / 'image_cache'


def _safe_int(value, default=0):
    """安全转换整数，解析失败时返回默认值"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _check_guild_lists(ev, filter_rule, cfg):
    """频道消息按白/黑名单过滤（白名单模式需命中任一白名单，黑名单模式需不命中任一黑名单）"""
    guild_id = _safe_int(ev.guild_id)
    channel_id = _safe_int(ev.channel_id)
    if filter_rule == 'white':
        return (
            guild_id in getattr(cfg, 'white_guild_list', [])
            or channel_id in getattr(cfg, 'white_channel_list', [])
        )
    if filter_rule == 'black':
        return (
            guild_id not in getattr(cfg, 'ban_guild_list', [])
            and channel_id not in getattr(cfg, 'ban_channel_list', [])
        )
    logger.warning(f'未知过滤规则 filter_rule={filter_rule}，按拒绝处理')
    return False


def check_rule(ev):
    cfg = driver.config
    filter_rule = getattr(cfg, 'filter_rule', None)
    if filter_rule in (None, 'None'):
        return True

    private = bool(getattr(cfg, 'private', True))

    # 私聊类消息（c2c 私聊 / 频道私信）：由 private 开关控制
    if isinstance(ev, C2CMessageCreateEvent):
        return private
    if isinstance(ev, DirectMessageCreateEvent):
        return private or _check_guild_lists(ev, filter_rule, cfg)

    # 群消息：黑名单模式按 ban_group_list 过滤（无群白名单配置，白名单模式默认放行）
    if isinstance(ev, GroupMessageCreateEvent):
        if filter_rule == 'black':
            return _safe_int(ev.group_id) not in getattr(cfg, 'ban_group_list', [])
        return True

    # 频道消息：按白/黑名单过滤
    if isinstance(ev, GuildMessageEvent):
        return _check_guild_lists(ev, filter_rule, cfg)

    logger.warning(f'未知消息类型，按放行处理: {type(ev).__name__}')
    return True


def is_text_or_at_message(ev: MessageEvent) -> bool:
    """仅当消息只含 纯文本 和 @提及 段时返回 True，其余（图片/表情/文件/@全体/@频道等）一律不处理"""
    return all(seg.type in ('text', 'mention_user') for seg in ev.get_message())


def byte2md5(data):
    return hashlib.md5(data).hexdigest()


def upload_oss(data):
    endpoint = config.oss_endpoint
    auth = oss2.Auth(config.oss_id, config.oss_key)
    bucket = oss2.Bucket(auth, endpoint, config.oss_bucket)
    md5 = byte2md5(data)
    key = f'bot_image/{md5}.png'
    bucket.put_object(key, data)
    url = bucket.sign_url('GET', key, 3600, slash_safe=True)
    url = url.replace('http://', 'https://')
    logger.info(f'上传oss图片成功，key: {key}')
    return url


async def upload_smms(data):
    headers = {'Authorization': config.smms_key}
    async with httpx.AsyncClient(headers=headers) as client:
        files = {'smfile': data}
        url = 'https://smms.app/api/v2/upload'
        resp = await client.post(url, files=files)
        result = orjson.loads(resp.content)
        logger.info(f'上传smms图片成功，data: {result}')
        if result['success']:
            return result['data']['url']
        else:
            return result['images']


def upload_local(data):
    md5 = byte2md5(data)
    image_path.mkdir(parents=True, exist_ok=True)
    with open(image_path / f'{md5}.jpg', 'wb') as f:
        f.write(data)
    return f'{get_driver().config.upload_local_url}/images/{md5}.jpg'


async def upload_image(data):
    if config.upload_image == 'oss':
        return upload_oss(data)
    elif config.upload_image == 'smms':
        return await upload_smms(data)
    elif config.upload_image == 'local':
        return upload_local(data)
    else:
        logger.warning(f'未知的上传方式 upload_image={config.upload_image}')
        return None
