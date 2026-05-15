import telebot
import requests
from flask import Flask, render_template_string, jsonify
from threading import Thread

# ================= CẤU HÌNH CỦA BẠN =================
# Thay thế chính xác Token và Link Render của bạn vào đây
TOKEN = "8759609630:AAEAJfmIIEZXcIR8OTRj2g_OmxCfxUXPKtc"
WEB_APP_URL = "https://regacc-4uk7.onrender.com" 
# Ví dụ: WEB_APP_URL = "https://regacc-4uk7.onrender.com"
# =====================================================

current_cookie = "CHUA_CO_COOKIE"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def get_shopee_orders(cookie):
    url = "https://shopee.vn/api/v4/order/get_order_list?order_type=3&offset=0&limit=10"
    headers = {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Shopee-Http-Client-Type": "phi-client-v2"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        return res.json().get('data', {}).get('details_list', [])
    except:
        return []

@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html lang="vi">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Shopee Orders</title>
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background-color: #f4f4f4; margin: 0; padding: 15px; color: #333; }
            h2 { text-align: center; color: #ee4d2d; font-size: 20px; }
            .order-card { background: white; border-radius: 12px; padding: 15px; margin-bottom: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 5px solid #ee4d2d; }
            .status { font-weight: bold; color: #ee4d2d; font-size: 13px; text-transform: uppercase; margin-bottom: 5px; }
            .product-name { font-size: 15px; line-height: 1.4; margin-bottom: 8px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
            .price { font-weight: bold; color: #333; font-size: 16px; text-align: right; }
            .loading { text-align: center; margin-top: 50px; color: #888; }
        </style>
    </head>
    <body>
        <h2>Đơn Hàng Của Bạn</h2>
        <div id="order-list"><div class="loading">Đang lấy dữ liệu từ Shopee...</div></div>

        <script>
            fetch('/api/orders')
                .then(response => response.json())
                .then(data => {
                    const list = document.getElementById('order-list');
                    if (data.length === 0) {
                        list.innerHTML = '<div class="loading">Không tìm thấy đơn hàng hoặc Cookie hết hạn.</div>';
                        return;
                    }
                    list.innerHTML = '';
                    data.forEach(order => {
                        const card = `
                            <div class="order-card">
                                <div class="status">${order.status}</div>
                                <div class="product-name">${order.name}</div>
                                <div class="price">₫${order.price.toLocaleString('vi-VN')}</div>
                            </div>
                        `;
                        list.innerHTML += card;
                    });
                })
                .catch(err => {
                    document.getElementById('order-list').innerHTML = '<div class="loading">Lỗi kết nối Server!</div>';
                });
        </script>
    </body>
    </html>
    """)
