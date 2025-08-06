import discord
import os
import datetime
import google.generativeai as genai
import asyncio
from typing import Dict, Any
import json

# ---------------------------------
# ▼▼▼ 設定項目 ▼▼▼
# ---------------------------------
# サマリーを投稿したいサーバーのID
TARGET_GUILD_ID = 1024957065686433802

# サマリーを投稿したいチャンネルのID
TARGET_CHANNEL_ID = 1321289060693704795

# タイムゾーンを日本時間に設定
JST = datetime.timezone(datetime.timedelta(hours=9), name="JST")
# ---------------------------------

# Botの権限（Intent）を設定
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True


async def create_discord_summary():
    """Discordサーバーのサマリーを作成する関数"""

    # Discord Clientの初期化
    client = discord.Client(intents=intents)

    try:
        # Discordにログイン
        discord_token = os.environ.get("DISCORD_TOKEN")
        if not discord_token:
            raise Exception("DISCORD_TOKEN環境変数が設定されていません")

        await client.login(discord_token)

        guild = client.get_guild(TARGET_GUILD_ID)
        channel_to_post = client.get_channel(TARGET_CHANNEL_ID)

        if not guild or not channel_to_post:
            raise Exception(
                f"サーバー(ID: {TARGET_GUILD_ID})またはチャンネル(ID: {TARGET_CHANNEL_ID})が見つかりません"
            )

        print(f"\n--- {guild.name} のサマリー作成開始 ---")

        # --- 1. 権限のある全チャンネルとスレッドからチャット履歴を取得 ---
        since = datetime.datetime.now(JST) - datetime.timedelta(days=1)
        all_text = ""
        print("📊 チャンネル権限の確認とチャット履歴の取得を開始します...")

        # サーバー内のすべてのテキストチャンネルをループ
        for channel in guild.text_channels:
            # Botがそのチャンネルの「メッセージ履歴を読む」権限を持っているかチェック
            if not channel.permissions_for(guild.me).read_message_history:
                print(f"  ❌ 閲覧不可: #{channel.name}")
                continue

            print(f"  ✅ 閲覧可能: #{channel.name}")
            all_text += f"\n\n--- チャンネル: #{channel.name} ---\n"

            # チャンネル内のメッセージを取得
            messages = [
                msg
                async for msg in channel.history(after=since, limit=100)
                if msg.content
            ]
            if not messages:
                all_text += "投稿なし\n"
            else:
                for msg in reversed(messages):
                    all_text += f"{msg.created_at.astimezone(JST).strftime('%H:%M')} {msg.author.display_name}: {msg.content}\n"

            # チャンネル内のアクティブなスレッドを取得
            for thread in channel.threads:
                if thread.archived:
                    continue
                print(f"    🧵 スレッド: {thread.name}")
                all_text += f"\n--- スレッド: {thread.name} ---\n"
                thread_messages = [
                    msg
                    async for msg in thread.history(after=since, limit=100)
                    if msg.content
                ]
                if not thread_messages:
                    all_text += "投稿なし\n"
                else:
                    for msg in reversed(thread_messages):
                        all_text += f"{msg.created_at.astimezone(JST).strftime('%H:%M')} {msg.author.display_name}: {msg.content}\n"

        if not all_text.strip():
            await channel_to_post.send("過去24時間のチャットはありませんでした。")
            print("📪 要約対象メッセージなし。")
            return {"status": "success", "message": "要約対象メッセージなし"}

        # --- 2. Gemini APIに要約を依頼 ---
        print("🧠 Gemini APIに要約を依頼中...")
        ai_response_body = ""
        try:
            gemini_api_key = os.environ.get("GEMINI_API_KEY")
            if not gemini_api_key:
                raise Exception("GEMINI_API_KEY環境変数が設定されていません")

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
            # AIの処理を実行
            response = model.generate_content(prompt)
            ai_response_body = response.text

        except Exception as e:
            ai_response_body = f"AIによる要約中にエラーが発生しました: {e}"
            print(f"❌ AI APIエラー: {e}")

        # --- 3. 結果をDiscordに投稿 ---
        today = datetime.datetime.now(JST)
        weekdays = ["月", "火", "水", "木", "金", "土", "日"]
        day_of_week = weekdays[today.weekday()]
        title = f"🗓️ {today.strftime('%Y年%m月%d日')}（{day_of_week}）投稿サマリー\n\n"

        print(ai_response_body)

        # タイトルとAIの要約本文を結合
        final_summary = title + ai_response_body

        print(f"📬 チャンネル「#{channel_to_post.name}」にサマリーを投稿します。")

        # Discordの文字数制限（2000文字）に対応して分割投稿
        for i in range(0, len(final_summary), 2000):
            await channel_to_post.send(final_summary[i : i + 2000])

        print("✅ サマリー投稿完了。")
        print(f"--- 処理終了 ---")

        return {
            "status": "success",
            "message": "サマリーを正常に投稿しました",
            "summary": final_summary,
        }

    except Exception as e:
        print(f"❌ エラー: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        # Discordクライアントを適切にクローズ
        await client.close()


def handler(request):
    """Vercel Serverless Function のエントリーポイント"""

    # POSTリクエストの場合のみ処理
    if request.method != "POST":
        return {
            "statusCode": 405,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"error": "Method not allowed. Use POST method."}, ensure_ascii=False
            ),
        }

    try:
        # 非同期処理を実行
        result = asyncio.run(create_discord_summary())

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result, ensure_ascii=False),
        }

    except Exception as e:
        print(f"❌ ハンドラーエラー: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"status": "error", "message": f"Internal server error: {str(e)}"},
                ensure_ascii=False,
            ),
        }


# Vercel用のエクスポート
app = handler
