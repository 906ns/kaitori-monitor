# カイトリショウテン 価格監視ツール

> ## ⚠️ このリポジトリについて(2026-05-04 追記)
>
> このプロジェクトは**現在動作しません**。GitHub上で Archive 化する予定で、**「学習過程の記録」**として残しています。
>
> ### 動作検証で判明した主な課題
>
> 1. スクレイパーのセレクタが対象サイトの実DOM構造と不一致(`.encrypt-num` → 実際は `.encrypt-price.plain-price` のプレーンテキスト。OCRそのものが不要だった)
> 2. 対象サイトが SPA(クライアントサイドルーティング)のため、カテゴリページ直接URLアクセスで404。トップページ経由のナビゲーションが必要
> 3. API(`add_item`)とスクレイパー(`get_product_info`)のインターフェース不整合 — JANコードのみ受け取る設計だがスクレイパーは URL 必須
> 4. `add_watched_item` で `product_url` が呼び出し元から渡されておらず、DBに保存されない
> 5. `monitor.py` での `add_log` 呼び出しでDBコネクション管理が層ごとに分散し、トランザクション管理が一貫していない
> 6. `headless=False` がハードコードされ、サーバー環境で動作不可
>
> ### このプロジェクトから学んだこと
>
> - **スクレイピング実装前に対象サイトのDOM構造を実機で必ず確認する**(想定で書かない)
> - SPAサイトのスクレイピングはクライアントサイドルーティングを考慮する必要がある
> - API層とスクレイパー層のインターフェース整合性は早期にテストで担保すべき
> - DBトランザクション管理は層ごとに分散せず、責務を明確にすべき
> - 環境依存パラメータ(headless 等)はハードコードせず設定化する
>
> これらの教訓は、後続プロジェクト [tax-automation](https://github.com/906ns/tax-automation) の実装習慣に反映済みです(Gemini API のレスポンスを実機で確認してから実装するなど)。
>
> アクティブなプロジェクトは以下を参照してください:
> - [tax-automation](https://github.com/906ns/tax-automation)(主力 / 確定申告自動化)
> - [x-tweet-fetcher](https://github.com/906ns/x-tweet-fetcher)(X API + Claude API)
>
> ---
>
> 以下は、このプロジェクトを最初に書いたときのオリジナルREADMEです(参考用)。

## 概要
カイトリショウテンの商品価格を監視し、価格変動をDiscordに通知するツール

## 機能
- JANコードによる商品監視
- 1分ごとの価格チェック
- 価格変動時のDiscord通知（上昇・下降両方）
- Webベースの管理画面（JAN追加/削除/ログ確認）
- OCRによる画像価格抽出

## セットアップ

### 1. 依存パッケージのインストール
```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Tesseractのインストール
- Windows: https://github.com/UB-Mannheim/tesseract/wiki からインストール
- Mac: `brew install tesseract tesseract-lang`
- Linux: `sudo apt-get install tesseract-ocr tesseract-ocr-jpn`

### 3. 設定ファイルの作成
`config.json`を作成し、Discord Webhook URLを設定:
```json
{
  "discord_webhook_url": "YOUR_DISCORD_WEBHOOK_URL_HERE"
}
```

### 4. 起動
```bash
python backend/main.py
```

ブラウザで `http://localhost:8000` にアクセス

## 使い方
1. WebUIでJANコードを入力して「追加」
2. 自動的に1分ごとに価格をチェック
3. 価格変動があればDiscordに通知

## 注意事項
- 監視間隔は1分に設定していますが、サイトの負荷を考慮してください
- OCR精度により価格抽出に失敗する可能性があります
