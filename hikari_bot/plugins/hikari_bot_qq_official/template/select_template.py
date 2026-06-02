from nonebot.adapters.qq import MessageSegment
from pydantic.v1 import BaseModel


class SelectShip(BaseModel):
    index: int = 1
    level_str: str = ""
    server_type_url: str = ""
    name_cn: str = ""
    name_cn360: str = ""
    name_en: str = ""

class SelectClan(BaseModel):
    index: int = 1
    tag: str = ""
    name: str = ""


def get_clan_markdown(data_list: list[SelectShip]) -> MessageSegment:
    table_rows = "\n".join([
        f"| {club.index} | {club.level_str}![Logo]({club.server_type_url}) | {club.name_cn} | {club.name_cn360} | {club.name_en} |"
        for club in data_list
    ])
    markdown_content = f"""
# ⏰ 战舰选择
存在多个符合条件的战舰  
**请在 20 秒内选择对应的序号**
| 序号 | 服务器/等级 | 名称1 | 名称2 | 名称3 |
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
