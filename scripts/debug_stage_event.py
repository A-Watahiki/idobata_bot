"""create_stage_eventだけを単体で試すデバッグ用スクリプト。
Discordスレッドの作成やNotionの更新は一切行わない。
問題切り分けが済んだら削除してよい。
"""
import os
from datetime import datetime, timedelta, timezone

import requests

import discord_utils


def list_guild_channels():
    """サーバー内の全チャンネルとその種別を確認する(ステージチャンネルはtype=13)。"""
    res = requests.get(
        f"{discord_utils.BASE_URL}/guilds/{os.environ['DISCORD_GUILD_ID']}/channels",
        headers=discord_utils.HEADERS,
    )
    res.raise_for_status()
    channels = res.json()
    print("[debug_stage_event] --- guild channels ---")
    for c in channels:
        marker = " <== DISCORD_STAGE_CHANNEL_ID" if c["id"] == os.environ.get("DISCORD_STAGE_CHANNEL_ID") else ""
        print(f"  id={c['id']} type={c['type']} name={c.get('name')}{marker}")
    print("[debug_stage_event] --- end of list ---")


MANAGE_EVENTS = 1 << 33


def check_bot_permissions():
    """BotのユーザーIDと、実際にサーバー側で保持している権限ビットを確認する。"""
    me_res = requests.get(f"{discord_utils.BASE_URL}/users/@me", headers=discord_utils.HEADERS)
    me_res.raise_for_status()
    bot_user_id = me_res.json()["id"]
    print(f"[debug_stage_event] bot user id: {bot_user_id}")

    member_res = requests.get(
        f"{discord_utils.BASE_URL}/guilds/{os.environ['DISCORD_GUILD_ID']}/members/{bot_user_id}",
        headers=discord_utils.HEADERS,
    )
    member_res.raise_for_status()
    member = member_res.json()
    role_ids = member.get("roles", [])
    print(f"[debug_stage_event] bot's role ids: {role_ids}")

    roles_res = requests.get(
        f"{discord_utils.BASE_URL}/guilds/{os.environ['DISCORD_GUILD_ID']}/roles",
        headers=discord_utils.HEADERS,
    )
    roles_res.raise_for_status()
    roles = {r["id"]: r for r in roles_res.json()}

    total_perms = 0
    for rid in role_ids:
        role = roles.get(rid)
        if not role:
            continue
        perms = int(role["permissions"])
        total_perms |= perms
        has_manage_events = bool(perms & MANAGE_EVENTS)
        print(f"[debug_stage_event]   role={role['name']} permissions={perms} manage_events={has_manage_events}")

    everyone_role = roles.get(os.environ["DISCORD_GUILD_ID"])
    if everyone_role:
        everyone_perms = int(everyone_role["permissions"])
        total_perms |= everyone_perms
        print(f"[debug_stage_event]   role=@everyone permissions={everyone_perms} manage_events={bool(everyone_perms & MANAGE_EVENTS)}")

    print(f"[debug_stage_event] combined manage_events (guild-level, before channel overwrites): {bool(total_perms & MANAGE_EVENTS)}")


def main():
    check_bot_permissions()
    list_guild_channels()

    start = datetime.now(timezone.utc) + timedelta(days=1)
    fields = {
        "title": "デバッグ用テストイベント",
        "summary": "create_stage_event単体テスト",
        "datetime": start.isoformat(),
    }
    try:
        url = discord_utils.create_stage_event(fields)
        print(f"[debug_stage_event] SUCCESS: {url}")
    except Exception as e:  # noqa: BLE001
        print(f"[debug_stage_event] FAILED: {e}")


if __name__ == "__main__":
    main()
