#!/usr/bin/env bash
# Cập nhật và cài đặt thư viện hệ thống
apt-get update && apt-get install -y libnss3 libnspr4 libatk-1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 librandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2

# Cài đặt Python package và trình duyệt
pip install -r requirements.txt

# Đổi lệnh gọi Playwright qua module Python
python -m playwright install chromium
