"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき、poll.ymlから実行)。

承認済み(Discordスレッド作成済み)のイベントについて、Notion側で
「更新通知」チェックボックスがtrueになっているものを検知する。これは
Notion上に用意した「更新情報をスレッドに通知する」ボタンが裏でセットする値で、
主催者がページを編集しただけでは自動通知されず、このボタンを押した時点で
はじめて通知される。承認後、運営がNotionの編集権限を主催者に付与する運用の
ため、主催者自身が直接ページを修正できることを前提にしている。

  - 日時が変更された場合:
    Googleカレンダーの予定の時刻を更新し、スレッドと
    「#🐸｜井戸端かいぎ」チャンネル全体(スレッドへのリンクつき)に通知する。
    会場URL(Zoomリンクなど)は主催者自身が管理するものであり、この
    スクリプトからは変更しない。
  - 日時以外が変更された場合:
    Googleカレンダーの予定のタイトル・説明欄を更新し、スレッドにのみ通知する。

いずれの場合も、告知メッセージ(スレッドの最初の投稿)を編集し、種別・日時・
主催者・対象のうち変更があった項目を取り消し線+新しい値で表示する
(概要は自由記述の長文のため対象外)。差分の判定は、Googleカレンダーの
extendedProperties.privateに保存してあるスナップショット(snapshot_*)と、
現在のNotionの値を比較して行う。処理後はスナップショットを更新し、
「更新通知」チェックボックスをfalseに戻す(ボタンは何度でも押し直せる)。
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


def _build_diff(fields: dict, props: dict, datetime_changed: bool, old_start) -> dict:
    """スナップショットと現在の値を比べ、変更があった項目だけを
    {項目キー: 旧表示値} の形で返す。スナップショットが空(この機能が
    追加される前に作成されたイベント等)の項目は、比較のしようがないため
    差分表示の対象から除外する。
    """
    diff = {}

    old_category = props.get("snapshot_category") or ""
    if old_category and old_category != (fields.get("category") or ""):
        diff["category"] = old_category

    old_organizer = props.get("snapshot_organizer_username") or ""
    if old_organizer and old_organizer != (fields.get("organizer_username") or ""):
        diff["organizer_username"] = old_organizer

    old_levels_raw = props.get("snapshot_levels") or ""
    old_levels = [v for v in old_levels_raw.split(",") if v]
    if old_levels and sorted(old_levels) != sorted(fields.get("levels") or []):
        diff["levels"] = "・".join(old_levels)

    if datetime_changed and old_start:
        diff["datetime"] = discord_utils.format_datetime(old_start)

    return diff


def main():
    pages = notion_utils.query_database(
        {"property": "更新通知", "checkbox": {"equals": True}}
    )
    print(f"[sync_updates] {len(pages)} update-notification request(s) found")

    for page in pages:
        fields = notion_utils.extract_fields(page)
        print(f"[sync_updates] processing: {fields.get('title')}")

        event = calendar_utils.find_event_by_notion_page_id(fields["page_id"])
        if event is None:
            print(f"[sync_updates] {fields.get('title')}: no calendar event found, skipping")
            notion_utils.mark_notify_processed(fields["page_id"])
            continue

        if not fields.get("datetime"):
            notion_utils.mark_notify_processed(fields["page_id"])
            continue

        props = event.get("extendedProperties", {}).get("private", {})
        thread_url = props.get("discord_thread_url")
        old_start = event.get("start", {}).get("dateTime")
        datetime_changed = old_start is None or not _same_instant(old_start, fields["datetime"])

        diff = _build_diff(fields, props, datetime_changed, old_start)

        if thread_url and diff:
            discord_utils.edit_announcement_message(
                _thread_id_from_url(thread_url),
                discord_utils.build_announcement_diff_content(fields, props.get("venue_url"), diff),
            )
            print(f"[sync_updates] announcement message updated with diff for: {fields.get('title')}")

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

        calendar_utils.set_extended_properties(event["id"], {
            "notion_last_edited_time": fields.get("last_edited_time") or "",
            "snapshot_category": fields.get("category") or "",
            "snapshot_organizer_username": fields.get("organizer_username") or "",
            "snapshot_levels": ",".join(fields.get("levels") or []),
        })
        notion_utils.mark_notify_processed(fields["page_id"])


if __name__ == "__main__":
    main()
