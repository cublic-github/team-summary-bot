import os
import requests
import datetime
import google.generativeai as genai
import json
from flask import Flask, request, jsonify

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = "1024957065686433802"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
JST = datetime.timezone(datetime.timedelta(hours=9), name="JST")


def get_channel_list():
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return [ch for ch in r.json() if ch["type"] == 0]  # type=0: text channel


def get_channel_messages(channel_id, since_iso):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    params = {"limit": 100, "after": since_iso}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()


def build_all_text():
    since = (datetime.datetime.now(JST) - datetime.timedelta(days=1)).isoformat()
    all_text = ""
    for ch in get_channel_list():
        all_text += f"\n\n--- チャンネル: #{ch['name']} ---\n"
        try:
            messages = get_channel_messages(ch["id"], since)
        except Exception as e:
            all_text += f"取得エラー: {e}\n"
            continue
        if not messages:
            all_text += "投稿なし\n"
        else:
            for msg in reversed(messages):
                # 投稿者名・時刻・内容
                dt = datetime.datetime.fromisoformat(
                    msg["timestamp"].replace("Z", "+00:00")
                ).astimezone(JST)
                time_str = dt.strftime("%H:%M")
                author = msg["author"]["username"]
                content = msg["content"]
                all_text += f"{time_str} {author}: {content}\n"
    return all_text


def generate_summary(all_text):
    gemini_api_key = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-pro-preview-06-05")
    prompt = f"""【タスク】
チャット履歴を確認し、社内での出来事・動きの全体像を把握するための日次サマリーを作成してください。

【カバレッジ要件】
すべてのチャンネルおよびスレッドを確認してください。
メインチャンネル（例：#出社メンバー連絡用、#制作案件 など）
スレッド（スレッドで進行している会話も対象です）
botによる自動投稿（例：cron、通知系）も含めます。
投稿がなかったチャンネルについても「投稿なし」と明記してください。
時刻・投稿者・主旨を簡潔にまとめてください。
投稿が長文または議論が発展している場合は、要点に絞ってまとめてください。

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

#〇〇
 • 投稿なし

【備考】
レスポンスには、"はい、承知いたしました"などの文章は含めないでください。
タイトルはすでに手動で記述しているので、不要です。本文から始めてください。
内容は要約で構いませんが、抜け漏れがないようにしてください。
引用が必要な場合は、スクリーンショット・Discordメッセージリンク・原文引用なども適宜利用してください。
全チャンネルを確認済みであることがわかるようにしてください（例：見落としのないよう、チャンネルごとに「投稿なし」も含める）。

---
【実際のチャット履歴】
{all_text}
---
"""
    response = model.generate_content(prompt)
    return response.text


app = Flask(__name__)


@app.route("/api/daily-summary", methods=["POST"])
def daily_summary():
    try:
        all_text = build_all_text()
        summary = generate_summary(all_text)
        today = datetime.datetime.now(JST)
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        day_of_week = weekdays[today.weekday()]
        title = f"🗓️ {today.strftime('%Y年%m月%d日')}（{day_of_week}）投稿サマリー（全チャンネル確認済）\n\n"
        final_summary = title + summary
        # Discordに投稿
        data = {"content": final_summary}
        r = requests.post(
            WEBHOOK_URL,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"},
        )
        if r.status_code in (200, 204):
            return jsonify(
                {"status": "success", "message": "投稿完了", "summary": final_summary}
            )
        else:
            return jsonify({"status": "error", "message": f"投稿失敗: {r.text}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
