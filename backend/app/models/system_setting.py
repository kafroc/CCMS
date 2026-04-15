from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text
from typing import Optional


class SystemSetting(SQLModel, table=True):
    __tablename__ = "system_settings"

    key: str = Field(primary_key=True, max_length=64)
    value: str = Field(sa_column=Column(Text, nullable=False))


# Default values and descriptions for system settings
SYSTEM_SETTING_DEFAULTS: dict[str, dict] = {
    "pdf_parse_timeout_seconds": {
        "default": "300",
        "label": "PDF Parse Timeout (seconds)",
        "type": "int",
        "min": 30,
        "max": 3600,
    },
    "st_template": {
        "default": "",
        "label": "ST Document Template (Markdown)",
        "type": "text",
    },
}
