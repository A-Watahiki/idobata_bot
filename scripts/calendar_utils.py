"""Google Calendar APIとやり取りするための共通関数。

必要な環境変数:
  GOOGLE_CALENDAR_CLIENT_ID       OAuthクライアントID
  GOOGLE_CALENDAR_CLIENT_SECRET   OAuthクライアントシークレット
  GOOGLE_CALENDAR_REFRESH_TOKEN   doubutsurinrikaigi@gmail.comで一度だけ認証して取得したリフレッシュトークン
  GOOGLE_CALENDAR_ID              対象カレンダーのID(通常は doubutsurinrikaigi@gmail.com 自身、
                                   または "primary")

Zoomリンクは対外公開のNotion DBには一切保存せず、このカレンダーの予定にのみ
記載する。予定のextendedProperties.privateにNotionのpage_idとDiscordスレッド
IDを保存しておき、リマインダー送信時にはカレンダー側からこれらを読み出す
(Notion側にZoomリンクを問い合わせる必要がないようにするため)。
"""
import os
from datetime import datetime, timedelta

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

FREQ_MAP = {
    "日ごと": "DAILY",
    "週ごと": "WEEKLY",
    "月ごと": "MONTHLY",
}


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

    body = {
        "summary": fields.get("title") or "井戸端かいぎ",
        "description": f"{fields.get('summary') or ''}\n\nZoom: {zoom_url}",
        "location": zoom_url,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Tokyo"},
        "extendedProperties": {
            "private": {
                "notion_page_id": fields["page_id"],
                "discord_thread_id": thread_id,
                "zoom_join_url": zoom_url,
            }
        },
    }

    frequency = fields.get("frequency") or "単発"
    if frequency != "単発":
        freq = FREQ_MAP.get(frequency)
        if freq is None:
            raise ValueError(f"unknown frequency: {frequency}")
        interval = int(fields.get("interval") or 1)
        count = int(fields.get("occurrence_count") or 1)
        body["recurrence"] = [f"RRULE:FREQ={freq};INTERVAL={interval};COUNT={count}"]

    event = service.events().insert(calendarId=calendar_id, body=body).execute()
    return event


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
