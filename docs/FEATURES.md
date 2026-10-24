# Feature List

- `F-000` Inference deployment fork
  - `F-100` Deployment and operation
    - `F-110` Existing SM80 model deployment
    - `F-120` Reviewed source-patch installation
    - `F-130` Native Responses stream identity
    - `F-131` Standard typed text history normalization
    - `F-140` Optional multi-node routing
    - `F-150` Verification and benchmark clients

## F-110 Existing SM80 model deployment

- 目的：从本地已有权重启动 DeepSeek V4.1 Flash。
- 使用者：推理服务运维者。
- 入口：`python launch.py MODEL_DIRECTORY`、容器构建。
- 输入：已有模型目录、容器镜像、端口和显存比例；模型目录必须含配置文件。
- 输出：带既有 SM80 优化及工具/推理解析器的 vLLM 服务。
- 前置条件：Docker、可用 GPU、模型权重及镜像依赖。
- 失败表现：非法目录、名称或显存比例在启动前失败；容器失败保留其日志。
- 关联契约：`C-001`、`C-004`。
- 证据：`launch.py`、`Dockerfile`、`config/serve.json`、`config/environment.json`。

## F-120 Reviewed source-patch installation

- 目的：仅将审查过的补丁装入已知运行时。
- 使用者：镜像构建者和运维者。
- 入口：基础补丁安装器及 Responses 身份补丁安装器。
- 输入：安装目标与匹配的源文件 SHA256；Responses profile 要求三个文件整体匹配。
- 输出：已知补丁内容；重复安装相同版本保持一致。
- 前置条件：完整匹配的源版本、目标写权限及安装器资源。
- 失败表现：未知、混合或损坏内容拒绝安装，不推断相近版本可用。
- 关联契约：`C-001`、`C-003`。
- 证据：`patches/install.py`、`patches/manifest.json`、`patches/responses_identity/install.py`、`tests/test_responses_identity_installer.py`、`tests/test_responses_identity_runtime.py`。

## F-130 Native Responses stream identity

- 目的：使客户端收到的函数调用与最终响应及后续工具结果指向同一次调用。
- 使用者：原生 Responses API 客户端及网关。
- 入口：`POST /v1/responses`，`stream:true`。
- 输入：原生输入、函数定义、流式选项及既有续接参数。
- 输出：有序 SSE；已完成的输出项在最终响应中保留相同身份与内容。
- 前置条件：受支持源 profile 已安装，模型与解析器可处理相应请求。
- 失败表现：不支持的源版本拒绝安装；HTTP/生成错误沿用运行时原有语义。
- 关联契约：`C-001`、`C-002`、`C-003`。
- 证据：`patches/responses_identity/install.py`、`tests/test_responses_identity_installer.py`、`tests/test_responses_identity_runtime.py`。

## F-131 Standard typed text history normalization

- 目的：让 A100 custom tokenizer 接受标准 Responses 文本历史并继续工具调用。
- 使用者：原生 Responses 客户端及使用类型化历史续写的网关。
- 入口：`POST /v1/responses` 的 typed input、历史回放与 `function_call_output` 续写。
- 输入：文本块 `text`、`input_text`、`output_text`；保留既有字符串及图像处理边界。
- 输出：按原顺序归一化的文本，客户端传入对象不被就地修改。
- 前置条件：A100 安装对应 tokenizer 补丁；H100 既有 tokenizer 已接受三种文本类型，不替换其文件。
- 失败表现：未知内容类型仍明确拒绝；第一轮函数或远端业务成功不能代替续写成功。
- 关联契约：`C-001`、`C-003`、`C-006`。
- 证据：`patches/files/vllm/tokenizers/deepseek_v41.py`、`patches/manifest.json`、`tests/test_deepseek_v41_text_content.py`。

## F-140 Optional multi-node routing

- 目的：在既有节点间按缓存/rank 或实时后端指标分配流量。
- 使用者：部署多个推理节点的运维者。
- 入口：router 启动器、adaptive router、`/workers` 和 `/state`。
- 输入：已有 tokenizer 路径、节点 URL 和路由配置。
- 输出：既有 OpenAI 请求转发、流式返回与路由状态。
- 前置条件：独立 router 依赖及可访问的后端。
- 失败表现：无新鲜健康指标的后端不接新请求；生成不自动重试。
- 关联契约：`C-005`。
- 证据：`router/launch.py`、`router/adaptive_router.py`、`router/rank_proxy.py`、`tests/test_routing_identity.py`。

## F-150 Verification and benchmark clients

- 目的：区分补丁回归、真实部署验收与历史性能结果。
- 使用者：开发者、发布者和性能研究者。
- 入口：测试集、文档检查器及 benchmarks 中既有脚本。
- 输入：确定性测试数据或显式指定的真实 endpoint/工作负载。
- 输出：断言结果、运行收据及有清晰口径的性能报告。
- 前置条件：CPU 测试依赖；GPU/网络验收另需对应服务与授权。
- 失败表现：失败保留失败结论；禁止用健康检查或历史成绩代替当前工具调用验证。
- 关联契约：`C-003`、`C-004`。
- 证据：`tests/test_responses_identity_installer.py`、`scripts/docs_check.py`、`benchmarks/README.md`、`benchmarks/evidence-manifest.json`。
