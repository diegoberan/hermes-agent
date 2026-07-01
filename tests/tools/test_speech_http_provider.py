"""Tests for the generic `type: http` TTS provider (Speech Router RFC, PR4).

Nothing here talks to a real network endpoint -- requests.post/get are
mocked directly (the module-level import inside _generate_http_tts is
deferred, but it binds to the same shared `requests` module object, so
patching "requests.post"/"requests.get" is visible regardless of where the
import happened).
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.tts_tool import (
    _generate_http_tts,
    _is_http_provider_config,
    _resolve_http_provider_config,
    text_to_speech_tool,
)


def _fake_response(status_code=200, content=b"RIFF....fake-wav-bytes", text=""):
    return SimpleNamespace(status_code=status_code, content=content, text=text)


class TestIsHttpProviderConfig:
    def test_requires_explicit_type_http(self):
        # url alone, no type, must NOT be treated as an http provider.
        assert _is_http_provider_config({"url": "https://example.com/speak"}) is False

    def test_valid_http_config(self):
        assert _is_http_provider_config({"type": "http", "url": "https://x/speak"}) is True

    def test_missing_url_is_invalid(self):
        assert _is_http_provider_config({"type": "http"}) is False

    def test_command_type_is_not_http(self):
        assert _is_http_provider_config({"type": "command", "command": "echo hi"}) is False

    def test_non_dict_is_invalid(self):
        assert _is_http_provider_config(None) is False


class TestResolveHttpProviderConfig:
    def test_builtin_names_are_never_http_providers(self):
        cfg = {"providers": {"edge": {"type": "http", "url": "https://x/speak"}}}
        assert _resolve_http_provider_config("edge", cfg) is None

    def test_unconfigured_name_returns_none(self):
        assert _resolve_http_provider_config("nope", {"providers": {}}) is None

    def test_declared_http_provider_resolves(self):
        cfg = {"providers": {"home-gpu": {"type": "http", "url": "https://x/speak"}}}
        resolved = _resolve_http_provider_config("home-gpu", cfg)
        assert resolved is not None
        assert resolved["url"] == "https://x/speak"


class TestGenerateHttpTts:
    def test_successful_post_writes_response_bytes(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {"type": "http", "url": "https://x/speak"}
        with patch("requests.post", return_value=_fake_response()) as mock_post:
            result_path = _generate_http_tts("hello", str(out), "home-gpu", config, {})
        assert result_path == str(out)
        assert out.read_bytes() == b"RIFF....fake-wav-bytes"
        mock_post.assert_called_once()

    def test_text_field_and_static_body_merged(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {
            "type": "http",
            "url": "https://x/speak",
            "body": {"token": "dotlocal-abc"},
        }
        with patch("requests.post", return_value=_fake_response()) as mock_post:
            _generate_http_tts("hello world", str(out), "home-gpu", config, {})
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"token": "dotlocal-abc", "text": "hello world"}

    def test_custom_text_field_name(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {"type": "http", "url": "https://x/speak", "text_field": "input"}
        with patch("requests.post", return_value=_fake_response()) as mock_post:
            _generate_http_tts("hi", str(out), "home-gpu", config, {})
        _, kwargs = mock_post.call_args
        assert kwargs["json"] == {"input": "hi"}

    def test_headers_passed_through(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {
            "type": "http",
            "url": "https://x/speak",
            "headers": {"CF-Access-Client-Id": "abc"},
        }
        with patch("requests.post", return_value=_fake_response()) as mock_post:
            _generate_http_tts("hi", str(out), "home-gpu", config, {})
        _, kwargs = mock_post.call_args
        assert kwargs["headers"] == {"CF-Access-Client-Id": "abc"}

    def test_get_method_uses_params_not_json(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {"type": "http", "url": "https://x/speak", "method": "get"}
        with patch("requests.get", return_value=_fake_response()) as mock_get:
            _generate_http_tts("hi", str(out), "home-gpu", config, {})
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"text": "hi"}

    def test_missing_url_raises_value_error(self, tmp_path):
        out = tmp_path / "reply.wav"
        with pytest.raises(ValueError):
            _generate_http_tts("hi", str(out), "home-gpu", {"type": "http"}, {})

    def test_non_2xx_status_raises_runtime_error(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {"type": "http", "url": "https://x/speak"}
        with patch("requests.post", return_value=_fake_response(status_code=500, text="boom")):
            with pytest.raises(RuntimeError, match="500"):
                _generate_http_tts("hi", str(out), "home-gpu", config, {})

    def test_empty_response_raises_runtime_error(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {"type": "http", "url": "https://x/speak"}
        with patch("requests.post", return_value=_fake_response(content=b"")):
            with pytest.raises(RuntimeError):
                _generate_http_tts("hi", str(out), "home-gpu", config, {})

    def test_timeout_raises_runtime_error(self, tmp_path):
        import requests as real_requests

        out = tmp_path / "reply.wav"
        config = {"type": "http", "url": "https://x/speak"}
        with patch("requests.post", side_effect=real_requests.exceptions.Timeout()):
            with pytest.raises(RuntimeError, match="timed out"):
                _generate_http_tts("hi", str(out), "home-gpu", config, {})


class TestHttpProviderEndToEnd:
    def test_text_to_speech_tool_uses_http_provider(self, tmp_path):
        cfg = {
            "provider": "home-gpu",
            "providers": {
                "home-gpu": {"type": "http", "url": "https://x/speak", "output_format": "wav"},
            },
        }
        out = tmp_path / "reply.wav"
        with patch("tools.tts_tool._load_tts_config", return_value=cfg), \
             patch("requests.post", return_value=_fake_response()):
            result_json = text_to_speech_tool(text="hi", output_path=str(out))
        result = json.loads(result_json)
        assert result["success"] is True
        assert result["provider"] == "home-gpu"

    def test_http_provider_failure_falls_back_to_next_in_chain(self, tmp_path):
        """PR3 + PR4 integration: an unreachable HTTP endpoint (e.g. desktop
        GPU offline) falls through to the next configured provider, same as
        a failing command provider already does."""
        cfg = {
            "provider": "home-gpu",
            "router": {"providers": ["home-gpu", "cloud-backup"]},
            "providers": {
                "home-gpu": {"type": "http", "url": "https://unreachable/speak"},
                "cloud-backup": {"type": "http", "url": "https://backup/speak"},
            },
        }
        out = tmp_path / "reply.wav"

        def fake_post(url, **kwargs):
            if "unreachable" in url:
                raise __import__("requests").exceptions.ConnectionError("refused")
            return _fake_response()

        with patch("tools.tts_tool._load_tts_config", return_value=cfg), \
             patch("requests.post", side_effect=fake_post):
            result_json = text_to_speech_tool(text="hi", output_path=str(out))
        result = json.loads(result_json)
        assert result["success"] is True
        assert result["provider"] == "cloud-backup"
