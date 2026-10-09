# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 概要

個人用のAIライティングツール（Python + Streamlit + Gemini API）。DB・認証は意図的に持たない。履歴は `st.session_state` のみで、ブラウザを閉じると消える。UI・プロンプト・コメントはすべて日本語。

## コマンド

```
pip install -r requirements.txt
streamlit run app.py            # http://localhost:8501（Windows では 起動.bat でも可）
```

venv は使わずユーザー環境に入れている（作業フォルダが OneDrive 配下で、venv の同期負荷が大きいため）。

テストファイル・リンターは無い。動作確認は `streamlit.testing.v1.AppTest` でヘッドレスに行う：

- `AppTest.from_file()` の相対パスは**呼び出し元スクリプト基準**で解決されるので、絶対パスを渡す
- プロジェクトを `PYTHONPATH` に入れる
- Windows のコンソールは cp932 なので、`PYTHONIOENCODING=utf-8` を付けないと日本語出力が化ける

## アーキテクチャ

- **`tools.py`** — 各ツールは `Tool` を1つ定義する。中身は、入力欄の宣言（`Field` の並び）、`build_prompt(values: dict) -> str`、システムプロンプト、既定の temperature。ツールを追加するときは、ここに `Tool` を足して `TOOLS` に並べるだけでよい。`app.py` は手を付けなくてよい。`values` のキーは `Field.key` と一致させる。
- **`app.py`** — `tool.fields` から入力欄を自動で組み立てる（`render_field`）。生成は `st.write_stream` で流しながら表示し、ツールごとの最新結果と履歴に保存してから `st.rerun()` する。修正指示は、前回の出力を `build_revision_prompt` で包み直して再生成する。
- **`gemini_client.py`** — `google-genai` SDK のラッパー。モデル一覧は実行時に API から取る。文章生成に向かないモデル（`_EXCLUDE_WORDS`：tts・image など）は除外し、取得に失敗したら `FALLBACK_MODELS` を使う。既定モデルは `gemini-flash-latest`。モデル名を固定しないのは、入れ替わりが速いため。

## 壊しやすい点

- **ウィジェットの key** は `f_` で始める（例：`f_<tool>_<field>`、`f_<tool>__temperature`）。`app.py` の冒頭で `f_` で始まる値を毎回入れ直していて、これでツールを切り替えても入力が残る。Streamlit は表示されていないウィジェットの値を捨てるため、この処理が必要になる。
- **メインの入力欄に `st.form` を使わない。** フォームは送信するまで値が確定しないので、途中でツールを切り替えると入力が消える。
- `stream_generate` は自動関数呼び出し（AFC）を明示的に無効にしている。有効のままだと SDK が呼び出しのたびに警告を出す。
- API キーは `WRITING_TOOL_API_KEY` → `GEMINI_API_KEY` → `GOOGLE_API_KEY` → サイドバーでの入力、の順に探す。`GEMINI_API_KEY` はユーザー環境変数にあり、他のアプリ（有料枠）と共用している。このアプリは無料枠のキーを `.env` の `WRITING_TOOL_API_KEY` に置いて使う。共用の変数を書き換えないこと。`.env` は `load_dotenv()` で読み込むが、既存の環境変数を上書きしない。
