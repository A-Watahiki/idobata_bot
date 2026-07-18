"""Notion API とやり取りするための共通関数。

必要な環境変数:
  NOTION_TOKEN                     Notion internal integration の Secret
  NOTION_DATABASE_ID               「井戸端かいぎの予定表」(公開)データベースのID
  NOTION_SUBMISSIONS_DATABASE_ID   「井戸端かいぎ 申込み」(非公開)データベースのID
  NOTION_RSVP_DATABASE_ID          「井戸端かいぎ 参加申込み」(非公開)データベースのID
                                    (「申込み必須」イベントの事前参加申込み用。
                                    get_rsvps_for_event等利用時のみ必要)

会場URL(Zoomリンクなど)は主催者が申込み時に用意し、非公開の「井戸端かいぎ
申込み」データベースの「会場URL」にのみ入力してもらう。公開の「井戸端かいぎの
予定表」にはこの値を一切コピーせず、承認時にpoll_approve.pyが申込みページから
直接読み出してGoogleカレンダーに書き込む。

公表前の研究成果を扱うなど、参加者を限定したいイベントは「申込み必須」を
チェックすると、会場URLが公開のDiscordチャンネル/スレッドに一切出なくなり、
代わりに「井戸端かいぎ 参加申込み」データベース(氏名・メールアドレス必須)
経由で、事前申込みした人にだけメールで会場URLが案内される
(rsvp_notify.py・remind_events.py参照)。

承認済みイベントのページ編集は、Notion側の「更新情報をスレッドに通知する」
ボタン(裏で「更新通知回数」数値プロパティを+1する)を押した時だけDiscordに
通知される。編集しただけで自動通知はされない。数値カウンタ方式のため、
短時間に連続で押しても取りこぼされない(sync_updates.py参照)。
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


def create_page(database_id: str, properties: dict) -> dict:
    """指定したデータベースに新しいページを作成する。"""
    res = requests.post(
        f"{BASE_URL}/pages",
        headers=HEADERS,
        json={"parent": {"database_id": database_id}, "properties": properties},
    )
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


def _checkbox(props, name):
    return bool(_prop(props, name, "checkbox", False))


def _number(props, name):
    return _prop(props, name, "number", 0) or 0


def _relation_ids(props, name):
    return [r["id"] for r in _prop(props, name, "relation", [])]


def extract_fields(page: dict) -> dict:
    """「井戸端かいぎの予定表」(公開)のページを扱いやすい dict に変換する。

    複数回シリーズの2回目以降は、Notion上で前回のページを「複製」して
    日時だけ書き換える運用を想定している(タイトル・種別・概要・対象は
    複製時に自動的に引き継がれるため、コード側での補完は不要)。会場URLは
    「申込みページID」経由で常に最初の申込みページから取得するため、
    複製後も自動的に同じ会場URLが再利用される。

    このデータベースにはメールアドレスなど個人情報は一切持たせない設計。
    会場URL(Zoomリンクなど)もここには持たせず、Googleカレンダーの
    extendedProperties.privateにのみ保存する。
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
        "status": _select(props, "ステータス"),
        "submission_page_id": _rich_text(props, "申込みページID"),
        "requires_rsvp": _checkbox(props, "申込み必須"),
        "notify_count": _number(props, "更新通知回数"),
    }


def extract_submission_fields(page: dict) -> dict:
    """「井戸端かいぎ 申込み」(非公開)のページを扱いやすい dict に変換する。
    メールアドレスは、このデータベース上でのみ扱い、公開DBには一切コピーしない。
    「会場URL」(Zoomリンクなど、主催者が用意した会場)も公開DBにはコピーせず、
    承認時にpoll_approve.pyがこのページから直接読み出してGoogleカレンダーに
    書き込む(get_submission_venue_url参照)。
    """
    props = page["properties"]

    return {
        "page_id": page["id"],
        "title": _title(props, "タイトル"),
        "datetime": _date_start(props, "日時"),
        "category": _select(props, "種別"),
        "organizer_username": _rich_text(props, "主催者ユーザ名"),
        "email": _rich_text(props, "メールアドレス"),
        "venue_url": _url(props, "会場URL"),
        "summary": _rich_text(props, "概要"),
        "levels": _multi_select(props, "対象"),
        "requires_rsvp": _checkbox(props, "申込み必須"),
    }


