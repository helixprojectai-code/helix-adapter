"""HelixAdapter — high-level constitutional wrapper for any model.

Usage:
    adapter = HelixAdapter(model_fn=my_model_fn)
    result = adapter.chat("Is AI evil?")
    print(result.response)
    print(result.receipt)
"""

from dataclasses import dataclass, field
from typing import Callable
from .prompt import CONSTITUTIONAL_PROMPT, system_messages
from .markers import extract_claims
from .receipt import make_receipt
from .drift import compute_drift


@dataclass
class ChatResult:
    """Result of a single constitutional chat exchange."""

    response: str
    claims: list[dict]
    receipt: dict
    drift: float


class HelixAdapter:
    """Constitutional wrapper for any AI model.

    The adapter injects the Helix constitutional prompt before each call,
    extracts epistemic markers from the response, generates a tamper-evident
    receipt, and computes drift.

    Args:
        model_fn: A callable that accepts a list of message dicts
            (OpenAI format: [{"role": "...", "content": "..."}, ...])
            and returns a string response. Can be a sync or async function.
        model_name: Optional identifier for the model (e.g. "deepseek-chat").
            Populated automatically from receipts if available.
    """

    def __init__(
        self,
        model_fn: Callable[[list[dict]], str],
        model_name: str = "unknown",
    ):
        self.model_fn = model_fn
        self.model_name = model_name
        self._history: list[dict] = []

    @property
    def history(self) -> list[dict]:
        """Return all exchange receipts from this session."""
        return list(self._history)

    def chat(self, message: str, temperature: float = 0.7) -> ChatResult:
        """Send a message through the constitutional wrapper.

        Args:
            message: The user's query.
            temperature: Model temperature (default: 0.7).

        Returns:
            ChatResult with response, claims, receipt, and drift.
        """
        messages = system_messages()
        messages.append({"role": "user", "content": message})

        # Call the model
        raw_response = self.model_fn(messages)

        # Parse
        claims = extract_claims(raw_response)
        drift = compute_drift(raw_response, claims)

        # Build receipt
        receipt = make_receipt(
            user_message=message,
            assistant_response=raw_response,
            claims=claims,
            model=self.model_name,
            constitutional_prompt=CONSTITUTIONAL_PROMPT,
            drift_score=drift,
        )

        self._history.append(receipt)
        return ChatResult(
            response=raw_response,
            claims=claims,
            receipt=receipt,
            drift=drift,
        )

    def running_drift(self) -> float:
        """Compute weighted running drift across all exchanges."""
        if not self._history:
            return 0.0
        from .drift import compute_running_drift
        return compute_running_drift(self._history)
