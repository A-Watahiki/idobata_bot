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


def _raise_for_status(res):
    if not res.ok:
        print(f"[discord_utils] Discord API error {res.status_code}: {res.text}")
    res.raise_for_status()


DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = os.environ["DISCORD_GUILD_ID"]
ANNOUNCE_CHANNEL_ID = os.environ["DISCORD_ANNOUNCE_CHANNEL_ID"]

BASE_URL = "https://discord.com/api/v10"
HEADERS = {
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "Content-Type": "application/json",
}

WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]

# 「申込み必須」イベント用の共有「参加申込み」フォームURL。
# Notion側でフォーム(氏名・メールアドレス・参加イベントのリレーションを収集)を
# 作成したら、実際のURLに書き換えてください。
RSVP_FORM_URL = "https://oval-open-d31.notion.site/3a1530487f0a8016a173c7a08748883d?pvs=105"


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
    _raise_for_status(res)
    for member in res.json():
        user = member.get("user", {})
        if handle.lower() in (
            (user.get("username") or "").lower(),
            (user.get("global_name") or "").lower(),
        ):
            return f"<@{user['id']}>"
    print(f"[discord_utils] WARNING: could not resolve Discord user for '{username}'")
    return f"@{handle}"


def _diff_line(label: str, current_display: str, old_display) -> str:
    """old_displayが指定されていれば「ラベル: ~~旧~~ → **新**」、
    なければ「ラベル: 新」を返す(更新通知の取り消し線表示用)。
    """
    if old_display is not None:
        return f"{label}: ~~{old_display}~~ → **{current_display}**"
    return f"{label}: {current_display}"


def _base_description(fields: dict, diff: dict = None) -> str:
    """会場情報を含まない、セッション内容の共通部分。
    diffには{"category": 旧種別, "organizer_username": 旧主催者, "levels": 旧対象,
    "datetime": 旧日時}のうち変更があった項目だけを渡すと、その項目を
    取り消し線+新しい値で表示する(更新通知メッセージ編集用)。概要は対象外
    (自由記述の長文を取り消し線で差分表示すると読みにくくなるため)。
    """
    diff = diff or {}
    levels = "・".join(fields.get("levels") or []) or "指定なし"
    organizer = fields.get("organizer_username")
    organizer_display = f"@{organizer.lstrip('@')}" if organizer else "未設定"
    return (
        f"{_diff_line('種別', fields.get('category') or '未設定', diff.get('category'))}\n"
        f"{_diff_line('日時', format_datetime(fields.get('datetime')), diff.get('datetime'))}\n"
        f"{_diff_line('主催者', organizer_display, diff.get('organizer_username'))}\n"
        f"{_diff_line('対象', levels, diff.get('levels'))}\n"
        f"概要:\n{fields.get('summary') or ''}"
    )


def build_shared_description(fields: dict, venue_url) -> str:
    """Googleカレンダーの説明欄で使うセッション内容。Googleカレンダーは
    メンバー向けの非公開情報のため、「申込み必須」イベントでも実際の
    venue_url(Zoomリンクなど)をそのまま表示してよい。未設定の場合はNoneでよい。
    """
    venue_display = venue_url or "主催者より別途ご案内予定"
    return f"{_base_description(fields)}\n\n会場: {venue_display}"


def _announcement_body(fields: dict, venue_url, diff: dict = None) -> str:
    """告知embedの本文(会場URL/参加申込み案内を含む)。このメッセージは
    公開チャンネルに投稿されるため、「申込み必須」イベントではvenue_urlを
    一切表示せず、代わりに参加申込みフォームへの案内を表示する。
    """
    if fields.get("requires_rsvp"):
        return (
            f"{_base_description(fields, diff)}\n\n"
            f"⚠️ このイベントは**事前申込み制**です。参加をご希望の方は下記フォームから"
            f"お申し込みください(氏名・メールアドレスが必要です)。会場URLは折り返し"
            f"メールでご案内します。\n"
            f"**参加申込みフォーム**: {RSVP_FORM_URL}"
        )
    venue_display = venue_url or "主催者より別途ご案内予定"
    return f"{_base_description(fields, diff)}\n\n会場: {venue_display}"


