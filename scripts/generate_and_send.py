"""
放射線技師note下書き 自動生成・送信スクリプト。
GitHub Actionsのcronから毎日実行される想定。

必要な環境変数(GitHub Actions Secretsから注入):
  ANTHROPIC_API_KEY   - Claude API キー
  OPENAI_API_KEY      - OpenAI Images API キー
  GMAIL_SENDER        - 送信元Gmailアドレス
  GMAIL_APP_PASSWORD  - 送信元Gmailのアプリパスワード(16文字連続、スペースなし)
  GMAIL_RECIPIENT     - 送信先メールアドレス
"""

import base64
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = REPO_ROOT / "state" / "used_themes.json"

GENRES = [
    "国家試験対策", "実務Tips", "患者向け解説", "キャリア・働き方",
    "学生時代あるある", "撮影技術・画像処理", "被曝管理", "検査説明",
    "若手技師の失敗談",
]

IMAGE_STYLES = [
    "パステル調フラットイラスト", "ネイビー×ホワイトの医療系配色",
    "線画+ワンポイントカラー", "アイソメトリック風のCT・X線機器イラスト",
    "温かみのある手描き風",
]

CONSTRAINTS = """\
# 制約(厳守)
- 断定的な医療診断・治療方針の提示はしない。「一般的には」「経験則では」という形で伝える
- 患者や同僚が特定できる実例は使わず、一般化・匿名化する
- 著作権のある教科書・論文の文章をそのまま引用せず、自分の言葉で説明する
- 個人が特定される患者情報、勤務先の内部情報は含めない
- 「絶対に」「必ず治る」等の医療的断定・煽り表現は禁止"""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string", "enum": GENRES},
        "image_style": {"type": "string", "enum": IMAGE_STYLES},
        "title": {"type": "string"},
        "alt_titles": {"type": "array", "items": {"type": "string"}, "description": "キャッチーなタイトル別案をちょうど2つ"},
        "lead": {"type": "string", "description": "無料部分のリード文"},
        "body_markdown": {
            "type": "string",
            "description": "見出しごとの本文。有料ラインを本文中に '---ここから有料---' で明示すること。",
        },
        "summary_cta": {"type": "string", "description": "まとめ・次のアクション"},
        "price": {"type": "string"},
        "price_reason": {"type": "string"},
        "image_prompt": {"type": "string", "description": "見出し画像生成用の英語プロンプト。文字は入れずイラストのみ、横長構図。"},
    },
    "required": [
        "genre", "image_style", "title", "alt_titles", "lead",
        "body_markdown", "summary_cta", "price", "price_reason", "image_prompt",
    ],
    "additionalProperties": False,
}


def load_history() -> list[dict]:
    if not STATE_PATH.exists():
        return []
    return json.loads(STATE_PATH.read_text(encoding="utf-8")).get("history", [])


def save_history(history: list[dict]) -> None:
    STATE_PATH.write_text(
        json.dumps({"history": history[-30:]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_prompt(history: list[dict]) -> str:
    recent = history[-10:]
    recent_summary = "\n".join(
        f"- {h['date']}: genre={h['genre']}, title={h['title']}, image_style={h['image_style']}"
        for h in recent
    ) or "(過去の実行記録なし)"

    return f"""あなたは放射線技師の専門性を活かしたnote有料記事を自動生成するエージェントです。

{CONSTRAINTS}

# 直近の実行履歴(このテーマ・タイトル・画像スタイルと重複しない新しい切り口を選ぶこと)
{recent_summary}

# ジャンル候補
{", ".join(GENRES)}

# 画像スタイル候補(直近履歴と異なるものを選ぶこと)
{", ".join(IMAGE_STYLES)}

# 手順
1. 直近履歴と重複しないジャンル・テーマを選ぶ。
2. 記事本文を執筆する。です/ます調。有資格者だからこそ書ける実務感覚を前面に。
   - タイトル(最終決定したもの)
   - リード文(無料部分、続きが気になる引き)
   - 本文(見出しごとに執筆、有料ラインを明示: 「---ここから有料---」)
   - まとめ・次のアクション(マガジン登録や次記事への誘導)
   - 価格とその理由(単発 or マガジンどちらが向くか、根拠付き)
   - キャッチーなタイトル別案を2つ(SNS拡散も意識)
3. 見出し画像のプロンプトを作成する(英語)。直近履歴の画像スタイルと重複しないスタイル・配色・構図にすること。文字は入れずイラストのみ、横長構図。

指定されたJSONスキーマに従って出力してください。"""


def generate_draft(history: list[dict]) -> dict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": "high",
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        messages=[{"role": "user", "content": build_prompt(history)}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def generate_image(image_prompt: str) -> Path:
    resp = requests.post(
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        json={"model": "gpt-image-1", "prompt": image_prompt, "size": "1536x1024", "n": 1},
        timeout=120,
    )
    resp.raise_for_status()
    b64_data = resp.json()["data"][0]["b64_json"]
    out_path = REPO_ROOT / "note_header.png"
    out_path.write_bytes(base64.b64decode(b64_data))
    return out_path


def build_email_body(draft: dict) -> str:
    alt_titles = "\n".join(f"{i}. {t}" for i, t in enumerate(draft["alt_titles"], 1))
    return f"""{draft['lead']}

{draft['body_markdown']}

{draft['summary_cta']}

--- 価格 ---
{draft['price']}
{draft['price_reason']}

--- タイトル別案 ---
{alt_titles}

--- 今回の記録(重複防止用) ---
ジャンル: {draft['genre']} / 画像スタイル: {draft['image_style']}"""


def send_email(draft: dict, image_path: Path, date_str: str) -> None:
    sender = os.environ["GMAIL_SENDER"]
    recipient = os.environ["GMAIL_RECIPIENT"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = f"【note下書き】{draft['title']} - {date_str}"
    msg.attach(MIMEText(build_email_body(draft), "plain", "utf-8"))

    with open(image_path, "rb") as f:
        img = MIMEImage(f.read(), name=f"note_header_{date_str}.png")
        msg.attach(img)

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls(context=context)
        server.login(sender, app_password)
        server.sendmail(sender, recipient, msg.as_string())


def main() -> None:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = load_history()

    draft = generate_draft(history)
    image_path = generate_image(draft["image_prompt"])
    send_email(draft, image_path, date_str)

    history.append({
        "date": date_str,
        "genre": draft["genre"],
        "title": draft["title"],
        "image_style": draft["image_style"],
    })
    save_history(history)
    print(f"sent: {draft['title']}")


if __name__ == "__main__":
    main()