def get_submission_venue_url(submission_page_id: str):
    """「井戸端かいぎ 申込み」ページから「会場URL」だけを読み出す。
    poll_approve.pyが承認時に(公開DBを経由せず)直接呼び出す。
    """
    page = get_page_or_none(submission_page_id)
    if page is None:
        return None
    return _url(page["properties"], "会場URL")


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


def mark_submission_processed(page_id: str):
    """「井戸端かいぎ 申込み」側のページに「転記済み」フラグを立てる。"""
    return update_page_properties(page_id, {"転記済み": {"checkbox": True}})


def create_public_event_page(fields: dict) -> dict:
    """申込み内容(メールアドレス・会場URLを除く)から、公開の「井戸端かいぎの
    予定表」に新しい行を作成する。ステータスは「承認待ち」で作成し、運営の
    確認・承認を待つ。

    「申込みページID」には申込み元ページのIDだけを書き戻す(個人情報を含まない
    単なる内部参照で、承認時にpoll_approve.pyが会場URLを取りに行くために使う)。
    """
    properties = {
        "タイトル": {"title": [{"text": {"content": fields.get("title") or ""}}]},
        "ステータス": {"select": {"name": "承認待ち"}},
        "申込みページID": {"rich_text": [{"text": {"content": fields["page_id"]}}]},
        "申込み必須": {"checkbox": bool(fields.get("requires_rsvp"))},
    }
    if fields.get("datetime"):
        properties["日時"] = {"date": {"start": fields["datetime"]}}
    if fields.get("category"):
        properties["種別"] = {"select": {"name": fields["category"]}}
    if fields.get("organizer_username"):
        properties["主催者ユーザ名"] = {"rich_text": [{"text": {"content": fields["organizer_username"]}}]}
    if fields.get("summary"):
        properties["概要"] = {"rich_text": [{"text": {"content": fields["summary"]}}]}
    if fields.get("levels"):
        properties["対象"] = {"multi_select": [{"name": v} for v in fields["levels"]]}

    return create_page(os.environ["NOTION_DATABASE_ID"], properties)


def extract_rsvp_fields(page: dict) -> dict:
    """「井戸端かいぎ 参加申込み」(非公開)のページを扱いやすい dict に変換する。
    「参加イベント」は公開の予定表ページへのリレーション(1件のみ選択を想定)。
    """
    props = page["properties"]
    event_ids = _relation_ids(props, "参加イベント")

    return {
        "page_id": page["id"],
        "name": _title(props, "氏名"),
        "email": _rich_text(props, "メールアドレス"),
        "event_page_id": event_ids[0] if event_ids else None,
    }


def get_rsvps_for_event(event_page_id: str, only_unreminded: bool = False) -> list:
    """指定した予定表ページに紐づく参加申込みを取得する
    (remind_events.pyが開催30分前のリマインダーメール送信に使う)。
    """
    filter_obj = {"property": "参加イベント", "relation": {"contains": event_page_id}}
    if only_unreminded:
        filter_obj = {
            "and": [
                filter_obj,
                {"property": "リマインダー送信済み", "checkbox": {"equals": False}},
            ]
        }
    pages = query_database(filter_obj, database_id=os.environ["NOTION_RSVP_DATABASE_ID"])
    return [extract_rsvp_fields(p) for p in pages]


def mark_rsvp_notified(page_id: str):
    """会場URLの案内メールを送信済みであることを記録する。"""
    return update_page_properties(page_id, {"案内送信済み": {"checkbox": True}})


def mark_rsvp_reminded(page_id: str):
    """開催30分前のリマインダーメールを送信済みであることを記録する。"""
    return update_page_properties(page_id, {"リマインダー送信済み": {"checkbox": True}})


def query_database(filter_obj: dict, database_id: str = None) -> list:
    """データベースをフィルタ条件付きで検索する。database_idを省略すると
    「井戸端かいぎの予定表」(NOTION_DATABASE_ID)を対象にする。
    """
    database_id = database_id or os.environ["NOTION_DATABASE_ID"]
    res = requests.post(
        f"{BASE_URL}/databases/{database_id}/query",
        headers=HEADERS,
        json={"filter": filter_obj},
    )
    if not res.ok:
        print(f"[notion_utils] Notion API error {res.status_code}: {res.text}")
    res.raise_for_status()
    return res.json()["results"]
