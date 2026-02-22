import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Optional

DATABASE_PATH = "kaitori_monitor.db"

async def init_db():
    """データベースの初期化"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 監視商品テーブル
        await db.execute("""
            CREATE TABLE IF NOT EXISTS watched_items (
                jan TEXT PRIMARY KEY,
                product_name TEXT,
                product_url TEXT,
                current_price INTEGER,
                last_checked TIMESTAMP,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # 価格履歴テーブル
        await db.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jan TEXT,
                price INTEGER,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (jan) REFERENCES watched_items(jan)
            )
        """)
        
        # ログテーブル
        await db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jan TEXT,
                log_type TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()

async def add_watched_item(jan: str, product_name: str = "", product_url: str = "", price: Optional[int] = None):
    """監視商品を追加"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO watched_items (jan, product_name, product_url, current_price, last_checked)
            VALUES (?, ?, ?, ?, ?)
        """, (jan, product_name, product_url, price, datetime.now()))
        
        if price is not None:
            await db.execute("""
                INSERT INTO price_history (jan, price)
                VALUES (?, ?)
            """, (jan, price))
        
        await add_log(db, jan, "info", f"監視開始: {product_name} (JAN: {jan})")
        await db.commit()

async def remove_watched_item(jan: str):
    """監視商品を削除"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 物理削除に変更
        await db.execute("DELETE FROM watched_items WHERE jan = ?", (jan,))
        await add_log(db, jan, "info", f"監視停止: JAN {jan}")
        await db.commit()

async def get_watched_items() -> List[Dict]:
    """監視中の商品一覧を取得"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT jan, product_name, product_url, current_price, last_checked, added_at
            FROM watched_items
            WHERE is_active = 1
            ORDER BY added_at DESC
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def update_price(jan: str, new_price: int, product_name: str = "") -> Dict:
    """価格を更新し、変動情報を返す"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # 現在の価格を取得
        async with db.execute(
            "SELECT current_price, product_name FROM watched_items WHERE jan = ?", 
            (jan,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {"changed": False}
            
            old_price = row[0]
            stored_name = row[1]
            
            # 商品名が空の場合は更新
            if not stored_name and product_name:
                await db.execute(
                    "UPDATE watched_items SET product_name = ? WHERE jan = ?",
                    (product_name, jan)
                )
                stored_name = product_name
        
        # 価格を更新
        await db.execute("""
            UPDATE watched_items 
            SET current_price = ?, last_checked = ?
            WHERE jan = ?
        """, (new_price, datetime.now(), jan))
        
        # 価格履歴に追加
        await db.execute("""
            INSERT INTO price_history (jan, price)
            VALUES (?, ?)
        """, (jan, new_price))
        
        result = {
            "changed": old_price is not None and old_price != new_price,
            "old_price": old_price,
            "new_price": new_price,
            "product_name": stored_name or f"JAN: {jan}",
            "jan": jan
        }
        
        if result["changed"]:
            direction = "上昇" if new_price > old_price else "下降"
            diff = abs(new_price - old_price)
            await add_log(
                db, jan, "price_change",
                f"価格{direction}: ¥{old_price:,} → ¥{new_price:,} (差額: ¥{diff:,})"
            )
        
        await db.commit()
        return result

async def get_logs(limit: int = 100) -> List[Dict]:
    """ログを取得"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT l.*, w.product_name
            FROM logs l
            LEFT JOIN watched_items w ON l.jan = w.jan
            ORDER BY l.created_at DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def add_log(db, jan: str, log_type: str, message: str):
    """ログを追加（トランザクション内で使用）"""
    await db.execute("""
        INSERT INTO logs (jan, log_type, message)
        VALUES (?, ?, ?)
    """, (jan, log_type, message))

async def get_price_history(jan: str, limit: int = 50) -> List[Dict]:
    """特定商品の価格履歴を取得"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT price, checked_at
            FROM price_history
            WHERE jan = ?
            ORDER BY checked_at DESC
            LIMIT ?
        """, (jan, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
