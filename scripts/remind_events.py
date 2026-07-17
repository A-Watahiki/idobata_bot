"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき、poll.ymlから実行)。

Googleカレンダーの予定(繰り返し予定は回ごとに展開される)を見て、
  - 開催24時間前              : Discordスレッドにリマインダーを投稿(Zoomリンクなし)
  - 開催30分前                : Discordスレッドにリマインダーを投稿(Zoomリンクつき)
を行う。カレンダー予定の extendedProperties.private に保存してある
notion_page_id / discord_thread_id / zoom_join_url を使う(Notion側には
Zoomリンクを一切問い合わせない)。

二重送信防止のため、送信済みの回にはextendedPropertiesにフラグを立てる。
"""
import calendar_utils
import discord_utils

DAY_BEFORE_WINDOW = (24 * 60, 24 * 60 + 10)  # 分
JUST_BEFORE_WINDOW = (25, 35)  # 分(30分前を少し余裕を持って狙う)


def _remind(minutes_window, flag_key, build_content):
    instances = calendar_utils.list_upcoming_instances(*minutes_window)
    print(f"[remind_events] {flag_key}: {len(instances)} instance(s) in window")

    for event in instances:
        props = event.get("extendedProperties", {}).get("private", {})
        if props.get(flag_key) == "true":
            continue

        thread_id = props.get("discord_thread_id")
        if not thread_id:
            print(f"[remind_events] {flag_key}: no discord_thread_id on event {event.get('id')}, skipping")
            continue

        content = build_content(event, props)
        discord_utils.post_message_to_thread(thread_id, content)
        calendar_utils.mark_reminder_sent(event["id"], flag_key)
        print(f"[remind_events] {flag_key}: reminder sent for {event.get('summary')}")


def main():
    _remind(
        DAY_BEFORE_WINDOW,
        "day_before_reminder_sent",
        lambda event, props: (
            f"⏰ リマインダー: 「{event.get('summary')}」の開催まで残り1日です。"
            f"当日の開催30分前に、このスレッドへZoomリンクを投稿します。"
        ),
    )
    _remind(
        JUST_BEFORE_WINDOW,
        "just_before_reminder_sent",
        lambda event, props: (
            f"🔔 まもなく開催: 「{event.get('summary')}」は30分後に始まります。\n"
            f"Zoom: {props.get('zoom_join_url')}"
        ),
    )


if __name__ == "__main__":
    main()
