"""Notionフォーム送信時(Webhook送信)から呼ばれるスクリプト。

処理内容:
  申込者にTODOリスト+リマインダー予告を記載した確認メールを送る。
"""
import json
import os

from notion_utils import get_page, extract_fields
from mail_utils import send_mail

MATERIAL_FOLDER_URL = "https://drive.google.com/drive/folders/1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU?usp=sharing"


def build_body(fields: dict) -> str:
    return f"""{fields.get('presenter') or 'ご担当者'} 様

「井戸端かいぎ」へのお申し込みありがとうございます。
以下の内容で受け付けました。運営による確認をお待ちください。

タイトル: {fields.get('title')}
種別: {fields.get('category')}
概要: {fields.get('summary')}

---
■ 今後の流れ(TODO)

□ 1. 運営による承認をお待ちください。
     承認され次第、「井戸端かいぎの予定表」に日程が確定として記載され、
     Discordの「#🐸｜井戸端かいぎ」チャンネルにお知らせスレッドが作成されます。

□ 2. 発表当日の2日前までに、発表資料を下記フォルダにアップロードしてください。
     資料共有用フォルダ: {MATERIAL_FOLDER_URL}
     (フォルダのURLではなく、アップロードした「資料そのもののURL」を、
      Discordのお知らせスレッドに返信する形でご共有ください)

□ 3. 2日前までに資料URLの共有が確認できない場合、リマインダーメールと
     Discordスレッドへの通知が自動で送信されます。

□ 4. 前日には、Discordのステージイベント機能によるリマインダーが
     興味あり登録者に届きます。

ご不明な点があれば、Discordの「#🐸｜井戸端かいぎ」チャンネルまでお気軽にどうぞ。

動物倫理かいぎ 運営
"""


def main():
    payload = json.loads(os.environ["GITHUB_EVENT_PAYLOAD"])
    page_id = payload["client_payload"]["page_id"]

    page = get_page(page_id)
    fields = extract_fields(page)

    if not fields.get("email"):
        print("[on_form_submit] no email address on this page, skipping")
        return

    send_mail(
        to_address=fields["email"],
        subject=f"【井戸端かいぎ】お申し込みを受け付けました:{fields.get('title')}",
        body=build_body(fields),
    )
    print(f"[on_form_submit] confirmation mail sent to {fields['email']}")


if __name__ == "__main__":
    main()
