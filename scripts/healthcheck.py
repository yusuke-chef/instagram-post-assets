#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""再発防止のための日次ヘルスチェック。GitHub Actionsから毎日1回呼ばれる。
AIを介さない機械的なチェックのみを行う。

チェック内容:
1. 直近3日分について、schedule/*.jsonに登録されているam/pm/reel枠が
   実際にInstagramへ投稿されているか確認する（欠落があれば検知）。
2. 今日から数えて、schedule/*.jsonに「am・pmとも登録済み」の連続日数が
   3日未満なら、在庫切れ警告とする。

いずれかに該当したら、標準エラー出力に理由を明記してexit(1)する。
GitHub Actionsは失敗したジョブを赤色で表示するため、Actionsタブを見れば
一目で異常に気づける（成功時は何も表示に出ない=正常、という設計）。
"""
import datetime
import glob
import json
import os
import sys

import requests

TOKEN = os.environ["IG_TOKEN"]
IG_ID = os.environ["IG_ID"]
BASE = "https://graph.facebook.com/v26.0"
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JST = datetime.timezone(datetime.timedelta(hours=9))

MIN_STOCK_DAYS = 3
LOOKBACK_DAYS = 3


def now_jst():
    return datetime.datetime.now(JST)


def load_schedule():
    merged = {}
    for path in sorted(glob.glob(os.path.join(REPO_ROOT, "schedule", "*.json"))):
        with open(path, encoding="utf-8") as f:
            merged.update(json.load(f))
    return merged


def fetch_recent_media(limit=50):
    r = requests.get(
        f"{BASE}/{IG_ID}/media",
        params={"fields": "id,timestamp,media_product_type,caption", "limit": limit, "access_token": TOKEN},
        timeout=30,
    ).json()
    items = []
    for m in r.get("data", []):
        ts = datetime.datetime.strptime(m["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        jst = ts.astimezone(JST)
        items.append({
            "type": m.get("media_product_type"),
            "jst": jst,
            "caption": (m.get("caption") or "").strip(),
        })
    return items


def read_caption(rel_path):
    path = os.path.join(REPO_ROOT, rel_path)
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def slot_present(media, expected_type, expected_caption):
    """日付・時間帯の一致ではなく、実際のキャプション本文が一致する投稿が存在するかで判定する。
    手動復旧した投稿は、本来の予定日ではなく実際にpublishした日時がInstagram上のtimestampになるため、
    日付一致だけの判定では永久に「見つからない」と誤検知し続ける（2026-08-25、post20・post23で実際に発生）。"""
    for m in media:
        if m["type"] != expected_type:
            continue
        if m["caption"] == expected_caption:
            return True
    return False


def main():
    today = now_jst().date()
    schedule = load_schedule()
    media = fetch_recent_media()

    problems = []

    # 1. 直近LOOKBACK_DAYS日分の欠落チェック（今日は実行時刻によっては未到来の枠があるので除外し、昨日以前のみ対象）
    for delta in range(1, LOOKBACK_DAYS + 1):
        d = today - datetime.timedelta(days=delta)
        d_str = d.strftime("%Y-%m-%d")
        entry = schedule.get(d_str)
        if not entry:
            continue
        for slot in ("am", "pm", "reel"):
            if slot not in entry:
                continue
            expected_type = "REELS" if entry[slot]["type"] == "reel" else "FEED"
            expected_caption = read_caption(entry[slot]["caption"])
            if not slot_present(media, expected_type, expected_caption):
                problems.append(f"欠落: {d_str} の {slot} 枠がInstagramに見当たりません（スケジュールには登録済み）")

    # 2. 在庫残数チェック（今日を含め、am+pmが両方登録されている連続日数を数える）
    stock_days = 0
    d = today
    while True:
        d_str = d.strftime("%Y-%m-%d")
        entry = schedule.get(d_str)
        if not entry or "am" not in entry or "pm" not in entry:
            break
        stock_days += 1
        d += datetime.timedelta(days=1)

    if stock_days < MIN_STOCK_DAYS:
        problems.append(f"在庫警告: 本日から連続してam/pm枠が揃っているのは{stock_days}日分のみです（基準: {MIN_STOCK_DAYS}日以上）。新バッチ作成が必要です。")

    if problems:
        print("HEALTHCHECK FAILED:")
        for p in problems:
            print(f"- {p}")
        sys.exit(1)

    print(f"HEALTHCHECK OK: 欠落なし、在庫{stock_days}日分あります。")


if __name__ == "__main__":
    main()
