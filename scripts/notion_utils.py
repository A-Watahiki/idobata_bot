"""Notion API とやり取りするための共通関数。

必要な環境変数:
  NOTION_TOKEN         Notion internal integration の Secret
  NOTION_DATABASE_ID   「井戸端かいぎの予定表」データベースの ID
"""
import os
import requests

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
# 2022-06-28: databases/{id}/query を database_id で直接叩ける最後の安定版。
# 2025-09-03以降はデータベースが複数の「データソース」に分割され、
# クエリにはdata_source_idが必要になるため、この方式のままでは使えない。
NOTION_VERSION = "2022-06-28"

BASE_URL = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}


def get_page(page_id: str) -> dict:
    """ページのプロパティを取得する。"""
    res = requests.get(f"{BASE_URL}/pages/{page_id}", headers=HEADERS)
    res.raise_for_status()
    return res.json()


def get_page_or_none(page_id: str):
    """ページを取得する。完全に削除されている(APIから404が返る)場合はNoneを返す。
    Notion上で「削除」してもゴミ箱に入るだけの場合はarchived=Trueとして通常どおり返る。
    """
    res = requests.get(f"{BASE_URL}/pages/{page_id}", headers=HEADERS)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return res.json()


def _plain_text(rich_text_list):
    return "".join(t.get("plain_text", "") for t in rich_text_list or [])


def _prop(props, name, prop_type, default):
    prop = props.get(name)
    if prop is None:
        print(f"[notion_utils] WARNING: property not found on page, skipping: {name}")
        return default
    return prop.get(prop_type, default)


def _title(props, name):
    return _plain_text(_prop(props, name, "title", []))


def _rich_text(props, name):
    return _plain_text(_prop(props, name, "rich_text", []))


def _select(props, name):
    sel = _prop(props, name, "select", None)
    return sel["name"] if sel else None


def _multi_select(props, name):
    return [o["name"] for o in _prop(props, name, "multi_select", [])]


def _url(props, name):
    return _prop(props, name, "url", None)


def _date_start(props, name):
    d = _prop(props, name, "date", None)
    return d["start"] if d else None


def extract_fields(page: dict) -> dict:
    """「井戸端かいぎの予定表」のページを扱いやすい dict に変換する。

    複数回シリーズの2回目以降は、Notion上で前回のページを「複製」して
    日時だけ書き換える運用を想定している(タイトル・種別・概要・対象・
    シリーズ名は複製時に自動的に引き継がれるため、コード側での補完は不要)。
    「シリーズ名」が前回と一致する場合のみ、Zoomリンクを再利用する。
    """
    props = page["properties"]

    return {
        "page_id": page["id"],
        "last_edited_time": page.get("last_edited_time"),
        "title": _title(props, "タイトル"),
        "datetime": _date_start(props, "日時"),
        "category": _select(props, "種別"),
        "organizer_username": _rich_text(props, "主催者ユーザ名"),
        "summary": _rich_text(props, "概要"),
        "levels": _multi_select(props, "対象"),
        "material_url": _url(props, "資料リンク"),
        "series_name": _rich_text(props, "シリーズ名"),
        "status": _select(props, "ステータス"),
    }


def update_page_properties(page_id: str, properties: dict) -> dict:
    """ページのプロパティを更新する(Discordスレッドの書き戻しなどに使用)。"""
    res = requests.patch(
        f"{BASE_URL}/pages/{page_id}",
        headers=HEADERS,
        json={"properties": properties},
    )
    res.raise_for_status()
    return res.json()


def set_discord_thread_url(page_id: str, thread_url: str):
    """「Discordスレッド」プロパティ(URL型)にスレッドURLを書き戻す。"""
    return update_page_properties(
        page_id,
        {"Discordスレッド": {"url": thread_url}},
    )


def query_database(filter_obj: dict) -> list:
    """データベースをフィルタ条件付きで検索する。"""
    res = requests.post(
        f"{BASE_URL}/databases/{os.environ['NOTION_DATABASE_ID']}/query",
        headers=HEADERS,
        json={"filter": filter_obj},
    )
    if not res.ok:
        print(f"[notion_utils] Notion API error {res.status_code}: {res.text}")
    res.raise_for_status()
    return res.json()["results"]
