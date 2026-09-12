import httpx
import json
import asyncio
from typing import Optional
from src.agent.schemas import TradeDecision
from src.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from src.monitoring.logging import logger

class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self.client.aclose()

    async def get_decision(self, context_json: str) -> Optional[TradeDecision]:
        if not self.base_url or not self.api_key:
            logger.warning("LLM API not configured. Returning WAIT decision.")
            return TradeDecision(action="WAIT", reasoning_summary="LLM API not configured.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(context_json)}
            ],
            "response_format": {"type": "json_object"}
        }

        url = f"{self.base_url}/chat/completions"
        if "openai" not in self.base_url and "completions" not in url:
            # Basic normalization for some providers if they don't append it
            pass

        for attempt in range(3):
            try:
                response = await self.client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

                content = data["choices"][0]["message"]["content"]

                # Try parsing to Pydantic model
                decision_dict = json.loads(content)
                decision = TradeDecision(**decision_dict)
                return decision

            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse LLM response as JSON/Pydantic: {e}. Attempt {attempt+1}")
            except httpx.HTTPError as e:
                logger.error(f"LLM API request failed: {e}. Attempt {attempt+1}")
            except Exception as e:
                logger.error(f"Unexpected error calling LLM: {e}. Attempt {attempt+1}")

            await asyncio.sleep(2 ** attempt)

        logger.error("Failed to get valid decision from LLM after retries. Defaulting to WAIT/HOLD.")
        return None
