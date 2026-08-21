from nonebot.adapters.qq import MessageSegment
from pydantic.v1 import BaseModel

from hikari_core.core.constants import shiptypes


class SelectShip(BaseModel):
    index: int = 1
    level_str: str = ""
    ship_type: str = ""
    ship_type_url: str = ""
    name_cn: str = ""
    name_cn360: str = ""
    name_en: str = ""


class SelectClan(BaseModel):
    index: int = 1
    tag: str = ""
    name: str = ""


def get_ship_markdown(data_list: list[SelectShip]) -> MessageSegment:
    table_rows = "\n".join([
        f"| {club.index} | {club.level_str} {match_ship_type(club.ship_type)} | {club.name_cn} | {club.name_cn360} | {club.name_en} |"
        for club in data_list
    ])
    markdown_content = f"""
# ⏰ 战舰选择
存在多个符合条件的战舰  
**请在 20 秒内选择对应的序号**
| 序号 | 等级/类型 | 名称1 | 名称2 | 名称3 |
|:---:|:---:|:---|:---|:---|
{table_rows}

---
"""
    return MessageSegment.markdown(markdown_content)


def get_clan_markdown(data_list: list[SelectClan]) -> MessageSegment:
    table_rows = "\n".join([
        f"| {club.index} | {club.tag} | {club.name} |"
        for club in data_list
    ])
    markdown_content = f"""
# ⏰ 公会选择
存在多个符合条件的公会  
**请在 20 秒内选择对应的序号**
| 序号 | 公会标签 | 公会名称 |
|:---:|:---:|:---|
{table_rows}

---
"""
    return MessageSegment.markdown(markdown_content)


def match_ship_type(value: str) -> str:
    """根据输入值匹配舰船类型"""
    for rule in shiptypes:
        if value in rule.keywords:
            return rule.keywords[-1]
    return value  # 未匹配时返回原值
