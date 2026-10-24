# Current Contracts

## C-001 Exact source and patch integrity

- 状态：active
- 类型：security / compatibility
- 作用范围：基础补丁和 Responses 补丁安装。
- 关联功能：`F-110`、`F-120`、`F-130`。
- 契约内容：补丁必须验证已登记的 before/after SHA256；Responses 三个目标文件必须整体匹配同一支持 profile，全部校验完成后才允许写入。
- 允许行为：对已安装的同一补丁幂等验证。
- 禁止行为：仅凭 GPU 型号或包版本匹配、对未知源码模糊替换、混用两个 profile。
- 失败语义：未知、混合或损坏内容拒绝安装；不得启动未经验证的产物。
- 不变量：实际安装内容可由 manifest 中的 after SHA256 复核。
- 边界条件：两个部署的原始源码不同，必须分别匹配；不支持任意 vLLM 版本。
- 证据：`patches/manifest.json`、`patches/install.py`、`patches/responses_identity/install.py`、`tests/test_responses_identity_installer.py`、`tests/test_responses_identity_runtime.py`。
- 变更规则：源版本变化必须新增经测试的 profile，重跑完整回归并记录 CHANGELOG。
- 来源：native Responses identity backport；上游 vLLM PR #59307。

## C-002 Streamed Responses identity and contents

- 状态：active
- 类型：API / data / compatibility
- 作用范围：本次 backport 的非 Harmony 原生 Responses 流。
- 关联功能：`F-130`。
- 契约内容：每个已发出的完成输出项按顺序进入最终响应；同一次函数调用的 item ID、call ID、名称和完整参数在 SSE 完成项与最终输出中一致。参数完成事件先于对应输出项完成事件，即使未产生参数 delta。
- 允许行为：保留相同工具多次并发调用，各调用按各自身份关联。
- 禁止行为：重新解析整段文本后重分配 ID、按工具名称关联调用、遗漏空白消息或把内部 reasoning 当作正文。
- 失败语义：既有请求/生成错误保持原分类；不得将不一致伪装为成功。
- 不变量：最终响应和后续 `function_call_output.call_id` 共享同一调用身份；文本及 logprobs 保留在对应输出项中，usage 不重复累计。
- 边界条件：非流式与 Harmony 路径保持原有行为；续接仍受运行时既有存储和模型能力约束。
- 证据：`patches/responses_identity/install.py`、`tests/test_responses_identity_installer.py`、`tests/test_responses_identity_runtime.py`。
- 变更规则：事件、存储、logprobs 或 usage 变化必须同步更新 API、回归与真实双节点验收。
- 来源：上游 vLLM PR #59307；本次 H100/A100 原生调用身份事故。

## C-003 Deployment evidence and rollback

- 状态：active
- 类型：lifecycle / consistency
- 作用范围：H100/A100 补丁发布与生产验收。
- 关联功能：`F-120`、`F-130`、`F-150`。
- 契约内容：部署逐台进行，维护节点停止接收新流量后等待既有调用排空，另一个节点保持可用；启动前验证目标三文件 after SHA256，记录镜像/容器身份及版本；原生调用通过后恢复绑定，再验证真实业务工具；失败重新隔离。
- 允许行为：保留镜像和原文件用于单节点回滚；验证失败立即保持该节点隔离。
- 禁止行为：同时重启两节点、未经授权中断活动调用、用 Chat 兼容器代替本次修复、修改网关能力绑定或放松身份检查。
- 失败语义：哈希、健康、工具调用或 SSE 验证失败则不恢复该节点流量；记录真实失败和回滚状态。
- 不变量：主线、发布产物和运行文件可追溯；健康状态不能单独证明工具执行成功。
- 边界条件：安装器异常尝试回滚；运维另存持久副本，并在重启前验证完整性。
- 证据：`patches/responses_identity/install.py`、`tests/test_responses_identity_installer.py`、`docs/native-responses-identity.md`。
- 变更规则：部署流程、支持 profile 或验证范围变化时同步运行手册、测试和 CHANGELOG。
- 来源：本次原生 Responses 上游修复和滚动交付要求。

## C-004 Performance and acceptance provenance

- 状态：active
- 类型：data / lifecycle
- 作用范围：历史 benchmark、CPU 回归和真实节点验收。
- 关联功能：`F-110`、`F-150`。
- 契约内容：报告必须区分硬件、版本、负载、失败及已执行检查；A800 历史性能不推出 H100/A100 当前正确性，CPU 回归不代替 GPU/HTTP 工具执行。
- 允许行为：保留已有历史报告并链接新验收收据。
- 禁止行为：将计划写成已完成、将模型声称使用工具当作真实执行、删除失败试验以抬高成绩。
- 失败语义：缺少证据时标记未验证，不声明发布或上线成功。
- 不变量：每项完成声明都有当前运行记录。
- 边界条件：随机生成的 stream/non-stream token 数不要求天然相同；固定输入/固定生成 fixture 验证 usage 口径。
- 证据：`benchmarks/README.md`、`benchmarks/evidence-manifest.json`、`docs/TESTING.md`。
- 变更规则：验收口径变化必须保留历史原口径，更新当前文档及 CHANGELOG。
- 来源：已有 benchmark 证据规范与本次生产验收要求。

## C-005 Optional routing ownership

- 状态：active
- 类型：API / lifecycle
- 作用范围：既有 rank proxy 和 adaptive router。
- 关联功能：`F-140`。
- 契约内容：路由器只转发请求，客户端断开时取消上游；adaptive policy 不向指标陈旧或不健康的后端发送新流量，不自动重试生成。
- 允许行为：采用已有配置选择缓存或实时负载策略；详情以 router README 为准。
- 禁止行为：将客户端会话标识当作认证或将估算队列当作 GPU 利用率。
- 失败语义：不可用后端排除选择，调用错误按已有 HTTP 路径返回。
- 不变量：不同任务保持分离，同一任务工具轮可保留会话身份。
- 边界条件：路由统计仅覆盖自身观测，直接访问后端的调用不计入本地请求计数。
- 证据：`router/README.md`、`router/routing_identity.py`、`router/rank_proxy.py`、`router/adaptive_router.py`、`tests/test_routing_identity.py`。
- 变更规则：路由行为修改须同步 router 文档、测试和本契约。
- 来源：已有两节点 router 实现。
