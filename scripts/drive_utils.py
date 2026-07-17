"""Google Drive APIで資料共有フォルダ内のファイルを確認するための関数。

必要な環境変数:
  GOOGLE_SERVICE_ACCOUNT_JSON  サービスアカウントの認証情報(JSON文字列)
  MATERIAL_FOLDER_ID           資料共有用フォルダのID
                                (例: 1NU_WFul8KPZP4pvkr-UU02sWtu4YavOU)

事前準備:
  Google Cloud Consoleでサービスアカウントを作成し、そのメールアドレス
  (xxx@xxx.iam.gserviceaccount.com)を、資料共有用フォルダに
  「閲覧者」として共有しておく必要があります。
"""
import json
import os
from datetime import datetime, timedelta

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def _get_service():
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds)


def find_file_for_title(title: str):
    """資料フォルダ内で、タイトルに部分一致するファイルを探す。
    見つかればそのファイルのwebViewLinkを返す。無ければNone。
    """
    service = _get_service()
    folder_id = os.environ["MATERIAL_FOLDER_ID"]

    # タイトルの一部だけでも部分一致すれば拾えるように、簡易的にキーワード検索する
    safe_title = title.replace("'", "").split()[0] if title else ""
    query = f"'{folder_id}' in parents and trashed = false"
    if safe_title:
        query += f" and name contains '{safe_title}'"

    results = service.files().list(
        q=query,
        fields="files(id, name, webViewLink)",
        pageSize=10,
    ).execute()

    files = results.get("files", [])
    return files[0]["webViewLink"] if files else None


def is_two_days_before(event_datetime_str: str) -> bool:
    event_dt = datetime.fromisoformat(event_datetime_str)
    return datetime.now().date() == (event_dt.date() - timedelta(days=2))
