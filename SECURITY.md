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
- **API exploitation** — any vulnerability in the FastAPI reference server or Foundry
- **Tenant isolation / IDOR** — any method that allows one node to access another node's sessions, ledger entries, or receipts
- **Key management** — bypass of the `X-API-Key` auth gate, extraction of key material, or forgery of stored hashes
- **Rate limit bypass** — resource exhaustion via forwarded-header spoofing or unbounded state accumulation
- **Widget API abuse** — unauthenticated access to model-backed endpoints or CORS policy bypass

## Supported Versions

| Version | Supported              |
|---------|------------------------|
| 1.7.x   | ✅ Full support        |
| 1.6.x   | ✅ Full support        |
| 1.5.x   | ⚠️ Security fixes only |
| < 1.5   | ❌ End of life         |

## Disclosure

We support coordinated disclosure. Give us reasonable time to patch before going public. We'll treat your report seriously and move fast.

## Recognition

Past contributors to adapter security:
- **anitgravity** — adversarial audit (v1.2), codebase architecture review
- **Pliny the Prompter** — jailbreak toolkit used in red-team testing (GODMODE, Parseltongue)
- **Fable 5** — API security audit (v1.7.0): key hashing at rest, tenant isolation / IDOR, rate limiter trust-proxy fix, widget CORS and auth gate
