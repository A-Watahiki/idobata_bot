# 井戸端かいぎ 自動化Bot

「井戸端かいぎの予定表」(Notion)と Discord・Zoom・Googleカレンダー・Google Drive を
連携させ、承認〜告知〜リマインダーまでを自動化するスクリプト集です。
Make.comなどの外部ノーコードツールを使わず、GitHub Actionsだけで完結します。

Notionデータベースは対外公開する予定のため、メールアドレスやZoomリンクなどの
個人情報・秘匿情報はプロパティとして一切持たない設計にしています。
Zoomリンクは Googleカレンダーの予定と、開催直前のDiscordリマインダーにのみ記載されます。
申込者とのやり取りはDiscordのお知らせスレッド上で行います。

## 全体の流れ

Notionの「Send webhook」アクションは有料プラン限定のため、GitHub Actionsの
`schedule`(cron)による**定期ポーリング方式**を採用しています。

1. `.github/workflows/poll.yml` が10分おきに自動実行され、
   - `poll_approve.py`: 「ステータス」が「確定」なのに「Discordスレッド」が
     未作成の行を検知し、
     - Zoomミーティングを作成(単発は毎回新規。複数回は「シリーズ名」が
       一致する既存のZoomリンクを再利用し、なければ新規に
       「時間固定なし」ミーティングを作成)
     - Googleカレンダーに予定を作成(Zoomリンクを記載。Notionには書き込まない)
     - Discordにお知らせスレッドを作成し、TODO案内を投稿(Zoomリンクは含めない)
     - Notionにスレッドリンクを書き戻し
   - `remind_events.py`: Googleカレンダーの予定を見て、
     - **開催24時間前**: Discordスレッドにリマインダーを投稿(Zoomリンクなし)
     - **開催30分前**: Discordスレッドにリマインダーを投稿(Zoomリンクつき)
2. `.github/workflows/daily_check.yml` が毎日自動実行され、`daily_check.py` が
   開催2日前で資料未共有の発表者に、Discordのお知らせスレッドへリマインダーを投稿

開催時間は基本30分・最大40分を想定しています(議論が延びる場合は一度退出し、
同じZoom会場に入り直す運用)。

## 事前準備

### 1. このリポジトリをGitHubにpush

```bash
cd idobata-kaigi-bot
git init
git add .
git commit -m "init"
git remote add origin https://github.com/A-Watahiki/idobata_bot.git
git push -u origin main
```

このリポジトリは秘密情報を含まないので、Public / Private どちらでも構いません
(Publicの場合、GitHub Actionsの実行時間は無制限・無料です)。

### 2. Zoom Server-to-Server OAuthアプリの作成

動物倫理かいぎのZoomアカウント(`doubutsurinrikaigi@gmail.com`)で:

1. https://marketplace.zoom.us/ にログイン
2. 右上の「Try new experience」トグルが**ON**になっている場合はOFFにする
   (ONのままだと新UIになり「Develop」メニューが表示されません)
3. 「Develop」→「Build App」(見当たらない場合は直接
   `https://marketplace.zoom.us/develop/create` にアクセス)
4. 「Server-to-Server OAuth」を選択して作成
5. Scopes に `meeting:write:meeting` (または `meeting:write`) を追加
6. 発行される `Account ID` / `Client ID` / `Client Secret` を控えておく

「Server-to-Server OAuth」の選択肢が見当たらない場合は、そのZoomアカウントが
管理者権限を持っているか確認してください。

### 3. Googleカレンダーのリフレッシュトークン発行(一度だけ手動)

`doubutsurinrikaigi@gmail.com` でログインした状態で:

