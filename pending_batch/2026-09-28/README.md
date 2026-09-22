# pending_batch/2026-09-28

この下書きは自動生成です。画像・動画生成はローカルマシンのAPIキーが必要なため未実施です。
人間が確認後、image_toolkit/runway_toolkit（またはscripts/generate_feed_images.py等）で生成し、本番のschedule/*.jsonに反映すること。

## 検知内容（実行日: 2026-09-22 JST）

- feed在庫: 2026-09-22〜2026-09-27の6日分（am/pm両方登録済み） → 7日未満のため不足
- reel在庫: 2026-09-22〜2026-09-27の6日分（reel登録済み） → 7日未満のため不足
- 開始日（既存スケジュール最終日2026-09-27の翌日）: 2026-09-28
- 不足日数: 8日分（14日分になるまで） → feed 16本（post86〜post101）、reel 8本（reel42〜reel49）を作成
- narration_pool/pending/ に未消費の録音なし → reel台本を新規作成

## 作成物

- captions/post86.txt 〜 post101.txt … フィード投稿用キャプション（16本）
- prompts/post86_prompts.txt 〜 post101_prompts.txt … 各投稿の画像生成プロンプト（hook 1枚+knowhow 3枚+cta 1枚、計5行/ファイル）
- reel_scripts.md … リール42〜49のナレーション台本+投稿用キャプション（8本）
- schedule_draft.json … 日付→枠→投稿番号の対応表（本番schedule/*.jsonへの反映用メモ）

## 人間が行う作業

1. image_toolkit等でprompts/post*_prompts.txtからpost{N}_slide1〜5.jpgを生成し、リポジトリ直下に配置
2. reel_scripts.mdの台本でナレーション録音（CoeFont）→ narration_pool/pending/に配置、またはrunway_toolkitでreel42〜49の動画を生成
3. schedule_draft.jsonを参照しながら、本番のschedule/2026-09.json（またはschedule/2026-10.json）に日付ごとのエントリを追記
4. 反映後、このpending_batch/2026-09-28/ディレクトリは削除してよい
