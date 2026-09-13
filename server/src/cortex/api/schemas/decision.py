from typing import Optional

from pydantic import BaseModel


class OverrideRequest(BaseModel):
    decision_id: str
    action: str
    override_params: Optional[dict] = None