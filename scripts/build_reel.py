#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在庫監視クラウドルーティンから呼ばれる、リール動画の組み立て本体(ffmpeg必須)。
ナレーション音声の長さに合わせて各クリップをsetptsで均等に伸縮し、連結、
音声を合成する。字幕は焼き込まない(既存reel13〜26と同じ、フラットな構成)。

使い方: python build_reel.py <clips_dir> <narration_path> <out_path>
"""
import glob
import os
import subprocess
import sys
import tempfile


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def main():
    if len(sys.argv) != 4:
        print("usage: build_reel.py <clips_dir> <narration_path> <out_path>", file=sys.stderr)
        sys.exit(1)
    clips_dir, narration_path, out_path = sys.argv[1:4]

    if not os.path.exists(narration_path):
        print(f"ERROR: narrationが見つかりません: {narration_path}", file=sys.stderr)
        sys.exit(1)

    clips = sorted(glob.glob(os.path.join(clips_dir, "*.mp4")))
    if not clips:
        print(f"ERROR: クリップが見つかりません: {clips_dir}", file=sys.stderr)
        sys.exit(1)

    dur = probe_duration(narration_path)
    per_clip = dur / len(clips)
    print(f"ナレーション長: {dur:.1f}s / クリップ数: {len(clips)} / 1本あたり目標: {per_clip:.1f}s")

    with tempfile.TemporaryDirectory() as tmp:
        seg_list = []
        for i, c in enumerate(clips):
            cd = probe_duration(c)
            factor = per_clip / cd
            seg = os.path.join(tmp, f"seg_{i:03d}.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-v", "error", "-i", c,
                    "-filter:v", f"setpts={factor}*PTS,scale=1080:1920:force_original_aspect_ratio=increase,"
                                 f"crop=1080:1920,fps=30,format=yuv420p",
                    "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", seg,
                ],
                check=True,
            )
            seg_list.append(seg)

        listfile = os.path.join(tmp, "list.txt")
        with open(listfile, "w") as f:
            for s in seg_list:
                f.write(f"file '{s}'\n")

        base = os.path.join(tmp, "base.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", listfile,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", base],
            check=True,
        )

        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", base, "-i", narration_path,
             "-c:v", "copy", "-c:a", "aac", "-shortest", out_path],
            check=True,
        )

    print(f"完了: {out_path}")


if __name__ == "__main__":
    main()