def _announcement_embed(fields: dict, venue_url, diff: dict = None) -> dict:
    description = (
        f"{_announcement_body(fields, venue_url, diff)}\n\n"
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


def build_announcement_content(fields: dict, venue_url) -> dict:
    """告知メッセージのembedを組み立てる(新規作成時。差分表示なし)。"""
    return _announcement_embed(fields, venue_url)


def build_announcement_diff_content(fields: dict, venue_url, diff: dict) -> dict:
    """「更新通知」ボタンが押された際に、告知メッセージ(スレッド最初の投稿)の
    embedを再構成する。diffに含まれる項目(category/organizer_username/
    levels/datetime)は取り消し線+新しい値で表示する。
    """
    return _announcement_embed(fields, venue_url, diff)


def create_announcement_thread(fields: dict, venue_url) -> tuple[str, str]:
    """告知メッセージを投稿し、そこからスレッドを作成する。戻り値は (スレッドURL, スレッドID)。
    Discordの仕様上、メッセージからスレッドを作成すると、そのスレッドのIDは
    元の告知メッセージのIDと同じ値になる。そのためedit_announcement_message()は
    このthread_idをそのままメッセージIDとして使って告知メッセージを編集できる。
    """
    # 1. 告知メッセージを投稿
    msg_res = requests.post(
        f"{BASE_URL}/channels/{ANNOUNCE_CHANNEL_ID}/messages",
        headers=HEADERS,
        json=build_announcement_content(fields, venue_url),
    )
    _raise_for_status(msg_res)
    message_id = msg_res.json()["id"]

    # 2. そのメッセージからスレッドを作成
    thread_name = (fields.get("title") or "井戸端かいぎ")[:100]
    thread_res = requests.post(
        f"{BASE_URL}/channels/{ANNOUNCE_CHANNEL_ID}/messages/{message_id}/threads",
        headers=HEADERS,
        json={"name": thread_name, "auto_archive_duration": 10080},  # 7日
    )
    _raise_for_status(thread_res)
    thread_id = thread_res.json()["id"]

    return f"https://discord.com/channels/{GUILD_ID}/{thread_id}", thread_id


def build_todo_content(fields: dict, venue_url) -> str:
    """承認直後にスレッドへ投稿するTODO案内。このメッセージは公開スレッド
    (サーバーメンバーなら誰でも閲覧・参加可能)に投稿されるため、「申込み必須」
    イベントではvenue_urlをここにも一切表示しない
    (主催者自身が入力した値なので、改めて表示する必要もない)。
    venue_urlが未設定の場合はNoneでよく、その場合は用意を促す案内を先頭に
    追加する(「申込み必須」の有無にかかわらず、会場URLが届かないと
    参加者に何も案内できないため)。
    """
    material_folder_url = (
        "https://drive.google.com/drive/folders/1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU?usp=sharing"
    )
    mention = resolve_mention(fields.get("organizer_username"))
    admin_mention = resolve_mention("xenamanex")

    if fields.get("requires_rsvp") and venue_url:
        venue_section = (
            f"**会場URL**: 事前申込み制のため、参加申込みフォームからお申し込みいただいた方に"
            f"個別にメールでご案内します(このスレッドには掲載されません)。\n\n"
        )
        reminder_note = "開催30分前のリマインダーには、事前申込み制である旨のみが記載されます(会場URLは記載されません)"
    elif fields.get("requires_rsvp") and not venue_url:
        venue_section = (
            f"**会場URL**: (未設定・事前申込み制)\n\n"
            f"□ 0. 会場のURL(Zoomなど)が届いていません。このイベントは事前申込み制のため、"
            f"会場URLは参加申込みいただいた方へ個別にメールでご案内する仕組みです。**会場URLが"
            f"届かない限り、参加申込みされた方にご案内できません。** ご自身でご用意のうえ、この"
            f"スレッドへの返信でお知らせください。**ご自身での用意がどうしても難しい場合は、"
            f"{admin_mention} までご相談ください。**\n\n"
        )
        reminder_note = "開催30分前のリマインダーには、事前申込み制である旨のみが記載されます(会場URLは記載されません)"
    elif venue_url:
        venue_section = f"**会場URL**: {venue_url}\n\n"
        reminder_note = "開催30分前のリマインダーには会場URLが記載されます"
    else:
        venue_section = (
            f"**会場URL**: (未設定)\n\n"
            f"□ 0. 会場のURL(Zoomなど)が届いていません。ご自身でご用意のうえ、このスレッドへの"
            f"返信でお知らせください。**ご自身での用意がどうしても難しい場合は、"
            f"{admin_mention} までご相談ください。**\n\n"
        )
        reminder_note = "開催30分前のリマインダーには会場URLが記載されます"

    return (
        f"{mention}\n\n"
        f"井戸端かいぎ「{fields.get('title')}」の開催が確定しました。以下、今後の流れです。\n\n"
        f"{venue_section}"
        f"□ 1. 発表当日の2日前までに、発表資料を下記フォルダにアップロードしてください。\n"
        f"　　資料共有用フォルダ: {material_folder_url}\n"
        f"　　(アップロードした「資料そのもののURL」を、このスレッドへの返信でご共有ください)\n\n"
        f"□ 2. 2日前までに資料URLの共有が確認できない場合、このスレッドにリマインダーが自動投稿されます。\n\n"
        f"□ 3. 前日と、開催30分前に「#🐸｜井戸端かいぎ」チャンネル全体へ、このスレッドへの"
        f"リンクつきでリマインダーが届きます({reminder_note})。\n\n"
        f"□ 4. 近日中に、Notionの「井戸端かいぎの予定表」データベースへの編集権限を運営から"
        f"付与します。ご自身のイベントページの内容を修正したら、そのページの「更新情報を"
        f"スレッドに通知する」ボタンを押してください。押した時点で、このスレッドの最初の投稿"
        f"(変更箇所に取り消し線)が更新されます。**日時を変更した場合は、加えて"
        f"「#🐸｜井戸端かいぎ」チャンネル全体へも通知が届きます**(Googleカレンダーの予定も"
        f"自動で更新されます)。ボタンを押すまでは通知されないため、修正が全て終わってから"
        f"押してください(何度でも押し直せます)。\n\n"
        f"□ 5. このイベントを継続シリーズとして次回も開催する場合は、このイベントのNotionページを"
        f"複製し、日時だけを変更して「ステータス」を「確定」にしてください。日時が入力されて"
        f"「確定」になると、その都度この案内と同じ流れで新しいスレッドが自動的に作成されます"
        f"(会場URLも前回と同じものが自動的に引き継がれます)。\n\n"
        f"□ 6. やむを得ず開催をキャンセルする場合は、このスレッドで {admin_mention} をメンションしてお知らせください。\n\n"
        f"ご不明な点があれば、このスレッドまでお気軽にどうぞ。"
    )


def build_participant_notice_content(fields: dict) -> str:
    """TODO案内に続けてスレッドへ投稿する、主催者以外の参加者向けの案内。
    このイベントについての問い合わせや、発表内容に関する質疑もこのスレッドで
    受け付けている旨を伝える。
    """
    return (
        f"📣 「{fields.get('title')}」について、ご質問やお問い合わせ、発表内容に関する"
        f"質疑応答も、主催者以外の方を含めどなたでもこのスレッドにご投稿いただけます。"
        f"お気軽にどうぞ。"
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
        f"公開予定表に転記済み(ステータス「承認待ち」): {notion_page_url(public_page_id)}\n\n"
        f"内容を確認し、問題なければ上記「申込み内容」ページでメールアドレスを確認のうえ、"
        f"予定表ページの「共有」からそのメールアドレスをゲスト招待して編集権限を付与し、"
        f"「ステータス」を「確定」に変更してください。"
    )


def edit_announcement_message(thread_id: str, content: dict):
    """告知メッセージ(スレッドの最初の投稿)を編集する。thread_idは
    create_announcement_thread()が返したスレッドID(=元メッセージIDと同じ値)。
    """
    res = requests.patch(
        f"{BASE_URL}/channels/{ANNOUNCE_CHANNEL_ID}/messages/{thread_id}",
        headers=HEADERS,
        json=content,
    )
    _raise_for_status(res)
    return res.json()


def post_message(channel_or_thread_id: str, content: str):
    """チャンネルまたはスレッドにメッセージを投稿する。"""
    res = requests.post(
        f"{BASE_URL}/channels/{channel_or_thread_id}/messages",
        headers=HEADERS,
        json={"content": content},
    )
    _raise_for_status(res)
    return res.json()
