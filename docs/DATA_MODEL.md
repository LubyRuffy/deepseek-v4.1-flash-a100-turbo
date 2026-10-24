# Data Model

本 fork 不创建业务数据库或新增凭证存储。运行配置、补丁 profile 和验收结果为
文件；vLLM 自身 response store 的生命周期及持久性仍由已部署运行时管理。

| Data | Authority and contents | Lifecycle |
|---|---|---|
| Source profiles | `patches/responses_identity/profiles.json`；三个源码模块的 before/after SHA256 | 随补丁版本发布；不同 profile 不混用 |
| Patch payloads | 同目录 unified diff；对精确源码计算的修复 | 哈希及 Python compile 均成功后安装 |
| Runtime output items | vLLM Responses context 持有已完成的原生输出对象 | 当前响应终态/既有 response store 路径 |
| Launch configuration | `config/serve.json`、`config/environment.json` | 由部署者配置；不是密钥存储 |
| Acceptance receipts | 安全的版本/哈希、请求 ID、事件统计和实际执行结论 | 运维证据，不能代替 API 历史查询权威 |
| Historical benchmarks | `benchmarks/evidence-manifest.json` 及对应报告 | 保留原始硬件、版本及测试口径 |

本次修复不为响应重建新的 `id/call_id`，不复制跨节点存储，不迁移既有响应。
续接使用服务器最终保存的同一组完成输出对象，见 `C-002`。补丁回滚恢复旧代码，
不重写已发生的响应历史；重启后的 store 可用性按原有运行时配置判断。

关联功能：`F-120`、`F-130`、`F-150`；契约：`C-001`、`C-002`、`C-004`。
