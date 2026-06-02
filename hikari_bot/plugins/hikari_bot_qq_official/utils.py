import gzip
import hashlib
import io

import httpx
import orjson
import oss2
from nonebot import get_driver
from nonebot.adapters.qq import DirectMessageCreateEvent, GuildMessageEvent
from nonebot.log import logger

driver = get_driver()
config = driver.config


def check_rule(ev):
    if driver.config.filter_rule == 'None':
        return True
    if isinstance(ev, DirectMessageCreateEvent) and driver.config.private:
        return True
    if isinstance(ev, GuildMessageEvent):
        if (
                driver.config.filter_rule == 'white'
                and (int(ev.guild_id) in driver.config.white_guild_list or int(ev.channel_id) in driver.config.white_channel_list)
        ) or (
                driver.config.filter_rule == 'black'
                and (int(ev.guild_id) not in driver.config.ban_guild_list and int(ev.channel_id) not in driver.config.ban_channel_list)
        ):
            return True
    else:
        return True
    logger.error('消息 msg=' + ev.get_message())
    return False


def encode_gzip(bytes):
    buf = io.BytesIO(bytes)
    gf = gzip.GzipFile(fileobj=buf)
    return gf.read().decode('utf-8')


def byte2md5(bytes):
    return hashlib.md5(bytes).hexdigest()


def upload_oss(bytes):
    endpoint = config.oss_endpoint
    auth = oss2.Auth(config.oss_id, config.oss_key)
    bucket = oss2.Bucket(auth, endpoint, config.oss_bucket)
    md5 = byte2md5(bytes)
    key = f'bot_image/{md5}.png'
    bucket.put_object(key, bytes)
    url = bucket.sign_url('GET', key, 3600, slash_safe=True)
    url = url.replace('http', 'https')
    logger.info(f'上传oss图片成功，url: {url}')
    return url


async def upload_smms(bytes):
    headers = {'Authorization': config.smms_key}
    async with httpx.AsyncClient(headers=headers) as client:
        files = {'smfile': bytes}
        url = 'https://smms.app/api/v2/upload'
        resp = await client.post(url, files=files)
        result = orjson.loads(resp.content)
        logger.info(f'上传smms图片成功，data: {result}')
        if result['success']:
            return result['data']['url']
        else:
            return result['images']


async def upload_image(bytes):
    if config.upload_image == 'oss':
        return upload_oss(bytes)
    elif config.upload_image == 'smms':
        return await upload_smms(bytes)
    elif config.upload_image == 'local':
        return None
    else:
        return None
