"""Google Calendar APIとやり取りするための共通関数。

必要な環境変数:
  GOOGLE_CALENDAR_CLIENT_ID       OAuthクライアントID
  GOOGLE_CALENDAR_CLIENT_SECRET   OAuthクライアントシークレット
  GOOGLE_CALENDAR_REFRESH_TOKEN   doubutsurinrikaigi@gmail.comで一度だけ認証して取得したリフレッシュトークン
  GOOGLE_CALENDAR_ID              対象カレンダーのID(通常は doubutsurinrikaigi@gmail.com 自身、
                                   または "primary")

Zoomリンクは対外公開のNotion DBには一切保存せず、このカレンダーの予定にのみ
記載する。予定のextendedProperties.privateにNotionのpage_id・Discordスレッド
ID・(複数回開催の場合の)シリーズ名を保存しておき、リマインダー送信時や
シリーズの2回目以降のZoomリンク再利用時にはカレンダー側からこれらを
読み出す(Notion側にZoomリンクを問い合わせる必要がないようにするため)。

「開催頻度」が「複数回」の場合、Notion側は開催の都度新しい行(ページ)を
作る運用のため、カレンダー側もRRULEによる繰り返し予定ではなく、
毎回1件ずつ通常の予定として作成する。同じシリーズかどうかは
「シリーズ名」で判定し、既存のZoomリンクを使い回す。
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
    zoom_url: str,
    thread_id: str,
    thread_url: str,
    description: str,
    duration_minutes: int = 30,
) -> dict:
    """Zoomリンクを含む予定をGoogleカレンダーに作成する。戻り値はイベント本体
    (event["htmlLink"] がその予定への直接リンクになる)。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    start_dt = datetime.fromisoformat(fields["datetime"])
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    private_props = {
        "notion_page_id": fields["page_id"],
        "discord_thread_id": thread_id,
        "discord_thread_url": thread_url,
        "zoom_join_url": zoom_url,
    }
    if fields.get("series_name"):
        private_props["series_name"] = fields["series_name"]

    body = {
        "summary": fields.get("title") or "井戸端かいぎ",
        "description": description,
        "location": zoom_url,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "extendedProperties": {"private": private_props},
    }

    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    return event


def delete_event(event_id: str):
    """予定を削除する(Notion側でキャンセル・削除された場合に呼ばれる)。"""
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()


def list_future_events_with_notion_link(days_ahead: int = 200) -> list:
    """今後開催予定の中で、notion_page_idが紐づいている予定を一覧する
    (Notion側のキャンセル・削除同期に使う)。
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


def find_series_zoom_url(series_name: str):
    """同じ「シリーズ名」を持つ過去のカレンダー予定から、既存のZoomリンクを探す。
    見つからなければNoneを返す(=このシリーズの初回として新規作成が必要)。
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
    return items[0].get("extendedProperties", {}).get("private", {}).get("zoom_join_url")


def mark_reminder_sent(event_id: str, key: str):
    """指定した回(インスタンス)のextendedPropertiesにリマインダー送信済みフラグを立てる。
    繰り返し予定でも、この回だけの上書きとして保存されるため、他の回には影響しない。
    """
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    props = event.get("extendedProperties", {}).get("private", {})
    props[key] = "true"
    service.events().patch(
        calendarId=calendar_id,
        eventId=event_id,
        body={"extendedProperties": {"private": props}},
    ).execute()


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
