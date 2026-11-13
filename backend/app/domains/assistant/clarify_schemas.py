from pydantic import BaseModel, Field


class ClarifyState(BaseModel):
    """澄清状态机状态：意图、已抽取槽位、已追问槽位、追问轮数。"""

    intent: str = "chat"
    slots: dict[str, str] = Field(default_factory=dict)
    asked: list[str] = Field(default_factory=list)
    round_no: int = 0
