from pydantic import BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    # 选择类消息（如战舰/公会选择）是否使用 md 格式发送，默认关闭（使用渲染图片）
    bot_select_msg_is_md: bool = False
    # 选择类消息最多展示的选择数量，默认 10
    bot_select_msg_is_md_max_size: int = 10
