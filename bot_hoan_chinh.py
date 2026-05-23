import os
import asyncio
import threading
import http.server
import socketserver
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

load_dotenv()

# ================= CẤU HÌNH TỪ BIẾN MÔI TRƯỜNG =================
TELEGRAM_TOKEN = os.environ.get("8792394937:AAHHROhBsoa0GvYzDfNuNufOC_VWhH1QTp8")
VIOTP_TOKEN = os.environ.get("19ff88d563be40ebac2c3103cdf80c2c")

# Lấy danh sách ADMIN_IDS (Hỗ trợ ngăn cách bằng dấu phẩy)
raw_admins = os.environ.get("ADMIN_IDS", os.environ.get("ADMIN_ID", "0"))
try:
    ADMIN_IDS = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]
except Exception:
    ADMIN_IDS = []

BASE_URL = "https://api.viotp.com"

# ================= KHO DỮ LIỆU LỊCH SỬ TOÀN CỤC =================
GLOBAL_HISTORY = {}

# ================= WEB SERVER ẢO CHO RENDER =================
PORT = int(os.environ.get("PORT", 10000))

class DummyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>Bot Telegram ViOTP dang hoat dong tot!</h1>")

def run_web():
    try:
        socketserver.TCPServer.allow_reuse_address = True 
        with socketserver.TCPServer(("0.0.0.0", PORT), DummyHandler) as httpd:
            print(f"🌐 Web Server da mo cong {PORT} cho Render...")
            httpd.serve_forever()
    except Exception as e:
        print(f"Lỗi Web Server: {e}")

# ================= CÁC HÀM TIỆN ÍCH =================

def is_admin(user_id):
    return user_id in ADMIN_IDS

def format_money(amount):
    try:
        return f"{int(amount):,}".replace(",", ".") + "đ"
    except (ValueError, TypeError):
        return f"{amount}đ"

# --- CÁC HÀM GỌI API VIOTP ---
def api_get(endpoint, params=None):
    if params is None:
        params = {}
    params['token'] = VIOTP_TOKEN
    try:
        return requests.get(f"{BASE_URL}{endpoint}", params=params, timeout=10).json()
    except Exception as e:
        return {"status_code": -1, "message": str(e)}

def get_balance(): return api_get("/users/balance")
def get_networks(): return api_get("/networks/get")
def get_services(): return api_get("/service/getv2", {"country": "vn"})
def request_number(service_id): return api_get("/request/getv2", {"serviceId": service_id})
def check_otp(request_id): return api_get("/session/getv2", {"requestId": request_id})

# --- HÀM GỬI THÔNG BÁO CHO TOÀN BỘ ADMIN ---
async def broadcast_to_admins(context: ContextTypes.DEFAULT_TYPE, text: str, voice_url: str = None, phone: str = ""):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=text, parse_mode='HTML')
            if voice_url and "http" in str(voice_url):
                try:
                    await context.bot.send_voice(chat_id=admin_id, voice=voice_url, caption=f"🎧 File Voice OTP của số {phone}")
                except Exception:
                    await context.bot.send_message(chat_id=admin_id, text=f"🔗 Link Audio OTP: {voice_url}")
        except Exception as e:
            print(f"⚠️ Không thể gửi thông báo tới Admin ID {admin_id}: {e}")

# ================= HỆ THỐNG LỌC SỐ & REG ACC =================

# --- 1. HÀM KIỂM TRA SỐ SẠCH/BẨN ---
async def check_number_status(phone: str, service_name: str) -> bool:
    """
    Trả về True nếu số ĐÃ BỊ LIÊN KẾT (Cần bỏ qua).
    Trả về False nếu số SẠCH (Có thể dùng tạo tài khoản).
    """
    print(f"🔎 Đang kiểm tra trạng thái của số {phone} cho {service_name}...")
    
    # [!] DÁN CODE KIỂM TRA (REQUEST/PLAYWRIGHT) CỦA BẠN VÀO ĐÂY [!]
    # ... logic check api shopee/facebook ...
    await asyncio.sleep(1) # Giả lập thời gian check
    
    return False # Đổi thành kết quả thực tế từ code của bạn

