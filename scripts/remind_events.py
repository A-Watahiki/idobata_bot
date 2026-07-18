"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(5分おき、poll.ymlから実行)。

Googleカレンダーの予定(繰り返し予定は回ごとに展開される)を見て、
  - 開催24時間前              : 「#🐸｜井戸端かいぎ」チャンネル全体にリマインダーを投稿
                                 (該当スレッドへのリンクつき。会場URLなし)
  - 開催30分前                : 同チャンネル全体にリマインダーを投稿
                                 (「申込み必須」でなければ会場URLつき。
                                 「申込み必須」の場合は会場URLを出さず、代わりに
                                 事前申込み者一人ひとりへ会場URLを個別にメールする)
を行う。カレンダー予定の extendedProperties.private に保存してある
notion_page_id / discord_thread_id / discord_thread_url / venue_url / requires_rsvp
を使う(Notion側には会場URLを一切問い合わせない。「申込み必須」イベントの
事前申込み者一覧だけは、参加申込みデータベースに問い合わせる)。

二重送信防止のため、送信済みの回にはextendedPropertiesにフラグを立てる
(チャンネル向け)。事前申込み者向けメールは申込み1件ごとに
「リマインダー送信済み」チェックボックスで二重送信を防ぐ。
"""
import calendar_utils
import discord_utils
import email_utils
import notion_utils

DAY_BEFORE_WINDOW = (24 * 60, 24 * 60 + 10)  # 分
JUST_BEFORE_WINDOW = (25, 35)  # 分(30分前を少し余裕を持って狙う)


def _remind(minutes_window, flag_key, build_content, on_sent=None):
    instances = calendar_utils.list_upcoming_instances(*minutes_window)
    print(f"[remind_events] {flag_key}: {len(instances)} instance(s) in window")

    for event in instances:
        props = event.get("extendedProperties", {}).get("private", {})
        if props.get(flag_key) == "true":
            continue

        thread_url = props.get("discord_thread_url")
        if not thread_url:
            print(f"[remind_events] {flag_key}: no discord_thread_url on event {event.get('id')}, skipping")
            continue

        content = build_content(event, props)
        discord_utils.post_message(discord_utils.ANNOUNCE_CHANNEL_ID, content)
        calendar_utils.mark_reminder_sent(event["id"], flag_key)
        print(f"[remind_events] {flag_key}: reminder sent for {event.get('summary')}")

        if on_sent:
            on_sent(event, props)


def _just_before_content(event, props):
    if props.get("requires_rsvp") == "true":
        return (
            f"🔔 まもなく開催: 「{event.get('summary')}」は30分後に始まります。\n"
            f"本イベントは事前申込み制のため、会場URLは申込みいただいた方へ個別にメールでご案内しています。\n"
            f"スレッド: {props.get('discord_thread_url')}"
        )
    return (
        f"🔔 まもなく開催: 「{event.get('summary')}」は30分後に始まります。\n"
        f"会場: {props.get('venue_url') or '(未設定。スレッドをご確認のうえ運営までお問い合わせください)'}\n"
        f"スレッド: {props.get('discord_thread_url')}"
    )


def _send_rsvp_reminder_emails(event, props):
    """「申込み必須」イベントの事前申込み者へ、開催30分前に会場URLを再送する。"""
    if props.get("requires_rsvp") != "true":
        return
    notion_page_id = props.get("notion_page_id")
    venue_url = props.get("venue_url")
    if not notion_page_id or not venue_url:
        print(f"[remind_events] RSVP reminder: no notion_page_id/venue_url for {event.get('summary')}, skipping")
        return

    rsvps = notion_utils.get_rsvps_for_event(notion_page_id, only_unreminded=True)
    for rsvp in rsvps:
        if not rsvp.get("email"):
            continue
        subject = f"【井戸端かいぎ】まもなく開催: 「{event.get('summary')}」"
        body = (
            f"{rsvp.get('name') or 'ご参加者'} 様\n\n"
            f"「{event.get('summary')}」は30分後に開催です。\n\n"
            f"会場URL: {venue_url}\n\n"
            f"本イベントは公表前の研究成果を含む場合があります。会場URLや発表内容を"
            f"第三者と共有したり、録音・録画・SNS等で公開したりすることはお控えください。"
        )
        email_utils.send_email(rsvp["email"], subject, body)
        notion_utils.mark_rsvp_reminded(rsvp["page_id"])
    print(f"[remind_events] RSVP reminder: {len(rsvps)} email(s) sent for {event.get('summary')}")


def main():
    _remind(
        DAY_BEFORE_WINDOW,
        "day_before_reminder_sent",
        lambda event, props: (
            f"⏰ リマインダー: 「{event.get('summary')}」の開催まで残り1日です。\n"
            f"スレッド: {props.get('discord_thread_url')}"
        ),
    )
    _remind(
        JUST_BEFORE_WINDOW,
        "just_before_reminder_sent",
        _just_before_content,
        on_sent=_send_rsvp_reminder_emails,
    )


if __name__ == "__main__":
    main()
