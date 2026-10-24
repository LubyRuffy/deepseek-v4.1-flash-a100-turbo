"""Exercise real vLLM modules without an engine or network.

Run with the serving environment's Python. Set RESPONSES_IDENTITY_MODULE_DIR to
an isolated directory of staged Responses modules to test before installation.
"""

import asyncio
import importlib
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


@unittest.skipUnless(importlib.util.find_spec("vllm"), "requires the installed vLLM Python environment")
class ResponsesIdentityRuntimeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            package = importlib.import_module("vllm.entrypoints.openai.responses")
        except ModuleNotFoundError as error:
            if error.name == "vllm.entrypoints.openai.responses":
                raise unittest.SkipTest("installed vLLM predates the Responses module") from error
            raise
        overlay = os.environ.get("RESPONSES_IDENTITY_MODULE_DIR")
        if overlay:
            package.__path__.insert(0, str(Path(overlay).resolve()))
            for name in ("serving", "streaming_events", "context"):
                sys.modules.pop(package.__name__ + "." + name, None)
        cls.serving_module = importlib.import_module(package.__name__ + ".serving")
        cls.context_module = importlib.import_module(package.__name__ + ".context")
        cls.protocol = importlib.import_module(package.__name__ + ".protocol")
        cls.delta_module = importlib.import_module("vllm.entrypoints.generate.base.protocol")
        cls.outputs = importlib.import_module("vllm.outputs")
        cls.sampling = importlib.import_module("vllm.sampling_params")
        cls.logprobs = importlib.import_module("vllm.logprobs")

    def make_serving(self):
        serving = self.serving_module.OpenAIServingResponses.__new__(self.serving_module.OpenAIServingResponses)
        serving.parser = MagicMock()
        serving.enable_auto_tools = True
        serving.enable_log_outputs = True
        serving.request_logger = MagicMock()
        serving.return_tokens_as_token_ids = False
        serving.enable_per_request_metrics = False
        serving.use_harmony = False
        serving.tool_server = None
        serving.response_store = {}
        serving.response_store_lock = asyncio.Lock()
        return serving

    def call(self, index, call_id, arguments):
        return self.delta_module.DeltaToolCall(
            index=index, id=call_id,
            function=self.delta_module.DeltaFunctionCall(name="echo", arguments=arguments),
        )

    async def stream_case(self, deltas, *, include_logprobs=False):
        serving = self.make_serving()
        parser = MagicMock()
        parser.parse_delta.side_effect = deltas
        parser.count_reasoning_tokens.return_value = 1
        # If the old path reparses, produce deliberately different identities.
        parser.parse.return_value = ("reparsed thought", "reparsed text", [
            SimpleNamespace(id="reparsed-call", name="echo", arguments="{}")
        ])
        context = self.context_module.SimpleContext(response_parser=parser)
        request = self.protocol.ResponsesRequest(
            input="test", stream=True, store=True,
            tools=[{"type": "function", "name": "echo", "parameters": {"type": "object"}}],
            include=["message.output_text.logprobs"] if include_logprobs else [],
        )

        async def generate():
            for index, _ in enumerate(deltas):
                token = index + 10
                output = self.outputs.CompletionOutput(
                    index=0, text=f"part-{index}", token_ids=[token],
                    cumulative_logprob=0.0,
                    logprobs=[{token: self.logprobs.Logprob(logprob=-0.5, decoded_token=f"part-{index}")}],
                    finish_reason="stop" if index == len(deltas) - 1 else None,
                    stop_reason=None,
                )
                context.append_output(self.outputs.RequestOutput(
                    request_id="test", prompt="test", prompt_token_ids=[7, 8],
                    prompt_logprobs=None, outputs=[output],
                    finished=index == len(deltas) - 1, num_cached_tokens=0,
                ))
                yield context

        with patch.object(self.serving_module.envs, "VLLM_USE_EXPERIMENTAL_PARSER_CONTEXT", False):
            events = [event async for event in serving.responses_stream_generator(
                request=request, sampling_params=self.sampling.SamplingParams(max_tokens=64),
                result_generator=generate(), context=context, model_name="test-model",
                tokenizer=MagicMock(),
                request_metadata=self.delta_module.RequestResponseMetadata(request_id="test"),
            )]
        done = [e.item for e in events if e.type == "response.output_item.done"]
        final = events[-1].response
        self.assertEqual(events[-1].type, "response.completed")
        self.assertEqual(final.output, done)
        self.assertEqual(serving.response_store[final.id].output, done)
        self.assertEqual(final.usage.input_tokens, 2)
        self.assertEqual(final.usage.output_tokens, len(deltas))
        self.assertEqual(final.usage.total_tokens, len(deltas) + 2)
        self.assertEqual(final.usage.output_tokens_details.reasoning_tokens, 1)
        self.assertEqual([e.sequence_number for e in events], list(range(len(events))))
        parser.parse.assert_not_called()
        serving.request_logger.log_outputs.assert_called_once()
        self.assertTrue(serving.request_logger.log_outputs.call_args.kwargs["is_streaming"])
        added = {e.item.id: e.item for e in events if e.type == "response.output_item.added"}
        for item in done:
            self.assertIn(item.id, added)
            if item.type == "function_call":
                self.assertEqual(item.call_id, added[item.id].call_id)
                deltas_for_item = [e.delta for e in events if e.type == "response.function_call_arguments.delta" and e.item_id == item.id]
                self.assertEqual("".join(deltas_for_item), item.arguments)
                completed_args = [e for e in events if e.type == "response.function_call_arguments.done" and e.item_id == item.id]
                self.assertEqual(len(completed_args), 1)
                self.assertEqual(completed_args[0].arguments, item.arguments)
        return done, events

    async def test_same_name_calls_preserve_all_streamed_items_and_logprobs(self):
        delta = self.delta_module.DeltaMessage
        done, events = await self.stream_case([
            delta(reasoning="thought"), delta(content="\n\n"),
            delta(tool_calls=[self.call(0, "parser-first", '{"value":')]),
            delta(tool_calls=[self.call(0, None, '9007199254740993}')]),
            delta(tool_calls=[self.call(1, "parser-second", '{"value":2}')]),
        ], include_logprobs=True)
        self.assertEqual([item.type for item in done], ["reasoning", "message", "function_call", "function_call"])
        calls = [item for item in done if item.type == "function_call"]
        self.assertEqual([item.call_id for item in calls], ["parser-first", "parser-second"])
        self.assertNotEqual(calls[0].id, calls[1].id)
        self.assertEqual(done[1].content[0].text, "\n\n")
        self.assertEqual(len(done[1].content[0].logprobs), 1)
        self.assertEqual(sum(len(e.logprobs) for e in events if e.type == "response.output_text.delta"), 1)

    async def test_zero_argument_call_without_deltas_has_done_event(self):
        done, _ = await self.stream_case([
            self.delta_module.DeltaMessage(tool_calls=[self.call(0, None, None)])
        ])
        self.assertEqual(len(done), 1)
        self.assertTrue(done[0].call_id)
        self.assertEqual(done[0].arguments, "")

    async def test_plain_text_retains_ids_logprobs_and_usage(self):
        done, _ = await self.stream_case([
            self.delta_module.DeltaMessage(content="Hello"),
            self.delta_module.DeltaMessage(content="!"),
        ], include_logprobs=True)
        self.assertEqual(len(done), 1)
        self.assertEqual(done[0].content[0].text, "Hello!")
        self.assertEqual(len(done[0].content[0].logprobs), 2)

    async def test_nonstreaming_keeps_full_parser_and_logging(self):
        serving = self.make_serving()
        parser = MagicMock()
        parser.parse.return_value = (None, "Hello", [])
        parser.count_reasoning_tokens.return_value = 0
        context = self.context_module.SimpleContext(response_parser=parser)
        context.append_output(self.outputs.RequestOutput(
            request_id="test", prompt="test", prompt_token_ids=[7, 8], prompt_logprobs=None,
            outputs=[self.outputs.CompletionOutput(index=0, text="Hello", token_ids=[10], cumulative_logprob=0.0, logprobs=None, finish_reason="stop", stop_reason=None)],
            finished=True, num_cached_tokens=0,
        ))

        async def empty():
            if False:
                yield

        final = await serving.responses_full_generator(
            request=self.protocol.ResponsesRequest(input="test", store=False),
            sampling_params=self.sampling.SamplingParams(max_tokens=64),
            result_generator=empty(), context=context, model_name="test-model", tokenizer=MagicMock(),
            request_metadata=self.delta_module.RequestResponseMetadata(request_id="test"),
        )
        parser.parse.assert_called_once()
        self.assertEqual(final.output[0].content[0].text, "Hello")
        self.assertEqual(final.usage.total_tokens, 3)
        self.assertFalse(serving.request_logger.log_outputs.call_args.kwargs["is_streaming"])


if __name__ == "__main__":
    unittest.main()
