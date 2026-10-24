# Changelog

This file tracks changes to this fork. Earlier optimization and benchmark history
remains in the existing README, reports and Git history.

## 0.1.1 - 2026-10-24

### Fixed

- `F-131` Accept standard Responses `input_text` and `output_text` blocks in
  the A100 custom tokenizer alongside legacy `text`, preserving block order
  and the original caller input. This corrects typed-history continuation that
  could return 400 after a function and real FOFA execution had succeeded
  (`C-006`). H100 already accepts these types and retains its existing tokenizer
  and reasoning settings.

### Changed

- `F-150` Require actual HTTP typed-history plus `function_call_output`
  continuation and final SSE success for tool-chain acceptance; a successful
  first tool call alone is insufficient (`C-003`, `C-006`). The A100 incremental
  upgrade verifies the exact prior and new tokenizer hashes while retaining
  the existing Responses identity correction (`C-001`).

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
