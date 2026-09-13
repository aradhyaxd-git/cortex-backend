# src/cortex/api/schemas/decision.py
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class OverrideRequest(BaseModel):
    decision_id: str
    action: str  # 'approve' | 'override'
    override_params: Optional[dict] = None
    notes: Optional[str] = None

class OverrideResponse(BaseModel):
    decision_id: str
    status: str

class ExplanationDetailSchema(BaseModel):
    situation: str
    decision: str
    reasoning: str
    expected_outcome: str
    future_consequences: str

class DecisionResponse(BaseModel):
    decision_id: str
    conflict_id: str
    status: str
    severity: str = "CRITICAL"
    location: str = "Segment S2 (Single Track)"
    train_to_continue: str
    train_to_hold: str
    action: str = ""
    reason: str
    expected_benefit_minutes: int = 24
    confidence_score: float = 0.95
    explanation: Optional[ExplanationDetailSchema] = None
    created_at: Optional[str] = None