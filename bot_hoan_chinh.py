import os
import sys
import json
import asyncio
import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from playwright.async_api import async_playwright

# Config logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- CONFIGURATION (Thay thế bằng thông tin của bạn) ---
API_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN' # Điền Token Bot của bạn vào đây
VIOTP_TOKEN = 'YOUR_VIOTP_TOKEN'       # Điền Token ViOTP của bạn vào đây
VIOTP_SERVICE_ID = '245'               # ID Dịch vụ Shopee trên ViOTP (Ví dụ: 245)

# Khởi tạo Bot và Dispatcher
storage = MemoryStorage()
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=storage)

# --- DATABASE SETUP (SQLite) ---
DB_FILE = "database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            password TEXT,
            cookies TEXT,
            spc_f TEXT,
            spc_t TEXT,
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- STATE MANAGEMENT (FSM) ---
class BotStates(StatesGroup):
    waiting_for_proxy = State()
    waiting_for_viotp_key = State()

# Quản lý các phiên giải captcha đang hoạt động giữa Playwright và Telegram
class CaptchaManager:
    def __init__(self):
        self.sessions = {}

    def create_session(self, user_id):
        self.sessions[user_id] = {
            'event': asyncio.Event(),
            'action': None,
            'value': 0,
            'offset_x': 0,
            'is_active': True
        }
        return self.sessions[user_id]

    def get_session(self, user_id):
        return self.sessions.get(user_id)

    def close_session(self, user_id):
        if user_id in self.sessions:
            self.sessions[user_id]['is_active'] = False
            self.sessions[user_id]['event'].set()
            del self.sessions[user_id]

captcha_manager = CaptchaManager()

# --- KEYBOARDS ---
def main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🚀 Reg Account", callback_data="menu_reg"),
        types.InlineKeyboardButton("🌐 Cài Đặt Proxy", callback_data="menu_proxy"),
        types.InlineKeyboardButton("📊 Check Acc Đã Reg", callback_data="menu_check")
    )
    return kb

def captcha_keyboard(offset):
    kb = types.InlineKeyboardMarkup(row_width=4)
    kb.add(
        types.InlineKeyboardButton("⏪ -30px", callback_data="cap_-30"),
        types.InlineKeyboardButton("⬅️ -5px", callback_data="cap_-5"),
        types.InlineKeyboardButton("➡️ +5px", callback_data="cap_5"),
        types.InlineKeyboardButton("⏩ +30px", callback_data="cap_30")
    )
    kb.add(
        types.InlineKeyboardButton("⏪ -2px", callback_data="cap_-2"),
        types.InlineKeyboardButton("⬅️ -1px", callback_data="cap_-1"),
        types.InlineKeyboardButton("➡️ +1px", callback_data="cap_1"),
        types.InlineKeyboardButton("⏩ +2px", callback_data="cap_2")
    )
    kb.add(types.InlineKeyboardButton(f"🎯 Xác Nhận Thả (Offset: {offset}px)", callback_data="cap_submit"))
    return kb

# --- TELEGRAM HANDLERS ---
@dp.message_handler(commands=['start', 'help'])
async def cmd_start(message: types.Message):
    await message.answer("🤖 CHÀO MỪNG BẠN ĐẾN VỚI BOT REG ACCOUNT AUTOMATION!\n\nVui lòng chọn chức năng dưới thanh điều hướng:", reply_markup=main_keyboard())

@dp.callback_query_handler(lambda c: c.data == "menu_proxy")
async def callback_proxy(call: types.CallbackQuery):
    await BotStates.waiting_for_proxy.set()
    await call.message.answer("🌐 Vui lòng gửi Proxy theo định dạng chuẩn:\n`IP:PORT` hoặc `IP:PORT:USER:PASS`\n\n*(Gửi /cancel nếu muốn hủy bỏ)*", parse_mode="Markdown")
    await call.answer()

@dp.message_handler(state="*", commands=['cancel'])
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.finish()
    await message.answer("❌ Đã hủy thao tác hiện tại.", reply_markup=main_keyboard())

