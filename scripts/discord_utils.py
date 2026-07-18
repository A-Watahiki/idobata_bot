"""Discord Bot API とやり取りするための共通関数。

必要な環境変数:
  DISCORD_BOT_TOKEN         Botのトークン
  DISCORD_GUILD_ID          サーバー(ギルド)のID
  DISCORD_ANNOUNCE_CHANNEL_ID  「#🐸｜井戸端かいぎ」チャンネルのID
  DISCORD_ADMIN_CHANNEL_ID  運営用チャンネルのID(新規申込み通知の投稿先。
                            build_new_submission_notification()利用時のみ必要)

Bot に必要な権限:
  View Channels / Send Messages / Create Public Threads /
  Send Messages in Threads / Embed Links
"""
import os
from datetime import datetime

import requests

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]
ANNOUNCE_CHANNEL_ID = os.environ["DISCORD_ANNOUNCE_CHANNEL_ID"]

BASE_URL = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type": "application/json",
}

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


def notion_page_url(page_id: str) -> str:
    """NotionのページIDから閲覧用URLを組み立てる。"""
    return f"https://www.notion.so/{page_id.replace('-', '')}"


def format_datetime(datetime_str: str) -> str:
    """ISO日時文字列を「2026年7月20日(月) 19:00」のような表記にする。"""
    if not datetime_str:
        return "調整中"
    dt = datetime.fromisoformat(datetime_str)
    weekday = WEEKDAY_JA[dt.weekday()]
    return f"{dt.year}年{dt.month}月{dt.day}日({weekday}) {dt.strftime('%H:%M')}"


def resolve_mention(username: str) -> str:
    """Discordのユーザー名(@から始まる/始まらない)からメンション文字列 <@id> を作る。
    サーバー内で見つからない場合はプレーンテキストのままにする。
    """
    if not username:
        return "ご担当者"
    handle = username.lstrip("@")
    res = requests.get(
        f"{BASE_URL}/guilds/{GUILD_ID}/members/search",
        headers=HEADERS,
        params={"query": handle, "limit": 5},
    )
    res.raise_for_status()
    for member in res.json():
        user = member.get("user", {})
        if handle.lower() in (
            (user.get("username") or "").lower(),
            (user.get("global_name") or "").lower(),
        ):
            return f"<@{user['id']}>"
    print(f"[discord_utils] WARNING: could not resolve Discord user for '{username}'")
    return f"@{handle}"


def build_shared_description(fields: dict, zoom_url: str) -> str:
    """告知embedとGoogleカレンダーの説明欄で共有するセッション内容。"""
    levels = "・".join(fields.get("levels") or []) or "指定なし"
    organizer = fields.get("organizer_username")
    organizer_display = f"@{organizer.lstrip('@')}" if organizer else "未設定"
    return (
        f"種別: {fields.get('category') or '未設定'}\n"
        f"日時: {format_datetime(fields.get('datetime'))}\n"
        f"主催者: {organizer_display}\n"
        f"対象: {levels}\n"
        f"概要:\n{fields.get('summary') or ''}\n\n"
        f"Zoom会場: {zoom_url}"
    )


def build_announcement_content(fields: dict, zoom_url: str) -> dict:
    """告知メッセージのembedを組み立てる。"""
    description = (
        f"{build_shared_description(fields, zoom_url)}\n\n"
        f"**本イベント用のNotionページ**: {notion_page_url(fields['page_id'])}\n\n"
        f"このセッションに関するお問い合わせ・質問・感想は、このスレッドにご投稿ください。"
    )

    return {
        "embeds": [
            {
                "title": f"🐸 {fields.get('title') or '井戸端かいぎ'}",
                "url": notion_page_url(fields["page_id"]),
                "description": description,
                "color": 0x6FCF97,
            }
        ]
    }


def create_announcement_thread(fields: dict, zoom_url: str) -> tuple[str, str]:
    """告知メッセージを投稿し、そこからスレッドを作成する。戻り値は (スレッドURL, スレッドID)。"""
    # 1. 告知メッセージを投稿
    msg_res = requests.post(
        f"{BASE_URL}/channels/{ANNOUNCE_CHANNEL_ID}/messages",
        headers=HEADERS,
        json=build_announcement_content(fields, zoom_url),
    )
    msg_res.raise_for_status()
    message_id = msg_res.json()["id"]

    # 2. そのメッセージからスレッドを作成
    thread_name = (fields.get("title") or "井戸端かいぎ")[:100]
    thread_res = requests.post(
        f"{BASE_URL}/channels/{ANNOUNCE_CHANNEL_ID}/messages/{message_id}/threads",
        headers=HEADERS,
        json={"name": thread_name, "auto_archive_duration": 10080},  # 7日
    )
    thread_res.raise_for_status()
    thread_id = thread_res.json()["id"]

    return f"https://discord.com/channels/{GUILD_ID}/{thread_id}", thread_id


