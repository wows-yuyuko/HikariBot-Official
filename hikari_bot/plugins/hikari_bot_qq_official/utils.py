import hashlib

import httpx
import orjson
import oss2
from hikari_core import get_cache_file
from nonebot import get_driver
from nonebot.adapters.qq import (
    C2CMessageCreateEvent,
    DirectMessageCreateEvent,
    GroupAtMessageCreateEvent,
    GroupMessageCreateEvent,
    GuildMessageEvent,
    MessageEvent,
)
from nonebot.log import logger

driver = get_driver()
config = driver.config

image_path = get_cache_file() / 'image_cache'


def is_text_or_at_message(ev: MessageEvent) -> bool:
    """仅当消息只含 纯文本 和 @提及 段时返回 True，其余（图片/表情/文件/@全体/@频道等）一律不处理"""
    return all(seg.type in ('text', 'mention_user') for seg in ev.get_message())


def has_file_segment(ev: MessageEvent) -> bool:
    """消息中是否包含 文件 段（收到的文件附件由适配器解析为 file 段）"""
    return any(seg.type == 'file' for seg in ev.get_message())


def get_message_event_type(ev: MessageEvent) -> str:
    """区分消息事件类型（注意继承关系，isinstance 判断顺序不能乱）

    - C2C_MESSAGE_CREATE      -> C2C（私聊）
    - GROUP_AT_MESSAGE_CREATE -> GROUP_AT（群@机器人）
    - GROUP_MESSAGE_CREATE    -> GROUP（群普通消息）
    - 频道消息 MESSAGE_CREATE  -> CHANNEL
    - 频道私信                 -> CHANNEL_DIRECT
    - 其他                     -> UNKNOWN
    """
    if isinstance(ev, C2CMessageCreateEvent):
        return 'C2C'
    if isinstance(ev, DirectMessageCreateEvent):   # 必须先于 GuildMessageEvent
        return 'CHANNEL_DIRECT'
    if isinstance(ev, GroupAtMessageCreateEvent):  # 必须先于 GroupMessageCreateEvent
        return 'GROUP_AT'
    if isinstance(ev, GroupMessageCreateEvent):
        return 'GROUP'
    if isinstance(ev, GuildMessageEvent):
        return 'CHANNEL'
    return 'UNKNOWN'


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
