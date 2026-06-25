"""Cedar policy loading, evaluation, and pre/post-tool-use hooks."""

import json
import hashlib
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

HERE = Path(__file__).parent
DEFAULT_POLICY = HERE / "policies" / "helix.policy"


def load_policy(path: Optional[Path] = None) -> str:
    """Load a Cedar policy file from disk."""
    path = path or DEFAULT_POLICY
    return path.read_text() if path.exists() else ""


class CedarGate:
    """Cedar policy gate for agent tool-use authorization.

    Usage:
        gate = CedarGate(policy_file="helix.policy")

        ok, reason = gate.authorize(
            principal={"type": "Helix::Agent", "id": "session_123"},
            action='Helix::Action::"bash"',
            resource={"type": "Helix::Environment", "id": "/sandbox"},
            context={"command": "rm", "arguments": ["-rf", "/tmp"]},
        )
        if not ok:
            raise PermissionError(reason)
    """

    def __init__(self, policy_file: Optional[str] = None):
        self.policy_text = load_policy(
            Path(policy_file) if policy_file else None
        )
        self.policy_hash = hashlib.sha256(
            self.policy_text.encode()
        ).hexdigest()[:16] if self.policy_text else "no_policy"

    def authorize(
        self,
        principal: Dict[str, str],
        action: str,
        resource: Dict[str, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Evaluate whether an action is authorized under the loaded policy.

        Returns (authorized: bool, reason: str).
        """
        if not self.policy_text:
            return (True, "no policy loaded — default permit")

        request: Dict[str, Any] = {
            "principal": f'{principal["type"]}::"{principal["id"]}"',
            "action": action,
            "resource": f'{resource["type"]}::"{resource["id"]}"',
        }
        if context:
            request["context"] = context

        try:
            result = subprocess.run(
                ["cedar", "authorize",
                 "--policies", "-",
                 "--request", json.dumps(request)],
                input=self.policy_text,
                capture_output=True, text=True, timeout=5,
            )
            output = json.loads(result.stdout)
            decision = output.get("decision", "Deny")
            reasons = output.get("reasons", [])
            return (decision == "Allow", "; ".join(reasons) if reasons else decision)
        except FileNotFoundError:
            return (True, "cedar CLI not found — default permit (warning)")
        except Exception as e:
            return (False, f"policy evaluation error: {e}")

    def seal_action(
        self, exchange_id: str, action: str,
        authorized: bool, result: Any = None,
    ) -> Dict[str, Any]:
        """Generate a tamper-evident action receipt chained to the chat receipt."""
        payload = {
            "exchange_id": exchange_id,
            "action": action,
            "authorized": authorized,
            "policy_hash": self.policy_hash,
            "result": str(result)[:500] if result else None,
        }
        receipt_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        payload["hash"] = f"sha256:{receipt_hash}"
        return payload
