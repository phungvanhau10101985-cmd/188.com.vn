"""Chi phí token AI — cùng bảng giá với nanoai.vn (`src/lib/pricing/api-token-cost.ts`)."""

from __future__ import annotations

import os
from typing import Dict, Optional, TypedDict

IMAGE_TOKENS = {"1K": 1120, "2K": 1120, "4K": 2000}

USD_TO_VND = 25_000
DEFAULT_FALLBACK_MODEL = "gemini-3-flash-preview"


class ModelUsdRates(TypedDict, total=False):
    input: float
    output: float
    outputImage: float
    inputLong: float
    outputLong: float


API_COST_PER_1M: Dict[str, ModelUsdRates] = {
    "deepseek-reasoner": {"input": 0.28, "output": 0.42},
    "deepseek-chat": {"input": 0.28, "output": 0.42},
    "deepseek-v4-flash": {"input": 0.28, "output": 0.42},
    "deepseek-v4-pro": {"input": 0.28, "output": 0.42},
    "gpt-5": {"input": 2.5, "output": 10},
    "gpt-4o": {"input": 2.5, "output": 10},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "gpt-4-turbo": {"input": 10, "output": 30},
    "gpt-4o-mini-tts": {"input": 0.6, "output": 12},
    # GPT Image: token đầu vào văn bản / đầu ra ảnh (bảng GPT Image 1). Không thay token bằng IMAGE_TOKENS.
    "gpt-image-1": {"input": 5, "output": 40},
    "gpt-image-1.5": {"input": 5, "output": 40},
    "gpt-image-2": {"input": 5, "output": 40},
    "gemini-3.1-pro-preview": {"input": 2, "output": 12, "inputLong": 4, "outputLong": 18},
    "gemini-3.1-pro-preview-customtools": {"input": 2, "output": 12, "inputLong": 4, "outputLong": 18},
    "gemini-3-pro-image": {"input": 2, "output": 12, "outputImage": 120, "inputLong": 4, "outputLong": 18},
    "gemini-3-pro-image-preview": {"input": 2, "output": 12, "outputImage": 120, "inputLong": 4, "outputLong": 18},
    "gemini-3-flash-preview": {"input": 0.5, "output": 3},
    "gemini-3-pro-preview": {"input": 2, "output": 12, "inputLong": 4, "outputLong": 18},
    "gemini-3.1-flash-lite-preview": {"input": 0.25, "output": 1.5},
    "gemini-3.1-flash-image-preview": {"input": 0.5, "output": 3, "outputImage": 60},
    "gemini-2.5-pro": {"input": 1.25, "output": 10, "inputLong": 2.5, "outputLong": 15},
    "gemini-2.5-flash": {"input": 0.3, "output": 2.5},
    "gemini-2.5-flash-preview-09-2025": {"input": 0.3, "output": 2.5},
    "gemini-2.5-flash-lite": {"input": 0.1, "output": 0.4},
    "gemini-2.5-flash-image": {"input": 0.3, "output": 2.5, "outputImage": 30},
    "gemini-2.0-flash": {"input": 0.1, "output": 0.4},
    "gemini-2.0-flash-lite": {"input": 0.075, "output": 0.3},
    "gemini-embedding-001": {"input": 0.15, "output": 0},
    "gemini-embedding-2-preview": {"input": 0.2, "output": 0},
    "gemini-embedding-2": {"input": 0.2, "output": 0},
    "gemini-2.5-flash-preview-tts": {"input": 0.5, "output": 10},
    "gemini-2.5-pro-preview-tts": {"input": 1, "output": 20},
    "gemini-3.1-flash-tts-preview": {"input": 1, "output": 10},
    "gemini-2.5-flash-native-audio-preview-12-2025": {"input": 3, "output": 12},
    "gemini-2.5-computer-use-preview-10-2025": {"input": 1.25, "output": 10, "inputLong": 2.5, "outputLong": 15},
    "gemini-robotics-er-1.5-preview": {"input": 0.3, "output": 2.5},
    "gemini-robotics-er-1.6-preview": {"input": 1, "output": 5},
    "gemini-3.1-flash-live-preview": {"input": 3, "output": 12},
    "veo-3.1-generate-preview": {"input": 0, "output": 0},
    "veo-3.1-fast-generate-preview": {"input": 0, "output": 0},
    "veo-3.1-lite-generate-preview": {"input": 0, "output": 0},
    "veo-3.0-generate-001": {"input": 0, "output": 0},
    "veo-3.0-fast-generate-001": {"input": 0, "output": 0},
    "veo-2.0-generate-001": {"input": 0, "output": 0},
    "imagen-4.0-generate-001": {"input": 0, "output": 0},
    "imagen-4.0-fast-generate-001": {"input": 0, "output": 0},
    "imagen-4.0-ultra-generate-001": {"input": 0, "output": 0},
    "lyria-3-clip-preview": {"input": 0, "output": 0},
    "lyria-3-pro-preview": {"input": 0, "output": 0},
}

