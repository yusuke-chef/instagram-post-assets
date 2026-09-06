#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在庫監視クラウドルーティンから呼ばれる、フィード画像の生成本体。
image_toolkit/generate.pyと同じロジック(gpt-image-1 → 4:5クロップ)だが、
出力先はリポジトリ直下(post{N}_slide{i}.jpg)に直接書く。

使い方: python generate_feed_images.py <post番号> <prompts_file>
<prompts_file> … 1行=1プロンプト、5行(hook+knowhow3+cta)
出力: <REPO_ROOT>/post{N}_slide1.jpg 〜 slide5.jpg
APIキーは環境変数 OPENAI_API_KEY から読む。
"""
import base64
import os
import subprocess
import sys
import tempfile

from openai import OpenAI


def load_prompts(path):
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip()]


def crop_to_4_5(raw_bytes, dest_path):
    """1024x1536(2:3)の出力をInstagram標準の4:5(1080x1350)に中央クロップする。"""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error", "-i", tmp_path,
                "-vf", "crop=iw:iw*5/4:0:(ih-iw*5/4)/2,scale=1080:1350",
                dest_path,
            ],
            check=True,
        )
    finally:
        os.remove(tmp_path)


def main():
    if len(sys.argv) != 3:
        print("usage: generate_feed_images.py <post番号> <prompts_file>", file=sys.stderr)
        sys.exit(1)
    post_num = sys.argv[1]
    prompts_file = sys.argv[2]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY が未設定です", file=sys.stderr)
        sys.exit(1)

    prompts = load_prompts(prompts_file)
    if len(prompts) != 5:
        print(f"ERROR: prompts_fileは5行である必要があります(実際: {len(prompts)}行)", file=sys.stderr)
        sys.exit(1)

    client = OpenAI()
    for i, prompt in enumerate(prompts, start=1):
        dest = os.path.join(repo_root, f"post{post_num}_slide{i}.jpg")
        print(f"[{i}/5] 生成中... {prompt[:60]}...")
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1536",
            quality="high",
            n=1,
        )
        raw = base64.b64decode(result.data[0].b64_json)
        crop_to_4_5(raw, dest)
        print(f"[{i}/5] 保存: {dest}")

    print("完了")


if __name__ == "__main__":
    main()