def build_todo_content(fields: dict, zoom_url: str) -> str:
    """承認直後にスレッドへ投稿するTODO案内。"""
    material_folder_url = (
        "https://drive.google.com/drive/folders/1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU?usp=sharing"
    )
    mention = resolve_mention(fields.get("organizer_username"))
    admin_mention = resolve_mention("xenamanex")
    return (
        f"{mention}\n\n"
        f"井戸端かいぎ「{fields.get('title')}」の開催が確定しました。以下、今後の流れです。\n\n"
        f"**Zoom会場**: {zoom_url}\n\n"
        f"□ 1. 発表当日の2日前までに、発表資料を下記フォルダにアップロードしてください。\n"
        f"　　資料共有用フォルダ: {material_folder_url}\n"
        f"　　(アップロードした「資料そのもののURL」を、このスレッドへの返信でご共有ください)\n\n"
        f"□ 2. 2日前までに資料URLの共有が確認できない場合、このスレッドにリマインダーが自動投稿されます。\n\n"
        f"□ 3. 前日と、開催30分前に「#🐸｜井戸端かいぎ」チャンネル全体へ、このスレッドへの"
        f"リンクつきでリマインダーが届きます。\n\n"
        f"□ 4. 近日中に、Notionの「井戸端かいぎの予定表」データベースへの編集権限を運営から"
        f"付与します。ご自身のイベントページの内容(日時以外)を修正すると、30分以内にこの"
        f"スレッドへ更新通知が届きます。**日時を変更した場合は、代わりに「#🐸｜井戸端かいぎ」"
        f"チャンネル全体へ通知が届きます**(Zoom・Googleカレンダーの予定も自動で更新されます)。\n\n"
        f"□ 5. このイベントを継続シリーズとして次回も開催する場合は、このイベントのNotionページを"
        f"複製し、日時だけを変更して「ステータス」を「確定」にしてください。日時が入力されて"
        f"「確定」になると、その都度この案内と同じ流れで新しいスレッドが自動的に作成されます。\n\n"
        f"□ 6. やむを得ず開催をキャンセルする場合は、このスレッドで {admin_mention} をメンションしてお知らせください。\n\n"
        f"ご不明な点があれば、このスレッドまでお気軽にどうぞ。"
    )


def build_new_submission_notification(fields: dict, submission_page_id: str, public_page_id: str) -> str:
    """新しい申込みを検知した際に運営用チャンネルへ投稿する通知。
    メールアドレスそのものは記載せず、非公開の「申込み」ページへのリンクのみを示す
    (運営側でそのページを開いてメールアドレスを確認する運用)。
    """
    return (
        f"📥 新しい井戸端かいぎの申込みがありました。\n\n"
        f"**タイトル**: {fields.get('title') or '未設定'}\n"
        f"**主催者**: {fields.get('organizer_username') or '未設定'}\n"
        f"**日時**: {format_datetime(fields.get('datetime'))}\n"
        f"**種別**: {fields.get('category') or '未設定'}\n\n"
        f"申込み内容(メールアドレス含む・非公開): {notion_page_url(submission_page_id)}\n"
        f"公開予定表に転記済み(ステータス「募集中」): {notion_page_url(public_page_id)}\n\n"
        f"内容を確認し、問題なければ上記「申込み内容」ページでメールアドレスを確認のうえ、"
        f"予定表ページの「共有」からそのメールアドレスをゲスト招待して編集権限を付与し、"
        f"「ステータス」を「確定」に変更してください。"
    )


def post_message(channel_or_thread_id: str, content: str):
    """チャンネルまたはスレッドにメッセージを投稿する。"""
    res = requests.post(
        f"{BASE_URL}/channels/{channel_or_thread_id}/messages",
        headers=HEADERS,
        json={"content": content},
    )
    res.raise_for_status()
    return res.json()
