"""
Hyper AI LLM Provider Configuration

Preset configurations for popular LLM providers with their base URLs and recommended models.
Users can select a provider during onboarding or configure a custom endpoint.

Supported providers:
- OpenAI (GPT-4o, GPT-4-turbo)
- Anthropic (Claude 3.5 Sonnet, Claude 3 Opus)
- Google Gemini (Gemini 2.0 Flash, Gemini 1.5 Pro)
- Deepseek (Deepseek Chat, Deepseek Reasoner)
- Z.ai/智谱 (GLM-4, GLM-4-Plus)
- OpenRouter (Multi-provider gateway)
- Qwen/通义千问 (Qwen-Max, Qwen-Plus)
- Moonshot/月之暗面 (Moonshot-v1-128k)
- Custom (User-defined endpoint)
"""
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class LLMProvider:
    """Configuration for an LLM provider."""
    id: str                      # Unique identifier (e.g., "openai", "anthropic")
    name: str                    # Display name (e.g., "OpenAI", "Anthropic")
    base_url: str                # API base URL
    models: List[str]            # Available models (first is recommended)
    api_format: str              # "openai" or "anthropic"
    description: str             # Brief description for UI
    requires_api_key: bool = True


# Preset LLM providers with their configurations
PRESET_PROVIDERS: Dict[str, LLMProvider] = {
    "openai": LLMProvider(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "o1", "o1-mini"],
        api_format="openai",
        description="GPT-4o series with strong reasoning capabilities"
    ),
    "anthropic": LLMProvider(
        id="anthropic",
        name="Anthropic",
        base_url="https://api.anthropic.com/v1",
        models=[
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229"
        ],
        api_format="anthropic",
        description="Claude models with excellent instruction following"
    ),
    "gemini": LLMProvider(
        id="gemini",
        name="Google Gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        models=["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        api_format="openai",
        description="Google's multimodal AI with large context window"
    ),
    "deepseek": LLMProvider(
        id="deepseek",
        name="Deepseek",
        base_url="https://api.deepseek.com/v1",
        models=["deepseek-chat", "deepseek-reasoner"],
        api_format="openai",
        description="Cost-effective Chinese AI with strong coding ability"
    ),
    "zhipu": LLMProvider(
        id="zhipu",
        name="Z.ai / 智谱",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        models=["glm-4-plus", "glm-4", "glm-4-flash"],
        api_format="openai",
        description="Chinese AI with excellent Chinese language support"
    ),
    "openrouter": LLMProvider(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        models=[
            "anthropic/claude-sonnet-4",
            "openai/gpt-4o",
            "google/gemini-2.0-flash-exp:free"
        ],
        api_format="openai",
        description="Multi-provider gateway with unified API"
    ),
    "qwen": LLMProvider(
        id="qwen",
        name="Qwen / 通义千问",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        models=["qwen-max", "qwen-plus", "qwen-turbo"],
        api_format="openai",
        description="Alibaba's AI with strong multilingual capabilities"
    ),
    "moonshot": LLMProvider(
        id="moonshot",
        name="Moonshot / 月之暗面",
        base_url="https://api.moonshot.cn/v1",
        models=["moonshot-v1-128k", "moonshot-v1-32k", "moonshot-v1-8k"],
        api_format="openai",
        description="Chinese AI with ultra-long context window (128K)"
    ),
    "custom": LLMProvider(
        id="custom",
        name="Custom / 自定义",
        base_url="",  # User provides
        models=[],    # User provides
        api_format="openai",
        description="Custom OpenAI-compatible endpoint",
        requires_api_key=True
    ),
}


def get_provider(provider_id: str) -> Optional[LLMProvider]:
    """Get a provider configuration by ID."""
    return PRESET_PROVIDERS.get(provider_id)


def get_all_providers() -> List[Dict[str, Any]]:
    """Get all providers as a list of dicts for API response."""
    return [
        {
            "id": p.id,
            "name": p.name,
            "base_url": p.base_url,
            "models": p.models,
            "api_format": p.api_format,
            "description": p.description,
            "requires_api_key": p.requires_api_key,
        }
        for p in PRESET_PROVIDERS.values()
    ]


def get_recommended_model(provider_id: str) -> Optional[str]:
    """Get the recommended (first) model for a provider."""
    provider = get_provider(provider_id)
    if provider and provider.models:
        return provider.models[0]
    return None
