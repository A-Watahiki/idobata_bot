"""Zoom REST API とやり取りするための共通関数(Server-to-Server OAuth)。

必要な環境変数:
  ZOOM_ACCOUNT_ID      Zoom Server-to-Server OAuthアプリのAccount ID
  ZOOM_CLIENT_ID       同アプリのClient ID
  ZOOM_CLIENT_SECRET   同アプリのClient Secret

事前準備:
  Zoom App Marketplace (https://marketplace.zoom.us/) で
  「Server-to-Server OAuth」タイプのアプリを作成し、
  Scopes に "meeting:write:meeting" (または meeting:write) を追加しておく。
"""
import os
from datetime import datetime, timedelta

import requests

ACCOUNT_ID = os.environ["ZOOM_ACCOUNT_ID"]
CLIENT_ID = os.environ["ZOOM_CLIENT_ID"]
CLIENT_SECRET = os.environ["ZOOM_CLIENT_SECRET"]

DEFAULT_DURATION_MINUTES = 30

# Notionの「開催頻度」プロパティの値 -> Zoom recurrence.type
RECURRENCE_TYPE = {
    "日ごと": 1,
    "週ごと": 2,
    "月ごと": 3,
}


def _get_access_token() -> str:
    res = requests.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": ACCOUNT_ID},
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    res.raise_for_status()
    return res.json()["access_token"]


def create_meeting(fields: dict) -> str:
    """Notionの開催頻度に応じてZoomミーティングを作成し、join_urlを返す。

    単発の場合は通常の予定済みミーティング、
    定期の場合は「固定時間で繰り返す」ミーティングを作成する
    (この場合、シリーズ全体で同じjoin_urlが使い回される)。
    """
    token = _get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    start_dt = datetime.fromisoformat(fields["datetime"])
    frequency = fields.get("frequency") or "単発"

    body = {
        "topic": (fields.get("title") or "井戸端かいぎ")[:200],
        "agenda": (fields.get("summary") or "")[:2000],
        "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "timezone": "Asia/Tokyo",
        "duration": DEFAULT_DURATION_MINUTES,
        "settings": {
            "join_before_host": True,
            "waiting_room": False,
        },
    }

    if frequency == "単発":
        body["type"] = 2  # scheduled meeting
    else:
        recurrence_type = RECURRENCE_TYPE.get(frequency)
        if recurrence_type is None:
            raise ValueError(f"unknown frequency: {frequency}")
        body["type"] = 8  # recurring meeting with fixed time
        body["recurrence"] = {
            "type": recurrence_type,
            "repeat_interval": int(fields.get("interval") or 1),
            "end_times": int(fields.get("occurrence_count") or 1),
        }

    res = requests.post(
        "https://api.zoom.us/v2/users/me/meetings",
        headers=headers,
        json=body,
    )
    if not res.ok:
        print(f"[zoom_utils] Zoom API error {res.status_code}: {res.text}")
    res.raise_for_status()
    return res.json()["join_url"]
