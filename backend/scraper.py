import asyncio
import sys
import re
import random
from playwright.async_api import async_playwright, Page
import pytesseract
from PIL import Image
import cv2
import numpy as np
import io
import os
from typing import Optional, Dict

# Windowsでのサブプロセス問題を回避
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

class KaitoriScraper:
    def __init__(self, tesseract_cmd: Optional[str] = None, proxy: Optional[str] = None):
        self.base_url = "https://www.kaitorishouten-co.jp/"
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self.browser = None
        self.context = None
        self.proxy = proxy  # 例: "http://proxy-server:port" or "socks5://proxy-server:port"
        self.playwright = None
        self.request_count = 0  # リクエストカウンター
        self.max_requests_before_restart = 5  # この回数ごとにブラウザを再起動
    
    async def init_browser(self):
        """ブラウザの初期化（ボット検出対策付き）"""
        if self.browser is None:
            if self.playwright is None:
                self.playwright = await async_playwright().start()

            # ボット検出対策
            self.browser = await self.playwright.chromium.launch(
                headless=False,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process'
                ]
            )

            # より現実的なブラウザ設定
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'locale': 'ja-JP',
                'timezone_id': 'Asia/Tokyo',
                'extra_http_headers': {
                    'Accept-Language': 'ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
            }

            # プロキシ設定があれば追加
            if self.proxy:
                context_options['proxy'] = {'server': self.proxy}
                print(f"プロキシを使用: {self.proxy}")

            self.context = await self.browser.new_context(**context_options)

            # JavaScriptでwebdriver検出を回避
            await self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });

                // Chrome detection
                window.chrome = {
                    runtime: {}
                };

                // Permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Plugin array
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });

                // Languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['ja-JP', 'ja', 'en-US', 'en']
                });
            """)
    
    async def close_browser(self):
        """ブラウザのクローズ"""
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None

    async def restart_browser_if_needed(self):
        """一定回数のリクエスト後にブラウザを再起動"""
        self.request_count += 1
        if self.request_count >= self.max_requests_before_restart:
            print(f"ブラウザを再起動します（{self.request_count}回のリクエスト後）")
            await self.close_browser()
            self.request_count = 0
            # 再起動後の待機時間
            await asyncio.sleep(random.randint(5, 10))
    
    def extract_price_from_image(self, image_bytes: bytes) -> Optional[int]:
        """画像から価格を抽出（OCR）- 複数手法で試行"""
        try:
            # 画像を読み込み
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                print("画像のデコードに失敗")
                return None

            # グレースケール変換
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 画像を拡大（OCR精度向上）
            scale_factor = 4  # 3→4に増加
            height, width = gray.shape
            gray = cv2.resize(gray, (width * scale_factor, height * scale_factor), interpolation=cv2.INTER_CUBIC)

            # 複数の前処理方法を試す
            processed_images = []
            method_names = []

            # 方法1: OTSU二値化のみ
            _, binary1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(binary1)
            method_names.append("OTSU")

            # 方法2: 適応的二値化
            binary2 = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            processed_images.append(binary2)
            method_names.append("Adaptive")

            # 方法3: ガウシアンぼかし + OTSU
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            _, binary3 = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(binary3)
            method_names.append("Blur+OTSU")

            # 方法4: シャープ化 + OTSU
            kernel_sharpen = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            sharpened = cv2.filter2D(gray, -1, kernel_sharpen)
            _, binary4 = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            processed_images.append(binary4)
            method_names.append("Sharpen+OTSU")

            # デバッグ用: 処理後の画像を保存
            import time
            timestamp = int(time.time() * 1000)
            cv2.imwrite(f'debug_original_{timestamp}.png', img)

            # 各方法でOCRを試行
            all_results = []
            for processed, method_name in zip(processed_images, method_names):
                cv2.imwrite(f'debug_{method_name}_{timestamp}.png', processed)

                # OCR実行
                configs = [
                    '--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789,',
                    '--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789,',
                    '--psm 13 --oem 3 -c tessedit_char_whitelist=0123456789,'
                ]

                for config in configs:
                    text = pytesseract.image_to_string(processed, lang='eng', config=config)
                    cleaned = text.replace('\n', '').replace(' ', '').replace('\t', '')
                    digits_only = re.sub(r'[^0-9,]', '', cleaned)

                    if digits_only:
                        price_str = digits_only.replace(',', '')
                        if price_str.isdigit() and len(price_str) > 0:
                            price = int(price_str)
                            if 100 <= price <= 10000000:
                                all_results.append((price, method_name, config, digits_only))
                                print(f"  {method_name}: {digits_only} → ¥{price:,}")

            if not all_results:
                print("すべての方法で価格取得失敗")
                return None

            # 最も頻出する価格を選択
            from collections import Counter

            # 価格を正規化（下1桁が余分な場合の修正）
            normalized_prices = []
            for price, method, _, _ in all_results:
                # 下1桁が0-9で、かつ価格が6桁以上の場合、下1桁を削除
                if len(str(price)) >= 6 and price % 10 != 0:
                    # 下1桁を削除（10で割って切り捨て）
                    corrected_price = price // 10
                    print(f"  価格修正: {price:,} → {corrected_price:,} ({method})")
                    normalized_prices.append(corrected_price)
                else:
                    normalized_prices.append(price)

            price_counts = Counter(normalized_prices)
            most_common_price = price_counts.most_common(1)[0][0]

            # その価格を得た方法を表示
            print(f"✓ 最終価格: ¥{most_common_price:,} (検出回数: {price_counts[most_common_price]}回)")

            return most_common_price

        except Exception as e:
            print(f"OCRエラー: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def get_product_info(self, jan: str, url: str = None) -> Optional[Dict]:
        """JANコードまたはURLから商品情報を取得"""
        # ブラウザの再起動チェック
        await self.restart_browser_if_needed()

        await self.init_browser()

        page = await self.context.new_page()
        print(f"[{jan}] 新しいページを作成")

        try:
            # IPブロック対策: URLが必須
            if not url:
                print(f"[{jan}] エラー: URLが指定されていません")
                await page.close()
                return None

            # 指定URLに直接アクセス
            print(f"[{jan}] 指定URLにアクセス: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            actual_url = url
            await page.wait_for_timeout(3000)

            print(f"[{jan}] ページ読み込み完了: {actual_url}")

            # 商品名を取得
            product_name = f"JAN: {jan}"
            try:
                # 複数のセレクタを試す
                selectors = [
                    '.ec-favoriteRole__itemTitle',
                    'h1',
                    '.product-name',
                    '[class*="product"][class*="title"]'
                ]
                for selector in selectors:
                    try:
                        name_element = await page.wait_for_selector(selector, timeout=2000)
                        if name_element:
                            text = await name_element.text_content()
                            if text and text.strip():
                                product_name = text.strip()
                                print(f"商品名取得: {product_name}")
                                break
                    except:
                        continue
            except:
                pass

            # 価格画像を取得（OCR）
            price = None
            try:
                print(f"価格要素を検索中...")

                # デバッグ: ページのHTMLを確認
                page_content = await page.content()
                if 'encrypt' in page_content:
                    print("✓ ページに'encrypt'が含まれています")
                    # encrypt関連のクラスを探す
                    import re
                    encrypt_classes = re.findall(r'class="[^"]*encrypt[^"]*"', page_content)
                    if encrypt_classes:
                        print(f"見つかったencryptクラス: {set(encrypt_classes[:5])}")
                else:
                    print("⚠ ページに'encrypt'が見つかりません")
                    # 価格に関連しそうなクラスを探す
                    price_classes = re.findall(r'class="[^"]*price[^"]*"', page_content)
                    if price_classes:
                        print(f"見つかったpriceクラス: {set(price_classes[:5])}")

                # class="encrypt-num"の要素のみを使用
                selector = '.encrypt-num'
                print(f"セレクタ: {selector}")
                elements = await page.query_selector_all(selector)
                print(f"  → {len(elements)}個の要素が見つかりました")

                if elements:
                    # 親要素を探す（すべてのencrypt-num要素を含む）
                    # 最初の要素の親をたどって、すべてのencrypt-num要素を含む要素を見つける
                    try:
                        first_element = elements[0]
                        parent = await first_element.evaluate_handle('el => el.parentElement')

                        # 親要素のスクリーンショットを撮る
                        screenshot = await parent.as_element().screenshot()
                        print(f"  親要素のスクリーンショット取得: {len(screenshot)} bytes")

                        extracted_price = self.extract_price_from_image(screenshot)
                        if extracted_price and extracted_price > 0:
                            price = extracted_price
                            print(f"✓ 価格取得成功: ¥{price:,}")
                    except Exception as e:
                        print(f"親要素取得エラー: {e}")

                if not price:
                    print("⚠ 価格取得失敗")

            except Exception as e:
                print(f"価格取得エラー (JAN: {jan}): {e}")
                import traceback
                traceback.print_exc()

            await page.close()

            return {
                "jan": jan,
                "product_name": product_name,
                "price": price,
                "url": actual_url
            }
            
        except Exception as e:
            print(f"スクレイピングエラー (JAN: {jan}): {e}")
            await page.close()
            return None
    
    async def get_product_info_by_url(self, url: str, jan: str) -> Optional[Dict]:
        """URLから直接商品情報を取得（より確実な方法）"""
        await self.init_browser()
        
        page = await self.context.new_page()
        
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await page.wait_for_timeout(3000)
            
            # 商品名を取得
            product_name = f"JAN: {jan}"
            try:
                # 複数のセレクタを試す
                selectors = [
                    '.ec-favoriteRole__itemTitle',
                    '.product-name',
                    '[class*="product"][class*="title"]',
                    'h1'
                ]
                for selector in selectors:
                    try:
                        name_element = await page.wait_for_selector(selector, timeout=2000)
                        if name_element:
                            text = await name_element.text_content()
                            if text and text.strip():
                                product_name = text.strip()
                                break
                    except:
                        continue
            except:
                pass
            
            # 価格を取得（OCR）
            price = None
            try:
                # 暗号化された価格要素
                price_selectors = [
                    'span.encrypt-num',
                    '[class*="encrypt"]',
                    '.ec-favoriteRole__itemPrice',
                    '[class*="price"]'
                ]
                
                for selector in price_selectors:
                    try:
                        elements = await page.query_selector_all(selector)
                        for element in elements:
                            screenshot = await element.screenshot()
                            extracted_price = self.extract_price_from_image(screenshot)
                            if extracted_price and extracted_price > 0:
                                price = extracted_price
                                break
                        if price:
                            break
                    except:
                        continue
                
            except Exception as e:
                print(f"価格取得エラー: {e}")
            
            await page.close()
            
            return {
                "jan": jan,
                "product_name": product_name,
                "price": price,
                "url": url
            }
            
        except Exception as e:
            print(f"スクレイピングエラー: {e}")
            await page.close()
            return None
