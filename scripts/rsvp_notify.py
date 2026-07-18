"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき、poll.ymlから実行)。

「申込み必須」イベントの参加申込み(非公開の「井戸端かいぎ 参加申込み」
データベース)を監視し、まだ「案内送信済み」でない申込みを検知したら、
対応する予定表ページ・Googleカレンダー予定を辿って会場URLを取得し、
申込み時に入力されたメールアドレス宛てに会場URLと機密保持の注意文を
メールで送信する。

会場URLは、そのイベントがまだ承認(poll_approve.py)されておらずGoogleカレンダー
に登録されていない場合はまだ取得できない。その場合は「案内送信済み」を
立てずにスキップし、次回以降のポーリングで再試行する。

会場URLはDiscordの公開チャンネル・スレッドには一切書き込まれない
(discord_utils.build_announcement_content / build_todo_content 参照)。
"""
import os

import notion_utils
import calendar_utils
import discord_utils
import email_utils

RSVP_DATABASE_ID = os.environ["NOTION_RSVP_DATABASE_ID"]


def main():
    rsvps = notion_utils.query_database(
        {"property": "案内送信済み", "checkbox": {"equals": False}},
        database_id=RSVP_DATABASE_ID,
    )
    print(f"[rsvp_notify] {len(rsvps)} unnotified RSVP(s) found")

    for page in rsvps:
        rsvp = notion_utils.extract_rsvp_fields(page)

        if not rsvp.get("email") or not rsvp.get("event_page_id"):
            print(f"[rsvp_notify] skipping incomplete RSVP: {rsvp['page_id']}")
            continue

        event_page = notion_utils.get_page_or_none(rsvp["event_page_id"])
        if event_page is None:
            print(f"[rsvp_notify] linked event page not found, skipping: {rsvp['page_id']}")
            continue
        event_fields = notion_utils.extract_fields(event_page)

        calendar_event = calendar_utils.find_event_by_notion_page_id(rsvp["event_page_id"])
        if calendar_event is None:
            print(f"[rsvp_notify] event not approved yet, will retry: {event_fields.get('title')}")
            continue

        venue_url = calendar_event.get("extendedProperties", {}).get("private", {}).get("venue_url")
        if not venue_url:
            print(f"[rsvp_notify] venue URL not available yet, will retry: {event_fields.get('title')}")
            continue

        subject = f"【井戸端かいぎ】「{event_fields.get('title')}」参加のご案内"
        body = (
            f"{rsvp.get('name') or 'ご参加者'} 様\n\n"
            f"井戸端かいぎ「{event_fields.get('title')}」へのお申し込みありがとうございます。\n\n"
            f"日時: {discord_utils.format_datetime(event_fields.get('datetime'))}\n"
            f"会場URL: {venue_url}\n\n"
            f"本イベントは公表前の研究成果を含む場合があります。会場URLや発表内容を"
            f"第三者と共有したり、録音・録画・SNS等で公開したりすることはお控えください。\n\n"
            f"当日お会いできることを楽しみにしています。"
        )
        email_utils.send_email(rsvp["email"], subject, body)
        notion_utils.mark_rsvp_notified(rsvp["page_id"])
        print(f"[rsvp_notify] sent confirmation email for: {event_fields.get('title')}")


if __name__ == "__main__":
    main()
