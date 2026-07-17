"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき)。

「ステータス」が「確定」になっているのに、まだ「Discordスレッド」が
作成されていない(=空の)ページを検知し、以下を行う。

  1. Zoomミーティングを作成(単発は毎回新規、複数回はシリーズ名が
     一致する既存のZoomリンクがあれば再利用し、なければ「時間固定なし」
     ミーティングを新規作成)
  2. Googleカレンダーに予定を作成(Zoomリンクを記載。NotionにはZoomリンクを書かない)
  3. Discordにお知らせスレッドを作成してTODO案内を投稿(Zoomリンクは含めない)
  4. スレッドURLをNotionのページに書き戻す
"""
from notion_utils import query_database, extract_fields, set_discord_thread_url
import calendar_utils
import discord_utils
import zoom_utils


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

        if not fields.get("datetime"):
            print(f"[poll_approve] {fields['title']}: datetime not set yet, skipping")
            continue

        thread_url, thread_id = discord_utils.create_announcement_thread(fields)
        print(f"[poll_approve] thread created: {thread_url}")

        zoom_url = None
        if fields.get("frequency") == "複数回" and fields.get("series_name"):
            zoom_url = calendar_utils.find_series_zoom_url(fields["series_name"])
            if zoom_url:
                print(f"[poll_approve] reusing existing zoom link for series: {fields['series_name']}")

        if not zoom_url:
            zoom_url = zoom_utils.create_meeting(fields)
            print(f"[poll_approve] zoom meeting created")

        calendar_utils.create_event(fields, zoom_url, thread_id)
        print(f"[poll_approve] calendar event created")

        discord_utils.post_message_to_thread(thread_id, discord_utils.build_todo_content(fields))
        print(f"[poll_approve] TODO message posted to thread: {fields['title']}")

        set_discord_thread_url(fields["page_id"], thread_url)
        print(f"[poll_approve] Notion page updated with thread URL: {fields['title']}")


if __name__ == "__main__":
    main()
