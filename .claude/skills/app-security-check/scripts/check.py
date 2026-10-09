"""AIライティングツールの機械的なセキュリティ点検。

使い方（プロジェクトのルートで）:
    PYTHONIOENCODING=utf-8 python .claude/skills/app-security-check/scripts/check.py [プロジェクトのパス]

標準ライブラリだけで動く。キーの値は表示しない（長さと有無だけ）。
各行は [要対応] [注意] [OK] [情報] のどれかで始まる。
"""

import importlib.metadata
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
SKILL_DIR = Path(__file__).resolve().parents[1]

# gemini_client.API_KEY_VARS と同じ順
API_KEY_VARS = ("WRITING_TOOL_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY")
PLACEHOLDERS = {"", "ここにAPIキー", "your-api-key", "xxx"}
# Google の API キー（AIza で始まる 39 文字）
KEY_PATTERN = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules"}
TEXT_SUFFIXES = {".py", ".bat", ".cmd", ".ps1", ".md", ".toml", ".txt", ".json", ".yaml", ".yml", ".cfg", ".ini", ".example"}

counts = {"要対応": 0, "注意": 0, "OK": 0, "情報": 0}


def report(level: str, msg: str):
    counts[level] += 1
    print(f"[{level}] {msg}")


def section(title: str):
    print(f"\n## {title}")


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def mask(value: str) -> str:
    return f"（{len(value)}文字・値は非表示）"


