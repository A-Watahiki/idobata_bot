// Vercel サーバレス関数: Notion の「インテグレーション Webhook」を受信し、
// GitHub Actions の poll.yml を即時実行させる(repository_dispatch を叩く)。
//
// これにより、フォーム提出・ステータス変更・ページ編集などが起きた数秒後に
// poll.yml が走るようになり、GitHub の不安定な cron に頼らず即応できる。
// (時刻ベースのリマインダーだけは cron が引き続き担当する。)
//
// このディレクトリ(webhook-proxy)を Vercel の「Root Directory」に指定して
// デプロイすると、`https://<プロジェクト>.vercel.app/api/notion-webhook` が
// エンドポイントになる。Python 本体とは独立してデプロイされる。
//
// Vercel プロジェクトに設定する環境変数:
//   GITHUB_TOKEN     GitHub の Personal Access Token。
//                    - classic の場合: `public_repo`(公開リポジトリ用)スコープ
//                    - fine-grained の場合: 対象リポジトリの "Contents: Read and write"
//   GITHUB_OWNER     リポジトリのオーナー(例: "A-Watahiki")
//   GITHUB_REPO      リポジトリ名(例: "idobata_bot")
//   WEBHOOK_SECRET   (任意)エンドポイント保護用の合言葉。設定した場合、
//                    Webhook URL に `?key=<この値>` を付け、一致しない
//                    リクエストは無視する(いたずら防止)。

export default async function handler(req, res) {
  // Notion は POST で送ってくる。それ以外は素通し。
  if (req.method !== "POST") {
    return res.status(200).send("ok");
  }

  // 任意の合言葉チェック(WEBHOOK_SECRET を設定した場合のみ有効)。
  const secret = process.env.WEBHOOK_SECRET;
  if (secret && req.query.key !== secret) {
    // 攻撃者に情報を与えないため 200 を返しつつ、何もしない。
    console.warn("[notion-webhook] rejected: bad or missing key");
    return res.status(200).json({ received: true });
  }

  const body = req.body || {};

  // 1) 初回の検証リクエスト。Notion は購読作成時に
  //    { "verification_token": "secret_xxx" } を一度だけ送ってくる。
  //    このトークンを Notion の管理画面に貼り付けて検証を完了する必要があるため、
  //    Vercel の関数ログに出力しておく(Vercel ダッシュボード → Logs で確認)。
  if (body.verification_token) {
    console.log(
      "[notion-webhook] verification_token (これをNotionの購読画面に貼り付けてください):",
      body.verification_token
    );
    return res.status(200).json({ received: true });
  }

  // 2) 通常のイベント。内容は問わず、poll.yml を1回起動するだけ。
  //    各スクリプトは冪等(処理済みフラグでガード)なので、余分に走っても安全。
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${process.env.GITHUB_OWNER}/${process.env.GITHUB_REPO}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({
          event_type: "notion-webhook",
          client_payload: { notion_event_type: body.type || "unknown" },
        }),
      }
    );
    if (!resp.ok) {
      const text = await resp.text();
      console.error("[notion-webhook] GitHub dispatch failed:", resp.status, text);
    } else {
      console.log("[notion-webhook] dispatched poll.yml for event:", body.type || "unknown");
    }
  } catch (e) {
    console.error("[notion-webhook] dispatch error:", e);
  }

  // Notion に「受信成功」を返す(処理の成否に関わらず素早く 200)。
  return res.status(200).json({ received: true });
}
