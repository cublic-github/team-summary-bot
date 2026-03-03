import os
from dotenv import load_dotenv

load_dotenv()  # .envファイルから環境変数を読み込む
import requests
import datetime
from google import genai
from google.genai import types
import json
from flask import Flask, request, jsonify
import logging
import sys

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = "1024957065686433802"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
JST = datetime.timezone(datetime.timedelta(hours=9), name="JST")

# 分析対象外のチャンネルIDリスト
EXCLUDED_CHANNEL_IDS = {
    "1149603662361014282",  # ユニコントロールズhotprofile通知
}

DISCORD_LOG_WEBHOOK_URL = os.getenv("DISCORD_LOG_WEBHOOK_URL")

MEMBER_LIST = [
    {
        "member_name": "酒井",
        "id": "1349135457463570604",
        "username": "jiujing_97925",
        "global_name": "酒井",
        "nick": None,
    },
    {
        "member_name": "原田",
        "id": "799519737612730378",
        "username": "yuki.harada",
        "global_name": "yuki harada",
        "nick": "Yuki Harada",
    },
    {
        "member_name": "鈴木",
        "id": "790129940002766859",
        "username": "axis1996jp",
        "global_name": "T.Suzuki",
        "nick": "Suzuki.T 平日10–19時/1時間ごと確認/全力貢献",
    },
    {
        "member_name": "中尾",
        "id": "1376722971602718720",
        "username": "nakao_tn_87506",
        "global_name": "中尾鷹也/Nakao Takanari（9/17稼働不可）",
        "nick": None,
    },
    {
        "member_name": "馬越",
        "id": "1113729171617763369",
        "username": "kentaumakoshi",
        "global_name": "Kenta Umakoshi",
        "nick": None,
    },
    {
        "member_name": "友梨",
        "id": "824598422778413067",
        "username": "yuri_0219_",
        "global_name": "ゆり",
        "nick": "yuri suzuki",
    },
    {
        "member_name": "川嵜",
        "id": "1229319365128749106",
        "username": "mashu_kawasaki",
        "global_name": "MASHU KAWASAKI",
        "nick": None,
    },
    {
        "member_name": "中村",
        "id": "1212936382205394965",
        "username": "ikuko0713",
        "global_name": "Ikuko Nakamura",
        "nick": None,
    },
    {
        "member_name": "丸山",
        "id": "1367775681878167562",
        "username": "c.maruyama0323",
        "global_name": "まるやま",
        "nick": None,
    },
    {
        "member_name": "安田",
        "id": "975951028799303710",
        "username": "yasuda4832",
        "global_name": "yasuda",
        "nick": None,
    },
    {
        "member_name": "本庄",
        "id": "1377843031134437427",
        "username": "honjo0705_28823",
        "global_name": "HONJO（基本在宅🏠・必要に応じ出勤🏃‍♀️🏢）",
        "nick": None,
    },
    {
        "member_name": "山本",
        "id": "1311876609535508514",
        "username": "yamamotokeiko_48619",
        "global_name": "Yamamoto Keiko",
        "nick": None,
    },
    {
        "member_name": "小島",
        "id": "1045228812998291469",
        "username": "kojima_minako",
        "global_gname": "KojimaMinako",
        "nick": None,
    },
    {
        "member_name": "宮田",
        "id": "1235564478482087956",
        "username": "rimoa_ayaka",
        "global_name": "Ayaka",
        "nick": "Ayaka Miyata",
    },
    {
        "member_name": "大高",
        "id": "1389229069626773624",
        "username": "dagaoyingyou_35561",
        "global_name": "大高瑛祐(毎週木曜日は22時以降対応になります)",
        "nick": None,
    },
]

ID_TO_MEMBER_NAME = {
    e["id"]: e["member_name"] for e in MEMBER_LIST if e.get("member_name")
}


def resolve_member_name(author: dict) -> str:
    uid = (author or {}).get("id")
    if uid and uid in ID_TO_MEMBER_NAME:
        return ID_TO_MEMBER_NAME[uid]
    return (
        (author or {}).get("global_name")
        or (author or {}).get("username")
        or (f"user:{uid}" if uid else "unknown")
    )


