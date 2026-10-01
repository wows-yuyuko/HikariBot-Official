"""Bot 适配器选择的单一事实来源。

根目录 ``bot.py``（注册适配器）与插件层（推导上报平台）都从这里取值，
避免「适配器名」和「上报给 yuyuko 的 platformType」两处各写一份、互相对不上。

注意：本模块必须留在插件包**之外**。
导入 ``hikari_bot.plugins.hikari_bot_qq_official`` 会执行它的 ``__init__.py``
（注册 matcher、读取插件配置），在 ``nonebot.init()`` 之后、插件正式加载之前
触发这些副作用会打乱 NoneBot 的加载顺序。
"""
from typing import Any

DEFAULT_ADAPTER = 'qq_official'

# 适配器名 -> 上报给 yuyuko 的 platformType（即 hikari_core 里的 Platform）。
# QQ_OFFICIAL 与 QQ 是两个独立的身份命名空间，绑定数据互不影响。
ADAPTER_PLATFORMS: dict[str, str] = {
    'qq_official': 'QQ_OFFICIAL',
    'onebot11': 'QQ',
}


def _resolve_config(config: Any = None) -> Any:
    if config is not None:
        return config
    from nonebot import get_driver
    return get_driver().config


def get_adapter_name(config: Any = None) -> str:
    """读取 BOT_ADAPTER；空值视为未配置（用默认值），写错的值直接报错。

    空值（``BOT_ADAPTER=`` 或纯空格）按「未配置」处理，避免留空行就启动失败；
    但填写了无法识别的值时必须显式失败 —— 静默回退到 QQ 会让 OneBot 部署者
    以为配置生效了却跑在错误的适配器上。
    """
    raw = getattr(_resolve_config(config), 'bot_adapter', '')
    name = str(raw).strip().lower() if raw is not None else ''
    if not name:
        return DEFAULT_ADAPTER
    if name not in ADAPTER_PLATFORMS:
        raise ValueError(f'BOT_ADAPTER={name!r} 不支持，可选值: {", ".join(sorted(ADAPTER_PLATFORMS))}')
    return name


def resolve_platform(config: Any = None) -> str:
    """上报给 yuyuko 的平台标识，**完全由适配器决定**。

    配置文件里不需要也不应再设置 PLATFORM：platformType 是 yuyuko 侧的**身份命名空间**，
    与适配器一一对应，留一个可覆盖的口子只会让人误配成另一套命名空间 ——
    表现就是用户原有的绑定数据「突然看不见了」。
    """
    return ADAPTER_PLATFORMS[get_adapter_name(config)]


def register_adapters(driver: Any) -> str:
    """按配置注册**唯一一个**适配器（两个适配器互斥，不同时在线），返回适配器名。

    导入放在分支内：只装了一种适配器依赖的场景（例如 CI 裁剪依赖）不会因为
    另一个适配器缺失而在启动期直接崩掉。
    """
    name = get_adapter_name(driver.config)
    if name == 'qq_official':
        from nonebot.adapters.qq import Adapter
    elif name == 'onebot11':
        from nonebot.adapters.onebot.v11 import Adapter
    else:
        raise ValueError(f'BOT_ADAPTER={name!r} 没有可注册的适配器')
    driver.register_adapter(Adapter)
    return name
