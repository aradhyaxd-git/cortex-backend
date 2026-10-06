# tests/unit/test_dispatcher_copilot.py
import pytest
from unittest.mock import MagicMock
from cortex.engine.llm.dispatcher_copilot import DispatcherCopilot, DispatcherExplanation
from cortex.api.schemas.decision import ExplanationDetailSchema


def test_copilot_fallback_when_no_key():
    """Verify copilot produces valid explanation with deterministic fallback when no API key exists."""
    copilot = DispatcherCopilot(api_key=None, client=None)
    copilot._client = None  # Ensure client is None

    exp = copilot.explain_decision(
        winner_id="12951",
        winner_name="Rajdhani Express",
        winner_priority="Class 1",
        loser_id="BOXN_99",
        loser_name="Freight Service",
        loser_priority="Class 5",
        segment_id="S2",
        segment_desc="Single Track Block",
        hold_duration_min=24,
        benefit_min=24,
        ml_predicted_delay_min=12.0
    )

    assert isinstance(exp, DispatcherExplanation)
    assert not exp.is_llm_generated
    assert "12951" in exp.situation
    assert "BOXN_99" in exp.decision
    assert exp.model_used == "deterministic-rules"
    assert "G&SR" in exp.regulatory_code

    # Verify Pydantic schema compatibility
    schema = ExplanationDetailSchema(
        situation=exp.situation,
        decision=exp.decision,
        reasoning=exp.reasoning,
        expected_outcome=exp.expected_outcome,
        future_consequences=exp.future_consequences,
        regulatory_code=exp.regulatory_code,
        passenger_announcement=exp.passenger_announcement,
        controller_order=exp.controller_order,
        is_llm_generated=exp.is_llm_generated,
        model_used=exp.model_used
    )
    assert schema.situation == exp.situation


def test_copilot_with_mocked_llm_client():
    """Verify copilot correctly parses structured JSON from an LLM response."""
    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{\n'
        '  "situation": "Bilateral approach conflict on single block S2.",\n'
        '  "decision": "Hold Freight BOXN_99 at Loop 1 for 24 min.",\n'
        '  "reasoning": "Rajdhani 12951 holds Class 1 priority over Class 5 freight.",\n'
        '  "expected_outcome": "Rajdhani clears with 0 delay; net delay reduced 24 min.",\n'
        '  "future_consequences": "Clear signal for BOXN_99 immediately upon block exit.",\n'
        '  "regulatory_code": "IR G&SR Rule 4.35",\n'
        '  "passenger_announcement": "Train 12951 passing Platform 1.",\n'
        '  "controller_order": "Hold BOXN_99 on siding loop."\n'
        '}'
    )
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response

    copilot = DispatcherCopilot(api_key="mock_key", client=mock_client)
    exp = copilot.explain_decision(
        winner_id="12951",
        winner_name="Rajdhani Express",
        winner_priority="Class 1",
        loser_id="BOXN_99",
        loser_name="Freight Service",
        loser_priority="Class 5",
        segment_id="S2",
        segment_desc="Single Track Block"
    )

    assert exp.is_llm_generated is True
    assert exp.situation == "Bilateral approach conflict on single block S2."
    assert exp.regulatory_code == "IR G&SR Rule 4.35"
    assert exp.model_used == DispatcherCopilot.DEFAULT_MODEL


def test_copilot_graceful_error_handling():
    """Verify that any exception raised by the LLM client triggers fallback without crashing."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Groq Rate Limit Exceeded")

    copilot = DispatcherCopilot(api_key="mock_key", client=mock_client)
    exp = copilot.explain_decision(
        winner_id="12951",
        winner_name="Rajdhani Express",
        winner_priority="Class 1",
        loser_id="BOXN_99",
        loser_name="Freight Service",
        loser_priority="Class 5",
        segment_id="S2",
        segment_desc="Single Track Block"
    )

    assert exp.is_llm_generated is False
    assert exp.model_used == "deterministic-rules"
    assert "12951" in exp.situation
