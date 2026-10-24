# API

本仓库继续提供 vLLM 原生 OpenAI HTTP 接口。此次修复针对原生
`POST /v1/responses` 的非 Harmony 流式输出，未将请求转为 Chat，未改变
AIGateway 的工具选择、授权、调用身份校验或模型绑定能力。

## Native Responses function stream

以下为直接连接推理节点的最小函数声明；使用实际节点地址和其公开的模型名。
节点若启用认证，由调用环境安全传入凭证，不在示例或验收记录中展开。

```bash
curl -N -sS http://127.0.0.1:8083/v1/responses \
  -H 'Content-Type: application/json' \
  --data '{
    "model": "deepseek-ai/DeepSeek-V4.1-Flash",
    "input": "请调用 get_weather 查询北京天气。",
    "stream": true,
    "tools": [{
      "type": "function",
      "name": "get_weather",
      "description": "查询城市天气",
      "parameters": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"]
      }
    }],
    "tool_choice": {"type": "function", "name": "get_weather"}
  }'
```

原生推理节点只产生 `function_call`，由调用者执行函数；它不在这里连接
FOFA 或执行 MCP。网关对外的 hosted-tool 类型仍由网关管理，不把 MCP
连接地址暴露给客户端。

## Output identity

- `response.output_item.added`、参数 delta/done 和
  `response.output_item.done` 使用同一输出项身份。
- 最终 `response.completed.response.output` 复用已完成的流式项及顺序，
  保留 `id`、函数 `call_id`、名称、参数、文本及对应 logprobs。
- 相同函数并发调用仍是不同 invocation，不能按函数名称匹配结果。
- 即使没有参数 delta，每个函数也应先发参数 done，再发输出项 done。
- reasoning、普通消息与函数调用保持各自类型；仅空白的已完成消息不丢弃。
- usage 保持原 runtime 计算，不能按 delta 重复累计。

## Returning a tool result

取当前响应实际返回的 ID，而非自行构造或按工具名查找：

```json
{
  "model": "deepseek-ai/DeepSeek-V4.1-Flash",
  "previous_response_id": "<response.id>",
  "input": [{
    "type": "function_call_output",
    "call_id": "<function_call.call_id>",
    "output": "{\"temperature\": 22}"
  }],
  "stream": true
}
```

续接仍要求节点开启并保有既有 response store。没有存储时，调用者须按
该 runtime 支持的显式历史方式发送调用项及结果。补丁不新增跨节点状态复制，
也不改变既有进程重启、过期或负载均衡限制。

## Unchanged boundaries

非流式 Responses、Chat Completions、Harmony、模型错误和 HTTP 鉴权保持
原路径。现有 `[DONE]`、终态和取消行为以运行时对应端点为准，不通过网关
兼容模式修复身份。验收范围和失败判定见 [TESTING](TESTING.md)。

相关契约：`C-002`、`C-003`；功能：`F-130`。
