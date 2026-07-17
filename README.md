# 井戸端かいぎ 自動化Bot

「井戸端かいぎの予定表」(Notion)と Discord・Gmail・Google Drive を連携させ、
承認〜告知〜リマインダーまでを自動化するスクリプト集です。
Make.comなどの外部ノーコードツールを使わず、GitHub Actionsだけで完結します。

## 全体の流れ

1. Notionで運営が「承認」ボタンを押す
   → Notionの自動化(Webhook送信)が GitHub の `repository_dispatch` API を叩く
   → `.github/workflows/on_approve.yml` が起動
   → Discordにお知らせスレッド作成 + ステージイベント作成 + Notionにスレッドリンクを書き戻し
2. Notionフォームが送信される
   → 同様に `on_form_submit.yml` が起動 → 申込者にTODOリスト付き確認メールを送信
3. 毎日決まった時刻に `daily_check.yml` が自動実行され、開催2日前で資料未共有の発表者にリマインダー送信

## 事前準備

### 1. このリポジトリをGitHubにpush

```bash
cd idobata-kaigi-bot
git init
git add .
git commit -m "init"
git remote add origin https://github.com/<あなたのアカウント>/idobata-kaigi-bot.git
git push -u origin main
```

このリポジトリは秘密情報を含まないので、Public / Private どちらでも構いません
(Publicの場合、GitHub Actionsの実行時間は無制限・無料です)。

### 2. GitHub Personal Access Token (PAT) を発行

Notion からこのリポジトリの Actions を起動するために必要です。

1. GitHubの Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. 対象リポジトリをこのリポジトリのみに限定
3. Permissions → "Contents" を Read and write に設定(repository_dispatchの実行に必要)
4. 発行されたトークンは、後述の Notion Webhook 設定にのみ使用し、他には貼らないこと

### 3. GitHub Secrets の登録

リポジトリの Settings → Secrets and variables → Actions → New repository secret から、以下をすべて登録してください。

| Secret名 | 内容 |
|---|---|
| `NOTION_TOKEN` | Notion internal integration のSecret |
| `NOTION_DATABASE_ID` | 「井戸端かいぎの予定表」データベースのID |
| `DISCORD_BOT_TOKEN` | Discord Botのトークン |
| `DISCORD_GUILD_ID` | サーバーのID |
| `DISCORD_ANNOUNCE_CHANNEL_ID` | 「#🐸｜井戸端かいぎ」チャンネルのID |
| `DISCORD_STAGE_CHANNEL_ID` | ステージチャンネルのID |
| `GMAIL_ADDRESS` | 通知送信用Gmailアドレス |
| `GMAIL_APP_PASSWORD` | Googleの「アプリパスワード」(2段階認証を有効にした上で発行) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google Driveアクセス用サービスアカウントの認証情報(JSON全文) |
| `MATERIAL_FOLDER_ID` | 資料共有用フォルダのID(`1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU`) |

Google Cloud Consoleでサービスアカウントを作成したら、そのメールアドレス
(`xxxx@xxxx.iam.gserviceaccount.com`)を資料共有用フォルダに「閲覧者」として
共有しておいてください。

### 4. Notion側の設定

「井戸端かいぎの予定表」データベースに以下のプロパティが必要です(名称は完全一致させてください):
タイトル / 日時 / 種別 / 担当者 / ステータス / 概要 / 対象レベル / 資料リンク /
録画 / 議事メモ / Discordスレッド(URL型) / メールアドレス(Email型)

#### 承認ボタンの設定

1. データベースに「承認」というボタンプロパティを追加
2. アクションで「Webhookを送信」を選択
3. URL: `https://api.github.com/repos/<あなたのアカウント>/idobata-kaigi-bot/dispatches`
4. メソッド: POST
5. ヘッダー:
   - `Authorization: Bearer <手順2で発行したPAT>`
   - `Accept: application/vnd.github+json`
6. ボディ:
   ```json
   {"event_type": "notion_approved", "client_payload": {"page_id": "{{page_id}}"}}
   ```
   (`{{page_id}}` の部分はNotionの自動化エディタで「このページのID」を挿入)
7. あわせて、このボタンで「ステータス」プロパティを「確定」に変更するアクションも追加しておくと、承認と同時にステータスも更新されます

#### フォーム送信時の自動化

データベースの自動化(雷アイコン)で「ページが追加されたとき」をトリガーにし、
承認ボタンと同様の形でWebhookを送信します(`event_type` は `notion_form_submitted` にする)。

## 動作確認

まず `workflow_dispatch`(daily_check.yml)を手動実行して、Secretsが正しく設定されているか確認するのがおすすめです。
GitHubリポジトリの Actions タブ → 該当ワークフロー → "Run workflow" から実行できます。

## 制限・注意点

- `discord_utils.py` のスレッド作成・イベント作成は、Botに該当チャンネルへのアクセス権限が必要です
- `drive_utils.py` のファイル検索はタイトルの部分一致による簡易的なものです。ファイル名に発表タイトルの一部を含めてアップロードしてもらうよう、事前に周知してください
- 本コードはひな形です。実際の運用前に、テスト用のNotionページ・Discordチャンネルで一通り動作確認することを強く推奨します
