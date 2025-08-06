import os
import requests
import datetime
import google.generativeai as genai
import json
from flask import Flask, request, jsonify

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
GUILD_ID = "1024957065686433802"
WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]


def get_channel_list():
    url = f"https://discord.com/api/v10/guilds/{GUILD_ID}/channels"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return [ch for ch in r.json() if ch["type"] == 0]  # type=0: text channel


def get_channel_messages(channel_id, since):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    params = {"limit": 100, "after": since}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()


def generate_summary(all_text):
    gemini_api_key = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel("gemini-2.5-pro-preview-06-05")
    prompt = f"【タスク】\n{all_text}\n---"
    response = model.generate_content(prompt)
    return response.text


app = Flask(__name__)


@app.route("/api/daily-summary", methods=["POST"])
def daily_summary():
    # ここでサマリーを生成する（AI要約など）
    summary = "ここにサマリー本文"
    # WebhookでDiscordに投稿
    data = {"content": summary}
    r = requests.post(
        WEBHOOK_URL, data=json.dumps(data), headers={"Content-Type": "application/json"}
    )
    if r.status_code == 204:
        return jsonify({"status": "success", "message": "投稿完了"})
    else:
        return jsonify({"status": "error", "message": f"投稿失敗: {r.text}"}), 500
