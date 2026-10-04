#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Instagram定期投稿の実行本体。GitHub Actionsから1日3回（7:30/12:00/19:00 JST頃）呼ばれる。
AIを介さない、純粋なスクリプト実行。schedule/*.json を見て、今日・今の枠にコンテンツがあり、
かつまだ未投稿なら1件だけpublishする。何度実行しても安全（冪等）。
"""
import datetime
import json
import os
import sys
import time
import glob

import requests

TOKEN = os.environ["IG_TOKEN"]
IG_ID = os.environ["IG_ID"]
BASE = "https://graph.facebook.com/v26.0"
REPO_RAW = "https://raw.githubusercontent.com/yusuke-chef/instagram-post-assets/main"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

JST = datetime.timezone(datetime.timedelta(hours=9))


def now_jst():
    return datetime.datetime.now(JST)


def load_today_schedule(today_str):
    month_file = os.path.join(REPO_ROOT, "schedule", f"{today_str[:7]}.json")
    if not os.path.exists(month_file):
        return None
    with open(month_file, encoding="utf-8") as f:
        data = json.load(f)
    return data.get(today_str)


# 各枠の予定時刻(JST)。GitHub Actionsの定期実行は数時間遅れることがあるため(2026-08-27以降の実測で
# 朝枠が約2時間、昼枠が約5時間遅れ)、実行時刻で枠を決めず「予定時刻を過ぎている未投稿の枠」をすべて投稿する。
SLOT_TIMES = {"am": (7, 45), "pm": (12, 45), "reel": (19, 15)}


def due_slots(now):
    return [s for s, (h, m) in SLOT_TIMES.items() if (now.hour, now.minute) >= (h, m)]


def already_posted(product_type, expected_caption):
    """直近のメディアの中に、種類(FEED/REELS)と本文が完全一致する投稿があれば投稿済みとみなす。
    2026-10-04の改修: 従来は「投稿時刻が10時前ならam、以降ならpm」で枠を判定していたが、
    GitHub Actionsの定期実行が数時間遅れるため、遅れて投稿したamが「pm」と誤判定される余地があった。
    本文は投稿ごとに固有なので、本文一致だけで冪等性は十分に保てる。"""
    r = requests.get(
        f"{BASE}/{IG_ID}/media",
        params={"fields": "id,timestamp,media_product_type,caption", "limit": 40, "access_token": TOKEN},
        timeout=30,
    ).json()
    if "data" not in r:
        print(f"FAILED: 直近投稿の取得に失敗しました(二重投稿を避けるため中止します)。Response: {r}")
        sys.exit(1)
    for m in r["data"]:
        if m.get("media_product_type") != product_type:
            continue
        if (m.get("caption") or "").strip() == expected_caption.strip():
            return True
    return False


def read_caption(rel_path):
    path = os.path.join(REPO_ROOT, rel_path)
    with open(path, encoding="utf-8") as f:
        return f.read()


def publish_feed(entry):
    caption = read_caption(entry["caption"])
    ids = []
    for slide in entry["slides"]:
        url = f"{REPO_RAW}/{slide}"
        r = requests.post(
            f"{BASE}/{IG_ID}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": TOKEN},
            timeout=60,
        ).json()
        if "id" not in r:
            print(f"FAILED: slide upload for {slide} did not return an id. Response: {r}")
            sys.exit(1)
        ids.append(r["id"])

    r = requests.post(
        f"{BASE}/{IG_ID}/media",
        data={"media_type": "CAROUSEL", "children": ",".join(ids), "caption": caption, "access_token": TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        print(f"FAILED: container creation did not return an id. Response: {r}")
        sys.exit(1)
    cid = r["id"]

    # カルーセルのコンテナがすぐには公開可能状態にならないことがある
    # （2026-08-22 post20で「Media ID is not available」エラーが実際に発生した）ため、
    # media_publishを最大3回、間隔を空けてリトライする。
    r = None
    for attempt in range(3):
        r = requests.post(
            f"{BASE}/{IG_ID}/media_publish",
            data={"creation_id": cid, "access_token": TOKEN},
            timeout=60,
        ).json()
        if "id" in r:
            break
        print(f"publish attempt {attempt + 1} failed: {r}")
        time.sleep(10)
    if not r or "id" not in r:
        print(f"FAILED: publish did not return an id after retries. Response: {r}")
        sys.exit(1)
    print(f"SUCCESS: feed published, media_id={r['id']}")


def publish_reel(entry):
    caption = read_caption(entry["caption"])
    video_url = f"{REPO_RAW}/{entry['video']}"

    r = requests.post(
        f"{BASE}/{IG_ID}/media",
        data={"media_type": "REELS", "video_url": video_url, "caption": caption, "access_token": TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        print(f"FAILED: container creation did not return an id. Response: {r}")
        sys.exit(1)
    cid = r["id"]

    for i in range(20):
        status = requests.get(
            f"{BASE}/{cid}", params={"fields": "status_code", "access_token": TOKEN}, timeout=30
        ).json().get("status_code", "?")
        print(f"poll {i + 1}: {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            print("FAILED: video processing error")
            sys.exit(1)
        time.sleep(8)
    else:
        print("FAILED: video processing timed out")
        sys.exit(1)

    r = requests.post(
        f"{BASE}/{IG_ID}/media_publish",
        data={"creation_id": cid, "access_token": TOKEN},
        timeout=60,
    ).json()
    if "id" not in r:
        print(f"FAILED: publish did not return an id. Response: {r}")
        sys.exit(1)
    print(f"SUCCESS: reel published, media_id={r['id']}")


def main():
    today = now_jst()
    today_str = today.strftime("%Y-%m-%d")
    print(f"TODAY={today_str} NOW={today.strftime('%H:%M')} JST")

    day_schedule = load_today_schedule(today_str)
    due = due_slots(today)
    if not day_schedule:
        if due:
            print(f"ERROR: 本日({today_str})の予約が1件もありません。在庫切れです。新しいバッチ作成が必要です。")
            sys.exit(1)
        return

    failed = []
    for slot in ("am", "pm", "reel"):
        if slot not in due:
            continue
        if slot not in day_schedule:
            if slot != "reel":
                print(f"ERROR: 本日({today_str})の{slot}枠が予約されていません。")
                failed.append(slot)
            continue
        entry = day_schedule[slot]
        product_type = "REELS" if entry["type"] == "reel" else "FEED"
        expected_caption = read_caption(entry["caption"])

        if already_posted(product_type, expected_caption):
            print(f"OK: {slot}枠は投稿済みです。")
            continue
        print(f"{slot}枠は予定時刻を過ぎていて未投稿のため、投稿します。")
        try:
            if entry["type"] == "reel":
                publish_reel(entry)
            else:
                publish_feed(entry)
        except SystemExit:
            failed.append(slot)

    if failed:
        print(f"FAILED SLOTS: {failed}")
        sys.exit(1)


if __name__ == "__main__":
    main()
