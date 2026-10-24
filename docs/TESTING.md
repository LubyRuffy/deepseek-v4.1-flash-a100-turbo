# Testing

## Local checks

```bash
python3 -m pytest -q tests
python3 scripts/docs_check.py
python3 -m compileall -q patches/responses_identity scripts
make check
```

安装器测试使用临时目录，不改运行节点源码；安装器测试必须证明未知/混合版本
失败且文件不变、支持 profile 精确匹配、已安装 no-op、完整校验后才写、写入
失败回滚及权限位保留。

运行模块回归需要实际 vLLM 依赖；不能把依赖缺失后的 skip 当通过。使用隔离
stage/overlay 载入补丁后的实际模块，禁止为运行测试改写线上 import 路径。
完整运行方式以测试文件及 [runbook](native-responses-identity.md) 为准。

## A100 typed text regression

```bash
python3 -m pytest -q tests/test_deepseek_v41_text_content.py
```

测试直接载入补丁文件的实际归一化函数及模板路径，覆盖 `text`、`input_text`、
`output_text`、混合块顺序、字符串、图像既有规则、未知类型拒绝，以及深层原
请求不变。工具历史还须保留实际 call ID 和 JSON 数值，标准 typed continuation
与同语义字符串历史生成相同 prompt。源码/manifest after SHA256 必须同步。

H100 已有文本类型支持，验收时记录其 tokenizer 安装前后哈希相同；不能通过
覆盖 H100 tokenizer 让两台源码看起来一致。

## Required behavioral matrix

| Case | Assertion |
|---|---|
| Single function | added/delta/done/final identify the same invocation |
| Parallel same-name functions | distinct call IDs and correct arguments per invocation |
| Zero-argument function | one arguments.done before its item.done, even without argument delta |
| Reasoning + whitespace + function | keep type, order and every completed item |
| Text and logprobs | text/token logprobs belong to their message; done equals final |
| Usage | no duplication; deterministic fixture preserves original token accounting |
| Non-streaming/Harmony | existing finalization path retained |
| Tool continuation | returned call_id is accepted with the prior response identity |
| Standard typed history | input_text/output_text plus function_call_output continues successfully without mutating caller input |
| HTTP/cancellation | exactly one successful terminal or an explicit failure; no false success |

行为测试必须先在原模块复现预期失败，再在补丁模块通过。仅查补丁字符串、哈希
或 AST 不能证明 SSE 身份正确。修改安装器时也要运行两种真实源 profile 的
模块测试，而不只测一套手写替身。

## Live node and gateway acceptance

1. 在 H100/A100 各自核验运行镜像、包版本和三个实际文件哈希；A100 另核验
   tokenizer 的精确升级哈希，H100 tokenizer 保持其原哈希及推理设置。
2. 直接调用该节点原生 `/v1/responses`，分别覆盖函数、并发同名、零参数、
   纯文本/logprobs、非流式和具存储条件的工具续接。另以标准 typed user
   `input_text`、实际输出项及 `function_call_output` 发送显式历史续写，要求
   原生 HTTP 接受并返回成功终态，不得用改写 input 的变体代替。
3. 对完整 SSE 做 JSON 解析，按输出项/call ID 关联；逐个比较 `output_item.done`
   与最终 `response.output`。不能仅检查 HTTP 200 或最后一句自然语言。
4. 经过原 AIGateway 请求与相同已授权 Key 执行真实 FOFA hosted tool。检查
   实际 MCP attempt、业务成功标志、后续 Provider typed-history 续写与最终
   SSE 终态，记录 request ID 和时序。第一轮 FOFA 成功而续写 400 仍是失败。
5. 另跑 Chat SSE，确认上游补丁未破坏已可用路径；网关绑定继续声明原生 Responses。
6. 逐节点恢复流量，重读实际容器/进程/哈希。健康、流量恢复与业务验收分别报告。

随机生成的 stream/non-stream 答案可以不同，usage 也可能不同；验收要求字段
正确、无重复，确定性 fixture 才可用于精确 token 对比。若节点不存响应，明确
报告 `previous_response_id` 未具备验收前提，不能暗中改变配置使其通过。

## Documentation checks

`scripts/docs_check.py` 只检查当前新增文档：必需文件、Feature/Contract ID
唯一性与引用闭合、每个叶子功能/契约的证据路径，以及文档内相对链接存在。
它不追溯重写历史 benchmark 或验证远程链接，也不能代替语义审查。

相关功能：`F-131`、`F-150`；契约：`C-001`、`C-002`、`C-003`、`C-004`、`C-006`。
