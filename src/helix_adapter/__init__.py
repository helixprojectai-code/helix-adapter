"""helix-adapter: Portable constitutional wrapper for any AI model.

Wraps any inference backend with Helix epistemic markers, structured
receipts, and drift detection. Model-agnostic — swap Deepseek for
GPT-4o, Claude, or a local Llama without changing a line.
"""

from .adapter import HelixAdapter
from .prompt import CONSTITUTIONAL_PROMPT, MARKERS
from .markers import extract_claims
from .receipt import make_receipt
from .drift import compute_drift

__all__ = [
    "HelixAdapter",
    "CONSTITUTIONAL_PROMPT",
    "MARKERS",
    "extract_claims",
    "make_receipt",
    "compute_drift",
]
