"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(5分おき、poll.ymlから実行)。

Googleカレンダーの今後の予定のうち、Notionの行と紐づいている(notion_page_id
つき)ものを一覧し、対応するNotionページが
  - 削除されている(APIから404)
  - ゴミ箱に入っている(archived: true)
  - 「ステータス」が「キャンセル」になっている
場合、そのカレンダー予定を自動的に削除する。Googleカレンダーは基本的に
このスクリプトからの削除以外では編集しない方針。
"""
import calendar_utils
import discord_utils
import notion_utils


def _is_cancelled(page) -> bool:
    if page is None:
        return True
    if page.get("archived"):
        return True
    fields = notion_utils.extract_fields(page)
    return fields.get("status") == "キャンセル"


def main():
    events = calendar_utils.list_future_events_with_notion_link()
    print(f"[sync_cancellations] {len(events)} future calendar event(s) linked to Notion")

    for event in events:
        props = event.get("extendedProperties", {}).get("private", {})
        page_id = props["notion_page_id"]
        page = notion_utils.get_page_or_none(page_id)

        if not _is_cancelled(page):
            continue

        thread_url = props.get("discord_thread_url")
        calendar_utils.delete_event(event["id"])
        print(f"[sync_cancellations] deleted calendar event for cancelled/removed page: {event.get('summary')}")

        if thread_url:
            thread_id = thread_url.rstrip("/").split("/")[-1]
            discord_utils.post_message(
                thread_id,
                f"❌ 「{event.get('summary')}」はキャンセルされました。Googleカレンダーの予定も削除しました。",
            )
            discord_utils.post_message(
                discord_utils.ANNOUNCE_CHANNEL_ID,
                f"❌ 「{event.get('summary')}」はキャンセルされました。\nスレッド: {thread_url}",
            )


if __name__ == "__main__":
    main()
