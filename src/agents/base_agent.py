import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from config.settings import settings

class GeminiAgentClient:
    """
    Client for OpenAgentic API running Gemini 3.8 Flash High.
    Compatible with OpenAI/OpenAgentic Chat Completions spec with automatic
    retry, exponential backoff, token usage tracking, and robust timeout handling.
    """
    # Class-level cumulative token and call counters
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_estimated_cost = 0.0
    total_requests = 0

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.OPENAGENTIC_API_KEY
        self.base_url = (base_url or settings.OPENAGENTIC_BASE_URL).rstrip('/')
        self.model = model or settings.MODEL_NAME
        self.timeout_seconds = 35.0
        self.max_retries = 3

    @classmethod
    def get_token_usage_stats(cls) -> Dict[str, Any]:
        """Return cumulative token usage and cost stats."""
        return {
            "total_requests": cls.total_requests,
            "total_prompt_tokens": cls.total_prompt_tokens,
            "total_completion_tokens": cls.total_completion_tokens,
            "total_tokens": cls.total_tokens,
            "estimated_cost_usd": round(cls.total_estimated_cost, 6),
        }

    async def generate_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature
        }

        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        for attempt in range(1, self.max_retries + 1):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            raw_text = await resp.text()
                            # Clean SSE data trailers e.g. 'data: [DONE]' if attached
                            clean_text = raw_text.split("data: [DONE]")[0].strip()
                            data = json.loads(clean_text)
                            
                            # Track token usage from response
                            usage = data.get("usage", {})
                            p_tok = usage.get("prompt_tokens", 0)
                            c_tok = usage.get("completion_tokens", 0)
                            t_tok = usage.get("total_tokens", p_tok + c_tok)
                            cost = usage.get("cost", 0.0)

                            GeminiAgentClient.total_requests += 1
                            GeminiAgentClient.total_prompt_tokens += p_tok
                            GeminiAgentClient.total_completion_tokens += c_tok
                            GeminiAgentClient.total_tokens += t_tok
                            GeminiAgentClient.total_estimated_cost += cost

                            return data["choices"][0]["message"]["content"]
                        elif resp.status == 429:
                            retry_after = int(resp.headers.get("Retry-After", 2 * attempt))
                            print(f"[OpenAgentic Warning] Rate limit (429) hit. Backing off for {retry_after}s (Attempt {attempt}/{self.max_retries})...")
                            await asyncio.sleep(retry_after)
                        elif resp.status == 503:
                            # 503: Provider offers exhausted / service unavailable.
                            # Skip retrying and abort immediately to save time and wait for next trigger
                            error_text = await resp.text()
                            print(f"[OpenAgentic 503] Provider offers exhausted / temporary unavailable: {error_text}. Aborting evaluation immediately to wait for next trigger.")
                            return "Error: 503 Service Unavailable"
                        elif resp.status in [500, 502, 504]:
                            print(f"[OpenAgentic Warning] Server error ({resp.status}). Retrying in {2 ** attempt}s...")
                            await asyncio.sleep(2 ** attempt)
                        else:
                            error_text = await resp.text()
                            print(f"[OpenAgentic Error] API returned status {resp.status}: {error_text}")
                            return f"Error: API returned {resp.status} - {error_text}"

            except asyncio.TimeoutError:
                print(f"[OpenAgentic Timeout] AI request timed out after {self.timeout_seconds}s. (Attempt {attempt}/{self.max_retries})")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    print(f"[OpenAgentic Error] All {self.max_retries} attempts timed out. Skipping pair cleanly.")
                    return "Error: Timeout"

            except aiohttp.ClientError as e:
                print(f"[OpenAgentic Network Error] Connection error: {e}. (Attempt {attempt}/{self.max_retries})")
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return f"Error connecting to OpenAgentic API: {str(e)}"

            except Exception as e:
                print(f"[OpenAgentic Unexpected Error] {e}")
                return f"Unexpected error: {str(e)}"

        return "Error: Max retries exceeded"

