---
title: "RFC 0002 — Sparse Attention Masks and Entropy Drift Metrics for Constraining Information Flow"
author: "Stephen Hope, Custodian"
date: "2026-06-23"
status: "Draft"
version: "0.2"
---

# RFC 0002: Sparse Attention Masks and Entropy Drift Metrics for Constraining Information Flow in Transformer Inference

## Abstract

This RFC defines mechanisms to constrain and audit information flow in transformer-based models through **sparse attention masks** and an **entropy-based drift metric** (γ). These primitives raise the cost and detectability of hidden high-dimensional reasoning across layers, enabling more verifiable governance than prompt-level or output-level techniques alone. The approach is paired with cryptographic receipts for external auditability.

## 1. Sparse Attention as a Constrained Information Flow Graph

In a standard transformer attention layer \( l \), the attention weights are computed as:

\[
A^{(l)} = \text{softmax}\left( \frac{QK^T}{\sqrt{d_k}} \right)
\]

We introduce a binary mask \( M^{(l)} \in \{0,1\}^{n \times n} \) that restricts which tokens may attend to each other:

\[
A^{(l)}_{ij} = \frac{\exp\left( \frac{q_i \cdot k_j}{\sqrt{d_k}} \right) \cdot M^{(l)}_{ij}}{\sum_m \exp\left( \frac{q_i \cdot k_m}{\sqrt{d_k}} \right) \cdot M^{(l)}_{im}}
\]

The mask \( M^{(l)} \) defines the allowed information flow graph for that layer. Tokens may only exchange information along edges where \( M_{ij} = 1 \).

## 2. Entropy-Based Drift Metric (γ)

For each token \( i \) at layer \( l \), let \( S_i = \{ j \mid M_{ij} = 1 \} \) be the set of tokens it is allowed to attend to. The attention entropy for that token is:

\[
H(A_i^{(l)}) = -\sum_{j \in S_i} A^{(l)}_{ij} \log A^{(l)}_{ij}
\]

The maximum possible entropy under the mask is \( H_{\max} = \log(|S_i|) \).

We define the **local drift coefficient** as the normalized entropy:

\[
\gamma_i^{(l)} = \frac{H(A_i^{(l)})}{\log(|S_i|)}
\]

- \( \gamma \to 0 \): Highly concentrated attention (focused, low-drift behavior)
- \( \gamma \to 1 \): Diffuse attention across all allowed channels (higher drift)

The **global drift score** across the model is:

\[
\Gamma = \frac{1}{L \cdot N} \sum_{l=1}^{L} \sum_{i=1}^{N} \gamma_i^{(l)}
\]

### Drift Thresholds (Policy Configurable)

These thresholds are **configurable policy parameters**, not hardcoded governance rules:

| Zone   | Condition          | Interpretation                     | Recommended Action      |
|--------|--------------------|------------------------------------|-------------------------|
| Green  | \( \Gamma < 0.10 \)   | Low drift, focused reasoning       | Accept                  |
| Yellow | \( 0.10 \leq \Gamma < 0.17 \) | Moderate diffusion                 | Log + optional review   |
| Red    | \( \Gamma \geq 0.17 \) | High diffusion within mask         | Halt or flag for audit  |

Default values are provided as starting points and should be tuned based on model behavior and use case.

## 3. Constraining Hidden Reasoning Channels

Dense attention produces a dense effective Jacobian between layers, allowing the model to maintain high-dimensional internal state that may not be visible in the output token stream.

By enforcing sparse attention masks, information flow is projected into a lower-dimensional subspace defined by the mask. This increases the difficulty and cost of maintaining complex, unlogged hidden computation across layers.

While sparse attention does not *eliminate* the possibility of hidden reasoning, it significantly raises the computational and statistical cost of doing so undetected. Complex multi-step reasoning is forced to route through the visible token channels (and therefore through explicit epistemic markers), making hidden state maintenance both more expensive and more detectable via elevated local entropy (\( \gamma \)).

## 4. Cryptographic Receipt Schema

Every inference produces a signed, tamper-evident receipt containing:

```json
{
  "receipt_id": "rcpt_...",
  "timestamp": "...",
  "hardware_attestation": {
    "tee_provider": "nitro_enclaves",
    "enclave_measurement_hash": "...",
    "signature": "..."
  },
  "execution_parameters": {
    "model_hash": "...",
    "temperature": 0.0,
    "mask_protocol": "LATTICE_SPARSE_V2",
    "mask_config_hash": "..."
  },
  "epistemic_payload": {
    "input_hash": "...",
    "output_text": "...",
    "computed_metrics": {
      "global_gamma": 0.003,
      "mask_compliance_checksum": "..."
    }
  }
}
```
