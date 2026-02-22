import json
import os
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import asyncio

from .database import (
    init_db,
    add_watched_item,
    remove_watched_item,
    get_watched_items,
    get_logs,
    get_price_history
)
from .monitor import PriceMonitor
from .scraper import KaitoriScraper
from .discord_notifier import DiscordNotifier

# 設定ファイル読み込み
CONFIG_PATH = "config.json"
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    config = json.load(f)

app = FastAPI(title="カイトリショウテン価格監視API")

# グローバル変数
monitor: Optional[PriceMonitor] = None
notifier: Optional[DiscordNotifier] = None

# リクエストモデル
class AddItemRequest(BaseModel):
    jan: str
    url: Optional[str] = None

class RemoveItemRequest(BaseModel):
    jan: str

@app.on_event("startup")
async def startup_event():
    """アプリケーション起動時の処理"""
    global monitor, notifier
    
    # データベース初期化
    await init_db()
    
    # Discord通知初期化
    notifier = DiscordNotifier(config['discord_webhook_url'])
    
    # 価格監視開始
    monitor = PriceMonitor(
        discord_webhook_url=config['discord_webhook_url'],
        check_interval=config.get('check_interval_seconds', 60),
        tesseract_cmd=config.get('tesseract_cmd')
    )
    await monitor.start()

@app.on_event("shutdown")
async def shutdown_event():
    """アプリケーション終了時の処理"""
    if monitor:
        await monitor.stop()

@app.get("/")
async def read_root():
    """フロントエンドHTMLを返す"""
    html_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse(content="<h1>Frontend not found</h1>", status_code=404)

@app.get("/api/items")
async def get_items():
    """監視中の商品一覧を取得"""
    items = await get_watched_items()
    return {"items": items}

@app.post("/api/items/add")
async def add_item(request: AddItemRequest):
    """監視商品を追加"""
    try:
        # スクレイパーで商品情報を取得
        scraper = KaitoriScraper(config.get('tesseract_cmd'))
        
        if request.url:
            product_info = await scraper.get_product_info_by_url(request.url, request.jan)
        else:
            product_info = await scraper.get_product_info(request.jan)
        
        await scraper.close_browser()
        
        if not product_info:
            raise HTTPException(status_code=404, detail="商品情報を取得できませんでした")
        
        # データベースに追加
        await add_watched_item(
            jan=request.jan,
            product_name=product_info.get('product_name', ''),
            price=product_info.get('price')
        )
        
        # Discord通知
        if notifier:
            await notifier.notify_item_added(
                jan=request.jan,
                product_name=product_info.get('product_name', f'JAN: {request.jan}'),
                price=product_info.get('price')
            )
        
        return {
            "success": True,
            "message": "商品を追加しました",
            "product_info": product_info
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/items/remove")
async def remove_item(request: RemoveItemRequest):
    """監視商品を削除"""
    try:
        await remove_watched_item(request.jan)
        return {"success": True, "message": "商品を削除しました"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs_api(limit: int = 100):
    """ログを取得"""
    logs = await get_logs(limit)
    return {"logs": logs}

@app.get("/api/history/{jan}")
async def get_history(jan: str, limit: int = 50):
    """特定商品の価格履歴を取得"""
    history = await get_price_history(jan, limit)
    return {"history": history}

@app.post("/api/items/check/{jan}")
async def check_item_now(jan: str):
    """特定商品を手動でチェック"""
    if not monitor:
        raise HTTPException(status_code=503, detail="監視システムが起動していません")
    
    try:
        result = await monitor.check_item_now(jan)
        if result:
            return {"success": True, "product_info": result}
        else:
            raise HTTPException(status_code=404, detail="商品情報を取得できませんでした")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/status")
async def get_status():
    """システムステータスを取得"""
    return {
        "is_running": monitor.is_running if monitor else False,
        "check_interval": config.get('check_interval_seconds', 60),
        "discord_configured": config['discord_webhook_url'] != "YOUR_DISCORD_WEBHOOK_URL_HERE"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
