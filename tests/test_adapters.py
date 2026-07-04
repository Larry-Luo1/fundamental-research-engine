from __future__ import annotations

import unittest

from fundamental_research_engine.adapters import (
    AdapterError,
    ClaudeAdapter,
    DeepSeekAdapter,
    ManualAdapter,
    ManualCompletionPending,
    OpenAIAdapter,
    get_adapter,
)


class ManualAdapterTest(unittest.TestCase):
    def test_complete_raises_with_prompt_attached(self) -> None:
        adapter = ManualAdapter()
        with self.assertRaises(ManualCompletionPending) as ctx:
            adapter.complete("draft this stage")
        self.assertEqual(ctx.exception.prompt, "draft this stage")


class OpenAIAdapterTest(unittest.TestCase):
    def test_complete_sends_expected_request_and_parses_response(self) -> None:
        captured = {}

        def fake_transport(url, headers, payload):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = payload
            return {"choices": [{"message": {"content": '{"mechanism": "because reasons"}'}}]}

        adapter = OpenAIAdapter(model="gpt-test", api_key="sk-test", transport=fake_transport)
        result = adapter.complete("draft the mechanism stage")

        self.assertEqual(result, '{"mechanism": "because reasons"}')
        self.assertEqual(captured["url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(captured["payload"]["model"], "gpt-test")
        self.assertEqual(captured["payload"]["messages"][0]["content"], "draft the mechanism stage")

    def test_missing_api_key_raises(self) -> None:
        adapter = OpenAIAdapter(model="gpt-test", api_key=None, transport=lambda *a: {})
        with self.assertRaises(AdapterError):
            adapter.complete("prompt")

    def test_unexpected_response_shape_raises(self) -> None:
        adapter = OpenAIAdapter(model="gpt-test", api_key="sk-test", transport=lambda *a: {"unexpected": True})
        with self.assertRaises(AdapterError):
            adapter.complete("prompt")


class ClaudeAdapterTest(unittest.TestCase):
    def test_complete_sends_expected_request_and_parses_response(self) -> None:
        captured = {}

        def fake_transport(url, headers, payload):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = payload
            return {"content": [{"type": "text", "text": '{"mechanism": "because reasons"}'}]}

        adapter = ClaudeAdapter(model="claude-test", api_key="sk-ant-test", transport=fake_transport)
        result = adapter.complete("draft the mechanism stage")

        self.assertEqual(result, '{"mechanism": "because reasons"}')
        self.assertEqual(captured["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(captured["headers"]["x-api-key"], "sk-ant-test")
        self.assertEqual(captured["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(captured["payload"]["model"], "claude-test")

    def test_missing_api_key_raises(self) -> None:
        adapter = ClaudeAdapter(model="claude-test", api_key=None, transport=lambda *a: {})
        with self.assertRaises(AdapterError):
            adapter.complete("prompt")

    def test_default_max_tokens_has_headroom(self) -> None:
        captured = {}

        def fake_transport(url, headers, payload):
            captured["payload"] = payload
            return {"content": [{"type": "text", "text": "ok"}]}

        adapter = ClaudeAdapter(model="claude-test", api_key="sk-ant-test", transport=fake_transport)
        adapter.complete("prompt")
        self.assertEqual(captured["payload"]["max_tokens"], 16000)

    def test_concatenates_multiple_text_blocks(self) -> None:
        def fake_transport(url, headers, payload):
            return {"content": [{"type": "text", "text": "part one "}, {"type": "text", "text": "part two"}]}

        adapter = ClaudeAdapter(model="claude-test", api_key="sk-ant-test", transport=fake_transport)
        self.assertEqual(adapter.complete("prompt"), "part one part two")


class DeepSeekAdapterTest(unittest.TestCase):
    def test_complete_sends_expected_request_and_parses_response(self) -> None:
        captured = {}

        def fake_transport(url, headers, payload):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = payload
            return {"choices": [{"message": {"content": '{"mechanism": "because reasons"}'}}]}

        adapter = DeepSeekAdapter(model="deepseek-v4-pro", api_key="sk-test", transport=fake_transport)
        result = adapter.complete("draft the mechanism stage")

        self.assertEqual(result, '{"mechanism": "because reasons"}')
        self.assertEqual(captured["url"], "https://api.deepseek.com/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer sk-test")
        self.assertEqual(captured["payload"]["model"], "deepseek-v4-pro")
        self.assertEqual(captured["payload"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})

    def test_missing_api_key_raises(self) -> None:
        adapter = DeepSeekAdapter(model="deepseek-v4-pro", api_key=None, transport=lambda *a: {})
        with self.assertRaises(AdapterError):
            adapter.complete("prompt")

    def test_unexpected_response_shape_raises(self) -> None:
        adapter = DeepSeekAdapter(model="deepseek-v4-pro", api_key="sk-test", transport=lambda *a: {"unexpected": True})
        with self.assertRaises(AdapterError):
            adapter.complete("prompt")


class GetAdapterTest(unittest.TestCase):
    def test_manual_adapter(self) -> None:
        self.assertIsInstance(get_adapter("manual"), ManualAdapter)

    def test_openai_adapter_requires_model_name(self) -> None:
        with self.assertRaises(ValueError):
            get_adapter("openai", None)
        adapter = get_adapter("openai", "gpt-test")
        self.assertIsInstance(adapter, OpenAIAdapter)
        self.assertEqual(adapter.model, "gpt-test")

    def test_claude_adapter_requires_model_name(self) -> None:
        with self.assertRaises(ValueError):
            get_adapter("claude", None)
        adapter = get_adapter("claude", "claude-test")
        self.assertIsInstance(adapter, ClaudeAdapter)
        self.assertEqual(adapter.model, "claude-test")

    def test_deepseek_adapter_requires_model_name(self) -> None:
        with self.assertRaises(ValueError):
            get_adapter("deepseek", None)
        adapter = get_adapter("deepseek", "deepseek-v4-pro")
        self.assertIsInstance(adapter, DeepSeekAdapter)
        self.assertEqual(adapter.model, "deepseek-v4-pro")

    def test_max_tokens_override_is_threaded(self) -> None:
        claude = get_adapter("claude", "claude-test", max_tokens=32000)
        self.assertIsInstance(claude, ClaudeAdapter)
        self.assertEqual(claude.max_tokens, 32000)

        openai = get_adapter("openai", "gpt-test", max_tokens=32000)
        self.assertIsInstance(openai, OpenAIAdapter)
        self.assertEqual(openai.max_tokens, 32000)

        deepseek = get_adapter("deepseek", "deepseek-v4-pro", max_tokens=32000)
        self.assertIsInstance(deepseek, DeepSeekAdapter)
        self.assertEqual(deepseek.max_tokens, 32000)

    def test_openai_omits_max_tokens_when_unset(self) -> None:
        captured = {}

        def fake_transport(url, headers, payload):
            captured["payload"] = payload
            return {"choices": [{"message": {"content": "ok"}}]}

        adapter = get_adapter("openai", "gpt-test")
        assert isinstance(adapter, OpenAIAdapter)
        adapter.api_key = "sk-test"
        adapter.transport = fake_transport
        adapter.complete("prompt")
        self.assertNotIn("max_tokens", captured["payload"])

    def test_unknown_adapter_raises(self) -> None:
        with self.assertRaises(ValueError):
            get_adapter("not-a-real-adapter")


if __name__ == "__main__":
    unittest.main()
