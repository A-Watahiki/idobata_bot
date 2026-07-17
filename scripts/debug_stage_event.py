"""create_stage_eventだけを単体で試すデバッグ用スクリプト。
Discordスレッドの作成やNotionの更新は一切行わない。
問題切り分けが済んだら削除してよい。
"""
from datetime import datetime, timedelta, timezone

import discord_utils


def main():
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
