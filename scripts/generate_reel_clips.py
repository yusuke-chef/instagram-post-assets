#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在庫監視クラウドルーティンから呼ばれる、リールB-roll映像の生成本体。
runway_toolkit/runway_batch.pyと同じロジック(Runway text-to-video)だが、
出力先はリポジトリ直下の一時フォルダに書く。

使い方: python generate_reel_clips.py <出力先ディレクトリ> <prompts_file>
<prompts_file> … 1行=1カット、英語プロンプト(4行推奨)
出力: <出力先ディレクトリ>/01.mp4, 02.mp4, ...
APIキーは環境変数 RUNWAYML_API_SECRET から読む。
"""
import os
import sys
import time
import urllib.request

from runwayml import RunwayML, TaskFailedError


def load_prompts(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def output_urls(task):
    for attr in ("output", "artifacts", "outputs"):
        val = getattr(task, attr, None)
        if val:
            if isinstance(val, list):
                out = []
                for item in val:
                    if isinstance(item, str):
                        out.append(item)
                    else:
                        u = getattr(item, "url", None) or (item.get("url") if isinstance(item, dict) else None)
                        if u:
                            out.append(u)
                if out:
                    return out
    return []


def main():
    if len(sys.argv) != 3:
        print("usage: generate_reel_clips.py <out_dir> <prompts_file>", file=sys.stderr)
        sys.exit(1)
    out_dir = sys.argv[1]
    prompts_file = sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)

    if not os.environ.get("RUNWAYML_API_SECRET"):
        print("ERROR: RUNWAYML_API_SECRET が未設定です", file=sys.stderr)
        sys.exit(1)

    prompts = load_prompts(prompts_file)
    client = RunwayML()

    for i, prompt in enumerate(prompts, start=1):
        dest = os.path.join(out_dir, f"{i:02d}.mp4")
        print(f"[{i:02d}] 生成中... {prompt[:60]}...")
        task = client.text_to_video.create(
            model="gen4.5",
            prompt_text=prompt,
            ratio="720:1280",
            duration=5,
        )
        try:
            task = task.wait_for_task_output()
        except TaskFailedError as e:
            print(f"[{i:02d}] 生成失敗: {e}")
            sys.exit(1)
        urls = output_urls(task)
        if not urls:
            print(f"[{i:02d}] 生成失敗: 出力URLが取得できません")
            sys.exit(1)
        urllib.request.urlretrieve(urls[0], dest)
        print(f"[{i:02d}] 保存: {dest}")
        time.sleep(1)

    print("完了")


if __name__ == "__main__":
    main()
