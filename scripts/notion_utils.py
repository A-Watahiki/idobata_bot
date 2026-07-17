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


def _plain_text(rich_text_list):
    return "".join(t.get("plain_text", "") for t in rich_text_list or [])


def extract_fields(page: dict) -> dict:
    """必要なプロパティだけを扱いやすい dict に変換する。

    NOTE: プロパティ名は実際のデータベースに合わせて調整してください。
    """
    props = page["properties"]

    def _prop(name, prop_type, default):
        prop = props.get(name)
        if prop is None:
            print(f"[notion_utils] WARNING: property not found on page, skipping: {name}")
            return default
        return prop.get(prop_type, default)

    def title(name):
        return _plain_text(_prop(name, "title", []))

    def rich_text(name):
        return _plain_text(_prop(name, "rich_text", []))

    def select(name):
        sel = _prop(name, "select", None)
        return sel["name"] if sel else None

    def multi_select(name):
        return [o["name"] for o in _prop(name, "multi_select", [])]

    def url(name):
        return _prop(name, "url", None)

    def date_start(name):
        d = _prop(name, "date", None)
        return d["start"] if d else None

    return {
        "page_id": page["id"],
        "title": title("タイトル"),
        "datetime": date_start("日時"),
        "category": select("種別"),
        "presenter": rich_text("担当者"),
        "summary": rich_text("概要"),
        "levels": multi_select("対象"),
        "material_url": url("資料リンク"),
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
