# Discord日次サマリーBot 仕様書

**バージョン**: 1.0
**作成日**: 2025年8月12日

---

## 1. 概要

### 1.1. システム目的
本システムは、指定されたDiscordサーバー内の全チャンネルおよびスレッドにおける過去24時間の活動内容を、Google Gemini APIを利用して要約し、毎日定時に指定チャンネルへ投稿することを目的とする。これにより、メンバーはサーバー内の全体像を効率的に把握できる。

### 1.2. 主要機能
-   **定時自動実行**: 毎日午前10時（日本時間）にサマリー作成タスクを自動で実行する。
-   **網羅的なデータ収集**: 権限のある全テキストチャンネルおよびアクティブなスレッドの投稿を収集対象とする。
-   **AIによる内容要約**: 収集したチャット履歴をGoogle Gemini APIに送信し、指定されたフォーマットに基づいた高品質な要約を生成する。
-   **Discordへの自動投稿**: 生成されたサマリーを、指定されたDiscordチャンネルに自動で投稿する。

---

## 2. システムアーキテクチャ

本システムはVercelのサーバーレスアーキテクチャを基盤とし、以下のコンポーネントで構成される。

```mermaid
graph TD
    subgraph "Vercelプラットフォーム"
        Cron(⏰ Vercel Cron Job)
        "ServerlessFunc[🤖 Pythonサーバーレス関数<br>(api/daily_summary.py)]"
    end

    subgraph "外部API"
        DiscordAPI(🔌 Discord API)
        GeminiAPI(🧠 Google Gemini API)
    end

    subgraph "Discord"
        Server(🏢 Discordサーバー)
        TargetChannel(🎯 投稿先チャンネル)
    end

    %% フロー
    Cron -- "毎日10時 (JST)" --> ServerlessFunc
    ServerlessFunc -- "Botトークンで認証し<br>全チャンネルの履歴を要求" --> DiscordAPI
    DiscordAPI -- "チャット履歴を返す" --> ServerlessFunc
    ServerlessFunc -- "履歴テキストと<br>プロンプトを送信" --> GeminiAPI
    GeminiAPI -- "生成された要約文を返す" --> ServerlessFunc
    ServerlessFunc -- "Webhook URLを使い<br>最終的なサマリーを投稿" --> TargetChannel
    TargetChannel -- "サマリーを表示" --> Server
```
