"""Tests for multi-URL candidate discovery on `type: http` providers
(Speech Router RFC, PR5).

This is distinct from PR3's provider-level fallback chain: `urls` tries
several addresses for the *same* logical service (e.g. "my local TTS
server, not sure if it's on 8732 or 8123"), not different backends.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.tts_tool import (
    _generate_http_tts,
    _get_http_provider_urls,
    _is_http_provider_config,
    text_to_speech_tool,
)


def _fake_response(status_code=200, content=b"fake-audio-bytes", text=""):
    return SimpleNamespace(status_code=status_code, content=content, text=text)


class TestGetHttpProviderUrls:
    def test_single_url_returns_one_item_list(self):
        assert _get_http_provider_urls({"url": "https://a/speak"}) == ["https://a/speak"]

    def test_urls_list_returned_in_order(self):
        cfg = {"urls": ["http://127.0.0.1:8732/speak", "http://127.0.0.1:8123/speak"]}
        assert _get_http_provider_urls(cfg) == [
            "http://127.0.0.1:8732/speak",
            "http://127.0.0.1:8123/speak",
        ]

    def test_blank_entries_in_urls_are_dropped(self):
        cfg = {"urls": ["http://a/speak", "", "  ", "http://b/speak"]}
        assert _get_http_provider_urls(cfg) == ["http://a/speak", "http://b/speak"]

    def test_url_singular_takes_precedence_over_urls_plural(self):
        cfg = {"url": "http://single/speak", "urls": ["http://a/speak", "http://b/speak"]}
        assert _get_http_provider_urls(cfg) == ["http://single/speak"]

    def test_neither_field_returns_empty_list(self):
        assert _get_http_provider_urls({}) == []

    def test_empty_urls_list_returns_empty(self):
        assert _get_http_provider_urls({"urls": []}) == []


class TestIsHttpProviderConfigWithUrls:
    def test_urls_list_alone_is_valid(self):
        cfg = {"type": "http", "urls": ["http://127.0.0.1:8732/speak"]}
        assert _is_http_provider_config(cfg) is True

    def test_empty_urls_list_is_invalid(self):
        cfg = {"type": "http", "urls": []}
        assert _is_http_provider_config(cfg) is False


class TestGenerateHttpTtsDiscovery:
    def test_first_candidate_failure_tries_second(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {
            "type": "http",
            "urls": ["http://127.0.0.1:8732/speak", "http://127.0.0.1:8123/speak"],
        }
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            if "8732" in url:
                raise __import__("requests").exceptions.ConnectionError("refused")
            return _fake_response()

        with patch("requests.post", side_effect=fake_post):
            result_path = _generate_http_tts("hi", str(out), "local-speech", config, {})

        assert result_path == str(out)
        assert calls == [
            "http://127.0.0.1:8732/speak",
            "http://127.0.0.1:8123/speak",
        ]

    def test_all_candidates_failing_raises_with_last_url(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {
            "type": "http",
            "urls": ["http://127.0.0.1:8732/speak", "http://127.0.0.1:8123/speak"],
        }
        with patch("requests.post", return_value=_fake_response(status_code=500, text="boom")):
            with pytest.raises(RuntimeError, match="8123"):
                _generate_http_tts("hi", str(out), "local-speech", config, {})

    def test_first_candidate_success_never_tries_second(self, tmp_path):
        out = tmp_path / "reply.wav"
        config = {
            "type": "http",
            "urls": ["http://127.0.0.1:8732/speak", "http://127.0.0.1:8123/speak"],
        }
        calls = []

        def fake_post(url, **kwargs):
            calls.append(url)
            return _fake_response()

        with patch("requests.post", side_effect=fake_post):
            _generate_http_tts("hi", str(out), "local-speech", config, {})

        assert calls == ["http://127.0.0.1:8732/speak"]

    def test_no_url_or_urls_raises_value_error(self, tmp_path):
        out = tmp_path / "reply.wav"
        with pytest.raises(ValueError):
            _generate_http_tts("hi", str(out), "local-speech", {"type": "http"}, {})


class TestUrlDiscoveryEndToEnd:
    def test_text_to_speech_tool_discovers_second_port(self, tmp_path):
        cfg = {
            "provider": "local-speech",
            "providers": {
                "local-speech": {
                    "type": "http",
                    "urls": ["http://127.0.0.1:8732/speak", "http://127.0.0.1:8123/speak"],
                    "output_format": "wav",
                },
            },
        }
        out = tmp_path / "reply.wav"

        def fake_post(url, **kwargs):
            if "8732" in url:
                raise __import__("requests").exceptions.ConnectionError("refused")
            return _fake_response()

        with patch("tools.tts_tool._load_tts_config", return_value=cfg), \
             patch("requests.post", side_effect=fake_post):
            result_json = text_to_speech_tool(text="hi", output_path=str(out))
        result = json.loads(result_json)
        assert result["success"] is True
        assert result["provider"] == "local-speech"

    def test_all_urls_failing_falls_back_to_next_router_provider(self, tmp_path):
        """PR3 + PR5 integration: a provider whose every candidate URL fails
        still falls through to the next entry in tts.router.providers."""
        cfg = {
            "provider": "local-speech",
            "router": {"providers": ["local-speech", "cloud-backup"]},
            "providers": {
                "local-speech": {
                    "type": "http",
                    "urls": ["http://127.0.0.1:8732/speak", "http://127.0.0.1:8123/speak"],
                },
                "cloud-backup": {"type": "http", "url": "https://backup/speak"},
            },
        }
        out = tmp_path / "reply.wav"

        def fake_post(url, **kwargs):
            if url.startswith("http://127.0.0.1"):
                raise __import__("requests").exceptions.ConnectionError("refused")
            return _fake_response()

        with patch("tools.tts_tool._load_tts_config", return_value=cfg), \
             patch("requests.post", side_effect=fake_post):
            result_json = text_to_speech_tool(text="hi", output_path=str(out))
        result = json.loads(result_json)
        assert result["success"] is True
        assert result["provider"] == "cloud-backup"