MODEL_DISPLAY_LABELS = {
    "gemini-3.1-pro-preview": "Gemini 3.1 Pro",
    "gemini-3.1-flash-lite-preview": "Gemini 3.1 Flash-Lite",
    "gemini-3.1-flash-image-preview": "Gemini 3.1 Flash Image",
    "gemini-3-pro-image": "Gemini 3 Pro Image (Nano Banana Pro)",
    "gemini-3-pro-image-preview": "Gemini 3 Pro Image (preview)",
    "gemini-3-flash-preview": "Gemini 3 Flash",
    "gemini-3-pro-preview": "Gemini 3 Pro",
    "gemini-2.5-pro": "Gemini 2.5 Pro",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
    "gemini-2.5-flash-lite": "Gemini 2.5 Flash-Lite",
    "gemini-2.5-flash-image": "Gemini 2.5 Flash Image",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.0-flash-lite": "Gemini 2.0 Flash-Lite",
    "gpt-5": "GPT-5",
    "gpt-4o": "GPT-4o",
    "gpt-4o-mini": "GPT-4o mini",
    "gpt-image-1": "GPT Image 1",
    "gpt-image-1.5": "GPT Image 1.5",
    "gpt-image-2": "GPT Image 2",
    "deepseek-chat": "DeepSeek Chat",
    "deepseek-reasoner": "DeepSeek Reasoner",
    "deepseek-v4-flash": "DeepSeek V4 Flash",
    "deepseek-v4-pro": "DeepSeek V4 Pro",
}

FEATURE_LABELS = {
    "category-seo": "SEO danh mục",
    "size-guide": "Ảnh hướng dẫn size",
    "product-classify": "Phân loại sản phẩm",
    "search-correct": "Sửa từ khóa tìm kiếm",
    "image-localization": "Bản địa hóa ảnh",
    "image-translate": "Dịch chữ trên ảnh",
    "ladipage": "Ladipage AI",
    "marketing-banner": "Banner marketing",
    "marketing-icon": "Icon marketing",
    "manual-product": "Đăng sản phẩm AI",
    "import-groups": "Gán nhóm khi import",
    "import-gender": "Nhận giới tính từ ảnh",
    "import-taxonomy": "Phân loại taxonomy",
    "variant-color": "Dịch màu biến thể",
    "legacy-oos": "Từ khóa sản phẩm hết hàng",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "openai": "OpenAI",
    "ai-other": "AI khác",
}


def is_listed_api_cost_model(model: str) -> bool:
    return model in API_COST_PER_1M


def model_display_label(model: str) -> str:
    return MODEL_DISPLAY_LABELS.get(model) or model


def feature_label(feature: str) -> str:
    return FEATURE_LABELS.get(feature) or feature


def get_partner_ai_token_cost_usd_to_vnd() -> float:
    raw = (os.getenv("PARTNER_AI_TOKEN_COST_USD_TO_VND") or "").strip()
    if not raw:
        return float(USD_TO_VND)
    try:
        n = float(raw.replace(",", "."))
    except ValueError:
        return float(USD_TO_VND)
    return n if n > 0 else float(USD_TO_VND)


def _rates_for(model: str) -> ModelUsdRates:
    return API_COST_PER_1M.get(model) or API_COST_PER_1M[DEFAULT_FALLBACK_MODEL]


def calc_cost_vnd_split(
    prompt_tokens: int,
    output_tokens: int,
    model: str,
    image_size: Optional[str] = None,
    *,
    usd_to_vnd: Optional[float] = None,
    pricing_mode: str = "per_call",
) -> Dict[str, int]:
    rate = float(usd_to_vnd) if usd_to_vnd and usd_to_vnd > 0 else float(USD_TO_VND)
    rates = _rates_for(model)
    use_long = (
        pricing_mode == "per_call"
        and prompt_tokens > 200_000
        and rates.get("inputLong") is not None
        and rates.get("outputLong") is not None
    )
    input_rate = float(rates["inputLong"] if use_long else rates["input"])
    output_rate = float(rates["outputLong"] if use_long else rates["output"])
    image_usd = rates.get("outputImage")
    size_ok = image_size in IMAGE_TOKENS
    if image_usd is not None and size_ok and image_size is not None:
        out_rate = float(image_usd)
        effective_output = IMAGE_TOKENS[image_size]
    elif image_usd is not None:
        out_rate = float(image_usd)
        effective_output = output_tokens
    else:
        out_rate = output_rate
        effective_output = output_tokens
    input_usd = (max(0, prompt_tokens) / 1_000_000) * input_rate
    output_usd = (max(0, effective_output) / 1_000_000) * out_rate
    return {
        "inputVnd": int(round(input_usd * rate)),
        "outputVnd": int(round(output_usd * rate)),
        "totalVnd": int(round((input_usd + output_usd) * rate)),
    }


def calc_cost_vnd(
    prompt_tokens: int,
    output_tokens: int,
    model: str,
    image_size: Optional[str] = None,
    *,
    usd_to_vnd: Optional[float] = None,
    pricing_mode: str = "per_call",
) -> int:
    return calc_cost_vnd_split(
        prompt_tokens,
        output_tokens,
        model,
        image_size,
        usd_to_vnd=usd_to_vnd,
        pricing_mode=pricing_mode,
    )["totalVnd"]
