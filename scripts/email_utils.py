"""Gmail SMTP経由でメールを送信するための共通関数。

「申込み必須」イベントで、事前申込み(氏名・メールアドレス)をした参加者へ
会場URL(Zoomリンクなど)を個別に案内するために使う。このメールアドレスは
Discordの公開チャンネル・スレッドには一切書き込まれない。

必要な環境変数:
  GMAIL_ADDRESS        送信元Gmailアドレス(例: doubutsurinrikaigi@gmail.com)
  GMAIL_APP_PASSWORD   同アカウントで発行した「アプリパスワード」
                        (通常のログインパスワードではない。Googleアカウントの
                        2段階認証を有効にした上で発行する)
"""
import os
import smtplib
from email.mime.text import MIMEText

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]


def send_email(to_address: str, subject: str, body: str):
    """プレーンテキストのメールを1通送信する。"""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)