def parse_dotenv(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        values[k] = v
    return values


def load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:
        report("注意", f"{path} を読めなかった：{type(e).__name__}")
        return {}


def iter_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


# ---------------------------------------------------------------- 1. API キー
def check_api_key():
    section("API キーの読み込み元")
    env_path = ROOT / ".env"
    dotenv = parse_dotenv(env_path) if env_path.exists() else {}

    if not env_path.exists():
        report("情報", ".env は無い（環境変数かサイドバー入力でキーを渡している）")
    else:
        for var in API_KEY_VARS:
            if var in dotenv:
                v = dotenv[var]
                if v in PLACEHOLDERS:
                    report("注意", f".env の {var} が空か見本の文字列のまま")
                else:
                    report("情報", f".env に {var} あり{mask(v)}")
        if "GEMINI_API_KEY" in dotenv and os.environ.get("GEMINI_API_KEY"):
            report("注意", ".env の GEMINI_API_KEY は効かない（load_dotenv は既存の環境変数を上書きしない）")

    # app と同じ規則で、実際に使われる変数を求める（環境変数が .env より優先）
    for var in API_KEY_VARS:
        value = os.environ.get(var) or dotenv.get(var, "")
        if value and value not in PLACEHOLDERS:
            where = "環境変数" if os.environ.get(var) else ".env"
            if var == "WRITING_TOOL_API_KEY":
                report("OK", f"このアプリ専用の {var}（{where}）が使われる{mask(value)}")
            else:
                report("注意", f"{var}（{where}）が使われる{mask(value)}。"
                       "GEMINI_API_KEY は他アプリ（有料枠）と共用。意図どおりか確認する")
            break
    else:
        report("情報", "どの変数にもキーが無い。起動するとサイドバーで手入力になる")


def check_env_storage():
    section(".env の置き場所と管理")
    env_path = ROOT / ".env"
    if env_path.exists():
        if "onedrive" in str(ROOT).lower():
            report("注意", ".env が OneDrive 配下にあり、キーが平文でクラウドに同期される")
        else:
            report("OK", ".env は同期フォルダの外にある")

    git_dir = ROOT / ".git"
    gitignore = ROOT / ".gitignore"
    ignored = gitignore.exists() and any(
        line.strip() in {".env", "/.env", ".env*", "*.env"} for line in gitignore.read_text(encoding="utf-8").splitlines()
    )
    if git_dir.exists():
        if ignored:
            report("OK", ".gitignore に .env が入っている")
        else:
            report("要対応", "git 管理下なのに .gitignore で .env を除外していない")
        if shutil.which("git"):
            r = subprocess.run(["git", "-C", str(ROOT), "ls-files", ".env"], capture_output=True, text=True)
            if r.stdout.strip():
                report("要対応", ".env が git に登録されている（履歴にキーが残る）")
    else:
        report("情報", "git 管理していない。始めるときは .gitignore に .env を先に入れる"
               + ("（.gitignore には既に入っている）" if ignored else ""))


def check_hardcoded_keys():
    section("ソース・設定ファイル中のキーの実物")
    found = False
    for p in iter_files():
        if p.name == ".env" or p.is_relative_to(SKILL_DIR):
            continue
        if p.suffix.lower() not in TEXT_SUFFIXES and not p.name.startswith(".env"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if KEY_PATTERN.search(line):
                report("要対応", f"{rel(p)}:{i} に API キーらしき文字列（値は非表示）")
                found = True
    # .env 以外の .env.* （.env.local など）も実物が入りがち
    for p in ROOT.glob(".env*"):
        if p.name not in {".env", ".env.example"}:
            report("注意", f"{p.name} がある。中身にキーがあれば .env と同じ扱いが要る")
    if not found:
        report("OK", ".env 以外のファイルに Google API キーの形の文字列は無い")


# ---------------------------------------------------------------- 2. Streamlit サーバー設定
def check_server():
    section("Streamlit の待ち受け・サーバー設定")
    project_cfg = load_toml(ROOT / ".streamlit" / "config.toml")
    user_cfg = load_toml(Path.home() / ".streamlit" / "config.toml")

    def get(section_name: str, key: str):
        for cfg in (project_cfg, user_cfg):  # プロジェクトの設定が優先
            if key in cfg.get(section_name, {}):
                return cfg[section_name][key]
        return None

    bat_text = ""
    for bat in ROOT.glob("*.bat"):
        bat_text += bat.read_text(encoding="cp932", errors="replace")

    address = get("server", "address")
    if address in ("localhost", "127.0.0.1", "::1"):
        report("OK", f"server.address = {address}（このPCからしか開けない）")
    elif address:
        report("要対応", f"server.address = {address}。localhost 以外で待ち受けている")
    elif "--server.address" in bat_text:
        report("注意", "起動.bat でだけ --server.address を指定している。"
               "streamlit run を直接打つと全インターフェースで待ち受ける")
    else:
        report("要対応", "server.address が未設定。Streamlit は既定で全インターフェースで待ち受けるため、"
               "同じ LAN の人が http://<このPCのIP>:8501 を開くと、本人のキーで生成できる")

    port = get("server", "port") or 8501
    for key, label in (("enableXsrfProtection", "XSRF 保護"), ("enableCORS", "CORS 保護")):
        if get("server", key) is False:
            report("要対応", f"server.{key} = false（{label}が切られている）")
    if get("server", "enableXsrfProtection") is not False and get("server", "enableCORS") is not False:
        report("OK", "XSRF・CORS 保護は既定（有効）のまま")

    stats = get("browser", "gatherUsageStats")
    if stats is False:
        report("OK", "browser.gatherUsageStats = false（利用統計を送らない）")
    else:
        report("情報", "browser.gatherUsageStats が既定（true）。Streamlit に匿名の利用統計が送られる（入力内容は含まない）")

    # 今まさに起動中なら、実際の待ち受けアドレスを見る
    if os.name == "nt":
        try:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=15).stdout
            out += subprocess.run(["netstat", "-ano", "-p", "TCPv6"], capture_output=True, text=True, timeout=15).stdout
        except Exception:
            out = ""
        listening = [l.split()[1] for l in out.splitlines() if "LISTENING" in l and l.split()[1].endswith(f":{port}")]
        if not listening:
            report("情報", f"ポート {port} で起動中のものは無い（設定からの判断のみ）")
        for addr in sorted(set(listening)):
            host = addr.rsplit(":", 1)[0]
            if host in ("0.0.0.0", "[::]"):
                report("要対応", f"いま {addr} で待ち受けている（LAN から開ける状態で起動中）")
            else:
                report("OK", f"いま {addr} で待ち受けている")


# ---------------------------------------------------------------- 3. コード中の危険な書き方
RISKY = [
    (r"unsafe_allow_html\s*=\s*True", "要対応", "HTML をそのまま表示している。生成結果を流していないか確認"),
    (r"\bst\.html\(|components\.v1\.html|components\.html\(", "要対応", "HTML を埋め込んでいる。生成結果を流していないか確認"),
    (r"\beval\(|\bexec\(", "要対応", "eval/exec がある"),
    (r"\bsubprocess\b|\bos\.system\(", "注意", "外部コマンドを実行している"),
    (r"\bpickle\b", "注意", "pickle を使っている"),
    (r"\btools\s*=", "注意", "モデルに道具（tools）を渡している。プロンプトインジェクションの影響が文章の外に及ぶ"),
]


def check_code():
    section("コード中の書き方")
    sources = [p for p in iter_files() if p.suffix == ".py" and not p.is_relative_to(SKILL_DIR)]
    hits = 0
    for p in sources:
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for pattern, level, msg in RISKY:
                if re.search(pattern, line):
                    report(level, f"{rel(p)}:{i} {msg}")
                    hits += 1
    if not hits:
        report("OK", "HTML 埋め込み・eval/exec・外部コマンド・pickle・tools 指定は無い")

    client = ROOT / "gemini_client.py"
    if client.exists():
        text = client.read_text(encoding="utf-8")
        if re.search(r"AutomaticFunctionCallingConfig\(\s*disable\s*=\s*True", text):
            report("OK", "自動関数呼び出し（AFC）は無効。モデルは文章を返すだけ")
        else:
            report("注意", "AFC を無効にする指定が見当たらない。tools を渡していないか確認")

    app = ROOT / "app.py"
    if app.exists():
        text = app.read_text(encoding="utf-8")
        m = re.search(r'st\.text_input\([^)]*API[^)]*\)', text)
        if m and 'type="password"' not in m.group(0):
            report("要対応", "サイドバーのキー入力欄が password 型になっていない")
        elif m:
            report("OK", "キー入力欄は password 型")
        if re.search(r"st\.(error|exception)\([^)]*\{e\}", text):
            report("情報", "例外メッセージをそのまま画面に出している箇所がある（キーが含まれないか要確認）")


# ---------------------------------------------------------------- 4. 依存パッケージ
def check_deps():
    section("依存パッケージ")
    req = ROOT / "requirements.txt"
    if req.exists():
        loose = [l.strip() for l in req.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#") and "==" not in l]
        if loose:
            report("情報", f"バージョンを固定していない：{', '.join(loose)}（入れ直すと版が変わる）")
    for name in ("streamlit", "google-genai", "python-dotenv"):
        try:
            report("情報", f"{name} {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            report("注意", f"{name} が入っていない")

    try:
        importlib.metadata.version("pip-audit")
        r = subprocess.run([sys.executable, "-m", "pip_audit", "-r", str(req), "--progress-spinner", "off"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            report("OK", "pip-audit：既知の脆弱性は見つからなかった")
        else:
            report("要対応", "pip-audit が既知の脆弱性を報告した：\n" + (r.stdout or r.stderr).strip())
    except importlib.metadata.PackageNotFoundError:
        report("情報", "pip-audit が無いので既知の脆弱性は照合していない（pip install pip-audit で可能）")
    except subprocess.TimeoutExpired:
        report("情報", "pip-audit が時間内に終わらなかった")


def main():
    print(f"# セキュリティ点検（機械的な項目）: {ROOT}")
    check_api_key()
    check_env_storage()
    check_hardcoded_keys()
    check_server()
    check_code()
    check_deps()
    print("\n## 集計")
    print("、".join(f"{k} {v}件" for k, v in counts.items()))


if __name__ == "__main__":
    main()
