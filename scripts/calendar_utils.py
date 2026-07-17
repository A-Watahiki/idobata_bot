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


def create_event(fields: dict, zoom_url: str, thread_id: str, duration_minutes: int = 30) -> dict:
    """Zoomリンクを含む予定をGoogleカレンダーに作成する。戻り値はイベントのid/htmlLink。"""
    service = _get_service()
    calendar_id = os.environ["GOOGLE_CALENDAR_ID"]

    start_dt = datetime.fromisoformat(fields["datetime"])
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    private_props = {
        "notion_page_id": fields["page_id"],
        "discord_thread_id": thread_id,
        "zoom_join_url": zoom_url,
    }
    if fields.get("series_name"):
        private_props["series_name"] = fields["series_name"]

    body = {
        "summary": fields.get("title") or "井戸端かいぎ",
        "description": f"{fields.get('summary') or ''}\n\nZoom: {zoom_url}",
        "location": zoom_url,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "extendedProperties": {"private": private_props},
    }

    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    return event


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