# --- 2. VÒNG LẶP LỌC SỐ TỰ ĐỘNG ---
async def auto_filter_and_register(service_id, service_name, raw_price, formatted_price, user_id, context, msg_context):
    max_retries = 10 # Giới hạn số lần thử tìm số sạch
    
    for attempt in range(1, max_retries + 1):
        await msg_context.edit_text(f"🔄 <b>Lần thử {attempt}/{max_retries}:</b> Đang yêu cầu số từ ViOTP...", parse_mode='HTML')
        
        # Bước 1: Gọi API thuê số
        res = await asyncio.to_thread(request_number, service_id)
        
        if str(res.get("status_code")) == "200":
            phone = res["data"].get("phone_number")
            req_id = res["data"].get("request_id")
            current_balance = format_money(res["data"].get("balance", 0))
            
            await msg_context.edit_text(f"🔄 <b>Lần thử {attempt}/{max_retries}:</b>\n📞 Lấy được số <code>{phone}</code>.\n🔎 Đang kiểm tra liên kết...", parse_mode='HTML')
            
            # Bước 2: Kiểm tra số xem có sạch không
            is_linked = await check_number_status(phone, service_name)
            
            if is_linked:
                # Nếu đã liên kết -> BỎ QUA VÀ TÌM SỐ MỚI
                await msg_context.edit_text(f"⚠️ Số <code>{phone}</code> đã dính tài khoản. Đang bỏ qua và lấy số mới...", parse_mode='HTML')
                await asyncio.sleep(3) # Nghỉ 3s tránh spam API ViOTP
                continue
                
            else:
                # Nếu số sạch -> LƯU VÀO HISTORY VÀ CANH MÃ
                vn_time = datetime.utcnow() + timedelta(hours=7)
                GLOBAL_HISTORY[str(req_id)] = {
                    "ID": req_id,
                    "ServiceID": service_id,
                    "ServiceName": service_name,
                    "Status": 0,
                    "Price": raw_price,
                    "Phone": phone,
                    "CreatedTime": vn_time.strftime('%Y-%m-%dT%H:%M:%S'),
                    "Code": ""
                }
                
                success_msg = (
                    f"✅ <b>TÌM THẤY SỐ SẠCH & BẮT ĐẦU CANH MÃ!</b>\n\n"
                    f"🏢 Dịch vụ: <b>{service_name}</b>\n"
                    f"📞 SĐT: <code>{phone}</code>\n"
                    f"💵 Giá thuê: <b>{formatted_price}</b>\n"
                    f"💰 Số dư tạm tính: <b>{current_balance}</b>\n"
                    f"🆔 Request ID: <code>{req_id}</code>\n\n"
                    f"🚀 <i>Hệ thống đang chạy ngầm Canh OTP & Reg Acc...</i>"
                )
                await msg_context.edit_text(success_msg, parse_mode='HTML')
                
                # Bắt đầu luồng canh OTP
                asyncio.create_task(monitor_otp(req_id, phone, service_name, formatted_price, context))
                
                # [!] BẠN CÓ THỂ ĐẶT HÀM ĐĂNG KÝ TÀI KHOẢN (REG ACC) VÀO ĐÂY [!]
                # asyncio.create_task(run_registration_logic(phone, ...))
                
                return # Hoàn tất việc lấy số
                
        else:
            # Lỗi API ViOTP (hết số, lỗi server...)
            await msg_context.edit_text(f"❌ Lỗi ViOTP: {res.get('message')}. Đang thử lại sau 5 giây...")
            await asyncio.sleep(5)
            
    # Nếu vòng lặp chạy hết mà không tìm được số sạch
    await msg_context.edit_text(f"❌ <b>Thất bại:</b> Đã thử lọc {max_retries} số nhưng đều bị liên kết hoặc ViOTP báo lỗi. Vui lòng thử lại sau.", parse_mode='HTML')


# ================= CÁC TIẾN TRÌNH VÀ HANDLERS CŨ =================

# --- TIẾN TRÌNH NGẦM QUÉT LỊCH SỬ TOÀN BỘ DỊCH VỤ ---
async def background_history_scanner():
    print("🔄 Bắt đầu tiến trình ngầm đồng bộ lịch sử toàn bộ dịch vụ...")
    while True:
        try:
            vn_time = datetime.utcnow() + timedelta(hours=7)
            today_str = vn_time.strftime('%Y-%m-%d')
            
            services_res = await asyncio.to_thread(get_services)
            if str(services_res.get("status_code")) == "200":
                services = services_res.get("data", [])
                
                for s in services:
                    service_id = s["id"]
                    
                    for stt in [1, 0]:
                        params = {
                            "service": service_id,
                            "status": stt,
                            "limit": 100,
                            "fromDate": today_str,
                            "toDate": today_str
                        }
                        res = await asyncio.to_thread(api_get, "/session/historyv2", params)
                        
                        if str(res.get("status_code")) == "200" and res.get("data"):
                            for item in res["data"]:
                                item_id = str(item.get("ID"))
                                GLOBAL_HISTORY[item_id] = item
                                
                        await asyncio.sleep(0.3)
        except Exception as e:
            print(f"Lỗi quét ngầm: {e}")
        
        await asyncio.sleep(300)

