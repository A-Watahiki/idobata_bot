"""Discord Bot API とやり取りするための共通関数。

必要な環境変数:
  DISCORD_BOT_TOKEN         Botのトークン
  DISCORD_GUILD_ID          サーバー(ギルド)のID
  DISCORD_ANNOUNCE_CHANNEL_ID  「#🐸｜井戸端かいぎ」チャンネルのID
  DISCORD_STAGE_CHANNEL_ID     ステージチャンネルのID

Bot に必要な権限:
  View Channels / Send Messages / Create Public Threads /
  Send Messages in Threads / Embed Links / Manage Events
"""
import os
import requests
from datetime import datetime, timedelta

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]
ANNOUNCE_CHANNEL_ID = os.environ["DISCORD_ANNOUNCE_CHANNEL_ID"]
STAGE_CHANNEL_ID = os.environ["DISCORD_STAGE_CHANNEL_ID"]

BASE_URL = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type": "application/json",
}


def notion_page_url(page_id: str) -> str:
    """NotionのページIDから閲覧用URLを組み立てる。"""
    return f"https://www.notion.so/{page_id.replace('-', '')}"


def build_announcement_content(fields: dict) -> dict:
    """告知メッセージのembedを組み立てる。"""
    levels = "・".join(fields.get("levels") or []) or "指定なし"
    material = fields.get("material_url") or "(後日共有予定)"

    description = (
        f"**種別**: {fields.get('category') or '未設定'}\n"
        f"**日時**: {fields.get('datetime') or '調整中'}\n"
        f"**発表者**: {fields.get('presenter') or '未設定'}\n"
        f"**対象レベル**: {levels}\n"
        f"**概要**:\n{fields.get('summary') or ''}\n\n"
        f"**資料リンク**: {material}\n\n"
        f"**Notionページ**: {notion_page_url(fields['page_id'])}\n\n"
        f"※ 発表資料は、発表日の2日前までにこのスレッドとNotionページの両方で共有される予定です。"
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


def create_announcement_thread(fields: dict) -> tuple[str, str]:
    """告知メッセージを投稿し、そこからスレッドを作成する。戻り値は (スレッドURL, スレッドID)。"""
    # 1. 告知メッセージを投稿
    msg_res = requests.post(
        f"{BASE_URL}/channels/{ANNOUNCE_CHANNEL_ID}/messages",
        headers=HEADERS,
        json=build_announcement_content(fields),
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


def build_todo_content(fields: dict) -> str:
    """承認直後にスレッドへ投稿するTODO案内。"""
    material_folder_url = (
        "https://drive.google.com/drive/folders/1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU?usp=sharing"
    )
    return (
        f"{fields.get('presenter') or 'ご担当者'} 様\n\n"
        f"「井戸端かいぎ」の開催が確定しました。以下、今後の流れです。\n\n"
        f"□ 1. 発表当日の2日前までに、発表資料を下記フォルダにアップロードしてください。\n"
        f"　　資料共有用フォルダ: {material_folder_url}\n"
        f"　　(アップロードした「資料そのもののURL」を、このスレッドへの返信でご共有ください)\n\n"
        f"□ 2. 2日前までに資料URLの共有が確認できない場合、このスレッドにリマインダーが自動投稿されます。\n\n"
        f"□ 3. 前日には、Discordのステージイベント機能によるリマインダーが興味あり登録者に届きます。\n\n"
        f"ご不明な点があれば、このスレッドまでお気軽にどうぞ。"
    )


def create_stage_event(fields: dict, duration_minutes: int = 90) -> str:
    """ステージチャンネルにスケジュールイベントを作成する。戻り値はイベントのURL。"""
    start_dt = datetime.fromisoformat(fields["datetime"])
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    body = {
        "name": (fields.get("title") or "井戸端かいぎ")[:100],
        "description": fields.get("summary") or "",
        "scheduled_start_time": start_dt.isoformat(),
        "scheduled_end_time": end_dt.isoformat(),
        "privacy_level": 2,  # GUILD_ONLY
        "entity_type": 1,  # STAGE_INSTANCE
        "channel_id": STAGE_CHANNEL_ID,
    }
    res = requests.post(
        f"{BASE_URL}/guilds/{GUILD_ID}/scheduled-events",
        headers=HEADERS,
        json=body,
    )
    if not res.ok:
        print(f"[discord_utils] Discord API error {res.status_code}: {res.text}")
    res.raise_for_status()
    event_id = res.json()["id"]
    return f"https://discord.com/events/{GUILD_ID}/{event_id}"


def post_message_to_thread(thread_id: str, content: str):
    """既存スレッドにメッセージ(リマインダーなど)を投稿する。"""
    res = requests.post(
        f"{BASE_URL}/channels/{thread_id}/messages",
        headers=HEADERS,
        json={"content": content},
    )
    res.raise_for_status()
    return res.json()
