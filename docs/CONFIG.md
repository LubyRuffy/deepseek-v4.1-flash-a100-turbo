# Configuration

## Existing deployment configuration

| File | Purpose | Boundary |
|---|---|---|
| `config/serve.json` | vLLM argv: model name, TP/DP, context, parser, cache, shutdown | Historical SM80 deployment defaults; do not copy into an unrelated H100 service |
| `config/environment.json` | Offline mode and existing CUDA/kernel environment | Not a secret store |
| `patches/manifest.json` | Pinned vendor image and existing optimization before/after hashes | Not a general version matcher |
| `router/config.example.json` | Optional router nodes/tokenizer settings | Copy and configure explicitly; do not commit credentials |
| `patches/responses_identity/profiles.json` | Exact Responses module hashes for H100/A100 | Three modules match one complete profile |

本次补丁不新增服务端模型参数、认证格式、环境变量或网关兼容开关。保留实际
节点原有模型挂载、TP/DP、parser、推理设置和 response store 配置。

## Supported source profiles

- H100：已采集的 vLLM `0.31.0` 运行源码 profile。
- A100：已采集的 vLLM `0.13.0` backport 运行源码 profile。

版本字符串用于说明来源，**三个目标文件 SHA256 才是安装门禁**。即使包版本
相同，任何未登记的本地改动也拒绝安装。三个文件都已为同一 profile 的 after
内容时，重复安装为 no-op；before/after 混合不视为成功安装。

profiles 只声明本次安装兼容性，不声明 H100/A100 的性能或其他模型兼容性。
升级 vLLM 后需要重新采集源码、审查差异、增加 profile 并验证，不能沿用旧
哈希或关闭校验。

## Secrets and receipts

补丁不读取 API key 或创建明文凭证配置。验收凭证从已授权环境传入，输出只保留
安全的节点标签、版本、镜像身份、源哈希、请求 ID、事件/调用计数、错误类别和
耗时。不得写入 Authorization、Cookie、完整业务结果或账户数据。

配置关联 `F-110`、`F-120`、`F-140`，契约 `C-001`、`C-003`、`C-005`。
