# API

本仓库继续提供 vLLM 原生 OpenAI HTTP 接口。此次修复针对原生
`POST /v1/responses` 的非 Harmony 流式输出及 A100 标准文本历史归一化，未将请求转为 Chat，未改变
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

## Standard typed text history

A100 custom tokenizer 接受 `text`、`input_text`、`output_text` 三种文本块，
保留既有字符串内容与文本顺序。H100 原 tokenizer 已支持这三种类型，本次
不替换其 tokenizer 或改变其推理设置。客户端无需将标准 typed input 改为
字符串或非标准文本块来绕过 400。

标准首轮 input 可以采用：

```json
[
  {
    "role": "user",
    "content": [{"type": "input_text", "text": "请调用 get_weather 查询北京天气。"}]
  }
]
```

没有 response store 时，显式历史续写应保留原 typed input，以及首轮实际
返回的完整输出项；其中 assistant 的 `output_text` 不能在 tokenizer 中被
误判为未知内容。以下构造展示调用关联，`first_request` 使用上面的 typed
input，`first_response` 是完整 SSE 终态中解析出的 response：

```python
from copy import deepcopy

call = next(item for item in first_response["output"] if item["type"] == "function_call")
continuation = {
    "model": first_request["model"],
    "input": [
        *deepcopy(first_request["input"]),
        *deepcopy(first_response["output"]),
        {
            "type": "function_call_output",
            "call_id": call["call_id"],
            "output": "{\"temperature\":22}",
        },
    ],
    "tools": deepcopy(first_request["tools"]),
    "tool_choice": "auto",
    "stream": True,
}
```

多调用时为每个实际 `call_id` 返回对应结果。输入归一化只处理副本，不就地
修改原消息或嵌套块；未知内容类型仍明确拒绝，图像处理保留原有规则。
首次函数生成和远端工具执行成功，只证明该轮成功；后续 typed history
续写和最终 SSE 也成功后，才算完整工具链通过。

## Unchanged boundaries

非流式 Responses 最终输出、Chat Completions、Harmony、模型错误和 HTTP 鉴权保持
原路径；A100 的标准文本类型支持在共享输入归一化处生效。现有 `[DONE]`、终态
和取消行为以运行时对应端点为准，不通过网关兼容模式修复身份。验收范围和失败判定见 [TESTING](TESTING.md)。

相关契约：`C-002`、`C-003`、`C-006`；功能：`F-130`、`F-131`。
