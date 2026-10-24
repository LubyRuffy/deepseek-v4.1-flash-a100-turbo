# Architecture

The repository packages an existing vLLM distribution, reviewed source patches,
launch configuration, optional node routers and benchmark clients. Model weights
are mounted from an existing local directory; the launch configuration enables
DeepSeek tool/reasoning parsers and preserves the native OpenAI HTTP endpoints.

## Components

| Component | Responsibility | Entry |
|---|---|---|
| Container build | Pinned vendor runtime and reviewed SM80 patch installation | `Dockerfile`, `patches/install.py` |
| Node launch | Existing model mount, GPU/container arguments and vLLM flags | `launch.py`, `config/serve.json` |
| Responses identity backport | Hash-gated installation of the native stream correction | `patches/responses_identity/install.py` |
| Optional routing | Cache/rank routing and backend-metric routing | `router/launch.py`, `router/adaptive_router.py` |
| Verification clients | Reproducible workload, smoke and benchmark evidence | `benchmarks/README.md`, `tests` |

## Native Responses data flow

1. A request reaches vLLM `/v1/responses`; tool definitions use the native
   function schema. The server generates a stream through its existing parser.
2. The streaming processor closes output items, including reasoning, messages
   and function calls. The Responses context retains those completed items.
3. `response.completed.response.output` reuses the completed streamed objects
   in their emitted order. Function `call_id` comes from that invocation's
   parser identity. It is never reconstructed by another parse of the full text.
4. The same final response follows the existing storage/continuation path, so a
   subsequent `function_call_output.call_id` can refer to the emitted invocation.
   Usage calculation, non-streaming parsing and Harmony behavior remain on their
   existing paths.

This repository does not execute the client's function. AIGateway may execute
an authorized hosted MCP tool and continue the model conversation. Its tool
selection, permission enforcement, journaling and identity checks remain separate
and are not changed by this backport.

## Patch and deployment boundary

The installer supports the exact H100/A100 source profiles in its manifest; a GPU
model name or a matching Python package version alone is insufficient. It checks
all target hashes before mutation. The runtime correction touches the Responses
context, streaming event processor and serving finalization; it does not alter
SM80 kernels, model weights, public gateway bindings or compatibility adapters.

See [current features](docs/FEATURES.md), [contracts](docs/CONTRACTS.md),
[configuration](docs/CONFIG.md) and the [deployment runbook](docs/native-responses-identity.md).
