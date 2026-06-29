import json
import os
import urllib.error
import urllib.request
from typing import Protocol

from news_events.classification import classify_news_event


NEWS_EXTRACTOR_SYSTEM_PROMPT = """
You classify stock news for Market Agent.

Return only JSON with these fields:
- sentiment: positive, negative, neutral, or unknown
- topic: earnings_guidance, risk_event, analyst_rating, product_demand,
  short_term_sentiment, market_attention, or general
- importance: high, medium, low, or unknown
- summary: one short Traditional Chinese sentence
- ticker_relevance: high, medium, or low

Use only the given title and snippet. Do not invent facts.
""".strip()

VALID_SENTIMENTS = {"positive", "negative", "neutral", "unknown"}
VALID_TOPICS = {
    "earnings_guidance",
    "risk_event",
    "analyst_rating",
    "product_demand",
    "short_term_sentiment",
    "market_attention",
    "general",
}
VALID_IMPORTANCE = {"high", "medium", "low", "unknown"}
VALID_RELEVANCE = {"high", "medium", "low"}


class NewsExtractorClient(Protocol):
    provider: str
    model: str

    def extract(self, *, ticker: str, title: str, content_snippet: str | None) -> dict:
        ...


class DeepSeekNewsExtractorClient:
    provider = "deepseek"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_env(cls):
        api_key = os.getenv("DEEPSEEK_API_KEY")

        if not api_key:
            return None

        return cls(
            api_key=api_key,
            model=os.getenv("NEWS_LLM_MODEL", "deepseek-chat"),
        )

    def extract(self, *, ticker: str, title: str, content_snippet: str | None) -> dict:
        user_prompt = json.dumps(
            {
                "ticker": ticker.upper(),
                "title": title,
                "content_snippet": content_snippet or "",
            },
            ensure_ascii=False,
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": NEWS_EXTRACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            "https://api.deepseek.com/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek news extractor error: {message}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"DeepSeek news extractor connection error: {error}") from error

        content = (
            response_data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            raise RuntimeError("DeepSeek news extractor returned empty content.")

        return json.loads(content)


class OpenRouterNewsExtractorClient:
    provider = "openrouter"

    def __init__(
        self,
        api_key: str,
        model: str = "openai/gpt-4.1-mini",
        site_url: str | None = None,
        app_name: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.site_url = site_url
        self.app_name = app_name

    @classmethod
    def from_env(cls):
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            return None

        return cls(
            api_key=api_key,
            model=os.getenv(
                "NEWS_LLM_MODEL",
                os.getenv("MARKET_AGENT_LLM_MODEL", "openai/gpt-4.1-mini"),
            ),
            site_url=os.getenv("OPENROUTER_SITE_URL"),
            app_name=os.getenv("OPENROUTER_APP_NAME", "market-agent"),
        )

    @classmethod
    def from_env_with_model(cls, model: str):
        api_key = os.getenv("OPENROUTER_API_KEY")

        if not api_key:
            return None

        return cls(
            api_key=api_key,
            model=model,
            site_url=os.getenv("OPENROUTER_SITE_URL"),
            app_name=os.getenv("OPENROUTER_APP_NAME", "market-agent"),
        )

    def extract(self, *, ticker: str, title: str, content_snippet: str | None) -> dict:
        user_prompt = json.dumps(
            {
                "ticker": ticker.upper(),
                "title": title,
                "content_snippet": content_snippet or "",
            },
            ensure_ascii=False,
        )
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": NEWS_EXTRACTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.site_url:
            headers["HTTP-Referer"] = self.site_url

        if self.app_name:
            headers["X-Title"] = self.app_name

        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter news extractor error: {message}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"OpenRouter news extractor connection error: {error}") from error

        content = (
            response_data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if not content:
            raise RuntimeError("OpenRouter news extractor returned empty content.")

        return json.loads(content)


def get_news_extractor_mode() -> str:
    mode = os.getenv("NEWS_EXTRACTOR_MODE", "rule_based").strip().lower()

    if mode in {"rule_based", "llm"}:
        return mode

    return "rule_based"


def get_news_extractor_client_from_env():
    provider = os.getenv("NEWS_LLM_PROVIDER", "openrouter").strip().lower()

    if provider == "openrouter":
        return OpenRouterNewsExtractorClient.from_env()

    if provider == "deepseek":
        return DeepSeekNewsExtractorClient.from_env()

    return None


def get_news_escalation_enabled() -> bool:
    value = os.getenv("NEWS_LLM_ESCALATION_ENABLED", "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def get_news_escalation_model() -> str:
    return os.getenv("NEWS_LLM_ESCALATION_MODEL", "openai/gpt-5.5").strip()


def get_news_escalation_client_from_env():
    provider = os.getenv("NEWS_LLM_PROVIDER", "openrouter").strip().lower()

    if provider == "openrouter":
        return OpenRouterNewsExtractorClient.from_env_with_model(
            get_news_escalation_model()
        )

    return None


def classify_news_event_with_optional_llm(
    *,
    ticker: str,
    title: str,
    content_snippet: str | None = None,
    mode: str | None = None,
    llm_client: NewsExtractorClient | None = None,
) -> dict:
    rule_based_result = classify_news_event(
        title=title,
        content_snippet=content_snippet,
    )
    requested_mode = (mode or get_news_extractor_mode()).strip().lower()

    if requested_mode != "llm":
        return {
            **rule_based_result,
            "extractor": {
                "requested_mode": requested_mode,
                "mode_used": "rule_based",
                "fallback_used": False,
            },
        }

    client = llm_client or get_news_extractor_client_from_env()

    if client is None:
        return {
            **rule_based_result,
            "extractor": {
                "requested_mode": "llm",
                "mode_used": "rule_based",
                "fallback_used": True,
                "message": "未設定新聞 LLM extractor，已 fallback 到 rule-based。",
            },
        }

    try:
        llm_result = sanitize_llm_extraction_result(
            client.extract(
                ticker=ticker,
                title=title,
                content_snippet=content_snippet,
            )
        )
    except Exception as error:
        return {
            **rule_based_result,
            "extractor": {
                "requested_mode": "llm",
                "mode_used": "rule_based",
                "provider": getattr(client, "provider", None),
                "model": getattr(client, "model", None),
                "fallback_used": True,
                "message": f"新聞 LLM extractor 失敗，已 fallback：{error}",
            },
        }

    return {
        **llm_result,
        "extractor": {
            "requested_mode": "llm",
            "mode_used": "llm",
            "provider": getattr(client, "provider", None),
            "model": getattr(client, "model", None),
            "fallback_used": False,
        },
    }


def sanitize_llm_extraction_result(result: dict) -> dict:
    return {
        "sentiment": normalize_choice(
            result.get("sentiment"),
            valid_values=VALID_SENTIMENTS,
            default="unknown",
        ),
        "topic": normalize_choice(
            result.get("topic"),
            valid_values=VALID_TOPICS,
            default="general",
        ),
        "importance": normalize_choice(
            result.get("importance"),
            valid_values=VALID_IMPORTANCE,
            default="unknown",
        ),
        "summary": clean_optional_text(result.get("summary")),
        "ticker_relevance": normalize_choice(
            result.get("ticker_relevance"),
            valid_values=VALID_RELEVANCE,
            default="medium",
        ),
    }


def normalize_choice(value, *, valid_values: set[str], default: str) -> str:
    if not isinstance(value, str):
        return default

    normalized = value.strip().lower()

    if normalized in valid_values:
        return normalized

    return default


def clean_optional_text(value) -> str | None:
    if not isinstance(value, str):
        return None

    cleaned = " ".join(value.split())
    return cleaned or None
