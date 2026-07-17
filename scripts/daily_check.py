"""GitHub Actionsのscheduleトリガーで毎日実行するスクリプト。

「確定」ステータスの発表のうち、開催日の2日前になっても
資料リンクが未設定 & 資料共有フォルダにもファイルが見当たらないものに対し、
発表者へのリマインダーメールと、Discordスレッドへの通知を送る。
"""
from notion_utils import query_database, extract_fields, update_page_properties
from mail_utils import send_mail
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
        print(f"[daily_check] {fields['title']}: material NOT found, sending reminders")

        if fields.get("email"):
            send_mail(
                to_address=fields["email"],
                subject=f"【リマインダー】{fields['title']} の資料アップロードをお願いします",
                body=(
                    f"{fields.get('presenter') or 'ご担当者'} 様\n\n"
                    f"「{fields['title']}」の開催まで2日となりましたが、"
                    f"発表資料がまだ確認できていません。\n"
                    f"お手数ですが、資料共有用フォルダにアップロードの上、\n"
                    f"資料そのもののURLをDiscordのお知らせスレッドにご返信ください。\n\n"
                    f"動物倫理かいぎ 運営"
                ),
            )

        thread_prop = page["properties"].get("Discordスレッド", {}).get("url")
        if thread_prop:
            discord_utils.post_message_to_thread(
                thread_id_from_url(thread_prop),
                f"⏰ リマインダー: 発表まであと2日です。資料のアップロードをお願いします。"
                f"（資料共有用フォルダのURLへのアップロード後、こちらのスレッドに資料URLをご返信ください）",
            )


if __name__ == "__main__":
    main()
