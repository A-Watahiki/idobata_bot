"""poll.ymlから定期実行するスクリプト(外部スケジューラ経由で5分おき+GitHub cron)。

Googleカレンダーの予定(繰り返し予定は回ごとに展開される)を見て、
  - 開催前日(24時間前)のリマインダー: 「#🐸｜井戸端かいぎ」チャンネル全体に投稿
                                 (該当スレッドへのリンクつき。会場URLなし)
  - 開催直前(30分前)のリマインダー : 同チャンネル全体に投稿
                                 (「申込み必須」でなければ会場URLつき。
                                 「申込み必須」の場合は会場URLを出さず、代わりに
                                 事前申込み者一人ひとりへ会場URLを個別にメールする)
を行う。カレンダー予定の extendedProperties.private に保存してある
notion_page_id / discord_thread_id / discord_thread_url / venue_url / requires_rsvp
を使う(Notion側には会場URLを一切問い合わせない。「申込み必須」イベントの
事前申込み者一覧だけは、参加申込みデータベースに問い合わせる)。

判定は「追いつき型」: 開催までの残り時間が窓の範囲内で、まだ未送信なら送る。
実行が遅れて狙った時刻を過ぎても、次の実行で送られる(GitHubのcronは
数時間単位で間引かれることがあり、10分程度の狭い窓だと取りこぼすため)。

二重送信防止のため、送信済みの回にはextendedPropertiesにフラグを立てる
(チャンネル向け)。事前申込み者向けメールは申込み1件ごとに
「リマインダー送信済み」チェックボックスで二重送信を防ぐ。日時が変更された
場合は、sync_updates.pyがチャンネル向けのフラグをリセットする。
"""
from datetime import datetime, timezone

import calendar_utils
import discord_utils
import email_utils
import notion_utils

# (下限, 上限] 分。開催までの残り時間がこの範囲にあり、未送信なら送る。
# 前日リマインダーは、残り60分を切ったら直前リマインダーに任せて送らない。
DAY_BEFORE_WINDOW = (60, 24 * 60 + 10)
JUST_BEFORE_WINDOW = (0, 35)


def _minutes_until_start(event) -> float:
    start = datetime.fromisoformat(event["start"]["dateTime"])
    return (start - datetime.now(timezone.utc)).total_seconds() / 60


def _start_display(event) -> str:
    return discord_utils.format_datetime(event["start"]["dateTime"])


def _remind(minutes_window, flag_key, build_content, on_sent=None):
    low, high = minutes_window
    instances = calendar_utils.list_upcoming_instances(low, high)

    targets = []
    for event in instances:
        if "dateTime" not in event.get("start", {}):
            continue  # 終日予定は対象外
        # Calendar APIのtimeMinは終了時刻で絞り込むため、開始時刻で改めて判定する
        if low < _minutes_until_start(event) <= high:
            targets.append(event)
    print(f"[remind_events] {flag_key}: {len(targets)} instance(s) in window")

    for event in targets:
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


def _day_before_content(event, props):
    return (
        f"⏰ リマインダー: 「{event.get('summary')}」は {_start_display(event)} に開催です。\n"
        f"スレッド: {props.get('discord_thread_url')}"
    )


def _just_before_content(event, props):
    minutes = max(1, round(_minutes_until_start(event)))
    head = f"🔔 まもなく開催: 「{event.get('summary')}」は約{minutes}分後({_start_display(event)})に始まります。\n"
    if props.get("requires_rsvp") == "true":
        return (
            f"{head}"
            f"本イベントは事前申込み制のため、会場URLは申込みいただいた方へ個別にメールでご案内しています。\n"
            f"スレッド: {props.get('discord_thread_url')}"
        )
    return (
        f"{head}"
        f"会場: {props.get('venue_url') or '(未設定。スレッドをご確認のうえ運営までお問い合わせください)'}\n"
        f"スレッド: {props.get('discord_thread_url')}"
    )


def _send_rsvp_reminder_emails(event, props):
    """「申込み必須」イベントの事前申込み者へ、開催直前に会場URLを再送する。"""
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
            f"「{event.get('summary')}」はまもなく開催です({_start_display(event)}開始)。\n\n"
            f"会場URL: {venue_url}\n\n"
            f"本イベントは公表前の研究成果を含む場合があります。会場URLや発表内容を"
            f"第三者と共有したり、録音・録画・SNS等で公開したりすることはお控えください。"
        )
        email_utils.send_email(rsvp["email"], subject, body)
        notion_utils.mark_rsvp_reminded(rsvp["page_id"])
    print(f"[remind_events] RSVP reminder: {len(rsvps)} email(s) sent for {event.get('summary')}")


def main():
    _remind(DAY_BEFORE_WINDOW, "day_before_reminder_sent", _day_before_content)
    _remind(
        JUST_BEFORE_WINDOW,
        "just_before_reminder_sent",
        _just_before_content,
        on_sent=_send_rsvp_reminder_emails,
    )


if __name__ == "__main__":
    main()
