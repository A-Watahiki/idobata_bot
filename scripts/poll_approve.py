"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき)。

「ステータス」が「確定」になっているのに、まだ「Discordスレッド」が
作成されていない(=空の)ページを検知し、以下を行う。

  1. Zoomミーティングを作成(「シリーズ名」が空なら毎回新規。入力されていて
     同じシリーズ名の既存Zoomリンクがあれば再利用し、なければ「時間固定なし」
     ミーティングを新規作成)
  2. Discordにお知らせスレッドを作成(種別・日時・主催者・Zoom会場などを記載)
  3. Googleカレンダーに予定を作成(スレッドと同じ内容+Zoomリンクを記載。
     NotionにはZoomリンクを書かない。Googleカレンダーはメンバー向けの
     非公開の日程確認手段であり、Discordには送らない)
  4. スレッドにTODO案内を投稿(主催者へのメンションつき)
  5. スレッドURLをNotionのページに書き戻す

「シリーズ名」が入力されている複数回開催は、開催の都度Notion上で前回の
ページを複製して日時だけ書き換える運用を前提としている(タイトル・種別・
概要・対象・シリーズ名は複製時に自動的に引き継がれるため、このスクリプトは
シリーズの正データを別途取得する処理を持たない)。
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

        zoom_meeting = None
        if fields.get("series_name"):
            zoom_meeting = calendar_utils.find_series_zoom_meeting(fields["series_name"])
            if zoom_meeting:
                print(f"[poll_approve] reusing existing zoom link for series")

        if not zoom_meeting:
            zoom_meeting = zoom_utils.create_meeting(fields)
            print(f"[poll_approve] zoom meeting created")

        zoom_url = zoom_meeting["join_url"]

        thread_url, thread_id = discord_utils.create_announcement_thread(fields, zoom_url)
        print(f"[poll_approve] thread created: {thread_url}")

        description = discord_utils.build_shared_description(fields, zoom_url)
        calendar_utils.create_event(fields, zoom_meeting, thread_id, thread_url, description)
        print(f"[poll_approve] calendar event created")

        todo_content = discord_utils.build_todo_content(fields, zoom_url)
        discord_utils.post_message(thread_id, todo_content)
        print(f"[poll_approve] TODO message posted to thread: {fields['title']}")

        set_discord_thread_url(fields["page_id"], thread_url)
        print(f"[poll_approve] Notion page updated with thread URL: {fields['title']}")


if __name__ == "__main__":
    main()
