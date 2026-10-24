# Native Responses stream identity backport

## Problem and scope

H100/A100 的原生 `/v1/responses` 非 Harmony 路径，在发送
`response.output_item.done` 后重新解析完整文本来构造 `response.completed`。
同一函数因此可能得到新 item ID/call ID，已流出的空白消息也可能丢失。
客户端的后续工具结果引用了已发送的调用，却无法匹配最终保存的响应。

本修复 backport [vLLM PR #59307](https://github.com/vllm-project/vllm/pull/59307)
的三模块变更：收集已经完成的流式项，最终响应直接复用它们；保留解析器
call ID、每条消息的文本 logprobs，并保证零参数调用也发参数完成事件。
官方修复已于 2026-09-30 合并；本仓库仅将相应逻辑适配至登记的两个旧源版本。

**保留原生 Responses。** 不切换 Chat 兼容器，不改变网关模型能力绑定，不放松
网关调用身份校验，不把内部 MCP 协议暴露为公共选择格式。
本说明是当前实现与验收要求；发布和部署完成情况必须由对应运行收据证明。

关联：`F-120`、`F-130`、`F-150`；`C-001`、`C-002`、`C-003`、`C-004`。

## Source profiles

安装器校验 `vllm/entrypoints/openai/responses/` 下三个模块：

| Module | Backported responsibility |
|---|---|
| `context.py` | Context retains the completed streamed output objects |
| `streaming_events.py` | Stable item/call identities, message logprobs, arguments.done and completed-item collection |
| `serving.py` | Streaming finalization reuses those items; existing usage/logging and non-streaming path retained |

`patches/responses_identity/profiles.json` 为唯一哈希门禁，记录
`h100-v0.31.0` 与 `a100-v0.13.0` 三文件各自 before/after SHA256。
包版本字符串和 GPU 型号只说明来源，不能代替文件哈希。

- 三文件全部匹配同一 profile 的 before：验证补丁结果及 Python 语法后安装。
- 三文件全部匹配同一 profile 的 after：返回 already-applied，不重写。
- 任一未知、损坏或 before/after 混合：失败，不能关闭校验强制套用。
- 安装器使用 exact-offset unified diff，不需要在线下载或运行 git/patch。
- 目标替换保持文件权限；异常执行回滚。运维仍须另留持久备份，不能把安装器
  的临时事务备份当作发布回滚产物。

升级 vLLM、换基础镜像或修改三个模块后必须重新审查并登记 profile。
此次补丁不包含模型权重、kernel、工具解析器或 GPU 性能优化。

## Install and check

使用运行服务同一环境内的 Python。`--package-root` 指向 **vllm 包目录**，
其下直接有 `entrypoints/`；不是 site-packages 父目录或模型权重目录。

```bash
python3 patches/responses_identity/install.py \
  --package-root /usr/local/lib/python3.12/dist-packages/vllm --check

python3 patches/responses_identity/install.py \
  --package-root /usr/local/lib/python3.12/dist-packages/vllm

python3 patches/responses_identity/install.py \
  --package-root /usr/local/lib/python3.12/dist-packages/vllm --check
```

安装前 check 应报告对应 profile 的 applicable；安装后 check 应为
already-applied。路径以实际容器 Python import 为准，不按示例猜测。
已运行进程可能持有旧模块，磁盘文件替换并不等于运行进程已升级。

A100 镜像构建先使用现有 `patches/install.py` 装入 SM80 优化，再装本补丁；
H100 使用相同发布包自动匹配其自身 profile，保留原镜像和既有启动参数。
不要把 A100 serve 配置复制到 H100。

## Regression commands

```bash
python3 -m pytest -q tests/test_responses_identity_installer.py
python3 scripts/docs_check.py
make check
```

实际 vLLM 环境中的模块行为回归可对隔离 stage 运行，stage 只包含受测
Responses 目录，保持生产源码不变：

```bash
RESPONSES_IDENTITY_MODULE_DIR=/isolated/stage/responses \
  python3 tests/test_responses_identity_runtime.py -v
```

未配置 stage 的默认模块测试必须明确说明运行环境；不能将 import 失败或 skip
报告成通过。验收矩阵要求覆盖以下行为；CPU 模块测试与真实 HTTP 收据应分别标明各自覆盖项：

- reasoning、空白消息、函数调用的输出顺序及 done/final 对象一致性；
- 并发同名函数的独立 ID 和参数；零参数调用的 arguments.done；
- message text/logprobs 归属和完整性；usage 保持原累计方式；
- 原非流式/Harmony 分支，带既有 response store 的调用结果续接；
- 源 profile 拒绝、幂等、payload 完整性、异常回滚及文件权限。

CPU 模块回归不生成真实模型 token，不代替后续直接 HTTP 验收。

## Release and per-node rollout

1. 从已验证主线构建版本化发布包。记录 tag/commit、包 SHA256、补丁
   profile 和三个模块的 before/after。发布包不含密钥和权重。
2. 读回两节点的实际容器/进程、镜像、Python/vLLM 路径、源哈希、参数及
   网关原生能力声明。保存各自回滚镜像/原文件和可复现的启动参数。
3. **每次只维护一台**：仅将该节点对应 Gateway binding 的 `enabled`
   临时设为 false，其他字段及原生 Responses 能力不变。另一节点继续在线。
4. 等待该节点 active/queued 清零，识别绕过网关的直接调用，再优雅停止
   服务/容器。不能因排空超时就自动杀死活动调用；应保留隔离和状态证据。
5. 安装补丁、复核完整 after 哈希及语法，使用原模型、挂载和服务参数启动。
   读回实际运行镜像/进程，不能只看本地发布文件。
6. 在隔离节点直接验收原生 Responses；通过后恢复该 binding enabled，
   使用原 Gateway Key 验证真实 hosted tool 及 SSE/持久执行记录。
7. 确认恢复节点健康且承担请求，再重复另一台。全程不重启宿主机、不同时
   停两台、不更改为 Chat-only 能力。

临时 binding 禁用只排除网关新请求，不能证明直连调用已排空。每个节点的
排空、停止、安装、启动、原生验收、恢复和网关验收必须分别记录。
维护失败时保留另一台可用，不能把“还有一台在线”当作失败节点已完成。

## Native HTTP acceptance

逐台使用实际模型名及原生 `/v1/responses`，保留安全请求 ID、事件类型、
item/call ID、计数及耗时；验收凭证只从已有授权环境传入。

1. 单函数、并发同名函数和零参数函数：added/delta/done 的身份不变，所有
   done 项按原顺序与最终 `response.output` 完全对应；参数 done 不遗漏。
2. 纯文本、reasoning 与空白消息：类型、文本与顺序保持，logprobs 在对应
   message 的 output_text 中；不得把 reasoning token 分配给正文 logprobs。
3. 非流式与 usage：确认未改原路径，token 字段完整且无双计数。随机采样
   的两个请求不要求 token 数天然相同；精确比较使用确定性 fixture。
4. 若原服务启用 response store，使用实际返回的 `response.id` 和
   `function_call.call_id` 发 `function_call_output`，验证真实续接。
5. 完整解析 SSE，要求单一成功终态、非空合法输出及预期事件顺序；收到
   HTTP 200、健康通过、模型口头“已调用”均不足以证明成功。

## Gateway hosted-tool and SSE acceptance

原 Key 通过原生 Responses 路径选择 `mcp_fofa_search`，使用公开且最小的
查询进行一次实际业务调用。执行记录应包含当前已授权服务器的真实 MCP attempt，
远端业务成功标志及最终回答。关联请求 ID 核对 wire、Provider attempt、MCP
attempt 和持久记录，确认终态成功；并补跑 Chat SSE 防回归。

不为通过验收自动增授权限、不输出远端凭证、不保存原始账户/业务数据，不用
管理员全集目录代替当前 Key 权限，不修改网关的 ID 不一致拒绝规则。

## Rollback

任一节点哈希、启动、原生流、续接或业务验收失败：保持该 binding 隔离，保留
另一台可用；按原服务停止/排空流程恢复原镜像或该节点持久备份中的完整三个
源码文件，核验旧哈希并用原参数启动。再次完成健康、原 HTTP 控制及业务验证后
再恢复 binding enabled。

仅把源码文件换回去不代表已运行进程回滚；必须读取新进程身份和实际加载文件。
回滚不重写历史响应，原有 response store 的重启/过期边界仍然适用。

## Evidence record

每次交付记录：版本与 commit、发布包 SHA256、每节点安装 profile、前后源
SHA256、实际容器/镜像/进程身份、网关原生能力保留、排空及恢复时间、各验收
request ID、事件/调用数量、耗时、持久业务结果布尔值及任何失败/回滚。

完成状态只能来自这些新鲜证据；本文件中的步骤不是已经执行的部署记录。