async def post_init(application: Application):
    asyncio.create_task(background_history_scanner())

# --- GIAO DIỆN BÀN PHÍM CHÍNH ---
def main_reply_keyboard():
    keyboard = [
        [KeyboardButton("💰 Tra cứu số dư"), KeyboardButton("🛒 Thuê số OTP")],
        [KeyboardButton("🏢 Danh sách nhà mạng"), KeyboardButton("🕒 Lịch sử thuê số")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

# --- TIẾN TRÌNH CHẠY NGẦM ĐỂ CANH OTP ---
async def monitor_otp(req_id, phone, service_name, price, context: ContextTypes.DEFAULT_TYPE):
    item_id = str(req_id)
    for _ in range(240): 
        await asyncio.sleep(5)
        check_res = await asyncio.to_thread(check_otp, req_id)
        
        if str(check_res.get("status_code")) == "200":
            status = check_res["data"].get("Status")
            
            if status == 1:
                code = check_res["data"].get("Code", "Không rõ")
                sms = check_res["data"].get("SmsContent", "")
                
                if item_id in GLOBAL_HISTORY:
                    GLOBAL_HISTORY[item_id]["Status"] = 1
                    GLOBAL_HISTORY[item_id]["Code"] = code
                
                balance_res = await asyncio.to_thread(get_balance)
                current_balance = format_money(balance_res['data']['balance']) if str(balance_res.get("status_code")) == "200" else "Không rõ"
                
                is_sound_raw = check_res["data"].get("IsSound", False)
                is_sound = str(is_sound_raw).lower() == "true"
                
                text = (
                    f"🎉 <b>CÓ MÃ MỚI TỪ VIOTP!</b>\n\n"
                    f"🏢 Dịch vụ: <b>{service_name}</b>\n"
                    f"📞 Số: <code>{phone}</code>\n"
                    f"🔑 Mã Code: <code>{code}</code>\n"
                    f"💵 Giá thuê: <b>{price}</b>\n"
                    f"💰 Số dư còn lại: <b>{current_balance}</b>\n"
                )
                
                if not is_sound:
                    text += f"📝 SMS: <code>{sms}</code>"
                
                await broadcast_to_admins(context, text, voice_url=(sms if is_sound else None), phone=phone)
                return 
            
            elif status == 2:
                if item_id in GLOBAL_HISTORY:
                    GLOBAL_HISTORY[item_id]["Status"] = 2
                
                balance_res = await asyncio.to_thread(get_balance)
                current_balance = format_money(balance_res['data']['balance']) if str(balance_res.get("status_code")) == "200" else "Không rõ"
                
                msg = (
                    f"❌ <b>SỐ ĐÃ HẾT HẠN (TIMEOUT)</b>\n\n"
                    f"🏢 Dịch vụ: <b>{service_name}</b>\n"
                    f"📞 Số: <code>{phone}</code>\n"
                    f"♻️ Tiền đã được hoàn lại vào tài khoản.\n"
                    f"💰 Số dư hiện tại: <b>{current_balance}</b>"
                )
                await broadcast_to_admins(context, msg)
                return

    if item_id in GLOBAL_HISTORY:
        GLOBAL_HISTORY[item_id]["Status"] = 2
        
    balance_res = await asyncio.to_thread(get_balance)
    current_balance = format_money(balance_res['data']['balance']) if str(balance_res.get("status_code")) == "200" else "Không rõ"
    msg = (
        f"⚠️ <b>QUÁ THỜI GIAN THEO DÕI (20 Phút)</b>\n\n"
        f"🏢 Dịch vụ: <b>{service_name}</b>\n"
        f"📞 Số: <code>{phone}</code>\n"
        f"Trạng thái: Tự động ngừng theo dõi để giải phóng bộ nhớ.\n"
        f"💰 Số dư hiện hành: <b>{current_balance}</b>"
    )
    await broadcast_to_admins(context, msg)

# --- XỬ LÝ LỆNH /START ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Bạn không có quyền sử dụng bot này.")
        return

    text = "🤖 <b>HỆ THỐNG BOT VIOTP ĐÃ SẴN SÀNG</b>\nBàn phím điều khiển đã được mở bên dưới 👇"
    await update.message.reply_text(text, reply_markup=main_reply_keyboard(), parse_mode='HTML')

# --- XỬ LÝ KHI BẤM NÚT Ở BÀN PHÍM DƯỚI ĐÁY ---
async def handle_text_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    text = update.message.text

    if text == "💰 Tra cứu số dư":
        res = await asyncio.to_thread(get_balance)
        msg = f"💰 <b>Số dư hiện tại:</b> <code>{format_money(res['data']['balance'])}</code>" if str(res.get("status_code")) == "200" else f"❌ Lỗi: {res.get('message')}"
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == "🏢 Danh sách nhà mạng":
        res = await asyncio.to_thread(get_networks)
        if str(res.get("status_code")) == "200":
            msg = "🏢 <b>Danh sách nhà mạng hỗ trợ:</b>\n\n" + "\n".join([f"- {net['name']} (ID: {net['id']})" for net in res["data"]])
        else:
            msg = f"❌ Lỗi: {res.get('message')}"
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == "🕒 Lịch sử thuê số":
        vn_time = datetime.utcnow() + timedelta(hours=7)
        today_str = vn_time.strftime('%Y-%m-%d')
        
        today_items = []
        for item in GLOBAL_HISTORY.values():
            created_time = item.get("CreatedTime", "")
            if today_str in created_time:
                today_items.append(item)
                
        if not today_items:
            await update.message.reply_text(f"🕒 <b>Lịch sử trống</b>\nChưa có giao dịch nào trong ngày hôm nay ({today_str}).", parse_mode='HTML')
            return
            
        try:
            today_items.sort(key=lambda x: x.get('CreatedTime', ''), reverse=True)
        except Exception:
            pass
            
        msg = f"🕒 <b>LỊCH SỬ THUÊ SỐ HÔM NAY ({today_str}):</b>\n\n"
        for item in today_items[:15]: 
            status_code = item.get("Status")
            stt = "🟢 Hoàn thành" if status_code == 1 else "🟡 Đang chờ mã" if status_code == 0 else "🔴 Hết hạn"
            msg += f"▪️ <b>{item.get('ServiceName', 'Dịch vụ')}</b> - <code>{item.get('Phone', '')}</code> ({stt})\n"
            if status_code == 1 and item.get("Code"):
                msg += f"   🔑 Mã: <code>{item.get('Code')}</code>\n"
            msg += "\n"
        
        await update.message.reply_text(msg, parse_mode='HTML')

    elif text == "🛒 Thuê số OTP":
        await send_services_page(update.message.reply_text, 0)

# --- HÀM GỬI DANH SÁCH DỊCH VỤ (INLINE KEYBOARD) ---
async def send_services_page(reply_method, page):
    res = await asyncio.to_thread(get_services)
    if str(res.get("status_code")) == "200":
        services = res["data"]
        start_idx, end_idx = page * 10, (page * 10) + 10
        current_services = services[start_idx:end_idx]
        
        keyboard = []
        for s in current_services:
            price_str = format_money(s['price'])
            btn_text = f"Thuê {s['name']} ({price_str})"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"rent_{s['id']}_{s['price']}_{s['name'][:15]}")])
        
        nav_buttons = []
        if page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Trước", callback_data=f"menu_services_{page-1}"))
        if end_idx < len(services): nav_buttons.append(InlineKeyboardButton("Sau ➡️", callback_data=f"menu_services_{page+1}"))
        if nav_buttons: keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("❌ Đóng Danh Sách", callback_data="close_menu")])
        
        await reply_method(f"🛒 <b>Chọn Dịch Vụ (Trang {page + 1})</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await reply_method(f"❌ Lỗi lấy dịch vụ: {res.get('message')}")

# --- XỬ LÝ NÚT BẤM (INLINE BUTTONS) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Bạn không có quyền thao tác!", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "close_menu":
        await query.message.delete()
        return

    if data.startswith("menu_services_"):
        page = int(data.split("_")[2])
        await send_services_page(query.edit_message_text, page)

    elif data.startswith("rent_"):
        parts = data.split("_")
        service_id = parts[1]
        raw_price = parts[2]
        formatted_price = format_money(raw_price)
        service_name = "_".join(parts[3:]) 
        
        # Bắt đầu luồng lọc thay vì request trực tiếp
        msg_wait = await query.edit_message_text(f"⏳ Bắt đầu tiến trình tự động lọc số cho <b>{service_name}</b>...", parse_mode='HTML')
        
        asyncio.create_task(
            auto_filter_and_register(service_id, service_name, raw_price, formatted_price, user_id, context, msg_wait)
        )

def main():
    if not ADMIN_IDS:
        print("LỖI: Chưa cấu hình danh sách ADMIN_IDS trong biến môi trường!")
        return
        
    threading.Thread(target=run_web, daemon=True).start()
        
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print(f"🤖 Bot đang chạy! Nhận lệnh từ {len(ADMIN_IDS)} Admin...")
    app.run_polling()

if __name__ == "__main__":
    main()
