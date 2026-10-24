# Development Rules

## Scope and contracts

This fork keeps the existing SM80 launch, router and benchmark paths. Native
Responses identity is a separately bounded backport of upstream vLLM PR #59307;
do not replace `/v1/responses` with Chat compatibility or weaken a caller's
identity checks to mask an upstream mismatch.

1. Inspect Git status and the actual source/image revision before editing.
2. Add a behavioral regression, observe its intended failure, then make the
   smallest fix. Test the installed target modules, not only patch text.
3. Keep API, configuration, Feature IDs, Contract IDs, tests and CHANGELOG
   synchronized. Existing A800 benchmark results do not establish H100/A100
   correctness, performance or deployment status.
4. Verify all three Responses source hashes as one supported profile before
   writing any target. Reject unknown or mixed revisions. Keep a rollback copy
   and verify the installed hashes and syntax before restarting a process.
5. Preserve non-streaming behavior, usage, logprobs, reasoning privacy, ordered
   concurrent calls and `previous_response_id` continuation. Do not reparse a
   completed stream to assign new item or call IDs.
6. Never record API keys, Authorization, cookies, prompts or raw account data
   in release receipts. Record revision/image/source hashes and safe request IDs.
7. Release and deploy only within the user's authorization. Drain and verify
   one node while the other remains available; never restart both together.
   Health alone is insufficient: pass direct native tool streams before
   reenabling the binding, then replay the original gateway hosted-tool request
   and inspect durable execution records. Re-isolate on a failed gateway probe.
8. New or modified production files must stay below 1,000 lines. Do not edit
   unrelated historical benchmark/research reports to imply new results.

## Checks

Run from the repository root:

```bash
python3 -m pytest -q tests
python3 scripts/docs_check.py
python3 -m compileall -q patches/responses_identity scripts
```

The release owner additionally runs the repository's `make check` entry point.
Native CPU tests do not replace GPU/container acceptance. Commands, deployment
checks and rollback are documented in [TESTING](docs/TESTING.md) and the
[native Responses runbook](docs/native-responses-identity.md).
