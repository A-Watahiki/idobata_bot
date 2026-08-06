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
import time
from email.mime.text import MIMEText

GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]


def send_email(to_address: str, subject: str, body: str, max_attempts: int = 3):
    """プレーンテキストのメールを1通送信する。
    smtplibには組み込みのリトライ機構がないため、接続確立・ログイン段階での
    一時的なエラー(SMTP自体の障害・ネットワーク瞬断など)に対して、
    指数バックオフで数回まで自前で再試行する。
    """
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = to_address

    for attempt in range(1, max_attempts + 1):
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
                server.send_message(msg)
            return
        except (smtplib.SMTPException, OSError):
            if attempt == max_attempts:
                raise
            wait_seconds = 2 ** (attempt - 1)  # 1s, 2s, 4s...
            print(
                f"[email_utils] send_email to {to_address} failed "
                f"(attempt {attempt}/{max_attempts}), retrying in {wait_seconds}s"
            )
            time.sleep(wait_seconds)
