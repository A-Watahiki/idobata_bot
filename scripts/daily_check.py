"""poll.ymlから定期実行するスクリプト(外部スケジューラ経由で5分おき+GitHub cron)。

開催まで2日を切った承認済みイベントのうち、資料リンクが未設定で、資料共有
フォルダにもそれらしいファイルが見当たらないものについて、Discordのお知らせ
スレッドにリマインダーを1回だけ投稿する。

判定は「追いつき型」: 開催までの残り時間が2日以内で、まだ未送信なら送る
(実行が遅れても次の実行で送られる)。送信済みフラグはGoogleカレンダーの
extendedProperties(material_reminder_sent)に保存する。日時が変更された
場合は、sync_updates.pyがこのフラグをリセットする。

以前は独立したワークフロー(daily_check.yml)で1日1回動かしていたが、GitHubは
60日間コミットのないリポジトリのcronを自動停止するため、外部スケジューラから
起動されるpoll.ymlに統合した。
"""
from datetime import datetime, timezone

import calendar_utils
import discord_utils
import drive_utils
from notion_utils import extract_fields, get_page_or_none, update_page_properties

FLAG_KEY = "material_reminder_sent"
# (下限, 上限] 分。開催まで1時間を切ったものは今さら促しても意味がないので送らない。
WINDOW = (60, 2 * 24 * 60)


def _thread_id_from_url(url: str) -> str:
    # https://discord.com/channels/{guild}/{thread_id} の形式からIDだけ取り出す
    return url.rstrip("/").split("/")[-1]


def _minutes_until_start(event) -> float:
    start = datetime.fromisoformat(event["start"]["dateTime"])
    return (start - datetime.now(timezone.utc)).total_seconds() / 60


def main():
    low, high = WINDOW
    events = [
        e for e in calendar_utils.list_upcoming_instances(low, high)
        if "dateTime" in e.get("start", {}) and low < _minutes_until_start(e) <= high
    ]
    print(f"[daily_check] {len(events)} event(s) within 2 days")

    for event in events:
        props = event.get("extendedProperties", {}).get("private", {})
        if props.get(FLAG_KEY) == "true":
            continue
        thread_url = props.get("discord_thread_url")
        page_id = props.get("notion_page_id")
        if not thread_url or not page_id:
            continue

        page = get_page_or_none(page_id)
        if page is None:
            continue
        fields = extract_fields(page)
        if fields.get("status") != "確定":
            continue

        # すでに資料リンクがNotion側に設定済みならリマインダー不要
        if fields.get("material_url"):
            print(f"[daily_check] {fields['title']}: material already linked, skip")
            calendar_utils.mark_reminder_sent(event["id"], FLAG_KEY)
            continue

        # Driveフォルダ内にそれらしいファイルがあれば、Notionに自動で書き込んで終わり
        found_url = drive_utils.find_file_for_title(fields["title"])
        if found_url:
            print(f"[daily_check] {fields['title']}: found matching file in Drive, updating Notion")
            update_page_properties(fields["page_id"], {"資料リンク": {"url": found_url}})
            calendar_utils.mark_reminder_sent(event["id"], FLAG_KEY)
            continue

        print(f"[daily_check] {fields['title']}: material NOT found, sending reminder")
        notion_url = discord_utils.notion_page_url(fields["page_id"])
        discord_utils.post_message(
            _thread_id_from_url(thread_url),
            f"⏰ リマインダー: 発表は {discord_utils.format_datetime(event['start']['dateTime'])} です。"
            f"資料のアップロードは任意ですが、お済みでなければご検討ください。"
            f"アップロードした資料のURLは、下記の「本イベント用のNotionページ」の"
            f"「資料リンク」欄にご記入ください。\n"
            f"{notion_url}",
        )
        calendar_utils.mark_reminder_sent(event["id"], FLAG_KEY)


if __name__ == "__main__":
    main()
