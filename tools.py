"""ライティングツールの定義。

ツールを追加するときは、Tool を1つ作って TOOLS に足すだけでよい。
画面（入力欄）は fields から自動で組み立てられる。
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Field:
    key: str
    label: str
    kind: str  # "text" | "textarea" | "select" | "slider" | "checkbox"
    options: list[str] = field(default_factory=list)  # select 用
    default: object = None
    min_value: int = 0  # slider 用
    max_value: int = 0
    step: int = 1
    placeholder: str = ""
    help: str = ""
    required: bool = False
    height: int = 150  # textarea 用


@dataclass
class Tool:
    key: str
    name: str
    icon: str
    description: str
    fields: list[Field]
    build_prompt: Callable[[dict], str]
    system: str
    temperature: float = 0.7


BASE_SYSTEM = (
    "あなたは日本語の文章作成に長けたプロのライターです。"
    "依頼された成果物だけを出力し、「承知しました」などの前置きや、最後の補足・感想は書かないでください。"
    "事実が不明な箇所は推測で断定せず、［要確認：〜］の形で示してください。"
)

TONES = ["丁寧", "フレンドリー", "カジュアル", "フォーマル", "専門的", "熱意がある"]


def _opt(label: str, value) -> str:
    """任意入力が空なら行ごと省く。"""
    return f"- {label}：{value}\n" if value else ""


# ---------------------------------------------------------------- ブログ記事
def _blog(v: dict) -> str:
    return (
        "次の条件でブログ記事を書いてください。\n\n"
        f"- テーマ：{v['theme']}\n"
        + _opt("含めたいキーワード", v["keywords"])
        + _opt("想定読者", v["audience"])
        + f"- 文字数の目安：約{v['length']}字\n"
        f"- トーン：{v['tone']}\n"
        + _opt("盛り込みたい内容・メモ", v["notes"])
        + "\n出力形式：Markdown。タイトル（# 見出し）、導入、"
        "H2/H3 の見出しで区切った本文、まとめの順に構成すること。"
        + ("\n記事の後に、SEO 用のメタディスクリプション（120字以内）を「---」で区切って付けること。" if v["meta"] else "")
    )


# ---------------------------------------------------------------- メール返信
def _email(v: dict) -> str:
    return (
        "次の受信メールへの返信文を書いてください。\n\n"
        f"【受信メール】\n{v['received']}\n\n"
        f"【返信で伝えたいこと】\n{v['intent'] or '（特になし。内容に沿って適切に返信）'}\n\n"
        f"- 相手との関係：{v['relation']}\n"
        f"- トーン：{v['tone']}\n"
        + _opt("署名に使う名前", v["sender"])
        + f"\n返信案を{v['variants']}通り、それぞれ件名と本文をつけて出力してください。"
        "複数案の場合は「## 案1」のように見出しで区切ってください。"
    )


# ---------------------------------------------------------------- 要約
_SUMMARY_FORMATS = {
    "箇条書き": "重要なポイントを箇条書きで",
    "3行まとめ": "ちょうど3行で",
    "段落（文章）": "読みやすい文章（段落）で",
    "要点＋次のアクション": "「要点」と「次にとるべきアクション」の2つの見出しに分けて箇条書きで",
    "TL;DR＋詳細": "冒頭に1文の TL;DR、その後に詳細な要約を",
}


def _summary(v: dict) -> str:
    return (
        f"次の文章を{_SUMMARY_FORMATS[v['format']]}要約してください。"
        f"長さは「{v['length']}」程度にしてください。原文にない情報は加えないこと。\n"
        + (f"特に「{v['focus']}」の観点を重視してください。\n" if v["focus"] else "")
        + f"\n【原文】\n{v['text']}"
    )


# ---------------------------------------------------------------- 校正・リライト
_REWRITE_MODES = {
    "校正（誤字脱字・文法チェック）": (
        "誤字脱字・文法の誤り・表記ゆれを直してください。文体や内容は変えないこと。"
        "修正後の全文を出したあと、「## 修正箇所」として変更点を「修正前 → 修正後（理由）」の形で一覧にしてください。"
    ),
    "読みやすく": "意味を変えずに、一文を短くし、構成を整えて読みやすく書き直してください。",
    "より丁寧に": "ビジネスでも失礼のない、丁寧な表現に書き直してください。",
    "簡潔に": "冗長な表現を削り、要点が伝わる簡潔な文章にしてください。",
    "カジュアルに": "親しみやすいカジュアルな口調に書き直してください。",
    "説得力を高める": "論理の流れを整え、根拠や具体性を補強して説得力のある文章にしてください。",
}


def _rewrite(v: dict) -> str:
    return (
        _REWRITE_MODES[v["mode"]]
        + "\n"
        + _opt("補足の指示", v["extra"])
        + f"\n【対象の文章】\n{v['text']}"
    )


# ---------------------------------------------------------------- 翻訳
def _translate(v: dict) -> str:
    return (
        f"次の文章を{v['target']}に翻訳してください。文体：{v['style']}。\n"
        + ("訳文のあとに「## 訳注」として、訳し方に迷った箇所や文化的な補足を短く書いてください。\n" if v["notes"] else "訳文だけを出力してください。\n")
        + f"\n【原文】\n{v['text']}"
    )


# ---------------------------------------------------------------- SNS 投稿
_SNS_RULES = {
    "X（旧Twitter）": "1投稿あたり全角140字以内",
    "Instagram": "最初の1行で惹きつけ、改行を多めに。絵文字を適度に使う",
    "Facebook": "やや長めでもよい。親しみやすく、最後に問いかけを入れる",
    "LinkedIn": "ビジネス向け。学びや知見が伝わる構成にする",
    "Threads": "会話調で短め。500字以内",
}


def _sns(v: dict) -> str:
    return (
        f"{v['platform']}向けの投稿文を{v['variants']}案作ってください。\n\n"
        f"【伝えたい内容】\n{v['content']}\n\n"
        f"- プラットフォームの作法：{_SNS_RULES[v['platform']]}\n"
        f"- トーン：{v['tone']}\n"
        + ("- 各案の末尾に関連するハッシュタグを3〜5個つける\n" if v["hashtags"] else "- ハッシュタグはつけない\n")
        + "\n各案は「## 案1」のように見出しで区切ってください。"
    )


# ---------------------------------------------------------------- タイトル・キャッチコピー
def _headline(v: dict) -> str:
    return (
        f"次の内容について、{v['purpose']}の案を{v['variants']}個出してください。\n\n"
        f"【内容】\n{v['content']}\n\n"
        f"- トーン：{v['tone']}\n"
        + _opt("ターゲット", v["audience"])
        + "\n番号つきリストで出し、各案の後ろに（ ）でねらいを一言添えてください。"
        "切り口（数字・問いかけ・ベネフィット・意外性など）が重ならないようにしてください。"
    )


# ---------------------------------------------------------------- 議事録・メモ整形
def _minutes(v: dict) -> str:
    return (
        f"次の走り書きのメモを、整理された{v['format']}にしてください。\n"
        "メモにない発言や決定事項を創作しないこと。日時・参加者が不明なら［要確認］と書くこと。\n"
        + (
            "構成：会議名／日時／参加者／議題ごとの要点／決定事項／ToDo（担当・期限）／次回予定。\n"
            if v["format"] == "議事録"
            else ""
        )
        + f"\n【メモ】\n{v['memo']}"
    )


# ---------------------------------------------------------------- アイデア出し
def _ideas(v: dict) -> str:
    return (
        f"「{v['topic']}」について、アイデアを{v['variants']}個出してください。\n"
        + _opt("前提・制約", v["constraints"])
        + "\n番号つきリストで、各アイデアは「見出し：1〜2文の説明」の形にしてください。"
        "似たアイデアを並べず、実現しやすいものから大胆なものまで幅を持たせてください。"
    )


# ---------------------------------------------------------------- 自由入力
def _free(v: dict) -> str:
    return v["prompt"]


TOOLS: list[Tool] = [
    Tool(
        key="blog",
        name="ブログ記事",
        icon="📝",
        description="テーマとキーワードから、見出し構成つきのブログ記事を書きます。",
        fields=[
            Field("theme", "テーマ", "text", required=True, placeholder="例：在宅勤務で集中力を保つコツ"),
            Field("keywords", "含めたいキーワード（任意）", "text", placeholder="例：ポモドーロ、作業環境、休憩"),
            Field("audience", "想定読者（任意）", "text", placeholder="例：在宅勤務を始めたばかりの会社員"),
            Field("length", "文字数の目安", "slider", default=2000, min_value=500, max_value=6000, step=500),
            Field("tone", "トーン", "select", options=TONES, default="フレンドリー"),
            Field("notes", "盛り込みたい内容・メモ（任意）", "textarea", height=100),
            Field("meta", "メタディスクリプションもつける", "checkbox", default=True),
        ],
        build_prompt=_blog,
        system=BASE_SYSTEM + "読者の役に立つ具体例を入れ、見出しだけ読んでも流れがわかる構成にしてください。",
        temperature=0.8,
    ),
    Tool(
        key="email",
        name="メール返信",
        icon="✉️",
        description="受け取ったメールを貼り付けると、返信文の案を作ります。",
        fields=[
            Field("received", "受信メール", "textarea", required=True, height=200),
            Field("intent", "返信で伝えたいこと（任意）", "textarea", height=100,
                  placeholder="例：日程は来週火曜なら可能。資料は金曜までに送る。"),
            Field("relation", "相手との関係", "select",
                  options=["社外（取引先・顧客）", "社内（上司）", "社内（同僚・部下）", "友人・知人"]),
            Field("tone", "トーン", "select", options=TONES, default="丁寧"),
            Field("sender", "署名に使う名前（任意）", "text"),
            Field("variants", "案の数", "slider", default=1, min_value=1, max_value=3),
        ],
        build_prompt=_email,
        system=BASE_SYSTEM + "日本のビジネスメールの慣習（宛名・挨拶・結び）に沿ってください。",
        temperature=0.6,
    ),
    Tool(
        key="summary",
        name="要約",
        icon="📋",
        description="長い文章を、目的に合った形式で要約します。",
        fields=[
            Field("text", "要約したい文章", "textarea", required=True, height=250),
            Field("format", "形式", "select", options=list(_SUMMARY_FORMATS)),
            Field("length", "長さ", "select", options=["短め", "標準", "詳しめ"], default="標準"),
            Field("focus", "重視する観点（任意）", "text", placeholder="例：費用面、リスク、結論"),
        ],
        build_prompt=_summary,
        system=BASE_SYSTEM,
        temperature=0.3,
    ),
    Tool(
        key="rewrite",
        name="校正・リライト",
        icon="✏️",
        description="誤字脱字のチェックや、丁寧・簡潔などの書き直しをします。",
        fields=[
            Field("text", "対象の文章", "textarea", required=True, height=250),
            Field("mode", "やりたいこと", "select", options=list(_REWRITE_MODES)),
            Field("extra", "補足の指示（任意）", "text", placeholder="例：「です・ます」調で統一"),
        ],
        build_prompt=_rewrite,
        system=BASE_SYSTEM,
        temperature=0.4,
    ),
    Tool(
        key="translate",
        name="翻訳",
        icon="🌐",
        description="自然な訳文に翻訳します。文体も選べます。",
        fields=[
            Field("text", "原文", "textarea", required=True, height=200),
            Field("target", "翻訳先の言語", "select",
                  options=["英語", "日本語", "中国語（簡体字）", "中国語（繁体字）", "韓国語", "スペイン語", "フランス語", "ドイツ語"]),
            Field("style", "文体", "select", options=["自然", "ビジネス", "カジュアル", "直訳寄り"]),
            Field("notes", "訳注をつける", "checkbox", default=False),
        ],
        build_prompt=_translate,
        system=BASE_SYSTEM.replace("日本語の", "多言語の") + "原文の意味とニュアンスを正確に保ってください。",
        temperature=0.3,
    ),
    Tool(
        key="sns",
        name="SNS投稿",
        icon="📣",
        description="伝えたい内容から、各SNSの作法に合った投稿文を作ります。",
        fields=[
            Field("content", "伝えたい内容", "textarea", required=True, height=150),
            Field("platform", "プラットフォーム", "select", options=list(_SNS_RULES)),
            Field("tone", "トーン", "select", options=TONES, default="フレンドリー"),
            Field("variants", "案の数", "slider", default=3, min_value=1, max_value=5),
            Field("hashtags", "ハッシュタグをつける", "checkbox", default=True),
        ],
        build_prompt=_sns,
        system=BASE_SYSTEM,
        temperature=0.9,
    ),
    Tool(
        key="headline",
        name="タイトル・キャッチコピー",
        icon="💡",
        description="記事タイトルやキャッチコピー、メール件名の案を出します。",
        fields=[
            Field("content", "内容・商品・記事の概要", "textarea", required=True, height=150),
            Field("purpose", "用途", "select",
                  options=["ブログ記事のタイトル", "キャッチコピー", "メールの件名", "YouTube動画のタイトル", "プレゼン資料のタイトル"]),
            Field("audience", "ターゲット（任意）", "text"),
            Field("tone", "トーン", "select", options=TONES, default="熱意がある"),
            Field("variants", "案の数", "slider", default=10, min_value=3, max_value=20),
        ],
        build_prompt=_headline,
        system=BASE_SYSTEM,
        temperature=1.0,
    ),
    Tool(
        key="minutes",
        name="議事録・メモ整形",
        icon="🗂️",
        description="走り書きのメモを、議事録や整理されたノートにまとめます。",
        fields=[
            Field("memo", "メモ", "textarea", required=True, height=250),
            Field("format", "まとめ方", "select", options=["議事録", "整理されたノート", "ToDoリスト"]),
        ],
        build_prompt=_minutes,
        system=BASE_SYSTEM,
        temperature=0.3,
    ),
    Tool(
        key="ideas",
        name="アイデア出し",
        icon="🧠",
        description="企画・ネタ・解決策などのアイデアをたくさん出します。",
        fields=[
            Field("topic", "お題", "text", required=True, placeholder="例：社内勉強会のテーマ"),
            Field("constraints", "前提・制約（任意）", "textarea", height=100),
            Field("variants", "アイデアの数", "slider", default=10, min_value=3, max_value=30),
        ],
        build_prompt=_ideas,
        system=BASE_SYSTEM,
        temperature=1.0,
    ),
    Tool(
        key="free",
        name="自由入力",
        icon="💬",
        description="どのツールにも当てはまらない依頼を自由に書けます。",
        fields=[Field("prompt", "依頼内容", "textarea", required=True, height=200)],
        build_prompt=_free,
        system="あなたは日本語の文章作成に長けたプロのライターです。",
        temperature=0.7,
    ),
]

TOOLS_BY_KEY = {t.key: t for t in TOOLS}


def build_revision_prompt(previous_output: str, instruction: str) -> str:
    return (
        "次の文章を、指示に従って修正してください。修正後の全文だけを出力してください。\n\n"
        f"【指示】\n{instruction}\n\n"
        f"【文章】\n{previous_output}"
    )
