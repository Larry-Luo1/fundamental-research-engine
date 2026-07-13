from __future__ import annotations

import os
import subprocess
import unittest
import unittest.mock

from fundamental_research_engine.adapters import (
    AdapterError,
    ClaudeAdapter,
    ClaudeCliAdapter,
    CodexCliAdapter,
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


class ClaudeCliAdapterTest(unittest.TestCase):
    def test_complete_invokes_claude_print_mode_and_returns_stdout(self) -> None:
        captured = {}

        def fake_runner(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0, stdout='{"mechanism": "ok"}\n', stderr="")

        with unittest.mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            adapter = ClaudeCliAdapter(model="sonnet", runner=fake_runner)
            result = adapter.complete("draft the mechanism stage")

        self.assertEqual(result, '{"mechanism": "ok"}')
        self.assertEqual(captured["argv"], ["claude", "-p", "--model", "sonnet", "draft the mechanism stage"])
        self.assertTrue(captured["kwargs"]["capture_output"])
        self.assertTrue(captured["kwargs"]["text"])
        self.assertNotIn("ANTHROPIC_API_KEY", captured["kwargs"]["env"])

    def test_command_can_be_overridden_from_environment(self) -> None:
        captured = {}

        def fake_runner(argv, **kwargs):
            captured["argv"] = argv
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        with unittest.mock.patch.dict(os.environ, {"CLAUDE_CLI_CMD": "custom-claude --print"}, clear=False):
            adapter = ClaudeCliAdapter(runner=fake_runner)
            self.assertEqual(adapter.complete("prompt"), "ok")

        self.assertEqual(captured["argv"], ["custom-claude", "--print", "prompt"])

    def test_nonzero_exit_raises_adapter_error(self) -> None:
        def fake_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not logged in")

        adapter = ClaudeCliAdapter(runner=fake_runner)
        with self.assertRaisesRegex(AdapterError, "not logged in"):
            adapter.complete("prompt")

    def test_empty_stdout_raises_adapter_error(self) -> None:
        def fake_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        adapter = ClaudeCliAdapter(runner=fake_runner)
        with self.assertRaisesRegex(AdapterError, "empty response"):
            adapter.complete("prompt")


class CodexCliAdapterTest(unittest.TestCase):
    @staticmethod
    def _runner_writing(message: str, returncode: int = 0, stderr: str = ""):
        captured = {}

        def fake_runner(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            if "--output-last-message" in argv and returncode == 0:
                out_path = argv[argv.index("--output-last-message") + 1]
                with open(out_path, "w", encoding="utf-8") as handle:
                    handle.write(message)
            return subprocess.CompletedProcess(argv, returncode, stdout="progress noise", stderr=stderr)

        return fake_runner, captured

    def test_complete_runs_codex_exec_and_reads_last_message_file(self) -> None:
        fake_runner, captured = self._runner_writing('{"mechanism": "ok"}\n')
        with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-should-be-stripped"}):
            adapter = CodexCliAdapter(model="gpt-5-codex", runner=fake_runner)
            result = adapter.complete("draft the mechanism stage")

        self.assertEqual(result, '{"mechanism": "ok"}')
        argv = captured["argv"]
        self.assertEqual(argv[:4], ["codex", "exec", "--model", "gpt-5-codex"])
        for flag in ("--skip-git-repo-check", "--ephemeral", "--output-last-message"):
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("--sandbox") + 1], "read-only")
        self.assertEqual(argv[-1], "-")
        # prompt goes in on stdin, not argv
        self.assertEqual(captured["kwargs"]["input"], "draft the mechanism stage")
        self.assertNotIn("draft the mechanism stage", argv)
        # subscription login must win over any ambient API key
        self.assertNotIn("OPENAI_API_KEY", captured["kwargs"]["env"])

    def test_command_can_be_overridden_from_environment(self) -> None:
        fake_runner, captured = self._runner_writing("ok")
        with unittest.mock.patch.dict(os.environ, {"CODEX_CLI_CMD": "custom-codex run"}, clear=False):
            adapter = CodexCliAdapter(runner=fake_runner)
            self.assertEqual(adapter.complete("prompt"), "ok")
        self.assertEqual(captured["argv"][:2], ["custom-codex", "run"])

    def test_nonzero_exit_raises_adapter_error(self) -> None:
        fake_runner, _ = self._runner_writing("", returncode=1, stderr="not logged in")
        adapter = CodexCliAdapter(runner=fake_runner)
        with self.assertRaisesRegex(AdapterError, "not logged in"):
            adapter.complete("prompt")

    def test_missing_output_file_raises_adapter_error(self) -> None:
        def fake_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, stdout="noise", stderr="")

        adapter = CodexCliAdapter(runner=fake_runner)
        with self.assertRaisesRegex(AdapterError, "empty response"):
            adapter.complete("prompt")


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

    def test_claude_cli_adapter_accepts_optional_model_name(self) -> None:
        adapter = get_adapter("claude-cli", None)
        self.assertIsInstance(adapter, ClaudeCliAdapter)
        self.assertIsNone(adapter.model)

        named = get_adapter("claude-cli", "sonnet")
        self.assertIsInstance(named, ClaudeCliAdapter)
        self.assertEqual(named.model, "sonnet")

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
