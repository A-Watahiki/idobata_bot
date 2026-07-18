"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき)。

「ステータス」が「確定」になっているのに、まだ「Discordスレッド」が
作成されていない(=空の)ページを検知し、以下を行う。

  1. 会場URL(Zoomリンクなど)を特定する。「シリーズ名」が入力されていて
     既存のカレンダー予定に同じシリーズ名のものがあれば、その会場URLを
     再利用する。なければ、申込み時に主催者自身が入力した「会場URL」を
     非公開の「井戸端かいぎ 申込み」ページから直接読み出す。
     会場URLが主催者からまだ届いていない場合はNoneのまま進め、
     TODO案内で主催者に用意を促す(自分で用意できない場合は運営に依頼)。
  2. Discordにお知らせスレッドを作成(種別・日時・主催者・会場URLなどを記載)
  3. Googleカレンダーに予定を作成(スレッドと同じ内容+会場URLを記載。
     NotionにはZoomリンクなどの会場URLを一切書かない。Googleカレンダーは
     メンバー向けの非公開の日程確認手段であり、Discordには送らない)
  4. スレッドにTODO案内を投稿(主催者へのメンションつき)
  5. スレッドURLをNotionのページに書き戻す

「シリーズ名」が入力されている複数回開催は、開催の都度Notion上で前回の
ページを複製して日時だけ書き換える運用を前提としている(タイトル・種別・
概要・対象・シリーズ名は複製時に自動的に引き継がれるため、このスクリプトは
シリーズの正データを別途取得する処理を持たない)。
"""
from notion_utils import (
    query_database,
    extract_fields,
    set_discord_thread_url,
    get_submission_venue_url,
)
import calendar_utils
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

        if not fields.get("datetime"):
            print(f"[poll_approve] {fields['title']}: datetime not set yet, skipping")
            continue

        venue_url = None
        if fields.get("series_name"):
            venue_url = calendar_utils.find_series_venue_url(fields["series_name"])
            if venue_url:
                print(f"[poll_approve] reusing existing venue URL for series")

        if not venue_url and fields.get("submission_page_id"):
            venue_url = get_submission_venue_url(fields["submission_page_id"])
            if venue_url:
                print(f"[poll_approve] venue URL fetched from submission page")

        if not venue_url:
            print(f"[poll_approve] {fields['title']}: no venue URL available yet")

        thread_url, thread_id = discord_utils.create_announcement_thread(fields, venue_url)
        print(f"[poll_approve] thread created: {thread_url}")

        description = discord_utils.build_shared_description(fields, venue_url)
        calendar_utils.create_event(fields, venue_url, thread_id, thread_url, description)
        print(f"[poll_approve] calendar event created")

        todo_content = discord_utils.build_todo_content(fields, venue_url)
        discord_utils.post_message(thread_id, todo_content)
        print(f"[poll_approve] TODO message posted to thread: {fields['title']}")

        set_discord_thread_url(fields["page_id"], thread_url)
        print(f"[poll_approve] Notion page updated with thread URL: {fields['title']}")


if __name__ == "__main__":
    main()
