# 井戸端かいぎ 自動化Bot

「井戸端かいぎの予定表」(Notion)と Discord・Google Drive を連携させ、
承認〜告知〜リマインダーまでを自動化するスクリプト集です。
Make.comなどの外部ノーコードツールを使わず、GitHub Actionsだけで完結します。

Notionデータベースは対外公開する予定のため、メールアドレスなどの個人情報は
プロパティとして持たない設計にしています。申込者とのやり取りはすべて
Discordのお知らせスレッド上で行います。

## 全体の流れ

Notionの「Send webhook」アクションは有料プラン限定のため、GitHub Actionsの
`schedule`(cron)による**定期ポーリング方式**を採用しています。

1. `.github/workflows/poll.yml` が10分おきに自動実行され、`poll_approve.py` が
   「ステータス」が「確定」なのに「Discordスレッド」が未作成の行を検知し、
   - Discordにお知らせスレッドを作成
   - スレッドにTODOリスト(資料アップロード期限など)を投稿
   - ステージイベントを作成
   - Notionにスレッドリンクを書き戻し
2. `.github/workflows/daily_check.yml` が毎日自動実行され、`daily_check.py` が
   開催2日前で資料未共有の発表者に、Discordのお知らせスレッドへリマインダーを投稿
3. 前日リマインダーは、Discordのステージイベント自体の通知機能で代替します(コード不要)

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

### 2. GitHub Secrets の登録

リポジトリの Settings → Secrets and variables → Actions → New repository secret から、以下をすべて登録してください。

| Secret名 | 内容 |
|---|---|
| `NOTION_TOKEN` | Notion internal integration のSecret |
| `NOTION_DATABASE_ID` | 「井戸端かいぎの予定表」データベースのID |
| `DISCORD_BOT_TOKEN` | Discord Botのトークン |
| `DISCORD_GUILD_ID` | サーバーのID |
| `DISCORD_ANNOUNCE_CHANNEL_ID` | 「#🐸｜井戸端かいぎ」チャンネルのID |
| `DISCORD_STAGE_CHANNEL_ID` | ステージチャンネルのID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Driveアクセス用サービスアカウントの認証情報(JSON全文) |
| `MATERIAL_FOLDER_ID` | 資料共有用フォルダのID(`1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU`) |

Google Cloud Consoleでサービスアカウントを作成したら、そのメールアドレス
(`xxxx@xxxx.iam.gserviceaccount.com`)を資料共有用フォルダに「閲覧者」として
共有しておいてください。

### 3. Notion側の設定

「井戸端かいぎの予定表」データベースに以下のプロパティが必要です(名称は完全一致させてください):
タイトル / 日時 / 種別 / 担当者 / ステータス / 概要 / 対象レベル / 資料リンク /
録画 / 議事メモ / Discordスレッド(URL型)

メールアドレスなどの個人情報プロパティは意図的に持たせていません。

#### 承認ボタンの設定

アクションは1つだけで構いません:「プロパティを編集」→「ステータス」を「確定」に変更。
(Webhookは使わないため、Webhook送信アクションの設定は不要です)

`poll.yml` が10分以内にこの変更を検知し、Discordへの告知・TODO投稿・イベント作成・
スレッドリンクの書き戻しを自動で行います。

## 動作確認

まず `workflow_dispatch` で `poll.yml` と `daily_check.yml` をそれぞれ手動実行して、
Secretsが正しく設定されているか確認するのがおすすめです。
GitHubリポジトリの Actions タブ → 該当ワークフロー → "Run workflow" から実行できます。

## 制限・注意点

- `discord_utils.py` のスレッド作成・イベント作成は、Botに該当チャンネルへのアクセス権限が必要です
- `drive_utils.py` のファイル検索はタイトルの部分一致による簡易的なものです。ファイル名に発表タイトルの一部を含めてアップロードしてもらうよう、事前に周知してください
- 本コードはひな形です。実際の運用前に、テスト用のNotionページ・Discordチャンネルで一通り動作確認することを強く推奨します
