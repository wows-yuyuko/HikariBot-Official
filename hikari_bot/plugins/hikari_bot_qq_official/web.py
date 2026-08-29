import nonebot
import re

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from hikari_bot.plugins.hikari_bot_qq_official.utils import image_path

from nonebot import get_driver
from nonebot.log import logger

driver = get_driver()


@driver.on_startup
def web_run():
    if get_driver().config.upload_image == 'local':
        app: FastAPI = nonebot.get_app()
        image_path.mkdir(parents=True, exist_ok=True)
        logger.success(f'本地文件服务器启动成功 path={image_path}，请确认是否放行对应端口，如果没有公网ip请将配置项UPLOAD_IMAGE改为qq、smms或oss')

        @app.get('/images/{filename}')
        async def get_file(filename: str):
            # 防路径穿越：仅允许本地图片缓存中的 md5 文件名（upload_local 的命名规则）
            if not re.fullmatch(r'[0-9a-f]{32}\.(?:jpg|png|gif|webp)', filename):
                return JSONResponse(status_code=400, content={'detail': 'invalid filename'})
            file = image_path / filename
            if not file.is_file():
                return JSONResponse(status_code=404, content={'detail': 'not found'})
            return FileResponse(file)
