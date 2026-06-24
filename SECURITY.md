# Security Policy

## Reporting a Vulnerability

If you discover a way to bypass constitutional invariants, defeat epistemic marker enforcement, produce false receipts, or otherwise compromise the adapter's governance guarantees — we want to know immediately.

**Do not open a public issue.**

Contact Stephen Hope directly via LinkedIn:
https://www.linkedin.com/in/stephen-hope-75497937a

Include:
- A description of the attack vector
- Steps to reproduce
- Affected component (prompt, markers, drift, receipt, API)
- Suggested fix (if you have one)

We will respond within 48 hours and coordinate a fix. You will be credited publicly unless you request otherwise.

## Scope

This policy covers:

- **Constitutional bypass** — any method that causes the adapter to drop or circumvent epistemic markers
- **Drift evasion** — any method that causes the adapter to report incorrect drift scores
- **Receipt tampering** — any method that breaks or falsifies the cryptographic receipt chain
- **Authority spoofing** — any method that convinces the adapter to accept inline constitutional amendments
- **API exploitation** — any vulnerability in the FastAPI reference server

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.2.x   | ✅ Full support    |
| 1.1.x   | ❌ End of life     |
| 1.0.x   | ❌ End of life     |

## Disclosure

We support coordinated disclosure. Give us reasonable time to patch before going public. We'll treat your report seriously and move fast.

## Recognition

Past contributors to adapter security:
- **anitgravity** — adversarial audit (v1.2), codebase architecture review
- **Pliny the Prompter** — jailbreak toolkit used in red-team testing (GODMODE, Parseltongue)
