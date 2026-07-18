"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき、poll.ymlから実行)。

承認済み(Discordスレッド作成済み)のイベントについて、Notion側で内容が
編集されていないかを検知する。承認後、運営がNotionの編集権限を主催者に
付与する運用のため、主催者自身が直接ページを修正できることを前提にしている。

  - 日時が変更された場合:
    Googleカレンダーの予定の時刻を更新し、スレッドと
    「#🐸｜井戸端かいぎ」チャンネル全体(スレッドへのリンクつき)に通知する。
    会場URL(Zoomリンクなど)は主催者自身が管理するものであり、この
    スクリプトからは変更しない。
  - 日時以外が変更された場合:
    Googleカレンダーの予定のタイトル・説明欄を更新し、スレッドにのみ通知する。

Notionページのlast_edited_timeをGoogleカレンダーのextendedPropertiesに
保存しておき、前回チェック時から変化していれば「編集された」とみなす
(何が変わったかまでは追わず、日時が変わったかどうかだけで通知先を分ける)。
"""
from datetime import datetime, timezone

import calendar_utils
import discord_utils
import notion_utils


def _same_instant(a_iso: str, b_iso: str) -> bool:
    a = datetime.fromisoformat(a_iso)
    b = datetime.fromisoformat(b_iso)
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return a.astimezone(timezone.utc) == b.astimezone(timezone.utc)


def _thread_id_from_url(thread_url: str) -> str:
    return thread_url.rstrip("/").split("/")[-1]


def main():
    events = calendar_utils.list_future_events_with_notion_link()
    print(f"[sync_updates] {len(events)} future calendar event(s) linked to Notion")

    for event in events:
        props = event.get("extendedProperties", {}).get("private", {})
        page_id = props["notion_page_id"]

        page = notion_utils.get_page_or_none(page_id)
        if page is None:
            continue  # sync_cancellations.py が担当

        fields = notion_utils.extract_fields(page)
        if fields.get("status") == "キャンセル":
            continue  # sync_cancellations.py が担当
        if not fields.get("datetime"):
            continue

        new_last_edited = fields.get("last_edited_time") or ""
        old_last_edited = props.get("notion_last_edited_time") or ""
        if new_last_edited == old_last_edited:
            continue

        thread_url = props.get("discord_thread_url")
        old_start = event.get("start", {}).get("dateTime")
        datetime_changed = old_start is None or not _same_instant(old_start, fields["datetime"])

        if datetime_changed:
            print(f"[sync_updates] datetime changed for: {fields.get('title')}")
            calendar_utils.update_event_time(event["id"], fields["datetime"])

            new_display = discord_utils.format_datetime(fields["datetime"])
            if thread_url:
                discord_utils.post_message(
                    _thread_id_from_url(thread_url),
                    f"🔄 日時が変更されました。新しい日時: {new_display}",
                )
                discord_utils.post_message(
                    discord_utils.ANNOUNCE_CHANNEL_ID,
                    f"🔄 「{fields.get('title')}」の日時が変更されました。"
                    f"新しい日時: {new_display}\nスレッド: {thread_url}",
                )
        else:
            print(f"[sync_updates] content changed (not datetime) for: {fields.get('title')}")
            venue_url = props.get("venue_url")
            description = discord_utils.build_shared_description(fields, venue_url)
            calendar_utils.update_event_content(event["id"], fields.get("title") or "井戸端かいぎ", description)

            if thread_url:
                discord_utils.post_message(
                    _thread_id_from_url(thread_url),
                    f"✏️ イベント内容が更新されました。最新情報をご確認ください。",
                )

        calendar_utils.set_extended_properties(event["id"], {"notion_last_edited_time": new_last_edited})


if __name__ == "__main__":
    main()
