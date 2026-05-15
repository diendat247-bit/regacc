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
    return "Bot Shopee đang chạy ổn định!"

@app.route('/api/orders')
def api_orders():
    orders = get_shopee_orders(current_cookie)
    result = []
    for o in orders:
        try:
            status = o['status_info']['status_label']['text']
            product = o['info_card']['order_list_cards'][0]['product_info']['item_groups'][0]['items'][0]['name']
            price = o['info_card']['final_total'] / 100000
            result.append({"status": status, "name": product, "price": price})
        except:
            continue
    return jsonify(result)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    btn = telebot.types.InlineKeyboardButton("Mở Mini App 📦", web_app=telebot.types.WebAppInfo(url=WEB_APP_URL))
    markup.add(btn)
    text = "Chào mừng bạn! Hãy dán Cookie Shopee (có chứa SPC_F) vào đây để mình kiểm tra đơn hàng giúp bạn nhé."
    bot.send_message(message.chat.id, text, reply_markup=markup)

@bot.message_handler(func=lambda m: "SPC_F=" in m.text)
def handle_cookie(message):
    global current_cookie
    current_cookie = message.text.strip()
    bot.reply_to(message, "✅ Đã nhận Cookie thành công! Bây giờ bạn hãy bấm nút 'Mở Mini App' ở trên để xem danh sách đơn hàng.")

def run_flask():
    app.run(host='0.0.0.0', port=8080)

if __name__ == "__main__":
    print("Bot đang khởi động...")
    # Chạy Flask ở một luồng riêng
    Thread(target=run_flask).start()
    # Chạy Bot Telegram
    bot.infinity_polling()
