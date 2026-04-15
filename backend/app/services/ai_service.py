"""
Unified AI invocation wrapper.
All modules call AI through this service instead of using the OpenAI SDK directly.
Compatible with any model following the OpenAI protocol, including local Ollama models.
"""
import json
import logging
import time
from typing import Optional
from openai import AsyncOpenAI
from app.core.security import decrypt_api_key

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self, api_base: str, api_key_encrypted: str, model_name: str, timeout_seconds: int = 60):
        api_key = decrypt_api_key(api_key_encrypted)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=float(timeout_seconds),
            max_retries=0,
        )
        self.model = model_name
        self.api_base = api_base

    async def chat(
        self,
        prompt: str,
        system: str = "You are an expert CC (Common Criteria) security evaluation specialist.",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat request and return the model's response text."""
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Some models (e.g. kimi-k2.5 on NVIDIA) do not support the response_format parameter.
        logger.info("[AI] base_url=%s model=%s max_tokens=%s", self.api_base, self.model, max_tokens)
        t0 = time.time()
        try:
            resp = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            logger.error("[AI] Call failed (%.1fs): %s: %s", time.time() - t0, type(exc).__name__, exc)
            raise
        logger.info("[AI] Success (%.1fs) finish_reason=%s", time.time() - t0, resp.choices[0].finish_reason)
        return resp.choices[0].message.content

    async def chat_json(self, prompt: str, system: str = None, **kwargs) -> dict | list:
        """Call AI and automatically parse JSON response"""
        sys_msg = system or "You are an expert CC security evaluation specialist. Return strictly valid JSON only and do not include any extra content."
        text = await self.chat(prompt, system=sys_msg, **kwargs)
        # Clean up possible markdown code blocks
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fix common invalid escape sequences from AI (e.g., \S \P \T etc.)
            import re
            fixed = re.sub(r'\\([^"\\\/bfnrtu])', r'\1', text)
            return json.loads(fixed)


async def get_ai_service(db, user_id: str) -> Optional[AIService]:
    """
    Get the user's configured verified AI model service.
    Prefer the first model with is_verified=True.
    """
    from sqlmodel import select
    from app.models.ai_model import AIModel

    # Prefer the active working model, otherwise fall back to the first verified model.
    result = await db.exec(
        select(AIModel).where(
            AIModel.user_id == user_id,
            AIModel.is_active == True,
            AIModel.deleted_at.is_(None),
        ).limit(1)
    )
    model = result.first()
    if not model:
        result = await db.exec(
            select(AIModel).where(
                AIModel.user_id == user_id,
                AIModel.is_verified == True,
                AIModel.deleted_at.is_(None),
            ).limit(1)
        )
        model = result.first()
    if not model:
        return None
    return AIService(
        api_base=model.api_base,
        api_key_encrypted=model.api_key_encrypted,
        model_name=model.model_name,
        timeout_seconds=model.timeout_seconds,
    )
