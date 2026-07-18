"""Google Calendar APIとやり取りするための共通関数。

必要な環境変数:
  GOOGLE_CALENDAR_CLIENT_ID       OAuthクライアントID
  GOOGLE_CALENDAR_CLIENT_SECRET   OAuthクライアントシークレット
  GOOGLE_CALENDAR_REFRESH_TOKEN   doubutsurinrikaigi@gmail.comで一度だけ認証して取得したリフレッシュトークン
  GOOGLE_CALENDAR_ID              対象カレンダーのID(通常は doubutsurinrikaigi@gmail.com 自身、
                                   または "primary")

会場URL(Zoomリンクなど。主催者が申込み時に用意したもの)は対外公開のNotion
DBには一切保存せず、このカレンダーの予定にのみ記載する。予定の
extendedProperties.privateにNotionのpage_id・Discordスレッド
ID・(複数回開催の場合の)シリーズ名・会場URLを保存しておき、リマインダー
送信時やシリーズの2回目以降の会場URL再利用時にはカレンダー側からこれらを
読み出す(Notion側に会場URLを問い合わせる必要がないようにするため)。

「シリーズ名」が入力されている場合、Notion側は開催の都度、前回のページを
複製して日時だけ書き換える運用のため、カレンダー側もRRULEによる繰り返し
予定ではなく、毎回1件ずつ通常の予定として作成する。同じシリーズかどうかは
「シリーズ名」の文字列一致で判定し、既存の会場URLを使い回す
(複製により再入力なしでシリーズ名が引き継がれる前提。主催者は初回申込み時に
入力した会場URLを、シリーズを通じて使い続けることを想定している)。

extendedProperties.privateには、種別・主催者ユーザ名・対象のスナップショット
(snapshot_*)も保存する。予定表の「更新通知」ボタンが押されたとき、
sync_updates.pyがこのスナップショットと現在のNotionの値を比較し、
変更された項目をDiscordの告知メッセージに取り消し線つきで表示する。
"""
import os
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_CALENDAR_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CALENDAR_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CALENDAR_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("calendar", "v3", credentials=creds)


def create_event(
    fields: dict,
    venue_url,
    thread_id: str,
    thread_url: str,
    description: str,
    duration_minutes: int = 30,
) -> dict:
    """会場URL(Zoomリンクなど)を含む予定をGoogleカレンダーに作成する。
    venue_urlは主催者から届いていない場合Noneでもよい(その場合はlocationも
    空のまま作成し、届き次第set_extended_propertiesで補完する運用)。
    戻り値はイベント本体(event["htmlLink"] がその予定への直接リンクになる)。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    start_dt = datetime.fromisoformat(fields["datetime"])
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    private_props = {
        "notion_page_id": fields["page_id"],
        "discord_thread_id": thread_id,
        "discord_thread_url": thread_url,
        "venue_url": venue_url or "",
        "requires_rsvp": "true" if fields.get("requires_rsvp") else "false",
        "notion_last_edited_time": fields.get("last_edited_time") or "",
        # 「更新通知」ボタンが押された際に、前回通知時点からの変更点を
        # 取り消し線つきで表示するためのスナップショット(sync_updates.py参照)。
        "snapshot_category": fields.get("category") or "",
        "snapshot_organizer_username": fields.get("organizer_username") or "",
        "snapshot_levels": ",".join(fields.get("levels") or []),
    }
    if fields.get("series_name"):
        private_props["series_name"] = fields["series_name"]

    body = {
        "summary": fields.get("title") or "井戸端かいぎ",
        "description": description,
        "location": venue_url or "",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "extendedProperties": {"private": private_props},
    }

    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    return event


def get_event(event_id: str) -> dict:
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    return service.events().get(calendarId=calendar_id, eventId=event_id).execute()


def delete_event(event_id: str):
    """予定を削除する(Notion側でキャンセル・削除された場合に呼ばれる)。"""
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def set_extended_properties(event_id: str, updates: dict):
    """extendedProperties.privateの一部キーだけを更新する(既存の値は保持)。"""
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    event = get_event(event_id)
    props = event.get("extendedProperties", {}).get("private", {})
    props.update({k: str(v) for k, v in updates.items()})
    service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body={"extendedProperties": {"private": props}},
    ).execute()


def mark_reminder_sent(event_id: str, key: str):
    """指定した回(インスタンス)のextendedPropertiesにリマインダー送信済みフラグを立てる。
    繰り返し予定でも、この回だけの上書きとして保存されるため、他の回には影響しない。
    """
    set_extended_properties(event_id, {key: "true"})


def update_event_time(event_id: str, datetime_str: str, duration_minutes: int = 30):
    """予定の開始・終了時刻を変更する(Notion側の日時変更検知時に使う)。"""
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    start_dt = datetime.fromisoformat(datetime_str)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body={
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tokyo"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        },
    ).execute()


def update_event_content(event_id: str, summary: str, description: str):
    """タイトル・説明欄を更新する(日時以外の変更検知時に使う)。"""
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body={"summary": summary, "description": description},
    ).execute()


def list_future_events_with_notion_link(days_ahead: int = 200) -> list:
    """今後開催予定の中で、notion_page_idが紐づいている予定を一覧する
    (Notion側のキャンセル・削除・変更同期に使う)。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

    events = []
    page_token = None
    while True:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token,
        ).execute()
        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return [e for e in events if e.get("extendedProperties", {}).get("private", {}).get("notion_page_id")]


def find_series_venue_url(series_name: str):
    """同じ「シリーズ名」を持つ過去のカレンダー予定から、既存の会場URLを探す。
    見つからなければNoneを返す(=このシリーズの初回として申込みページから
    会場URLを取得する必要がある)。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    result = service.events().list(
        calendarId=calendar_id,
        privateExtendedProperty=f"series_name={series_name}",
        maxResults=1,
        orderBy="updated",
        singleEvents=True,
    ).execute()
    items = result.get("items", [])
    if not items:
        return None
    props = items[0].get("extendedProperties", {}).get("private", {})
    return props.get("venue_url") or None


def find_event_by_notion_page_id(notion_page_id: str):
    """指定したNotionページIDに紐づくカレンダー予定を1件探す。
    見つからなければNoneを返す(=このイベントはまだ承認・カレンダー登録されて
    いない。rsvp_notify.pyが「申込み必須」イベントの会場URLを引くために使う)。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    result = service.events().list(
        calendarId=calendar_id,
        privateExtendedProperty=f"notion_page_id={notion_page_id}",
        maxResults=1,
        singleEvents=True,
    ).execute()
    items = result.get("items", [])
    return items[0] if items else None


def list_upcoming_instances(minutes_from_now_start: int, minutes_from_now_end: int) -> list:
    """指定した「今からN分後〜M分後」の範囲で始まる予定インスタンスを返す
    (繰り返し予定は singleEvents=True で個々の回に展開される)。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    now = datetime.utcnow()
    time_min = (now + timedelta(minutes=minutes_from_now_start)).isoformat() + "Z"
    time_max = (now + timedelta(minutes=minutes_from_now_end)).isoformat() + "Z"

    result = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return result.get("items", [])
