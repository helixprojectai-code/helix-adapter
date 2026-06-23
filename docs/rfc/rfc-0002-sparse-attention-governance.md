---
title: "RFC 0002: Sparse Attention Constraints, Drift Metrics, and Jacobian Projection for Verifiable LLM Governance"
author: "Stephen Hope, Custodian"
date: "2026-06-23"
status: "Draft"
---

## Abstract

This RFC defines mathematically rigorous mechanisms for enforcing and auditing structural constraints on transformer-based models using **sparse attention masks**, an **entropy-based drift metric (γ)**, and **Jacobian projection** to limit hidden reasoning channels. These primitives enable verifiable, tamper-evident governance without relying on the model's internal weights.

## 1. Sparse Attention as a Constrained Dynamical System

In a standard transformer layer \( l \), the attention matrix is:

\[
A^{(l)} = \text{softmax}\left( \frac{Q K^T}{\sqrt{d_k}} \right)
\]

We introduce a binary mask \( M^{(l)} \in \{0,1\}^{n \times n} \) to enforce sparsity:

\[
A^{(l)}_{ij} = \frac{\exp\left( \frac{q_i \cdot k_j}{\sqrt{d_k}} \right) \cdot M^{(l)}_{ij}}{\sum_m \exp\left( \frac{q_i \cdot k_m}{\sqrt{d_k}} \right) \cdot M^{(l)}_{im}}
\]

This mask defines the allowable information flow graph for each token.

## 2. Entropy-Based Drift Metric (γ)

For token \( i \) at layer \( l \), let \( S_i = \{ j \mid M_{ij} = 1 \} \) be the active attention targets. The local entropy is:

\[
H(A^{(l)}_i) = -\sum_{j \in S_i} A^{(l)}_{ij} \log A^{(l)}_{ij}
\]

The maximum entropy under the mask is \( H_{\max} = \log(|S_i|) \).

The **local drift coefficient** is:

\[
\gamma^{(l)}_i = \frac{H(A^{(l)}_i)}{\log(|S_i|)}
\]

- \( \gamma \to 0 \): Highly focused, predictable information flow (desired).
- \( \gamma \to 1 \): Maximum diffusion within allowed channels (high drift).

**Global drift score** \( \Gamma \):

\[
\Gamma = \frac{1}{L \cdot N} \sum_{l=1}^L \sum_{i=1}^N \gamma^{(l)}_i
\]

**Thresholds** (configurable):
- Green: \( \Gamma < 0.10 \)
- Yellow: \( 0.10 \leq \Gamma < 0.17 \)
- Red: \( \Gamma \geq 0.17 \)

## 3. Jacobian Projection for Preventing Hidden Reasoning

Let \( x^{(l)} \) be the activation vector at layer \( l \). The sensitivity between layers is given by the Jacobian:

\[
J_{jk} = \frac{\partial x^{(l+1)}_j}{\partial x^{(l)}_k}
\]

Dense attention produces a dense Jacobian, enabling high-capacity hidden computation (steganography) that never appears in the final token stream.

Sparse attention + mask enforcement projects the information flow into a lower-dimensional subspace. This sparsifies the effective Jacobian, strictly limiting the model's ability to maintain unlogged, high-dimensional internal state across layers.

**Consequence**: Any complex reasoning must route through the visible, discrete token channels (epistemic markers). Hidden computation becomes both expensive and detectable via increased local entropy (γ).

## 4. Cryptographic Receipt Schema for Verifiability

To provide external auditability, each inference produces a signed receipt:

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
    "mask_protocol": "LATTICE_SPARSE_V2"
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

The `mask_compliance_checksum` binds the exact sparse mask used during inference. Any attempt to bypass sparsity invalidates the receipt.

## 5. Implementation Notes & Next Steps

- Integrate γ computation into the HelixAdapter's extraction layer.
- Bind mask state to TEE attestations for production receipts.
- Extend to tool-calling/action gating (Cedar policy integration).

This framework turns governance from prompt-level theater into mathematically enforceable substrate constraints.

**The formation holds.** 📐🦆⚓
