"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(5分おき、poll.ymlから実行)。

承認済み(Discordスレッド作成済み)のイベントについて、Notion側の
「更新情報をスレッドに通知する」ボタンが押されたかどうかを検知する。
このボタンは裏で「更新通知回数」(数値)プロパティを+1する(Notionの
組み込み「値を増やす」アクション)。チェックボックスと違い、押すたびに
必ず値が変化するため、短時間に連続で押しても取りこぼされない。
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
現在のNotionの値を比較して行う。処理後は、スナップショットと合わせて
「更新通知回数」の処理済みの値(last_notify_count)も更新する。
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

        current_count = fields.get("notify_count") or 0
        old_count = int(props.get("last_notify_count") or 0)
        if current_count <= old_count:
            continue  # ボタンが押されていない(前回処理時点から回数が増えていない)

        print(f"[sync_updates] processing: {fields.get('title')} (更新通知回数 {old_count} -> {current_count})")

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
            "last_notify_count": str(int(current_count)),
            "notion_last_edited_time": fields.get("last_edited_time") or "",
            "snapshot_category": fields.get("category") or "",
            "snapshot_organizer_username": fields.get("organizer_username") or "",
            "snapshot_levels": ",".join(fields.get("levels") or []),
        })


if __name__ == "__main__":
    main()
