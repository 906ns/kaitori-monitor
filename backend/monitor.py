import asyncio
from datetime import datetime
from typing import Optional
from .scraper import KaitoriScraper
from .database import (
    get_watched_items, 
    update_price,
    add_log,
    init_db
)
from .discord_notifier import DiscordNotifier
import aiosqlite

class PriceMonitor:
    def __init__(self, discord_webhook_url: str, check_interval: int = 60, 
                 tesseract_cmd: Optional[str] = None):
        self.scraper = KaitoriScraper(tesseract_cmd)
        self.notifier = DiscordNotifier(discord_webhook_url)
        self.check_interval = check_interval
        self.is_running = False
        self.task = None
    
    async def start(self):
        """監視を開始"""
        if self.is_running:
            print("監視はすでに実行中です")
            return
        
        await init_db()
        self.is_running = True
        self.task = asyncio.create_task(self._monitor_loop())
        print(f"価格監視を開始しました（チェック間隔: {self.check_interval}秒）")
    
    async def stop(self):
        """監視を停止"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        await self.scraper.close_browser()
        print("価格監視を停止しました")
    
    async def _monitor_loop(self):
        """メイン監視ループ"""
        while self.is_running:
            try:
                await self._check_all_items()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"監視ループエラー: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_all_items(self):
        """すべての監視アイテムをチェック"""
        items = await get_watched_items()

        if not items:
            return

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {len(items)}個の商品を監視中...")

        # IPブロック対策: 順次実行に変更（並列実行を無効化）
        import random
        for idx, item in enumerate(items):
            await self._check_item_sequential(item)
            # 最後の商品でなければ待機
            if idx < len(items) - 1:
                # 各商品チェック後にランダムな遅延を追加（延長）
                delay = random.randint(10000, 20000)  # 10-20秒
                print(f"次の商品まで {delay/1000:.1f}秒 待機...")
                await asyncio.sleep(delay / 1000)
    
    async def _check_item_sequential(self, item: dict):
        """個別商品の価格をチェック（順次実行用）"""
        jan = item['jan']
        url = item.get('product_url', '')

        # IPブロック対策: URLが登録されていない場合はスキップ
        if not url:
            print(f"⚠ URL未登録のためスキップ: {item.get('product_name', jan)} (JAN: {jan})")
            return

        try:
            # 商品情報を取得（URL直接アクセスのみ）
            product_info = await self.scraper.get_product_info(jan, url)

            if not product_info or product_info['price'] is None:
                print(f"価格取得失敗: {item['product_name']} (JAN: {jan})")

                # エラーログを記録
                async with aiosqlite.connect("kaitori_monitor.db") as db:
                    await add_log(db, jan, "error", "価格取得失敗")
                    await db.commit()

                return

            # 価格を更新
            result = await update_price(
                jan,
                product_info['price'],
                product_info['product_name']
            )

            # 価格変動があればDiscord通知
            if result['changed']:
                print(f"価格変動検出: {result['product_name']} "
                      f"¥{result['old_price']:,} → ¥{result['new_price']:,}")

                await self.notifier.notify_price_change(
                    jan=jan,
                    product_name=result['product_name'],
                    old_price=result['old_price'],
                    new_price=result['new_price'],
                    url=product_info['url']
                )
            else:
                print(f"価格変動なし: {result['product_name']} (¥{result['new_price']:,})")

        except Exception as e:
            print(f"チェックエラー (JAN: {jan}): {e}")

            # エラー通知
            await self.notifier.notify_error(
                jan=jan,
                product_name=item['product_name'] or f"JAN: {jan}",
                error_message=str(e)
            )
    
    async def check_item_now(self, jan: str) -> Optional[dict]:
        """特定商品を即座にチェック（手動チェック用）"""
        try:
            # データベースからURLを取得
            items = await get_watched_items()
            item = next((i for i in items if i['jan'] == jan), None)

            if not item:
                print(f"商品が見つかりません: JAN {jan}")
                return None

            url = item.get('product_url', None)
            product_info = await self.scraper.get_product_info(jan, url)

            if product_info and product_info['price'] is not None:
                result = await update_price(
                    jan,
                    product_info['price'],
                    product_info['product_name']
                )

                if result['changed']:
                    await self.notifier.notify_price_change(
                        jan=jan,
                        product_name=result['product_name'],
                        old_price=result['old_price'],
                        new_price=result['new_price'],
                        url=product_info['url']
                    )

                return product_info

            return None

        except Exception as e:
            print(f"手動チェックエラー: {e}")
            return None
