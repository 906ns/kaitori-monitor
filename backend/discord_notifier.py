import aiohttp
import json
from datetime import datetime
from typing import Optional

class DiscordNotifier:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
    
    async def send_notification(self, title: str, description: str, color: int = 0x3498db, 
                               fields: Optional[list] = None):
        """Discord通知を送信"""
        if not self.webhook_url or self.webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
            print(f"[Discord通知スキップ] {title}: {description}")
            return
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {
                "text": "カイトリショウテン監視"
            }
        }
        
        if fields:
            embed["fields"] = fields
        
        payload = {
            "embeds": [embed]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status != 204:
                        print(f"Discord通知エラー: {response.status}")
        except Exception as e:
            print(f"Discord通知送信失敗: {e}")
    
    async def notify_item_added(self, jan: str, product_name: str, price: Optional[int] = None):
        """商品追加通知"""
        description = f"**{product_name}**\nJAN: `{jan}`"
        if price:
            description += f"\n現在価格: ¥{price:,}"
        
        await self.send_notification(
            title="✅ 監視開始",
            description=description,
            color=0x2ecc71  # 緑
        )
    
    async def notify_price_change(self, jan: str, product_name: str, 
                                  old_price: int, new_price: int, url: str):
        """価格変動通知"""
        diff = new_price - old_price
        diff_percent = (diff / old_price * 100) if old_price > 0 else 0
        
        if diff > 0:
            # 価格上昇
            title = "📈 価格上昇"
            color = 0xe74c3c  # 赤
            emoji = "⬆️"
        else:
            # 価格下降
            title = "📉 価格下降"
            color = 0x3498db  # 青
            emoji = "⬇️"
        
        fields = [
            {
                "name": "旧価格",
                "value": f"¥{old_price:,}",
                "inline": True
            },
            {
                "name": "新価格",
                "value": f"¥{new_price:,}",
                "inline": True
            },
            {
                "name": "変動額",
                "value": f"{emoji} ¥{abs(diff):,} ({diff_percent:+.1f}%)",
                "inline": True
            },
            {
                "name": "JAN",
                "value": f"`{jan}`",
                "inline": False
            },
            {
                "name": "商品ページ",
                "value": f"[カイトリショウテンで確認]({url})",
                "inline": False
            }
        ]
        
        await self.send_notification(
            title=f"{title}: {product_name}",
            description="",
            color=color,
            fields=fields
        )
    
    async def notify_error(self, jan: str, product_name: str, error_message: str):
        """エラー通知"""
        await self.send_notification(
            title="⚠️ 監視エラー",
            description=f"**{product_name}** (JAN: `{jan}`)\n```{error_message}```",
            color=0xe67e22  # オレンジ
        )
