"""Load the complete tokenizer module with only heavyweight imports stubbed."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


ROOT = Path(__file__).parents[1]
TOKENIZERS = ROOT / "patches/files/vllm/tokenizers"


class FakeTokenizer:
    def encode(self, text, **kwargs):
        return [ord(character) for character in text]

    def get_added_vocab(self):
        return {"special": 100}


@pytest.fixture(scope="module")
def tokenizer_module():
    package_name = "test_responses_deepseek_tokenizers"
    modules = {name: ModuleType(name) for name in (
        "transformers", "vllm", "vllm.entrypoints", "vllm.entrypoints.chat_utils",
        package_name, package_name + ".hf", package_name + ".protocol",
    )}
    modules[package_name].__path__ = [str(TOKENIZERS)]
    modules["transformers"].TokenizersBackend = FakeTokenizer
    modules["vllm.entrypoints.chat_utils"].ChatCompletionMessageParam = dict
    modules[package_name + ".hf"].HfTokenizer = FakeTokenizer
    modules[package_name + ".hf"].get_cached_tokenizer = lambda tokenizer: tokenizer
    modules[package_name + ".protocol"].TokenizerLike = type("TokenizerLike", (), {})
    name = package_name + ".deepseek_v41"
    spec = importlib.util.spec_from_file_location(name, TOKENIZERS / "deepseek_v41.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        # The sibling prompt encoder is imported and executed from its real file.
        spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("role,part_type", [
    ("user", "input_text"), ("developer", "input_text"), ("assistant", "output_text"),
    ("system", "text"), ("tool", "text"),
])
def test_normalizes_standard_text_parts(tokenizer_module, role, part_type):
    messages = [{"role": role, "content": [{"type": part_type, "text": "first"}, {"type": part_type, "text": "second"}]}]
    original = copy.deepcopy(messages)
    result = tokenizer_module._normalize_messages(messages)
    assert result == [{"role": role, "content": "first\n\nsecond"}]
    assert messages == original


def test_preserves_images_tool_identity_reasoning_and_original_input(tokenizer_module):
    messages = [
        {"role": "user", "content": [
            {"type": "text", "text": "legacy"}, {"type": "input_text", "text": "standard"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA=="}},
            {"type": "input_image", "image_url": "data:image/png;base64,AA=="},
            {"type": "image_pil", "image": "fixture"},
        ]},
        {"role": "assistant", "reasoning": "thought", "content": [{"type": "output_text", "text": ""}],
         "tool_calls": [{"id": "call_exact", "type": "function", "function": {"name": "echo", "arguments": '{"n":9007199254740993}'}}]},
        {"role": "tool", "tool_call_id": "call_exact", "content": "{\"success\":true}"},
        {"role": "assistant", "content": None},
    ]
    original = copy.deepcopy(messages)
    result = tokenizer_module._normalize_messages(messages)
    assert result[0]["content"] == "\n\n".join(["legacy", "standard"] + [tokenizer_module.IMAGE_PLACEHOLDER] * 3)
    assert result[1]["reasoning_content"] == "thought"
    assert result[1]["tool_calls"] == original[1]["tool_calls"]
    assert result[1]["tool_calls"] is not messages[1]["tool_calls"]
    assert result[2]["tool_call_id"] == "call_exact"
    assert result[2]["content"] == '{"success":true}'
    assert result[3]["content"] is None
    assert messages == original


def test_legacy_strings_empty_parts_and_missing_text_remain_supported(tokenizer_module):
    messages = [{"role": "user", "content": "raw"}, {"role": "assistant", "content": []},
                {"role": "developer", "content": [{"type": "input_text"}]}]
    assert tokenizer_module._normalize_messages(messages) == [
        {"role": "user", "content": "raw"}, {"role": "assistant", "content": ""},
        {"role": "developer", "content": ""},
    ]


@pytest.mark.parametrize("part_type", ["input_audio", "refusal", "arbitrary"])
def test_unknown_content_types_still_fail_closed(tokenizer_module, part_type):
    messages = [{"role": "user", "content": [{"type": part_type, "text": "value"}]}]
    with pytest.raises(ValueError, match="supports text and image content only"):
        tokenizer_module._normalize_messages(messages)


def test_invalid_role_still_fails_closed(tokenizer_module):
    with pytest.raises(ValueError, match="Invalid role"):
        tokenizer_module._normalize_messages([{"role": "unknown", "content": "value"}])


def test_real_template_encodes_typed_tool_continuation_without_mutating_input(tokenizer_module):
    wrapped = tokenizer_module.get_deepseek_v41_tokenizer(FakeTokenizer())
    typed = [
        {"role": "developer", "content": [{"type": "input_text", "text": "Use the result."}]},
        {"role": "user", "content": [{"type": "input_text", "text": "Find an example."}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Checking."}],
         "tool_calls": [{"id": "call_exact", "type": "function", "function": {"name": "echo", "arguments": '{"n":9007199254740993}'}}]},
        {"role": "tool", "tool_call_id": "call_exact", "content": '{"success":true}'},
    ]
    original = copy.deepcopy(typed)
    plain = copy.deepcopy(typed)
    for message in plain:
        if isinstance(message["content"], list):
            message["content"] = "\n\n".join(block["text"] for block in message["content"])
    tools = [{"type": "function", "function": {"name": "echo", "parameters": {"type": "object"}}}]
    expected = wrapped.apply_chat_template(plain, tools=tools, tokenize=False, thinking=False)
    actual = wrapped.apply_chat_template(typed, tools=tools, tokenize=False, thinking=False)
    assert actual == expected
    assert "Find an example." in actual and "Checking." in actual
    assert "9007199254740993" in actual and "success" in actual
    assert wrapped.apply_chat_template(typed, tools=tools, thinking=False) == wrapped.encode(actual)
    assert typed == original


def test_tokenizer_payload_hash_matches_install_manifest():
    manifest = json.loads((ROOT / "patches/manifest.json").read_text())
    entry = next(item for item in manifest["files"] if item["target"] == "vllm/tokenizers/deepseek_v41.py")
    assert entry["before"] == "d6e9cbce7c5f127819452fa5d03dd4f22ad9f136dd202a54b5b31fe42402cae2"
    assert hashlib.sha256((TOKENIZERS / "deepseek_v41.py").read_bytes()).hexdigest() == entry["after"]
