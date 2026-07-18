"""GitHub Actionsのscheduleトリガーで定期実行するスクリプト(10分おき、poll.ymlから実行)。

「井戸端かいぎ 申込み」データベース(非公開。Notionフォームの送信先。
メールアドレスを含む)を監視し、まだ「転記済み」でない申込みを検知したら、
メールアドレスを除いた内容を「井戸端かいぎの予定表」(公開)に新しい行として
作成する(ステータス「承認待ち」)。

こうすることで、承認後に予定表側の編集権限を主催者に付与しても、
他の申込者のメールアドレスが見えることはない(予定表にはそもそも
メールアドレスというプロパティ自体が存在しないため)。

転記のたびに、Discordの運営用チャンネル(DISCORD_ADMIN_CHANNEL_ID)へ、
新規申込みがあった旨と、承認手順(申込みページでメールアドレスを確認し、
予定表ページへゲスト招待のうえ「ステータス」を「確定」に変更する)を通知する。
"""
import os

from notion_utils import (
    query_database,
    extract_submission_fields,
    create_public_event_page,
    mark_submission_processed,
)
import discord_utils

SUBMISSIONS_DATABASE_ID = os.environ["NOTION_SUBMISSIONS_DATABASE_ID"]
ADMIN_CHANNEL_ID = os.environ["DISCORD_ADMIN_CHANNEL_ID"]


def main():
    pages = query_database(
        {"property": "転記済み", "checkbox": {"equals": False}},
        database_id=SUBMISSIONS_DATABASE_ID,
    )
    print(f"[sync_submissions] {len(pages)} new submission(s) found")

    for page in pages:
        fields = extract_submission_fields(page)
        print(f"[sync_submissions] processing submission: {fields.get('title')}")

        public_page = create_public_event_page(fields)
        mark_submission_processed(fields["page_id"])
        print(f"[sync_submissions] created public event page for: {fields.get('title')}")

        notification = discord_utils.build_new_submission_notification(
            fields, fields["page_id"], public_page["id"]
        )
        discord_utils.post_message(ADMIN_CHANNEL_ID, notification)
        print(f"[sync_submissions] notified admin channel for: {fields.get('title')}")


if __name__ == "__main__":
    main()
