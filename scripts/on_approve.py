"""Notionの「承認」ボタン(Webhook送信)から呼ばれるスクリプト。

GitHub Actions の repository_dispatch イベント経由で起動される想定。
client_payload に Notion の page_id が含まれている前提。

処理内容:
  1. Notionページから必要な情報を取得
  2. Discordにお知らせスレッドを作成
  3. Discordのステージチャンネルにイベントを作成
  4. スレッドURLをNotionのページに書き戻す
"""
import json
import os
import sys

from notion_utils import get_page, extract_fields, set_discord_thread_url
import discord_utils


def main():
    payload = json.loads(os.environ["GITHUB_EVENT_PAYLOAD"])
    page_id = payload["client_payload"]["page_id"]

    page = get_page(page_id)
    fields = extract_fields(page)
    print(f"[on_approve] processing: {fields['title']}")

    thread_url = discord_utils.create_announcement_thread(fields)
    print(f"[on_approve] thread created: {thread_url}")

    try:
        if fields.get("datetime"):
            event_url = discord_utils.create_stage_event(fields)
            print(f"[on_approve] stage event created: {event_url}")
        else:
            print("[on_approve] datetime not set yet, skipping stage event creation")
    except Exception as e:  # noqa: BLE001
        # イベント作成に失敗してもスレッド作成・書き戻しは続行する
        print(f"[on_approve] WARNING: failed to create stage event: {e}", file=sys.stderr)

    set_discord_thread_url(page_id, thread_url)
    print("[on_approve] Notion page updated with thread URL")


if __name__ == "__main__":
    main()
