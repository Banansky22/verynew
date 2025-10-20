import os
import asyncio

print("🚀 Starting Financial Analyzer Bot...")

# Проверяем токен
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    print("❌ ERROR: TELEGRAM_BOT_TOKEN not set!")
    exit(1)

print("✅ Token found, starting bot...")

# Запускаем основной файл
try:
    from balance_analyzer import main
    asyncio.run(main())
except Exception as e:
    print(f"❌ Failed to start bot: {e}")
    exit(1)
