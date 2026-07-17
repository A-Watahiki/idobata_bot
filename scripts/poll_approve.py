"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき)。

「ステータス」が「確定」になっているのに、まだ「Discordスレッド」が
作成されていない(=空の)ページを検知し、以下を行う。

  1. 「複数回」シリーズの2回目以降で、タイトル・種別・概要・対象・発表者氏名が
     未入力の場合、同じシリーズ名の直近の行から引き継いでNotionに書き戻す
     (発表者はシリーズ名と日時だけ入力すればよい)
  2. Zoomミーティングを作成(単発は毎回新規、複数回はシリーズ名が
     一致する既存のZoomリンクがあれば再利用し、なければ「時間固定なし」
     ミーティングを新規作成)
  3. Discordにお知らせスレッドを作成(Zoomリンク・種別・日時などを記載)
  4. Googleカレンダーに予定を作成(スレッドと同じ内容+Zoomリンクを記載。
     NotionにはZoomリンクを書かない)
  5. スレッドにTODO案内を投稿(主催者へのメンションつき。Googleカレンダーの
     予定へのリンクも記載)
  6. スレッドURLをNotionのページに書き戻す
"""
from notion_utils import (
    query_database,
    extract_fields,
    find_previous_series_page,
    set_inherited_fields,
    set_discord_thread_url,
)
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

        if fields.get("frequency") == "複数回" and fields.get("series_name"):
            missing = not all(
                fields.get(k) for k in ("title", "category", "presenter_name", "summary", "levels")
            )
            if missing:
                prev = find_previous_series_page(fields["series_name"], fields["page_id"])
                if prev:
                    for key in ("title", "category", "presenter_name", "summary", "levels"):
                        if not fields.get(key):
                            fields[key] = prev[key]
                    set_inherited_fields(fields["page_id"], fields)
                    print(f"[poll_approve] inherited fields from previous series entry: {fields['series_name']}")

        zoom_url = None
        if fields.get("frequency") == "複数回" and fields.get("series_name"):
            zoom_url = calendar_utils.find_series_zoom_url(fields["series_name"])
            if zoom_url:
                print(f"[poll_approve] reusing existing zoom link for series: {fields['series_name']}")

        if not zoom_url:
            zoom_url = zoom_utils.create_meeting(fields)
            print(f"[poll_approve] zoom meeting created")

        thread_url, thread_id = discord_utils.create_announcement_thread(fields, zoom_url)
        print(f"[poll_approve] thread created: {thread_url}")

        description = discord_utils.build_shared_description(fields, zoom_url)
        calendar_event = calendar_utils.create_event(fields, zoom_url, thread_id, thread_url, description)
        calendar_link = calendar_event["htmlLink"]
        print(f"[poll_approve] calendar event created")

        todo_content = discord_utils.build_todo_content(fields, zoom_url, calendar_link)
        discord_utils.post_message(thread_id, todo_content)
        print(f"[poll_approve] TODO message posted to thread: {fields['title']}")

        set_discord_thread_url(fields["page_id"], thread_url)
        print(f"[poll_approve] Notion page updated with thread URL: {fields['title']}")


if __name__ == "__main__":
    main()
