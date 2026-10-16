import asyncio

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from agence.llm import BRIDGE_RETRIES, FallbackChat, PromptModeChat, strip_bridge_summary
from agence.structured import _TAGGED_CALL, _parse


def test_strip_bridge_summary_removes_tagged_prefix():
    text = '<summary>\n## Overview\nThe user asked...\n## Current State\n...\n</summary>\n{"tasks": []}'
    assert strip_bridge_summary(text) == '{"tasks": []}'


def test_strip_bridge_summary_flags_summary_only_reply():
    assert strip_bridge_summary("## Overview\nThe agent...\n\n## Current State\nThe agent is ...") is None
    assert strip_bridge_summary("## Overview\nThe agent is acting as a Social Media Manager...") is None


def test_strip_bridge_summary_keeps_normal_reply():
    assert strip_bridge_summary('```json\n{"tasks": []}\n```') == '```json\n{"tasks": []}\n```'


@pytest.mark.parametrize(
    "text",
    [
        '{"tool": "list_social_channels", "args": {}}',
        '<run_tool>\n{"tool": "list_social_channels", "args": {}}\n</run_tool>',
        'I understand. My first step is to list the channels.{"tool": "list_social_channels", "args": {}}',
    ],
)
def test_parse_accepts_wrapped_json(text):
    assert _parse(text) == {"tool": "list_social_channels", "args": {}}


def test_tool_name_used_as_tag_is_recognised():
    call = _TAGGED_CALL.fullmatch("<list_social_channels>\n{}\n</list_social_channels>")
    assert call and call.group(1) == "list_social_channels" and call.group(2) == "{}"


def test_parse_rejects_text_without_json():
    with pytest.raises(ValueError):
        _parse("Je vais d'abord lister les canaux.")


def _fake_generate(failing: set[str], summary_only: set[str] = frozenset()):
    calls = []

    async def fake(self, messages, *args, **kwargs):
        calls.append(self.model_name)
        if self.model_name in failing:
            raise openai.APIConnectionError(request=httpx.Request("POST", "http://omniroute/v1/chat/completions"))
        text = "## Overview\nThe agent..." if self.model_name in summary_only else '{"ok": true}'
        return ChatResult(generations=[ChatGeneration(message=AIMessage(text))])

    return fake, calls


def test_fallback_on_provider_error(monkeypatch):
    fake, calls = _fake_generate(failing={"dva/opus"})
    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake)
    llm = FallbackChat(model="dva/opus", fallback_models=["cfp/glm"], api_key="k")
    assert asyncio.run(llm.ainvoke("hi")).content == '{"ok": true}'
    assert calls == ["dva/opus", "cfp/glm"]
    assert llm.model_name == "cfp/glm"


def test_error_raised_when_no_fallback_left(monkeypatch):
    fake, _ = _fake_generate(failing={"dva/opus", "cfp/glm"})
    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake)
    llm = FallbackChat(model="dva/opus", fallback_models=["cfp/glm"], api_key="k")
    with pytest.raises(openai.APIConnectionError):
        asyncio.run(llm.ainvoke("hi"))


def test_prompt_mode_falls_back_after_summary_only_replies(monkeypatch):
    fake, calls = _fake_generate(failing=set(), summary_only={"dva/opus"})
    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake)
    llm = PromptModeChat(model="dva/opus", fallback_models=["cfp/glm"], api_key="k")
    assert asyncio.run(llm.ainvoke("hi")).content == '{"ok": true}'
    assert calls == ["dva/opus"] * BRIDGE_RETRIES + ["cfp/glm"]
