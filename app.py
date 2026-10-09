"""AIライティングツール（Streamlit + Gemini API）

起動: streamlit run app.py
"""

from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from google.genai import errors as genai_errors

import gemini_client as gc
from tools import TOOLS, TOOLS_BY_KEY, Field, Tool, build_revision_prompt

load_dotenv()

st.set_page_config(page_title="AIライティングツール", page_icon="✍️", layout="wide")

# 入力欄の値は、別のツールに切り替えても消えないように毎回入れ直す
# （表示されていないウィジェットの値は Streamlit が破棄するため）
for _k in [k for k in st.session_state if str(k).startswith("f_")]:
    st.session_state[_k] = st.session_state[_k]

st.session_state.setdefault("results", {})  # ツールごとの最新結果
st.session_state.setdefault("history", [])  # このセッションで生成したもの全部


@st.cache_resource
def get_client(api_key: str):
    return gc.make_client(api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def get_models(api_key: str) -> list[str]:
    return gc.list_text_models(get_client(api_key))


def render_field(tool: Tool, f: Field):
    key = f"f_{tool.key}_{f.key}"
    if key not in st.session_state and f.default is not None:
        st.session_state[key] = f.default
    common = {"key": key, "help": f.help or None}
    if f.kind == "text":
        return st.text_input(f.label, placeholder=f.placeholder, **common)
    if f.kind == "textarea":
        return st.text_area(f.label, placeholder=f.placeholder, height=f.height, **common)
    if f.kind == "select":
        return st.selectbox(f.label, f.options, **common)
    if f.kind == "slider":
        return st.slider(f.label, f.min_value, f.max_value, step=f.step, **common)
    if f.kind == "checkbox":
        return st.checkbox(f.label, **common)
    raise ValueError(f"未対応の入力種別: {f.kind}")


def run_generation(client, model: str, prompt: str, system: str, temperature: float) -> str | None:
    """結果をストリーミング表示し、全文を返す。失敗したら None。"""
    try:
        with st.container(border=True):
            text = st.write_stream(gc.stream_generate(client, model, prompt, system, temperature))
    except genai_errors.APIError as e:
        st.error(f"Gemini API エラー（{e.code}）：{e.message}")
        return None
    except Exception as e:  # ネットワーク断など
        st.error(f"生成に失敗しました：{e}")
        return None
    if not text:
        st.warning("応答が空でした。入力内容を変えるか、別のモデルで試してください。")
        return None
    return text


def save_result(tool: Tool, output: str, label: str):
    st.session_state["results"][tool.key] = output
    st.session_state["history"].insert(
        0, {"time": datetime.now().strftime("%H:%M"), "tool": tool.key, "label": label, "output": output}
    )


# ---------------------------------------------------------------- サイドバー
with st.sidebar:
    st.title("✍️ AIライティング")
    tool_key = st.radio(
        "ツール",
        [t.key for t in TOOLS],
        format_func=lambda k: f"{TOOLS_BY_KEY[k].icon} {TOOLS_BY_KEY[k].name}",
        key="selected_tool",
    )
    tool = TOOLS_BY_KEY[tool_key]

    st.divider()
    st.subheader("設定")
    api_key, key_source = gc.get_api_key()
    if api_key:
        st.caption(f"🔑 API キー：`{key_source}` から読み込み済み")
    else:
        api_key = st.text_input("Gemini API キー", type="password", help="Google AI Studio で発行したキー")

    models = get_models(api_key) if api_key else gc.FALLBACK_MODELS
    default_index = models.index(gc.DEFAULT_MODEL) if gc.DEFAULT_MODEL in models else 0
    model = st.selectbox("モデル", models, index=default_index, key="f_model")

    temp_key = f"f_{tool.key}__temperature"
    st.session_state.setdefault(temp_key, tool.temperature)
    temperature = st.slider(
        "創造性（temperature）", 0.0, 2.0, step=0.1, key=temp_key,
        help="低いほど堅実で安定、高いほど自由で多様な文章になります。ツールごとに初期値が違います。",
    )

# ---------------------------------------------------------------- メイン
st.header(f"{tool.icon} {tool.name}")
st.caption(tool.description)

if not api_key:
    st.info("サイドバーに Gemini API キーを入力するか、`.env` に `WRITING_TOOL_API_KEY` を設定してください。")
    st.stop()

client = get_client(api_key)

# st.form は使わない：フォームは送信するまで値が確定せず、途中でツールを切り替えると入力が消えるため
with st.container(border=True):
    values = {f.key: render_field(tool, f) for f in tool.fields}
    submitted = st.button("✨ 生成する", type="primary", width="stretch")

if submitted:
    missing = [f.label for f in tool.fields if f.required and not str(values[f.key]).strip()]
    if missing:
        st.warning("入力してください：" + "、".join(missing))
    else:
        output = run_generation(client, model, tool.build_prompt(values), tool.system, temperature)
        if output:
            first_required = next((values[f.key] for f in tool.fields if f.required), "")
            save_result(tool, output, str(first_required).strip().splitlines()[0][:40])
            st.rerun()

output = st.session_state["results"].get(tool.key)
if output:
    st.subheader("結果")
    st.caption(f"{len(output):,} 文字")
    view_tab, copy_tab = st.tabs(["表示", "コピー用（右上のボタンでコピー）"])
    with view_tab:
        with st.container(border=True):
            st.markdown(output)
    with copy_tab:
        st.code(output, language=None, wrap_lines=True)

    col_dl, col_clear = st.columns([1, 1])
    col_dl.download_button(
        "⬇️ Markdown で保存",
        output,
        file_name=f"{tool.name}_{datetime.now():%Y%m%d_%H%M}.md",
        mime="text/markdown",
        width="stretch",
    )
    if col_clear.button("🗑️ 結果を消す", width="stretch"):
        del st.session_state["results"][tool.key]
        st.rerun()

    st.markdown("##### 🔁 この結果を修正する")
    with st.form(f"revise_{tool.key}", clear_on_submit=True):
        instruction = st.text_input("修正の指示", placeholder="例：もっと短く／見出しを増やして／語尾を柔らかく")
        revise = st.form_submit_button("修正する")
    if revise and instruction.strip():
        revised = run_generation(
            client, model, build_revision_prompt(output, instruction), tool.system, temperature
        )
        if revised:
            save_result(tool, revised, f"修正：{instruction.strip()[:30]}")
            st.rerun()

# ---------------------------------------------------------------- 履歴
history = st.session_state["history"]
if history:
    st.divider()
    with st.expander(f"🕘 このセッションの履歴（{len(history)}件・ブラウザを閉じると消えます）"):
        for h in history:
            t = TOOLS_BY_KEY[h["tool"]]
            st.markdown(f"**{h['time']}　{t.icon} {t.name}** — {h['label']}")
            st.code(h["output"], language=None, wrap_lines=True)
