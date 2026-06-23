# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""helix-adapter: Portable constitutional wrapper for any AI model.

Wraps any inference backend with Helix epistemic markers, structured
receipts, and drift detection. Model-agnostic — swap Deepseek for
GPT-4o, Claude, or a local Llama without changing a line.
"""

from .adapter import HelixAdapter
from .drift import compute_drift
from .markers import detect_nonstandard_markers, extract_claims, validate_response
from .prompt import CONSTITUTIONAL_PROMPT, MARKERS
from .receipt import make_receipt

__all__ = [
    "HelixAdapter",
    "CONSTITUTIONAL_PROMPT",
    "MARKERS",
    "extract_claims",
    "validate_response",
    "detect_nonstandard_markers",
    "make_receipt",
    "compute_drift",
]