class DiscordWebhookHandler(logging.Handler):
    def __init__(self, webhook_url, username="TeamSummaryBot Logs"):
        super().__init__()
        self.webhook_url = webhook_url
        self.username = username

    def emit(self, record):
        try:
            msg = self.format(record)
            # Discordは2000文字制限。少し余裕を見て分割。
            for i in range(0, len(msg), 1800):
                chunk = msg[i : i + 1800]
                data = {"content": f"[{record.levelname}] {chunk}"}
                response = requests.post(
                    self.webhook_url,
                    data=json.dumps(data),
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                # デバッグ用：レスポンスステータスをチェック
                if response.status_code not in (200, 204):
                    print(
                        f"Discord webhook failed: {response.status_code} {response.text}"
                    )
        except Exception as e:
            # ログ送信失敗時はコンソールに出力（デバッグ用）
            print(f"Discord webhook error: {e}")


# カスタムロガーを作成（Flaskのloggerと分離）
logger = logging.getLogger("daily_summary")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# 追加: 親ロガーへの伝播を止める（重複・stderr出力の赤表示を防止）
logger.propagate = False

# Flaskのデフォルトログを無効化してログ重複を防ぐ
logging.getLogger("werkzeug").setLevel(logging.WARNING)


class MaxLevelFilter(logging.Filter):
    def __init__(self, max_level):
        self.max_level = max_level

    def filter(self, record):
        return record.levelno <= self.max_level


_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

# 既存のハンドラーをクリア（重複防止）
logger.handlers.clear()

stdout_handler = logging.StreamHandler(stream=sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.addFilter(MaxLevelFilter(logging.INFO))
stdout_handler.setFormatter(_formatter)
logger.addHandler(stdout_handler)

stderr_handler = logging.StreamHandler(stream=sys.stderr)
stderr_handler.setLevel(logging.WARNING)
stderr_handler.setFormatter(_formatter)
logger.addHandler(stderr_handler)

if DISCORD_LOG_WEBHOOK_URL:
    _discord = DiscordWebhookHandler(DISCORD_LOG_WEBHOOK_URL)
    # INFOレベル以上をDiscordに送信（成功メッセージも含める）
    DISCORD_LOG_LEVEL = os.getenv("DISCORD_LOG_LEVEL", "INFO").upper()
    _discord.setLevel(getattr(logging, DISCORD_LOG_LEVEL, logging.INFO))
    _discord.setFormatter(_formatter)
    logger.addHandler(_discord)


def get_channel_list():
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return [
        ch for ch in r.json()
        if ch["type"] == 0 and ch["id"] not in EXCLUDED_CHANNEL_IDS
    ]


def get_channel_messages(channel_id, since_dt, *, kind="channel", name=None):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    params = {"limit": 100}
    r = requests.get(url, headers=headers, params=params)
    logger.info(f"{kind.title()}: {name or channel_id}, Status: {r.status_code}")
    if r.status_code == 403:
        logger.warning("  → 権限なし")
        return None
    if r.status_code != 200:
        logger.error(f"  → エラー: {r.text}")
        _log_error_to_discord(
            "❌ get_channel_messages:",
            f"{kind}={name or channel_id} status={r.status_code} body={r.text[:200]}",
        )
        return None
    messages = r.json()
    filtered = []
    for msg in messages:
        msg_dt = datetime.datetime.fromisoformat(
            msg["timestamp"].replace("Z", "+00:00")
        )
        if msg_dt > since_dt:
            filtered.append(msg)
    logger.info(f"  → {len(filtered)}件のメッセージを取得")
    return filtered


# 追加: ギルド内のアクティブなスレッド一覧
def get_active_threads():
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/threads/active"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json().get("threads", [])  # threads配列


# 追加: チャンネルの公開アーカイブ済みスレッド（直近分）
def get_public_archived_threads(channel_id, before=None):
    url = f"https://discord.com/api/v10/channels/{channel_id}/threads/archived/public"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    params = {}
    if before:
        params["before"] = before  # ISO8601文字列
    r = requests.get(url, headers=headers, params=params, timeout=15)
    if r.status_code == 403:
        return []
    r.raise_for_status()
    return r.json().get("threads", [])


def build_all_text():
    since_dt = datetime.datetime.now(JST) - datetime.timedelta(days=1)
    all_text = ""

    active_threads = get_active_threads()  # 先に全アクティブ取得
    threads_by_parent = {}
    for t in active_threads:
        pid = t.get("parent_id")
        if pid:
            threads_by_parent.setdefault(pid, []).append(t)

    for ch in get_channel_list():
        logger.info(f"--- チャンネル: #{ch['name']} ---")
        # 本体メッセージ
        messages = get_channel_messages(
            ch["id"], since_dt, kind="channel", name=ch["name"]
        )
        if messages is None:
            logger.info("  → スキップ")
        else:
            all_text += f"\n\n--- チャンネル: #{ch['name']} ---\n"
            if not messages:
                all_text += "投稿なし\n"
            else:
                for msg in reversed(messages):
                    dt = datetime.datetime.fromisoformat(
                        msg["timestamp"].replace("Z", "+00:00")
                    ).astimezone(JST)
                    name = resolve_member_name(msg["author"])
                    all_text += f"{dt.strftime('%H:%M')} {name}: {msg['content']}\n"

        # スレッド（アクティブ）
        for t in threads_by_parent.get(ch["id"], []):
            all_text += f"\n--- スレッド: {t.get('name','(no title)')} ---\n"
            t_msgs = get_channel_messages(
                t["id"], since_dt, kind="thread", name=t.get("name", "(no title)")
            )
            if not t_msgs:
                all_text += "投稿なし\n"
            else:
                for msg in reversed(t_msgs):
                    dt = datetime.datetime.fromisoformat(
                        msg["timestamp"].replace("Z", "+00:00")
                    ).astimezone(JST)
                    name = resolve_member_name(msg["author"])
                    all_text += f"{dt.strftime('%H:%M')} {name}: {msg['content']}\n"

        # スレッド（公開アーカイブの直近分も拾う・必要に応じて）
        archived = get_public_archived_threads(ch["id"])
        for t in archived:
            # 直近24hに関わるものだけ
            meta = t.get("thread_metadata", {})
            arch_ts = meta.get("archive_timestamp")
            if arch_ts:
                arch_dt = datetime.datetime.fromisoformat(
                    arch_ts.replace("Z", "+00:00")
                )
                if arch_dt < since_dt:
                    continue
            all_text += (
                f"\n--- スレッド(アーカイブ): {t.get('name','(no title)')} ---\n"
            )
            t_msgs = get_channel_messages(
                t["id"], since_dt, kind="thread", name=t.get("name", "(no title)")
            )
            if not t_msgs:
                all_text += "投稿なし\n"
            else:
                for msg in reversed(t_msgs):
                    dt = datetime.datetime.fromisoformat(
                        msg["timestamp"].replace("Z", "+00:00")
                    ).astimezone(JST)
                    name = resolve_member_name(msg["author"])
                    all_text += f"{dt.strftime('%H:%M')} {name}: {msg['content']}\n"

    return all_text


def generate_summary(all_text):
    # 新SDK: google-genai を使用（APIキーは環境変数 GEMINI_API_KEY から自動取得）
    client = genai.Client()
    model_candidates = ["gemini-3.1-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash"]

    prompt = f"""【タスク】
チャット履歴を確認し、社内での出来事・動きの全体像を把握するための日次サマリーを作成してください。

【カバレッジ要件】
すべてのチャンネルおよびスレッドを確認してください。
メインチャンネル（例：#出社メンバー連絡用、#制作案件 など）
スレッド（スレッドで進行している会話も対象です）
botによる自動投稿（例：cron、通知系）も含めます。
時刻・投稿者・主旨を簡潔にまとめてください。
投稿が長文または議論が発展している場合は、要点に絞ってまとめてください。
サマリーの最後に、AI(あなた)から見たチームのやり取りの中での問題点や改善点、評価できる点などを、率直に（メンバーに忖度せず）述べてください。あなたがもしこの会社のメンバーだったら、どのような行動を取るか、という観点から親身なって、フィードバックをしていただきたいです。

【表記ルール】
投稿者名は必ずメンバー辞書のmember_name（例：酒井、原田、鈴木 等）を使用してください。
Discordのusername／global_name／nickは出力に用いないでください。
入力ログの投稿者名はすでにmember_nameに正規化されています。そのままの表記でまとめてください。

【出力フォーマット（例）】
#出社メンバー連絡用
 • 11:30〜12:30 会議のお知らせ（原田勇樹）
→「ノックがあったら開けてください」と案内あり。

#hotprofile通知
 • 02:00 定期処理：新規名刺データなし（cron）
 • 16:30 定期処理：新規名刺データなし（cron）

#cubic-未来構想
 • 14:20 新提案のブレスト投稿（佐藤）
→『AI議事録連携のPoC』について共有あり。

〜AIからのフィードバック〜
"フィードバックの内容"

【備考】
レスポンスには、"はい、承知いたしました"などの文章は含めないでください。
タイトルはすでに手動で記述しているので、不要です。本文から始めてください。
内容は要約で構いませんが、抜け漏れがないようにしてください。
引用が必要な場合は、スクリーンショット・Discordメッセージリンク・原文引用なども適宜利用してください。

---
【実際のチャット履歴】
{all_text}
---
"""
    last_err = None
    for name in model_candidates:
        try:
            logger.info(f"generate_summary: trying model={name}")
            resp = client.models.generate_content(
                model=name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=10000,
                    temperature=0.2,
                ),
            )
            text = getattr(resp, "text", None)
            if not text:
                try:
                    c0 = (resp.candidates or [None])[0]
                    parts = getattr(getattr(c0, "content", None), "parts", []) or []
                    text = "".join(
                        [(getattr(p, "text", "") or "") for p in parts]
                    ).strip()
                except Exception as e2:
                    logger.warning(f"generate_summary: extract parts failed: {e2}")
                    text = ""
            if text:
                try:
                    usage = getattr(resp, "usage_metadata", None)
                    post_discord_log_direct(f"🧠 model_used={name} usage={usage}")
                except Exception as e_log:
                    logger.warning(f"generate_summary: model log failed: {e_log}")
                return text
            else:
                fr = None
                try:
                    fr = getattr((resp.candidates or [None])[0], "finish_reason", None)
                except Exception:
                    pass
                logger.warning(
                    f"generate_summary: empty text from {name}, finishReason={fr}"
                )
        except Exception as e:
            logger.error(f"generate_summary: {name} failed: {e}")
            _log_error_to_discord("❌ generate_summary:", f"{name} failed: {e}")
            last_err = e

    # 最終フォールバック（必ず str を返す）
    fallback = "（自動生成に失敗しました。入力ログの先頭を添付します）\n\n" + (
        all_text[:800] or ""
    )
    return fallback

    raise last_err or RuntimeError("All model attempts failed")


def post_to_discord(final_summary):
    # 2000文字ごとに分割して送信
    for i in range(0, len(final_summary), 2000):
        chunk = final_summary[i : i + 2000]
        data = {"content": chunk}
        r = requests.post(
            WEBHOOK_URL,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
        )
        if r.status_code not in (200, 204):
            logger.error(f"投稿失敗: {r.status_code} {r.text}")
            _log_error_to_discord(
                "❌ post_to_discord:", f"status={r.status_code} body={r.text[:200]}"
            )
            return False
    return True


def send_discord_log(message):
    if not DISCORD_LOG_WEBHOOK_URL:
        logger.warning("DISCORD_LOG_WEBHOOK_URL not configured")
        return
    try:
        response = requests.post(
            DISCORD_LOG_WEBHOOK_URL,
            data=json.dumps({"content": message}),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if response.status_code not in (200, 204):
            logger.error(
                f"Discord log webhook failed: {response.status_code} {response.text}"
            )
    except Exception as e:
        logger.error(f"Discord log webhook error: {e}")


def post_discord_log_direct(content):
    if not DISCORD_LOG_WEBHOOK_URL:
        return False, "DISCORD_LOG_WEBHOOK_URL not set"
    try:
        resp = requests.post(
            DISCORD_LOG_WEBHOOK_URL,
            data=json.dumps({"content": content}),
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        if resp.status_code not in (200, 204):
            return False, f"{resp.status_code} {resp.text}"
        return True, None
    except Exception as e:
        return False, str(e)


def _log_error_to_discord(prefix, message):
    try:
        ok, err = post_discord_log_direct(f"{prefix} {message}")
        if not ok:
            logger.warning(f"Discord log send failed: {err}")
    except Exception as e:
        # 最後の砦としてWARNに残す（Discord側が落ちている場合など）
        logger.warning(f"Discord log send exception: {e}")


app = Flask(__name__)

# 既存
app.logger.setLevel(logging.WARNING)

# 追加: Flask ロガーも親へ伝播させない
app.logger.propagate = False


@app.route("/api/daily-summary", methods=["GET", "POST"])
def daily_summary():
    ok, err = post_discord_log_direct("🚀 daily-summary 開始")
    if not ok:
        logger.warning(f"Discord開始通知失敗: {err}")

    logger.info("daily-summary: job started")
    all_text = build_all_text()
    logger.info(f"daily-summary: collected text length={len(all_text)}")
    summary = generate_summary(all_text)
    if not summary:
        logger.error("generate_summary returned empty; using fallback text")
        summary = "（自動生成に失敗しました）"

    target = datetime.datetime.now(JST) - datetime.timedelta(days=1)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    day_of_week = weekdays[target.weekday()]
    title = f"🗓️ {target.strftime('%Y年%m月%d日')}（{day_of_week}）サマリー\n\n"
    final_summary = title + summary
    ok2 = post_to_discord(final_summary)
    logger.info(
        f"daily-summary: post_to_discord ok={ok2} total_length={len(final_summary)}"
    )
    if ok2:
        # 成功時も直送（任意）
        post_discord_log_direct("✅ daily-summary 成功")
    else:
        logger.error("❌ daily-summary 失敗")
    return jsonify({"status": "success", "summary": final_summary})


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback

    error_msg = f"Exception in daily-summary: {str(e)}\n{traceback.format_exc()}"
    logger.error(error_msg)
    try:
        _log_error_to_discord("🔥 unhandled:", error_msg[:1500])
    except Exception:
        pass
    return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    app.run(host="0.0.0.0", port=5001, debug=True)
