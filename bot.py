#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import nonebot
from nonebot.log import default_format, logger

from hikari_bot.adapter_registry import register_adapters

nonebot.init()
app = nonebot.get_asgi()

driver = nonebot.get_driver()
# 适配器由 BOT_ADAPTER 决定，两个适配器互斥（同一进程只注册一个）
register_adapters(driver)

logger.add(
    'logs/info.log',
    rotation='00:00',
    retention='1 week',
    diagnose=False,
    level='INFO',
    format=default_format,
    encoding='utf-8',
)
nonebot.load_from_toml('pyproject.toml')

if __name__ == '__main__':
    nonebot.run()
