"""create_stage_eventだけを単体で試すデバッグ用スクリプト。
Discordスレッドの作成やNotionの更新は一切行わない。
問題切り分けが済んだら削除してよい。
"""
import os
from datetime import datetime, timedelta, timezone

import requests

import discord_utils


def list_guild_channels():
    """サーバー内の全チャンネルとその種別を確認する(ステージチャンネルはtype=13)。"""
    res = requests.get(
        f"{discord_utils.BASE_URL}/guilds/{os.environ['DISCORD_GUILD_ID']}/channels",
        headers=discord_utils.HEADERS,
    )
    res.raise_for_status()
    channels = res.json()
    print("[debug_stage_event] --- guild channels ---")
    for c in channels:
        marker = " <== DISCORD_STAGE_CHANNEL_ID" if c["id"] == os.environ.get("DISCORD_STAGE_CHANNEL_ID") else ""
        print(f"  id={c['id']} type={c['type']} name={c.get('name')}{marker}")
    print("[debug_stage_event] --- end of list ---")


def main():
    list_guild_channels()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    fields = {
        "title": "デバッグ用テストイベント",
        "summary": "create_stage_event単体テスト",
        "datetime": start.isoformat(),
    }
    try:
        url = discord_utils.create_stage_event(fields)
        print(f"[debug_stage_event] SUCCESS: {url}")
    except Exception as e:  # noqa: BLE001
        print(f"[debug_stage_event] FAILED: {e}")


if __name__ == "__main__":
    main()
