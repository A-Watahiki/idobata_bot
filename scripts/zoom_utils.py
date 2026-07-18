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
from datetime import datetime

import requests

ACCOUNT_ID = os.environ["ZOOM_ACCOUNT_ID"]
CLIENT_ID = os.environ["ZOOM_CLIENT_ID"]
CLIENT_SECRET = os.environ["ZOOM_CLIENT_SECRET"]

DEFAULT_DURATION_MINUTES = 30


def _get_access_token() -> str:
    res = requests.post(
        "https://zoom.us/oauth/token",
        params={"grant_type": "account_credentials", "account_id": ACCOUNT_ID},
        auth=(CLIENT_ID, CLIENT_SECRET),
    )
    res.raise_for_status()
    return res.json()["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_access_token()}", "Content-Type": "application/json"}


def create_meeting(fields: dict) -> dict:
    """「シリーズ名」の有無に応じてZoomミーティングを作成する。戻り値は
    {"meeting_id": ..., "join_url": ...}。

    「シリーズ名」が空の場合は通常の予定済みミーティング。
    入力されている場合は「時間固定なしの繰り返しミーティング」を作成する。
    このタイプはシリーズを通じて同じjoin_urlを使い回せるため、
    2回目以降の開催では新規作成せずこのURLを再利用する想定。
    """
    body = {
        "topic": (fields.get("title") or "井戸端かいぎ")[:200],
        "agenda": (fields.get("summary") or "")[:2000],
        "duration": DEFAULT_DURATION_MINUTES,
        "settings": {
            "join_before_host": True,
            "waiting_room": False,
        },
    }

    if fields.get("series_name"):
        body["type"] = 3  # recurring meeting, no fixed time
    else:
        start_dt = datetime.fromisoformat(fields["datetime"])
        body["type"] = 2  # scheduled meeting
        body["start_time"] = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        body["timezone"] = "Asia/Tokyo"

    res = requests.post(
        "https://api.zoom.us/v2/users/me/meetings",
        headers=_headers(),
        json=body,
    )
    if not res.ok:
        print(f"[zoom_utils] Zoom API error {res.status_code}: {res.text}")
    res.raise_for_status()
    data = res.json()
    return {"meeting_id": data["id"], "join_url": data["join_url"]}


def update_meeting_time(meeting_id: str, datetime_str: str):
    """単発ミーティングの開始時刻を変更する(日時変更の同期用)。
    「時間固定なし」の繰り返しミーティング(シリーズ用)には時刻の概念がないため対象外。
    """
    start_dt = datetime.fromisoformat(datetime_str)
    res = requests.patch(
        f"https://api.zoom.us/v2/meetings/{meeting_id}",
        headers=_headers(),
        json={
            "start_time": start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timezone": "Asia/Tokyo",
        },
    )
    if not res.ok:
        print(f"[zoom_utils] Zoom API error {res.status_code}: {res.text}")
    res.raise_for_status()
