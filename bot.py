import telebot
import requests
from flask import Flask, render_template_string, jsonify
from threading import Thread

# --- CẤU HÌNH ---
TOKEN = "8759609630:AAEAJfmIIEZXcIR8OTRj2g_OmxCfxUXPKtc"
# Biến tạm để lưu Cookie trong lúc chạy
current_cookie = "CHUA_CO_COOKIE" 
web_app_url = "https://regacc-4uk7.onrender.com"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- LOGIC LẤY ĐƠN HÀNG ---
def get_shopee_orders(cookie):
    url = "https://shopee.vn/api/v4/order/get_order_list?order_type=3&offset=0&limit=10"
    headers = {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Shopee-Http-Client-Type": "phi-client-v2"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get('data', {}).get('details_list', [])
        return []
    except:
        return []

# --- GIAO DIỆN MINI APP ---
@app.route('/')
def index():
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Shopee Check</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: sans-serif; background: #f0f2f5; padding: 10px; }
            .card { background: white; border-radius: 8px; padding: 12px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
            .status { color: #ee4d2d; font-weight: bold; font-size: 13px; }
            .name { font-size: 14px; margin: 5px 0; }
            h2 { text-align: center; color: #ee4d2d; }
        </style>
    </head>
    <body>
        <h2>Đơn Hàng Của Bạn</h2>
        <div id="list">Đang tải...</div>
        <script>
            fetch('/api/orders').then(r => r.json()).then(data => {
                let div = document.getElementById('list');
                div.innerHTML = data.length ? '' : 'Chưa có dữ liệu hoặc Cookie lỗi.';
                data.forEach(o => {
                    div.innerHTML += `<div class="card">
                        <div class="status">${o.status}</div>
                        <div class="name">${o.name}</div>
                        <div>₫${(o.price).toLocaleString()}</div>
                    </div>`;
                });
            });
        </script>
    </body>
    </html>
    """)

@app.route('/api/orders')
def api_orders():
    orders = get_shopee_orders(current_cookie)
    result = []
    for o in orders:
        result.append({
            "status": o['status_info']['status_label']['text'],
            "name": o['info_card']['order_list_cards'][0]['product_info']['item_groups'][0]['items'][0]['name'],
            "price": o['info_card']['final_total'] / 100000
        })
    return jsonify(result)

# --- LỆNH TELEGRAM ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = telebot.types.InlineKeyboardMarkup()
    btn = telebot.types.InlineKeyboardButton("Mở Mini App 📦", web_app=telebot.types.WebAppInfo(url=web_app_url))
    markup.add(btn)
    bot.send_message(message.chat.id, "Gửi Cookie mới cho mình hoặc bấm nút bên dưới:", reply_markup=markup)

@bot.message_handler(func=lambda m: "SPC_EC=" in m.text)
def update_cookie(message):
    global current_cookie
    current_cookie = message.text.strip()
    bot.reply_to(message, "✅ Đã nhận Cookie mới! Bây giờ bạn có thể mở Mini App để check đơn.")

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    Thread(target=run_flask).start()
    bot.infinity_polling()