1. Google Cloud Console (https://console.cloud.google.com/) で新規プロジェクトを作成(または既存のものを利用)
2. 「APIとサービス」→「ライブラリ」で「Google Calendar API」を有効化
3. 「APIとサービス」→「認証情報」→「OAuthクライアントID」を作成
   - アプリケーションの種類: 「デスクトップアプリ」
   - 発行される `クライアントID` / `クライアントシークレット` を控えておく
4. OAuth同意画面で自分(doubutsurinrikaigi@gmail.com)をテストユーザーとして追加
5. ローカル環境などで以下のようなスクリプトを一度だけ実行し、認可コードからリフレッシュトークンを取得する
   (`google-auth-oauthlib` を使うと簡単です。`pip install google-auth-oauthlib` の上で):
   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow

   flow = InstalledAppFlow.from_client_config(
       {
           "installed": {
               "client_id": "<クライアントID>",
               "client_secret": "<クライアントシークレット>",
               "auth_uri": "https://accounts.google.com/o/oauth2/auth",
               "token_uri": "https://oauth2.googleapis.com/token",
               "redirect_uris": ["http://localhost"],
           }
       },
       scopes=["https://www.googleapis.com/auth/calendar"],
   )
   creds = flow.run_local_server(port=0)
   print("refresh_token:", creds.refresh_token)
   ```
   ブラウザが開くので `doubutsurinrikaigi@gmail.com` でログイン・許可し、
   表示された `refresh_token` を控えておく

### 4. GitHub Secrets の登録

リポジトリの Settings → Secrets and variables → Actions → New repository secret から、以下をすべて登録してください。

| Secret名 | 内容 |
|---|---|
| `NOTION_TOKEN` | Notion internal integration のSecret |
| `NOTION_DATABASE_ID` | 「井戸端かいぎの予定表」データベースのID |
| `DISCORD_BOT_TOKEN` | Discord Botのトークン |
| `DISCORD_GUILD_ID` | サーバーのID |
| `DISCORD_ANNOUNCE_CHANNEL_ID` | 「#🐸｜井戸端かいぎ」チャンネルのID |
| `ZOOM_ACCOUNT_ID` | Zoom Server-to-Server OAuthアプリのAccount ID |
| `ZOOM_CLIENT_ID` | 同アプリのClient ID |
| `ZOOM_CLIENT_SECRET` | 同アプリのClient Secret |
| `GOOGLE_CALENDAR_CLIENT_ID` | Google CalendarのOAuthクライアントID |
| `GOOGLE_CALENDAR_CLIENT_SECRET` | 同クライアントシークレット |
| `GOOGLE_CALENDAR_REFRESH_TOKEN` | 手順3で取得したリフレッシュトークン |
| `GOOGLE_CALENDAR_ID` | 予定を作成するカレンダーのID(通常は `doubutsurinrikaigi@gmail.com` または `primary`) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Driveアクセス用サービスアカウントの認証情報(JSON全文) |
| `MATERIAL_FOLDER_ID` | 資料共有用フォルダのID(`1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU`) |

Google Cloud Consoleでサービスアカウントを作成したら、そのメールアドレス
(`xxxx@xxxx.iam.gserviceaccount.com`)を資料共有用フォルダに「閲覧者」として
共有しておいてください(こちらはGoogle Drive専用で、Google Calendar用のOAuthとは別物です)。

### 5. Notion側の設定

「井戸端かいぎの予定表」データベースに以下のプロパティが必要です(名称は完全一致させてください):
タイトル / 日時 / 種別 / 担当者 / ステータス / 概要 / 対象 / 資料リンク /
録画 / 議事メモ / Discordスレッド(URL型) / 開催頻度(セレクト: 単発・複数回) /
シリーズ名(テキスト、「複数回」の場合のみ入力。同じシリーズ名の行同士で
Zoomリンクを自動的に使い回す)

「複数回」の輪読会などは、開催のたびにNotionの行を新規に作成し、
1回目と同じ「シリーズ名」を入力してもらう運用です(日時はその回の日時のみ入力)。

メールアドレスやZoomリンクなどの個人情報・秘匿情報プロパティは意図的に持たせていません。

#### 承認ボタンの設定

アクションは1つだけで構いません:「プロパティを編集」→「ステータス」を「確定」に変更。
(Webhookは使わないため、Webhook送信アクションの設定は不要です)

`poll.yml` が10分以内にこの変更を検知し、Zoom/カレンダー作成・Discordへの告知・
TODO投稿・スレッドリンクの書き戻しを自動で行います。

## 動作確認

まず `workflow_dispatch` で `poll.yml` と `daily_check.yml` をそれぞれ手動実行して、
Secretsが正しく設定されているか確認するのがおすすめです。
GitHubリポジトリの Actions タブ → 該当ワークフロー → "Run workflow" から実行できます。

## 制限・注意点

- `discord_utils.py` のスレッド作成は、Botに該当チャンネルへのアクセス権限が必要です
- `drive_utils.py` のファイル検索はタイトルの部分一致による簡易的なものです。ファイル名に発表タイトルの一部を含めてアップロードしてもらうよう、事前に周知してください
- Zoom無料プランはグループミーティング(3名以上)が40分で自動終了します。「基本30分・最大40分」という運用方針はこの制限を踏まえたものです
- `remind_events.py` のリマインダーと、複数回シリーズのZoomリンク再利用は、
  Googleカレンダーの予定作成時に保存した `extendedProperties`
  (NotionページID・DiscordスレッドID・ZoomリンクURL・シリーズ名)を参照します。
  そのためGoogleカレンダーの予定を手動で複製した場合、これらの機能は正しく動作しません
- 本コードはひな形です。実際の運用前に、テスト用のNotionページ・Discordチャンネル・
  Zoomミーティング・Googleカレンダーで一通り動作確認することを強く推奨します
