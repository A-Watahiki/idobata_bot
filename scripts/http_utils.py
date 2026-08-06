"""外部API(Notion/Discord)呼び出し用の、リトライ機構付きrequestsセッションを提供する。

GitHub Actionsのランナーと外部APIサービスの間では、TLSハンドシェイク中の
接続リセットやタイムアウトなど、一時的なネットワークエラーがまれに発生する
(例: ConnectionResetError)。1回きりのこうした失敗でワークフロー全体を
失敗させないよう、指数バックオフで自動リトライする。

なお、404や400などのリクエスト内容自体が誤っているエラーはリトライ対象外
(status_forcelistに含めていない)。リトライしても直らないため。
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def build_session(total_retries: int = 3, backoff_factor: float = 1.0) -> requests.Session:
    """notion_utils.py・discord_utils.pyが共通で使うリトライ付きセッションを作る。

    - 接続確立前の切断(今回実際に発生したConnectionResetErrorなど)は、相手に
      リクエストが届く前の失敗のため、GET/POST/PATCHいずれでもリトライして安全。
    - レスポンスステータスによるリトライ(429/5xx)は、urllib3のデフォルト挙動で
      冪等なメソッド(GET/HEAD/PUT/DELETE/OPTIONS/TRACE)にのみ適用され、POSTには
      適用されない(ページ作成などの二重実行を避けるため)。
    - backoff_factor=1.0の場合、リトライ間隔は概ね 1秒 → 2秒 → 4秒。
    """
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
