from nonebot.adapters.qq import MessageSegment
from pydantic.v1 import BaseModel


class SelectClan(BaseModel):
    index: int = 1
    tag: str = ""
    name: str = ""


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
