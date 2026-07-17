"""GitHub Actionsのscheduleトリガーで毎日実行するスクリプト。

「確定」ステータスの発表のうち、開催日の2日前になっても
資料リンクが未設定 & 資料共有フォルダにもファイルが見当たらないものに対し、
Discordのお知らせスレッドにリマインダーを投稿する。
"""
from notion_utils import query_database, extract_fields, update_page_properties
import discord_utils
import drive_utils


def thread_id_from_url(url: str) -> str:
    # https://discord.com/channels/{guild}/{thread_id} の形式からIDだけ取り出す
    return url.rstrip("/").split("/")[-1]


def main():
    pages = query_database({"property": "ステータス", "select": {"equals": "確定"}})
    print(f"[daily_check] {len(pages)} confirmed sessions found")

    for page in pages:
        fields = extract_fields(page)
        if not fields.get("datetime"):
            continue
        if not drive_utils.is_two_days_before(fields["datetime"]):
            continue

        # すでに資料リンクがNotion側に設定済みならスキップ
        if fields.get("material_url"):
            print(f"[daily_check] {fields['title']}: material already linked, skip")
            continue

        # Driveフォルダ内にそれらしいファイルがないか一応確認
        found_url = drive_utils.find_file_for_title(fields["title"])
        if found_url:
            print(f"[daily_check] {fields['title']}: found matching file in Drive, updating Notion")
            update_page_properties(fields["page_id"], {"資料リンク": {"url": found_url}})
            continue

        # ここまで来たら未アップロードと判断し、リマインダーを送る
        print(f"[daily_check] {fields['title']}: material NOT found, sending reminder")

        thread_prop = page["properties"].get("Discordスレッド", {}).get("url")
        if thread_prop:
            discord_utils.post_message(
                thread_id_from_url(thread_prop),
                f"⏰ リマインダー: 発表まであと2日です。資料のアップロードをお願いします。"
                f"（資料共有用フォルダのURLへのアップロード後、こちらのスレッドに資料URLをご返信ください）",
            )


if __name__ == "__main__":
    main()
