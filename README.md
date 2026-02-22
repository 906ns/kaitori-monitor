# カイトリショウテン 価格監視ツール

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
