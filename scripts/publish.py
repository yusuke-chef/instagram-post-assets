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


def slot_for_now(hour):
    # 7:30/12:00/19:00 JSTの実行タイミングに合わせて判定。多少のズレは許容する。
    if 6 <= hour < 11:
        return "am"
    if 11 <= hour < 17:
        return "pm"
    if 17 <= hour < 23:
        return "reel"
    return None


def already_posted(product_type, today_str, slot, expected_caption):
    """product_typeとその日付が一致するだけでなく、FEEDの場合はam/pmの枠まで区別する。
    区別しないと「AM枠が済んでいればPM枠も済んだこと」に誤判定されるバグがあった（2026-08-21〜23で実際に発生、
    post19/post23が誤ってスキップされた）。

    さらに、日付・時間帯が一致するだけでなく、実際のキャプション本文が今日の予定コンテンツと一致するかまで
    確認する。これが無いと、別日の欠落分を当日朝に手動復旧した投稿が「今日の予定枠」と誤認識され、
    本来の予定枠がスキップされる事故が起きる（2026-08-24に実際に発生、post24が誤ってスキップされた）。"""
    r = requests.get(
        f"{BASE}/{IG_ID}/media",
        params={"fields": "id,timestamp,media_product_type,caption", "limit": 15, "access_token": TOKEN},
        timeout=30,
    ).json()
    for m in r.get("data", []):
        if m.get("media_product_type") != product_type:
            continue
        ts = datetime.datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        jst = ts.astimezone(JST)
        if jst.strftime("%Y-%m-%d") != today_str:
            continue
        if product_type == "FEED":
            post_slot = "am" if jst.hour < 10 else "pm"
            if post_slot != slot:
                continue
        if (m.get("caption") or "").strip() != expected_caption.strip():
            continue
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
    slot = slot_for_now(today.hour)
    print(f"TODAY={today_str} HOUR={today.hour} SLOT={slot}")

    if slot is None:
        print("対象時間外です。何もしません。")
        return

    day_schedule = load_today_schedule(today_str)
    if not day_schedule or slot not in day_schedule:
        print(f"本日({today_str})の{slot}枠はスケジュールに登録されていません。新しいバッチ作成が必要です。")
        return

    entry = day_schedule[slot]
    product_type = "REELS" if entry["type"] == "reel" else "FEED"
    expected_caption = read_caption(entry["caption"])

    if already_posted(product_type, today_str, slot, expected_caption):
        print(f"SUCCESS: {slot}枠は本日既に公開済みです。何もしません。")
        return

    if entry["type"] == "reel":
        publish_reel(entry)
    else:
        publish_feed(entry)


if __name__ == "__main__":
    main()
