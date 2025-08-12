# Discord日次サマリーBot 仕様書

**バージョン**: 1.0
**作成日**: 2025年8月12日

---

## 1. 概要

### 1.1. システム目的
本システムは、指定されたDiscordサーバー内の全チャンネルおよびスレッドにおける過去24時間の活動内容を、Google Gemini APIを利用して要約し、毎日定時に指定チャンネルへ投稿することを目的とする。これにより、メンバーはサーバー内の全体像を効率的に把握できる。

### 1.2. 主要機能
-   **定時自動実行**: 毎日午前9~10時（日本時間）にサマリー作成タスクを自動で実行する。
-   **網羅的なデータ収集**: 権限のある全テキストチャンネルおよびアクティブなスレッドの投稿を収集対象とする。
-   **AIによる内容要約**: 収集したチャット履歴をGoogle Gemini APIに送信し、指定されたフォーマットに基づいた高品質な要約を生成する。
-   **Discordへの自動投稿**: 生成されたサマリーを、指定されたDiscordチャンネルに自動で投稿する。

---

## 2. 機能仕様

### 2.1. 定期実行機能
-   **トリガー**: Vercel Cron Job
-   **スケジュール**: `0 0 * * *` (UTC)。日本時間の毎日午前9~10時に設定。
-   **アクション**: `/api/daily_summary`のパスにリクエストを送信し、Pythonサーバーレス関数を起動する。

### 2.2. データ収集機能
-   **収集対象**: 指定されたサーバー（Guild）内の、Botが`メッセージ履歴を読む`権限を持つ全てのテキストチャンネルおよびその中のアクティブなスレッド。
-   **収集期間**: 実行時から遡って過去24時間。
-   **収集データ**: チャンネル名、スレッド名、投稿者名（サーバーでの表示名）、投稿時刻、メッセージ本文。
-   **除外対象**: Botによる投稿、メッセージ本文が空の投稿。

### 2.3. 要約生成機能
-   **使用サービス**: Google Gemini API
-   **使用モデル**: `gemini-1.5-pro-latest`
-   **プロンプト**: 収集した全チャット履歴を付与し、以下の要件に基づき要約を指示する。
    -   全チャンネル・スレッドを網羅すること。
    -   投稿がなかったチャンネルは「投稿なし」と明記すること。
    -   時刻、投稿者、主旨を簡潔にまとめること。
    -   指定された出力フォーマット例に従うこと。

### 2.4. 投稿機能
-   **投稿方式**: Discord Webhook
-   **投稿先**: 環境変数で指定された単一のチャンネル。
-   **投稿フォーマット**:
    1.  Python側で現在の日付と曜日を含む固定タイトルを生成。
        -   `🗓️ YYYY年MM月DD日（曜）投稿サマリー（全チャンネル確認済）`
    2.  Gemini APIから返却された要約本文を上記タイトルの下に結合する。
    3.  Discordの文字数制限（2000文字）を超える場合は、自動で分割して連続投稿する。

---

## 3. 非機能要件

### 3.1. 実行環境
-   **プラットフォーム**: Vercel

### 3.2. 使用言語・ライブラリ
-   **言語**: Python
-   **主要ライブラリ**:
    -   `discord.py`: チャット履歴の読み取り用
    -   `google-generativeai`: Gemini APIとの連携用
    -   `requests`: Discord Webhookへの投稿用

### 3.3. 外部サービス連携
-   Discord API (Bot Token経由)
-   Google Gemini API (API Key経由)
-   Discord Webhook (Webhook URL経由)

### 3.4. 環境変数
Vercelのプロジェクト設定で、以下の環境変数を設定する必要がある。
-   `DISCORD_BOT_TOKEN`: Discordからチャット履歴を取得するためのBotトークン。
-   `GEMINI_API_KEY`: Google Gemini APIを利用するためのAPIキー。
-   `DISCORD_WEBHOOK_URL`: サマリーを投稿する先のチャンネルのWebhook URL。

## 4. プロジェクトファイル構成
```
.
├── api/
│   └── daily_summary.py   # メインのPythonコード
├── requirements.txt         # 依存ライブラリ一覧
└── vercel.json              # Vercel Cron Job設定ファイル
```

## 5. システムアーキテクチャ
```mermaid
graph TD
    subgraph "Vercelプラットフォーム"
        ServerlessFunc[🤖 Pythonサーバーレス関数<br>(Bot本体)]
    end

    subgraph "Discordの機能"
        DiscordAPI[🔌 Discord API<br>(Botとして認証・データ読み取り)]
        Webhook[🔗 Discord Webhook<br>(メッセージ書き込み)]
    end

    subgraph "外部AI"
        GeminiAPI(🧠 Google Gemini API)
    end
    
    subgraph "Discordサーバー"
        TargetChannel(🎯 投稿先チャンネル)
    end

    %% フロー
    ServerlessFunc -- "毎日10時にVercel Cronで起動" --> ServerlessFunc
    ServerlessFunc -- "Botトークンを使いAPI経由で<br>チャット履歴を要求" --> DiscordAPI
    DiscordAPI -- "権限に基づき履歴を返す" --> ServerlessFunc
    
    ServerlessFunc -- "収集した履歴を送信し<br>要約を依頼" --> GeminiAPI
    GeminiAPI -- "要約文を返す" --> ServerlessFunc
    
    ServerlessFunc -- "Webhook URLを使い<br>サマリーを投稿" --> Webhook
    Webhook -- "チャンネルにメッセージを書き込む" --> TargetChannel
```
