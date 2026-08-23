#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import nonebot
from nonebot.adapters.qq import Adapter
from nonebot.log import default_format, logger

nonebot.init()
app = nonebot.get_asgi()

driver = nonebot.get_driver()
driver.register_adapter(Adapter)

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