@dp.message_handler(state=BotStates.waiting_for_proxy)
async def process_proxy_input(message: types.Message, state: FSMContext):
    proxy_str = message.text.strip()
    # Kiểm tra cơ bản cấu trúc định dạng
    parts = proxy_str.split(':')
    if len(parts) in [2, 4]:
        await state.update_data(proxy=proxy_str)
        await message.answer(f"✅ Đã lưu Proxy thành công:\n`{proxy_str}`", parse_mode="Markdown", reply_markup=main_keyboard())
        await state.reset_state(with_data=False)
    else:
        await message.answer("⚠️ Định dạng proxy không hợp lệ. Vui lòng nhập lại (IP:PORT hoặc IP:PORT:USER:PASS):")

@dp.callback_query_handler(lambda c: c.data == "menu_check")
async def callback_check_accounts(call: types.CallbackQuery):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, phone, status, created_at FROM accounts ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await call.message.answer("📊 Hiện tại chưa có tài khoản nào được đăng ký trong hệ thống.")
    else:
        msg = "📊 **DANH SÁCH 10 TÀI KHOẢN REG GẦN NHẤT:**\n\n"
        for row in rows:
            msg += f"🆔 ID: {row[0]} | 📱 SĐT: `{row[1]}` | 📌 STT: {row[2]} | 📅 {row[3]}\n"
        await call.message.answer(msg, parse_mode="Markdown")
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "menu_reg")
async def callback_start_reg(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    proxy = user_data.get('proxy')
    
    if not proxy:
        await call.message.answer("❌ Bạn chưa cài đặt Proxy! Vui lòng chọn 'Cài Đặt Proxy' trước khi tiến hành Reg.", reply_markup=main_keyboard())
        await call.answer()
        return

    await call.message.answer("⏳ Đang tiến hành lấy số điện thoại từ ViOTP và khởi chạy trình duyệt ngầm...")
    await call.answer()
    
    # Chạy tác vụ Reg Account trong nền (không làm nghẽn Bot)
    asyncio.create_task(run_registration_flow(call.from_user.id, proxy))

# Xử lý điều hướng giải Captcha trực tiếp từ phím nhấn Telegram
@dp.callback_query_handler(lambda c: c.data.startswith("cap_"))
async def handle_captcha_navigation(call: types.CallbackQuery):
    user_id = call.from_user.id
    session = captcha_manager.get_session(user_id)
    
    if not session or not session['is_active']:
        await call.answer("⚠️ Phiên giải Captcha này đã kết thúc hoặc không tồn tại.", show_alert=True)
        return
        
    action_data = call.data.split('_')[1]
    
    if action_data == 'submit':
        session['action'] = 'submit'
        session['event'].set()
        await call.answer("🚀 Đang gửi lệnh thả mảnh ghép...")
    else:
        move_val = int(action_data)
        session['action'] = 'move'
        session['value'] = move_val
        session['offset_x'] += move_val
        session['event'].set()
        await call.answer(f"Kéo sang {'phải' if move_val > 0 else 'trái'} {abs(move_val)}px")

# --- CORE AUTOMATION FLOW (PLAYWRIGHT + VIOTP) ---
async def fetch_phone_viotp():
    url = f"https://api.viotp.com/request/getv2?token={VIOTP_TOKEN}&serviceId={VIOTP_SERVICE_ID}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            res_json = await response.json()
            if res_json.get('status_code') == 200:
                return res_json['data']['phone_number'], res_json['data']['request_id']
            return None, res_json.get('message', 'Lỗi không xác định')

async def fetch_otp_viotp(request_id):
    url = f"https://api.viotp.com/request/getotp?token={VIOTP_TOKEN}&requestId={request_id}"
    async with aiohttp.ClientSession() as session:
        # Polling lấy OTP trong vòng 60 giây
        for _ in range(12):
            await asyncio.sleep(5)
            async with session.get(url) as response:
                res_json = await response.json()
                if res_json.get('status_code') == 200:
                    status = res_json['data']['Status']
                    if status == 1: # Đã có OTP
                        return res_json['data']['Code']
    return None

async def run_registration_flow(user_id, proxy_str):
    # 1. Thuê số điện thoại
    phone, req_id_or_err = await fetch_phone_viotp()
    if not phone:
        await bot.send_message(user_id, f"❌ Không thể thuê số điện thoại từ ViOTP. Lý do: {req_id_or_err}")
        return
        
    await bot.send_message(user_id, f"📱 Đã thuê được SĐT: `{phone}`\nĐang tiến hành mở trang đăng ký...", parse_mode="Markdown")
    
    # Cấu hình proxy cho Playwright
    proxy_parts = proxy_str.split(':')
    proxy_config = {"server": f"http://{proxy_parts[0]}:{proxy_parts[1]}"}
    if len(proxy_parts) == 4:
        proxy_config["username"] = proxy_parts[2]
        proxy_config["password"] = proxy_parts[3]

    async with async_playwright() as p:
        # Khởi chạy Chromium ở chế độ Headless=True vì chạy trên Render không có màn hình
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            proxy=proxy_config,
            viewport={'width': 375, 'height': 812}, # Giả lập giao diện Mobile để dễ bắt gói và giải Captcha mảnh ghép
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        )
        page = await context.new_page()
        
        try:
            # Truy cập trang Đăng ký tài khoản (Ví dụ mẫu: trang đăng ký Shopee Mobile)
            await page.goto("https://shopee.vn/buyer/signup?next=https%3A%2F%2Fshopee.vn%2F")
            await page.wait_for_timeout(3000)
            
            # Điền số điện thoại vào input field (Cần thay đổi Selector phù hợp với cấu trúc thực tế của web)
            # Selector dưới đây mang tính chất minh họa chuẩn cấu trúc form phổ biến
            phone_input = await page.query_selector("input[type='tel']")
            if phone_input:
                await phone_input.fill(phone)
                await page.wait_for_timeout(1000)
                # Bấm nút Tiếp Tục / Đăng Ký
                btn_next = await page.query_selector("button:has-text('Tiếp theo'), button:has-text('Đăng ký')")
                if btn_next:
                    await btn_next.click()
            
            await page.wait_for_timeout(4000)
            
            # --- KIỂM TRA VÀ XỬ LÝ CAPTCHA MẢNH GHÉP (SLIDER CAPTCHA) ---
            # Tìm Selector của khung chứa Captcha và nút gạt slider
            captcha_box = await page.query_selector(".shopee-captcha-box, .grecaptcha-badge, div[class*='captcha']")
            slider_handle = await page.query_selector(".shopee-slider__handle, div[class*='slider-handle'], div[class*='btn_slide']")
            
            if slider_handle:
                await bot.send_message(user_id, "🧩 Phát hiện Captcha mảnh ghép! Đang thiết lập thanh điều hướng giải tay...")
                
                # Lấy tọa độ ban đầu của thanh trượt để di chuyển chuột
                box = await slider_handle.bounding_box()
                start_x = box['x'] + box['width'] / 2
                start_y = box['y'] + box['height'] / 2
                
                # Di chuyển chuột tới vị trí nút gạt và nhấn giữ xuống
                await page.mouse.move(start_x, start_y)
                await page.mouse.down()
                
                # Khởi tạo phiên tương tác giải captcha trên bot Telegram
                session = captcha_manager.create_session(user_id)
                msg_captcha = None
                
                while session['is_active']:
                    # Chụp hình vùng chứa captcha (Hoặc chụp toàn màn hình thiết bị nếu không định vị được element)
                    captcha_img_path = f"captcha_{user_id}.png"
                    if captcha_box:
                        await captcha_box.screenshot(path=captcha_img_path)
                    else:
                        await page.screenshot(path=captcha_img_path)
                        
                    # Gửi hoặc cập nhật ảnh lên khung chat Telegram
                    with open(captcha_img_path, "rb") as photo:
                        if msg_captcha is None:
                            msg_captcha = await bot.send_photo(
                                user_id, 
                                photo=photo, 
                                caption=f"🔄 Dùng các nút dưới đây để căn chỉnh mảnh ghép vào ô trống thích hợp:", 
                                reply_markup=captcha_keyboard(session['offset_x'])
                            )
                        else:
                            # Cập nhật ảnh mới và thanh điều hướng sau mỗi lượt dịch chuyển pixel
                            media = types.InputMediaPhoto(photo, caption=f"🔄 Dùng các nút dưới đây để căn chỉnh mảnh ghép vào ô trống thích hợp:")
                            await msg_captcha.edit_media(media=media, reply_markup=captcha_keyboard(session['offset_x']))
                    
                    # Xóa file ảnh tạm
                    if os.path.exists(captcha_img_path):
                        os.remove(captcha_img_path)
                        
                    # Chờ người dùng nhấn nút trên Telegram điều khiển
                    await session['event'].wait()
                    session['event'].clear()
                    
                    if session['action'] == 'move':
                        # Di chuyển chuột theo tọa độ offset lũy kế mới
                        await page.mouse.move(start_x + session['offset_x'], start_y)
                        await page.wait_for_timeout(300) # Đợi trình duyệt cập nhật hình ảnh mảnh ghép dịch chuyển
                    elif session['action'] == 'submit':
                        # Nhả chuột ra để xác nhận vị trí mảnh ghép đã khớp
                        await page.mouse.up()
                        captcha_manager.close_session(user_id)
                        await bot.send_message(user_id, "🎯 Đã thả mảnh ghép! Đang kiểm tra kết quả xác thực...")
                        break
            
            await page.wait_for_timeout(4000)
            
            # --- CHỜ VÀ ĐIỀN MÃ OTP TỪ VIOTP ---
            await bot.send_message(user_id, "⏳ Đang lắng nghe hệ thống lấy mã OTP gửi về số điện thoại...")
            otp_code = await fetch_otp_viotp(req_id_or_err)
            
            if not otp_code:
                await bot.send_message(user_id, "❌ Quá thời gian chờ OTP từ nhà mạng hệ thống ViOTP.")
                return
                
            await bot.send_message(user_id, f"🔑 Đã lấy được mã OTP: `{otp_code}`. Tiến hành điền mã...")
            
            # Điền OTP vào ô nhận dạng trên trình duyệt
            otp_input = await page.query_selector("input[type='password'], input[placeholder*='OTP'], input[class*='otp']")
            if otp_input:
                await otp_input.fill(otp_code)
                await page.wait_for_timeout(1000)
                btn_submit_otp = await page.query_selector("button[type='submit'], button:has-text('Xác nhận')")
                if btn_submit_otp:
                    await btn_submit_otp.click()
            
            await page.wait_for_timeout(5000)
            
            # --- LẤY COOKIE VÀ THÔNG TIN TÀI KHOẢN (SPC_F, SPC_T) ---
            cookies = await context.cookies()
            cookies_json = json.dumps(cookies)
            
            spc_f = next((c['value'] for c in cookies if c['name'] == 'SPC_F'), "Không tìm thấy")
            spc_t = next((c['value'] for c in cookies if c['name'] == 'SPC_T'), "Không tìm thấy")
            
            # Lưu tài khoản thành công vào Database SQLite
            password_default = "AccShop2026@" # Mật khẩu mặc định tự tạo cho acc mới
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO accounts (phone, password, cookies, spc_f, spc_t, status) VALUES (?, ?, ?, ?, ?, ?)",
                (phone, password_default, cookies_json, spc_f, spc_t, "Thành Công")
            )
            conn.commit()
            conn.close()
            
            # Xuất kết quả toàn diện ra màn hình Telegram chat
            success_msg = f"🎉 **REG TÀI KHOẢN THÀNH CÔNG!**\n\n" \
                          f"📱 SĐT: `{phone}`\n" \
                          f"🔑 MK: `{password_default}`\n" \
                          f"🌐 SPC_F: `{spc_f}`\n" \
                          f"🌐 SPC_T: `{spc_t}`\n\n" \
                          f"📦 Dữ liệu Cookie đầy đủ đã được lưu trữ an toàn trong DB."
            await bot.send_message(user_id, success_msg, parse_mode="Markdown", reply_markup=main_keyboard())
            
        except Exception as e:
            logging.error(f"Lỗi trong quá trình Reg: {str(e)}")
            await bot.send_message(user_id, f"❌ Quá trình Reg thất bại do xuất hiện lỗi: {str(e)}", reply_markup=main_keyboard())
        finally:
            captcha_manager.close_session(user_id)
            await browser.close()

# --- WEB SERVER BINDING FOR RENDER ---
# Render yêu cầu một Port dịch vụ mở lắng nghe nếu cấu hình Web Service để không bị báo lỗi Deploy Failed.
# Nếu bạn tạo ứng dụng dạng Background Worker thì phần web server này không bắt buộc nhưng vẫn nên giữ để linh hoạt.
async def dummy_web_server():
    from aiohttp import web
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot is running completely on Render!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get('PORT', 8080)))
    await site.start()

if __name__ == '__main__':
    # Khởi chạy dummy web server song song cùng telegram bot polling
    loop = asyncio.get_event_loop()
    loop.create_task(dummy_web_server())
    executor.start_polling(dp, skip_updates=True)
