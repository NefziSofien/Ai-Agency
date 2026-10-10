"""Génération d'images et de voix via OmniRoute (/v1/images, /v1/audio)."""

import base64

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agence.config import settings
from agence.llm import raw_client
from agence.storage import presigned_url, save_asset
from agence.tools.common import as_tool_result, context, require


@tool
@as_tool_result
async def generate_image(prompt: str, config: RunnableConfig, size: str = "1024x1024") -> dict:
    """Génère un visuel (post, bannière, publicité) et le stocke. Formats : 1024x1024, 1024x1536 (story), 1536x1024 (bannière).
    Le prompt doit être détaillé : sujet, style, couleurs de la marque, cadrage, texte éventuel."""
    client, run_id = context(config)
    model = require(settings().model_image, "MODEL_IMAGE")
    res = await raw_client(client).images.generate(model=model, prompt=prompt, size=size, n=1)
    item = res.data[0]
    if item.b64_json:
        data = base64.b64decode(item.b64_json)
    else:
        async with httpx.AsyncClient(timeout=120) as http:
            data = (await http.get(item.url)).content
    asset = await save_asset(client["id"], run_id, "image", data, "png", "image/png", prompt)
    return {"asset_id": asset["id"], "key": asset["key"], "preview_url": presigned_url(asset["key"])}


@tool
@as_tool_result
async def generate_voiceover(text: str, config: RunnableConfig, voice: str = "alloy") -> dict:
    """Génère une voix off MP3 (script de reel, publicité audio, vidéo explicative) et la stocke."""
    client, run_id = context(config)
    model = require(settings().model_tts, "MODEL_TTS")
    res = await raw_client(client).audio.speech.create(model=model, voice=voice, input=text)
    asset = await save_asset(client["id"], run_id, "audio", res.content, "mp3", "audio/mpeg", text[:500])
    return {"asset_id": asset["id"], "key": asset["key"], "preview_url": presigned_url(asset["key"])}
