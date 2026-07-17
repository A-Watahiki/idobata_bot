"""メール送信用の共通関数。Gmailのアプリパスワードを使ったSMTP送信。

必要な環境変数:
  GMAIL_ADDRESS       送信元Gmailアドレス
  GMAIL_APP_PASSWORD  Googleアカウントで発行した「アプリパスワード」
                       (通常のログインパスワードではない点に注意)
"""
import os
import smtplib
from email.mime.text import MIMEText

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]


def send_mail(to_address: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, [to_address], msg.as_string())
