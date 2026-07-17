"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき)。

「ステータス」が「確定」になっているのに、まだ「Discordスレッド」が
作成されていない(=空の)ページを検知し、以下を行う。

  1. Discordにお知らせスレッドを作成
  2. Discordのステージチャンネルにイベントを作成
  3. スレッドURLをNotionのページに書き戻す
"""
import sys

from notion_utils import query_database, extract_fields, set_discord_thread_url
import discord_utils


def main():
    pages = query_database(
        {
            "and": [
                {"property": "ステータス", "select": {"equals": "確定"}},
                {"property": "Discordスレッド", "url": {"is_empty": True}},
            ]
        }
    )
    print(f"[poll_approve] {len(pages)} newly approved session(s) found")

    for page in pages:
        fields = extract_fields(page)
        print(f"[poll_approve] processing: {fields['title']}")

        thread_url, thread_id = discord_utils.create_announcement_thread(fields)
        print(f"[poll_approve] thread created: {thread_url}")

        discord_utils.post_message_to_thread(thread_id, discord_utils.build_todo_content(fields))
        print(f"[poll_approve] TODO message posted to thread: {fields['title']}")

        try:
            if fields.get("datetime"):
                event_url = discord_utils.create_stage_event(fields)
                print(f"[poll_approve] stage event created: {event_url}")
            else:
                print("[poll_approve] datetime not set yet, skipping stage event creation")
        except Exception as e:  # noqa: BLE001
            # イベント作成に失敗してもスレッド作成・書き戻しは続行する
            print(f"[poll_approve] WARNING: failed to create stage event: {e}", file=sys.stderr)

        set_discord_thread_url(fields["page_id"], thread_url)
        print(f"[poll_approve] Notion page updated with thread URL: {fields['title']}")


if __name__ == "__main__":
    main()
