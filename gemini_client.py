"""Gemini API との通信をまとめたモジュール。"""

import os
from collections.abc import Iterator

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-pro-latest", "gemini-flash-lite-latest"]

# 文章生成に向かないモデル（音声・画像・ロボット制御など）を一覧から外すための語
_EXCLUDE_WORDS = ("tts", "image", "computer-use", "robotics", "transcribe", "banana", "customtools", "embedding")


# このアプリ専用の変数を最優先にする。GEMINI_API_KEY は他のアプリ（有料枠）と共用のため、
# このアプリだけ別のキー（無料枠など）を使いたいときは WRITING_TOOL_API_KEY に書く
API_KEY_VARS = ("WRITING_TOOL_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")


def get_api_key() -> tuple[str, str]:
    """環境変数（.env 含む）から API キーを読み、(キー, 変数名) を返す。無ければ ("", "")。"""
    for name in API_KEY_VARS:
        if value := os.environ.get(name):
            return value, name
    return "", ""


def make_client(api_key: str) -> genai.Client:
    return genai.Client(api_key=api_key)


def list_text_models(client: genai.Client) -> list[str]:
    """文章生成に使える Gemini モデル名の一覧。取得に失敗したら固定の候補を返す。"""
    try:
        names = []
        for m in client.models.list():
            name = m.name.removeprefix("models/")
            if "generateContent" not in (m.supported_actions or []):
                continue
            if not name.startswith("gemini") or any(w in name for w in _EXCLUDE_WORDS):
                continue
            names.append(name)
    except Exception:
        return FALLBACK_MODELS
    if not names:
        return FALLBACK_MODELS
    # 「-latest」の別名を先頭に、残りは新しい版から並べる
    latest = sorted(n for n in names if n.endswith("-latest"))
    others = sorted((n for n in names if not n.endswith("-latest")), reverse=True)
    return latest + others


def stream_generate(
    client: genai.Client,
    model: str,
    prompt: str,
    system_instruction: str,
    temperature: float,
) -> Iterator[str]:
    """生成結果を少しずつ返す（st.write_stream にそのまま渡せる）。"""
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
        # 関数呼び出しは使わない（有効のままだと SDK が毎回警告を出す）
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    for chunk in client.models.generate_content_stream(model=model, contents=prompt, config=config):
        if chunk.text:
            yield chunk.text
