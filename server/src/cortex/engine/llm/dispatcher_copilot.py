# src/cortex/engine/llm/dispatcher_copilot.py
"""
CORTEX GenAI Dispatcher Copilot.

Powered by Groq LPUs for sub-second, real-time natural language explanations
of CP-SAT constraint optimization decisions and XGBoost delay forecasts.
Adheres to Indian Railways General & Subsidiary Rules (G&SR).
"""
import os
import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class DispatcherExplanation:
    situation: str
    decision: str
    reasoning: str
    expected_outcome: str
    future_consequences: str
    regulatory_code: str
    passenger_announcement: str
    controller_order: str
    is_llm_generated: bool
    model_used: str


class DispatcherCopilot:
    """
    Inference client for AI-assisted rail dispatching explanations.
    Uses Groq for ultra-low latency with deterministic fallback.
    """

    DEFAULT_MODEL = "qwen/qwen3.8-27b"
    FALLBACK_MODELS = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[Any] = None
    ):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            # Try loading from .env if present
            try:
                from dotenv import load_dotenv
                # Check server/.env and root .env
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
                env_path = os.path.join(base_dir, ".env")
                if os.path.exists(env_path):
                    load_dotenv(env_path, override=True)
                else:
                    load_dotenv(override=True)
                self.api_key = os.getenv("GROQ_API_KEY")
            except ImportError:
                pass

        self.model = model or os.getenv("GROQ_MODEL", self.DEFAULT_MODEL)
        self._client = client

        if self._client is None and self.api_key:
            try:
                from groq import Groq
                self._client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Groq client: {e}")
                self._client = None

    def explain_decision(
        self,
        winner_id: str,
        winner_name: str,
        winner_priority: str,
        loser_id: str,
        loser_name: str,
        loser_priority: str,
        segment_id: str,
        segment_desc: str,
        hold_duration_min: int = 24,
        benefit_min: int = 24,
        ml_predicted_delay_min: float = 0.0,
        solver_name: str = "CP-SAT Multi-Train Global Optimizer"
    ) -> DispatcherExplanation:
        """
        Generates a structured, regulatory-compliant natural language explanation
        for a dispatching decision.
        """
        if self._client is not None:
            try:
                prompt = (
                    f"You are a Senior Chief Section Controller for Indian Railways Centralized Traffic Control (CTC).\n"
                    f"Generate an operational explanation for a computerized train conflict resolution decision.\n\n"
                    f"OPERATIONAL INCIDENT:\n"
                    f"- Contested Section: {segment_id} ({segment_desc})\n"
                    f"- Priority Train: {winner_id} ({winner_name}, Priority Class: {winner_priority})\n"
                    f"- Preempted Train: {loser_id} ({loser_name}, Priority Class: {loser_priority})\n"
                    f"- Decision Engine: {solver_name}\n"
                    f"- Machine Learning Context: XGBoost predicts incoming delay variance of {ml_predicted_delay_min:.1f} min\n"
                    f"- Action: Hold {loser_id} at upstream station crossing loop for {hold_duration_min} minutes; clear main line for {winner_id}\n"
                    f"- Corridor Delay Savings: {benefit_min} net minutes saved across the corridor\n\n"
                    f"INSTRUCTIONS:\n"
                    f"Return a strictly valid JSON object with EXACTLY the following keys:\n"
                    f"- \"situation\": A concise 1-sentence description of the spatial-temporal track conflict.\n"
                    f"- \"decision\": Clear operational instruction stating which train is held, at what siding, and for how long.\n"
                    f"- \"reasoning\": Thorough justification referencing train priority classes, bottleneck capacity, and ML delay risk.\n"
                    f"- \"expected_outcome\": Quantified punctuality result for both services.\n"
                    f"- \"future_consequences\": Immediate signal routing once the priority train clears the block.\n"
                    f"- \"regulatory_code\": Official citation under Indian Railways General & Subsidiary Rules (e.g. G&SR Rule 4.35 / Operating Manual Chapter 7).\n"
                    f"- \"passenger_announcement\": Public address (PA) announcement script for station platforms.\n"
                    f"- \"controller_order\": Formal telegram/control order to Section Controller and Station Master."
                )

                models_to_try = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]
                last_err = None
                for model_candidate in models_to_try:
                    try:
                        response = self._client.chat.completions.create(
                            model=model_candidate,
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        "You are an expert Indian Railways railway dispatching engine. "
                                        "You always output strictly valid JSON matching the requested schema without markdown backticks."
                                    )
                                },
                                {"role": "user", "content": prompt}
                            ],
                            response_format={"type": "json_object"},
                            max_tokens=800,
                            temperature=0.2
                        )

                        content = response.choices[0].message.content.strip()
                        data = json.loads(content)

                        return DispatcherExplanation(
                            situation=data.get("situation", f"Contention on {segment_id} between {winner_id} and {loser_id}."),
                            decision=data.get("decision", f"Hold Train {loser_id} for {hold_duration_min} min; clear main line for {winner_id}."),
                            reasoning=data.get("reasoning", f"{winner_id} ({winner_priority}) takes precedence over {loser_id} ({loser_priority})."),
                            expected_outcome=data.get("expected_outcome", f"{winner_id} clears without delay; corridor delay reduced by {benefit_min} min."),
                            future_consequences=data.get("future_consequences", f"{loser_id} clears onto {segment_id} once block occupancy resets."),
                            regulatory_code=data.get("regulatory_code", "IR G&SR Rule 4.35 (Precedence of Trains at Crossing Stations)"),
                            passenger_announcement=data.get("passenger_announcement", f"Attention passengers, Train {winner_name} will pass through platform 1 shortly."),
                            controller_order=data.get("controller_order", f"CONTROL ORDER: Hold {loser_id} on siding loop; grant line clear to {winner_id} on S2."),
                            is_llm_generated=True,
                            model_used=model_candidate
                        )
                    except Exception as err:
                        last_err = err
                        logger.warning(f"Groq call with {model_candidate} failed: {err}")

                logger.warning(f"All Groq LLM candidates failed (last error: {last_err}). Falling back to deterministic template.")
            except Exception as e:
                logger.warning(f"Groq LLM explanation generation failed: {e}. Falling back to deterministic template.")

        # Deterministic Fallback Template
        return DispatcherExplanation(
            situation=f"Train {winner_id} ({winner_name}) and Train {loser_id} ({loser_name}) approaching single-track {segment_id} from opposite directions.",
            decision=f"Hold Train {loser_id} at Station B Crossing Loop (X1) for {hold_duration_min} minutes until Train {winner_id} clears {segment_id}.",
            reasoning=(
                f"Train {winner_id} carries Priority Class {winner_priority} vs Train {loser_id} Priority Class {loser_priority}. "
                f"Single-track block capacity is strictly 1 train. XGBoost delay model projects knock-on cascading risk of "
                f"{ml_predicted_delay_min:.1f} min if {winner_id} is stopped."
            ),
            expected_outcome=f"Train {winner_id} clears {segment_id} on schedule; net corridor delay minimized by {benefit_min} minutes.",
            future_consequences=f"Train {loser_id} is cleared onto {segment_id} immediately once Train {winner_id} exits the block.",
            regulatory_code="IR G&SR Rule 4.35 (Precedence of Trains on Single-Line Block Sections)",
            passenger_announcement=f"Attention passengers: Train {winner_id} ({winner_name}) is passing through on Main Line.",
            controller_order=f"CONTROL ORDER: Set point to reverse for {loser_id} to enter Crossing Loop; signal clear for {winner_id} on {segment_id}.",
            is_llm_generated=False,
            model_used="deterministic-rules"
        )
