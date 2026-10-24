# Changelog

This file tracks changes to this fork. Earlier optimization and benchmark history
remains in the existing README, reports and Git history.

## 0.1.0 - 2026-10-24

### Added

- `F-120` Add separately hash-gated H100/A100 Responses identity patch profiles
  and an idempotent installer for exact known source revisions (`C-001`).
- `F-150` Add current architecture/API/configuration/operation documentation and
  structural documentation checks. Historical benchmark claims retain their
  original hardware and workload boundaries (`C-004`).

### Fixed

- `F-130` Backport vLLM PR #59307 to reuse completed streamed Responses items in
  the final output, preserving item/call identity, order, message logprobs and
  argument completion events (`C-002`). Non-streaming and usage retain their
  original paths; native Responses remains enabled.

### Security

- `F-120` Reject unknown/mixed source profiles before mutation and verify the
  complete patch payload; retain explicit per-node rollback and deployment
  evidence requirements (`C-001`, `C-003`).
