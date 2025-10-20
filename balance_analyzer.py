import os
import logging
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import pandas as pd
import io
import numpy as np
from datetime import datetime
import re
import json

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получаем токен из переменных окружения
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    print("❌ ОШИБКА: TELEGRAM_BOT_TOKEN не установлен!")
    exit(1)

print("✅ Токен успешно загружен!")
print("🚀 БУХГАЛТЕРСКИЙ АНАЛИЗАТОР ЗАПУЩЕН...")

# Создаем папку для временных файлов
os.makedirs("temp_files", exist_ok=True)

# Состояния для ConversationHandler
SELECT_ANALYSIS, SELECT_INDICATORS, SELECT_INDUSTRY = range(3)

# Расширенный словарь для соответствия названий статей
BALANCE_ITEMS = {
    # АКТИВЫ
    'внеоборотные активы': ['внеоборотные', 'non-current', 'основные средства', 'нематериальные', 'нма'],
    'основные средства': ['основные средства', 'fixed assets', 'property plant', 'основной', 'ося'],
    'нематериальные активы': ['нематериальные', 'intangible', 'нма'],
    'запасы': ['запасы', 'inventories', 'inventory', 'товарно-материальные', 'тмц'],
    'дебиторская задолженность': ['дебиторская', 'accounts receivable', 'receivables', 'дебитор'],
    'денежные средства': ['денежные средства', 'cash', 'cash and equivalents', 'деньги', 'касса', 'расчетный счет'],
    'оборотные активы': ['оборотные активы', 'current assets', 'оборотные'],
    'активы всего': ['активы', 'актив всего', 'total assets', 'итого активы', 'баланс актив'],
    
    # ПАССИВЫ
    'капитал': ['капитал', 'собственный капитал', 'equity', 'share capital', 'уставный'],
    'уставный капитал': ['уставный капитал', 'authorized capital', 'уставной'],
    'нераспределенная прибыль': ['нераспределенная прибыль', 'retained earnings', 'прибыль отчетного года'],
    'долгосрочные обязательства': ['долгосрочные обязательства', 'long-term liabilities', 'долгосрочные'],
    'краткосрочные обязательства': ['краткосрочные обязательства', 'short-term liabilities', 'current liabilities', 'краткосрочные'],
    'кредиты займы': ['кредиты', 'займы', 'loans', 'borrowings', 'кредит'],
    'кредиторская задолженность': ['кредиторская задолженность', 'accounts payable', 'кредиторская'],
    'обязательства всего': ['обязательства', 'пассив всего', 'total liabilities', 'итого пассивы', 'баланс пассив'],
    
    # ОФР
    'выручка': ['выручка', 'revenue', 'sales', 'доход', 'объем продаж'],
    'себестоимость': ['себестоимость', 'cost of sales', 'cost', 'себестоимость продаж'],
    'валовая прибыль': ['валовая прибыль', 'убыток', 'gross profit', 'прибыль валовая'],
    'операционные расходы': ['операционные расходы', 'operating expenses', 'коммерческие расходы', 'управленческие расходы'],
    'прибыль до налогообложения': ['прибыль до налогообложения', 'profit before tax', 'прибыль до налога'],
    'чистая прибыль': ['чистая прибыль', 'net profit', 'net income', 'прибыль чистая']
}

# Отраслевые нормативы
INDUSTRY_STANDARDS = {
    'retail': {
        'name': 'Розничная торговля',
        'standards': {
            'Коэффициент текущей ликвидности': (1.2, 2.0),
            'Коэффициент абсолютной ликвидности': (0.2, 0.5),
            'Рентабельность продаж (ROS)': (3.0, 8.0),
            'Рентабельность активов (ROA)': (5.0, 12.0),
            'Коэффициент автономии': (0.3, 0.6),
            'Оборачиваемость активов': (1.5, 3.0)
        }
    },
    'manufacturing': {
        'name': 'Производство',
        'standards': {
            'Коэффициент текущей ликвидности': (1.5, 2.5),
            'Коэффициент абсолютной ликвидности': (0.1, 0.3),
            'Рентабельность продаж (ROS)': (8.0, 15.0),
            'Рентабельность активов (ROA)': (6.0, 14.0),
            'Коэффициент автономии': (0.4, 0.7),
            'Оборачиваемость активов': (0.8, 1.5)
        }
    },
    'services': {
        'name': 'Сфера услуг',
        'standards': {
            'Коэффициент текущей ликвидности': (1.0, 1.8),
            'Коэффициент абсолютной ликвидности': (0.3, 0.6),
            'Рентабельность продаж (ROS)': (10.0, 20.0),
            'Рентабельность активов (ROA)': (8.0, 18.0),
            'Коэффициент автономии': (0.4, 0.7),
            'Оборачиваемость активов': (1.0, 2.5)
        }
    }
}

# Группы показателей для выборочного анализа
INDICATOR_GROUPS = {
    'Выручка и прибыль': ['выручка', 'чистая прибыль', 'валовая прибыль', 'прибыль до налогообложения'],
    'Активы и обязательства': ['активы всего', 'оборотные активы', 'внеоборотные активы', 'капитал', 'краткосрочные обязательства'],
    'Ликвидность': ['денежные средства', 'дебиторская задолженность', 'запасы'],
    'Рентабельность': ['выручка', 'чистая прибыль', 'активы всего', 'капитал'],
    'Финансовая устойчивость': ['капитал', 'обязательства всего', 'активы всего'],
    'Оборачиваемость': ['выручка', 'запасы', 'дебиторская задолженность', 'активы всего']
}

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

def save_uploaded_file(file_bytes, user_id, file_name):
    """Сохраняет загруженный файл на сервере"""
    try:
        user_dir = f"temp_files/user_{user_id}"
        os.makedirs(user_dir, exist_ok=True)
        
        file_path = os.path.join(user_dir, file_name)
        with open(file_path, 'wb') as f:
            f.write(file_bytes)
        
        return file_path
    except Exception as e:
        print(f"❌ Ошибка сохранения файла: {e}")
        return None

def save_user_data(user_id, data):
    """Сохраняет данные пользователя в файл"""
    try:
        user_dir = f"temp_files/user_{user_id}"
        os.makedirs(user_dir, exist_ok=True)
        
        data_file = os.path.join(user_dir, 'user_data.json')
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")
        return False

def load_user_data_with_fallback(context, user_id):
    """Загружает данные пользователя с возвратом к файловому хранилищу"""
    try:
        # Сначала проверяем, есть ли данные в контексте
        if 'periods_data' in context.user_data and context.user_data['periods_data']:
            return True
        
        # Если нет в контексте, пробуем загрузить из файла
        user_dir = f"temp_files/user_{user_id}"
        data_file = os.path.join(user_dir, 'user_data.json')
        
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
                context.user_data.update(user_data)
            return True
        
        return False
    except Exception as e:
        print(f"❌ Ошибка загрузки данных: {e}")
        return False

async def template_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает шаблон для заполнения"""
    template = """
📋 **ШАБЛОН ОТЧЕТНОСТИ С ПЕРИОДАМИ:**

| Наименование показателя | 31.12.2022 | 31.12.2023 | 31.12.2024 |
|-------------------------|------------|------------|------------|
| Выручка                 | 800,000    | 1,000,000  | 1,200,000  |
| Чистая прибыль          | 150,000    | 200,000    | 250,000    |
| Основные средства       | 450,000    | 500,000    | 550,000    |
| Запасы                  | 120,000    | 150,000    | 180,000    |
| Дебиторская задолженность | 80,000   | 100,000    | 120,000    |
| Денежные средства       | 40,000     | 50,000     | 60,000     |
| Итого активы            | 750,000    | 800,000    | 850,000    |
| Уставный капитал        | 300,000    | 300,000    | 300,000    |
| Нераспределенная прибыль | 120,000   | 200,000    | 250,000    |
| Краткосрочные обязательства | 330,000 | 300,000 | 300,000 |

💡 **Бот понимает различные форматы дат**
"""
    await update.message.reply_text(template)

async def sample_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создает пример файла с периодами для тестирования"""
    sample_data = {
        'Наименование показателя': [
            'Выручка', 
            'Чистая прибыль', 
            'Основные средства', 
            'Запасы',
            'Дебиторская задолженность', 
            'Денежные средства', 
            'Итого активы',
            'Уставный капитал', 
            'Нераспределенная прибыль', 
            'Краткосрочные обязательства'
        ],
        '31.12.2022': [800000, 150000, 450000, 120000, 80000, 40000, 750000, 
                       300000, 120000, 330000],
        '31.12.2023': [1000000, 200000, 500000, 150000, 100000, 50000, 800000,
                       300000, 200000, 300000],
        '31.12.2024': [1200000, 250000, 550000, 180000, 120000, 60000, 850000,
                       300000, 250000, 300000]
    }
    
    df = pd.DataFrame(sample_data)
    
    # Сохраняем в буфер
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Отчетность по периодам', index=False)
    
    buffer.seek(0)
    
    # Отправляем файл
    await update.message.reply_document(
        document=buffer,
        filename='пример_отчетности_с_периодами.xlsx',
        caption='📋 Вот пример файла с отчетами за несколько периодов. Отправьте его боту для анализа динамики!'
    )
    
# === ОСНОВНЫЕ ОБРАБОТЧИКИ КОМАНД ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Улучшенный обработчик команды /start с меню выбора"""
    user_id = update.message.from_user.id
    context.user_data.clear()
    
    keyboard = [
        [KeyboardButton("📊 Полный анализ"), KeyboardButton("🎯 Выборочный анализ")],
        [KeyboardButton("📈 Анализ ликвидности"), KeyboardButton("💎 Анализ рентабельности")],
        [KeyboardButton("🏛️ Финансовая устойчивость"), KeyboardButton("📋 Сравнение с нормативами")],
        [KeyboardButton("🔮 Прогноз тенденций"), KeyboardButton("📄 Экспорт в TXT")],
        [KeyboardButton("ℹ️ Помощь"), KeyboardButton("📁 Загрузить файл")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    
    await update.message.reply_text(
        f"🤖 **ДОБРО ПОЖАЛОВАТЬ В ФИНАНСОВЫЙ АНАЛИЗАТОР!**\n\n"
        f"📊 **Статус:** 📁 Ожидание загрузки файла\n\n"
        f"🎯 **Выберите тип анализа:**\n\n"
        "• 📊 Полный анализ - комплексная оценка всех показателей\n"
        "• 🎯 Выборочный анализ - только нужные вам показатели\n"
        "• 📈 Анализ ликвидности - платежеспособность компании\n"
        "• 💎 Анализ рентабельности - эффективность бизнеса\n"
        "• 🏛️ Финансовая устойчивость - стабильность и риски\n"
        "• 📋 Сравнение с нормативами - отраслевые benchmarks\n"
        "• 🔮 Прогноз тенденций - тренды на будущее\n"
        "• 📄 Экспорт в TXT - отчет в текстовом формате\n\n"
        "📁 **Начните с загрузки файла или выберите анализ**",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
💡 **РАСШИРЕННЫЙ АНАЛИЗ ПО ПЕРИОДАМ**

🎯 **НОВЫЕ ВОЗМОЖНОСТИ:**
• Интерактивное меню выбора анализа
• Выборочный анализ нужных показателей
• Сравнение с отраслевыми нормативами
• Прогнозирование тенденций
• Экспорт отчетов в TXT

📊 **ТИПЫ АНАЛИЗА:**
• 📊 Полный анализ - все показатели
• 🎯 Выборочный анализ - только выбранные группы
• 📈 Ликвидность - платежеспособность
• 💎 Рентабельность - эффективность
• 🏛️ Устойчивость - стабильность
• 📋 Сравнение - отраслевые benchmarks
• 🔮 Прогноз - будущие тренды
• 📄 TXT - текстовый отчет

📁 **ФОРМАТ ФАЙЛА:**
Отправьте Excel файл с столбцами периодов:
• 31.12.2023, 31.12.2022
• На 31 декабря 2023
• За 2023 год, За 2022 год
"""
    await update.message.reply_text(help_text)

async def receive_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик загрузки Excel файлов"""
    try:
        if not update.message.document:
            await update.message.reply_text("📎 Пожалуйста, пришлите Excel файл с отчетностью")
            return

        file = update.message.document
        file_name = file.file_name.lower()

        if not (file_name.endswith('.xlsx') or file_name.endswith('.xls')):
            await update.message.reply_text("❌ Пожалуйста, пришлите файл в формате Excel (.xlsx или .xls)")
            return

        await update.message.reply_text("⏳ Анализирую структуру файла...")

        # Скачиваем файл
        file_obj = await file.get_file()
        file_bytes = await file_obj.download_as_bytearray()

        # Читаем Excel файл
        try:
            df = read_excel_file(file_bytes, file_name)
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка чтения файла: {str(e)}")
            return
        
        # Определяем периоды
        periods = detect_periods(df)
        
        if not periods:
            await update.message.reply_text("❌ Не удалось определить периоды в файле")
            return
        
        # Извлекаем данные по периодам
        periods_data = extract_financial_data_by_period(df, periods)
        
        # Сохраняем данные в контекст пользователя
        context.user_data.update({
            'periods_data': periods_data,
            'file_name': file_name,
            'loaded_at': datetime.now().isoformat()
        })
        
        extracted_count = sum(len(data) for data in periods_data.values())
        await update.message.reply_text(
            f"✅ Файл успешно обработан!\n"
            f"📊 Извлечено показателей: {extracted_count}\n"
            f"📅 Периодов: {len(periods)}\n\n"
            f"🎯 **Теперь выберите тип анализа:**"
        )

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при анализе: {str(e)}")
        logger.error(f"Ошибка в receive_document: {e}")

# === ФУНКЦИИ АНАЛИЗА ДАННЫХ ===

def read_excel_file(file_bytes, file_name):
    """Читает Excel файл с поддержкой разных форматов"""
    try:
        if file_name.endswith('.xls'):
            return pd.read_excel(io.BytesIO(file_bytes), engine='xlrd')
        else:
            return pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl')
    except Exception as e:
        try:
            return pd.read_excel(io.BytesIO(file_bytes))
        except Exception as e2:
            raise Exception(f"Не удалось прочитать файл: {str(e2)}")

def detect_periods(df):
    """Определяет периоды в столбцах DataFrame с правильной сортировкой"""
    periods = []
    
    for col in df.columns:
        col_str = str(col).lower().strip()
        
        # Поиск дат в различных форматах
        date_patterns = [
            r'\d{2}.\d{2}.\d{4}',  # 31.12.2023
            r'\d{4}-\d{2}-\d{2}',   # 2023-12-31
            r'\d{2}/\d{2}/\d{4}',   # 31/12/2023
            r'\d{4}.\d{2}.\d{2}',   # 2023.12.31
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, col_str)
            if matches:
                try:
                    date_str = matches[0]
                    # Приводим к стандартному формату
                    if '.' in date_str and len(date_str.split('.')[0]) == 2:
                        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                    elif '-' in date_str:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    elif '/' in date_str:
                        date_obj = datetime.strptime(date_str, '%d/%m/%Y')
                    else:
                        date_obj = datetime.strptime(date_str, '%Y.%m.%d')
                    
                    periods.append({
                        'column': col,
                        'date': date_obj,
                        'date_str': date_str,
                        'formatted': date_obj.strftime('%d.%m.%Y'),
                        'year': date_obj.year
                    })
                    break
                except:
                    continue
        
        # Поиск периодов в текстовом формате
        period_keywords = {
            'на 31.12': '31.12',
            'на 31.03': '31.03', 
            'на 30.06': '30.06',
            'на 30.09': '30.09',
            'за 2024': '2024',
            'за 2023': '2023',
            'за 2022': '2022',
            '1 квартал': 'Q1',
            '2 квартал': 'Q2',
            '3 квартал': 'Q3',
            '4 квартал': 'Q4'
        }
        
        for keyword, period in period_keywords.items():
            if keyword in col_str:
                year = 2024 if '2024' in col_str else 2023 if '2023' in col_str else 2022
                periods.append({
                    'column': col,
                    'date': datetime(year, 12, 31),
                    'date_str': period,
                    'formatted': f"{period}.{year}",
                    'year': year
                })
                break
    
    # Сортируем периоды по году (от старых к новым)
    periods.sort(key=lambda x: x['year'])
    
    return periods

def find_balance_item(column_name, df_columns):
    """Находит соответствие столбца статьям баланса"""
    column_name = str(column_name).lower().strip()
    
    # Убираем римские цифры и точки в начале
    cleaned_name = re.sub(r'^[ivx]+\.?\s*', '', column_name).strip()
    
    for item, keywords in BALANCE_ITEMS.items():
        for keyword in keywords:
            if keyword in cleaned_name:
                return item
    
    # Дополнительные проверки для сложных случаев
    if 'внеоборотные активы' in column_name:
        return 'внеоборотные активы'
    elif 'нематериальные активы' in column_name:
        return 'нематериальные активы'
    elif 'основные средства' in column_name:
        return 'основные средства'
    elif 'запасы' in column_name:
        return 'запасы'
    elif 'дебиторская' in column_name:
        return 'дебиторская задолженность'
    elif 'денежные средства' in column_name:
        return 'денежные средства'
    elif 'оборотные активы' in column_name:
        return 'оборотные активы'
    elif 'актив' == cleaned_name or 'активы' in cleaned_name:
        return 'активы всего'
    elif 'капитал' in column_name:
        return 'капитал'
    elif 'уставный капитал' in column_name:
        return 'уставный капитал'
    elif 'нераспределенная' in column_name:
        return 'нераспределенная прибыль'
    elif 'долгосрочные' in column_name and 'обязательства' in column_name:
        return 'долгосрочные обязательства'
    elif 'краткосрочные' in column_name and 'обязательства' in column_name:
        return 'краткосрочные обязательства'
    elif 'кредиторская' in column_name:
        return 'кредиторская задолженность'
    elif 'обязательства' == cleaned_name:
        return 'обязательства всего'
    elif 'выручка' in column_name:
        return 'выручка'
    elif 'прибыль' in column_name and 'валовая' in column_name:
        return 'валовая прибыль'
    elif 'прибыль' in column_name and 'чистая' in column_name:
        return 'чистая прибыль'
    elif 'прибыль' in column_name and 'налог' in column_name:
        return 'прибыль до налогообложения'
    
    return None

def extract_financial_data_by_period(df, periods):
    """Извлекает финансовые данные по периодам для структуры с столбцом наименований"""
    financial_data = {}
    
    print(f"🔍 Анализирую {len(periods)} периодов:")
    
    # Инициализируем данные для каждого периода
    for period in periods:
        financial_data[period['formatted']] = {}
    
    # Ищем столбец с наименованиями показателей
    indicator_column = None
    for col in df.columns:
        if 'наименование' in str(col).lower() or 'показатель' in str(col).lower():
            indicator_column = col
            break
    
    if not indicator_column:
        print("❌ Не найден столбец с наименованиями показателей")
        return financial_data
    
    print(f"📋 Столбец с показателями: '{indicator_column}'")
    
    # Проходим по всем строкам и извлекаем данные
    for row_idx in range(len(df)):
        indicator_name = str(df[indicator_column].iloc[row_idx]).strip()
        
        # Пропускаем пустые строки и заголовки
        if not indicator_name or indicator_name in ['Актив', 'Пассив', 'Наименование показателя']:
            continue
        
        # Определяем тип показателя
        item = find_balance_item(indicator_name, [indicator_name])
        
        if item:
            print(f"   📊 Найден показатель: '{indicator_name}' → {item}")
            
            # Извлекаем значения для каждого периода
            for period in periods:
                period_key = period['formatted']
                col_name = period['column']
                
                try:
                    value = pd.to_numeric(df[col_name].iloc[row_idx], errors='coerce')
                    if not pd.isna(value) and value != 0:
                        financial_data[period_key][item] = value
                        print(f"      {period_key}: {value:,.0f}")
                except Exception as e:
                    print(f"      Ошибка извлечения для {period_key}: {e}")
    
    return financial_data

def calculate_financial_ratios_for_period(data):
    """Рассчитывает финансовые коэффициенты для одного периода"""
    ratios = {}
    
    try:
        # Извлекаем данные
        assets = data.get('активы всего', 0)
        current_assets = data.get('оборотные активы', 0)
        cash = data.get('денежные средства', 0)
        receivables = data.get('дебиторская задолженность', 0)
        inventory = data.get('запасы', 0)
        
        # Если нет оборотных активов, но есть их компоненты - рассчитываем
        if current_assets == 0:
            current_assets = cash + receivables + inventory
        
        equity = data.get('капитал', 0)
        current_liabilities = data.get('краткосрочные обязательства', 0)
        total_liabilities = data.get('обязательства всего', 0)
        
        revenue = data.get('выручка', 0)
        net_profit = data.get('чистая прибыль', 0)
        gross_profit = data.get('валовая прибыль', 0)
        
        # 1. КОЭФФИЦИЕНТЫ ЛИКВИДНОСТИ
        if current_liabilities > 0:
            ratios['Коэффициент текущей ликвидности'] = current_assets / current_liabilities
            ratios['Коэффициент абсолютной ликвидности'] = cash / current_liabilities
            if cash + receivables > 0:
                ratios['Коэффициент срочной ликвидности'] = (cash + receivables) / current_liabilities
        
        # 2. РЕНТАБЕЛЬНОСТЬ
        if assets > 0:
            ratios['Рентабельность активов (ROA)'] = (net_profit / assets) * 100
        if equity > 0:
            ratios['Рентабельность капитала (ROE)'] = (net_profit / equity) * 100
        if revenue > 0:
            ratios['Рентабельность продаж (ROS)'] = (net_profit / revenue) * 100
            if gross_profit > 0:
                ratios['Валовая рентабельность'] = (gross_profit / revenue) * 100
        
        # 3. ФИНАНСОВАЯ УСТОЙЧИВОСТЬ
        if assets > 0:
            ratios['Коэффициент автономии'] = equity / assets
            if equity > 0:
                ratios['Коэффициент финансового левериджа'] = total_liabilities / equity
        
        # 4. ДЕЛОВАЯ АКТИВНОСТЬ
        if assets > 0:
            ratios['Оборачиваемость активов'] = revenue / assets
        
    except Exception as e:
        print(f"   ❌ Ошибка расчета коэффициентов: {e}")
    
    return ratios

# === ФУНКЦИИ ГЕНЕРАЦИИ ОТЧЕТОВ ===

def generate_period_analysis_report(periods_data):
    """Генерирует расширенный отчет анализа по периодам"""
    if not periods_data or all(len(data) == 0 for data in periods_data.values()):
        return "❌ Не удалось извлечь данные по периодам."
    
    # Рассчитываем коэффициенты для каждого периода
    periods_ratios = {}
    for period, data in periods_data.items():
        if data:
            periods_ratios[period] = calculate_financial_ratios_for_period(data)
    
    report = "📊 **ФИНАНСОВЫЙ АНАЛИЗ ПО ПЕРИОДАМ**\n\n"
    
    # Основные показатели по периодам
    report += "💰 **ДИНАМИКА ОСНОВНЫХ ПОКАЗАТЕЛЕЙ:**\n\n"
    
    key_indicators = ['выручка', 'чистая прибыль', 'активы всего', 'капитал', 'оборотные активы', 'краткосрочные обязательства']
    
    for indicator in key_indicators:
        values = []
        for period, data in periods_data.items():
            if data and indicator in data:
                values.append((period, data[indicator]))
        
        if values:
            report += f"📈 **{indicator.title()}:**\n"
            for period, value in values:
                report += f"• {period}: {value:,.0f} руб.\n"
            
            # Анализ динамики
            if len(values) >= 2:
                first_period, first_val = values[0]
                last_period, last_val = values[-1]
                change_abs = last_val - first_val
                change_rel = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0
                trend = "📈" if change_rel > 0 else "📉" if change_rel < 0 else "➡️"
                report += f"  {trend} Изменение за период: {change_abs:+,.0f} руб. ({change_rel:+.1f}%)\n"
            
            report += "\n"
    
    # Анализ коэффициентов по периодам
    if any(periods_ratios.values()):
        report += "📊 **ДИНАМИКА ФИНАНСОВЫХ КОЭФФИЦИЕНТОВ:**\n\n"
        
        ratio_categories = {
            '💧 **ЛИКВИДНОСТЬ:**': ['Коэффициент текущей ликвидности', 'Коэффициент абсолютной ликвидности'],
            '🎯 **РЕНТАБЕЛЬНОСТЬ:**': ['Рентабельность активов (ROA)', 'Рентабельность капитала (ROE)', 'Рентабельность продаж (ROS)'],
            '🏛️ **ФИНАНСОВАЯ УСТОЙЧИВОСТЬ:**': ['Коэффициент автономии', 'Коэффициент финансового левериджа'],
            '📈 **ДЕЛОВАЯ АКТИВНОСТЬ:**': ['Оборачиваемость активов']
        }
        
        for category, ratios_list in ratio_categories.items():
            report += f"{category}\n"
            
            category_has_data = False
            for ratio_name in ratios_list:
                if any(ratio_name in ratios for ratios in periods_ratios.values()):
                    category_has_data = True
                    break
            
            if not category_has_data:
                report += "• ❌ Недостаточно данных для расчета\n\n"
                continue
            
            for ratio_name in ratios_list:
                ratio_values = []
                for period, ratios in periods_ratios.items():
                    if ratio_name in ratios:
                        ratio_values.append((period, ratios[ratio_name]))
                
                if ratio_values:
                    report += f"• {ratio_name}:\n"
                    for period, value in ratio_values:
                        if 'рентабельность' in ratio_name.lower():
                            report += f"  {period}: {value:.1f}%\n"
                        else:
                            report += f"  {period}: {value:.2f}\n"
                    
                       # Анализ тренда
                    if len(ratio_values) >= 2:
                        first_val = ratio_values[0][1]
                        last_val = ratio_values[-1][1]
                        change = last_val - first_val
                        
                        if 'ликвидности' in ratio_name:
                            if change > 0.1:
                                report += f"  📈 Улучшение +{change:.2f}\n"
                            elif change < -0.1:
                                report += f"  📉 Ухудшение {change:.2f}\n"
                        
                        elif 'рентабельность' in ratio_name.lower():
                            if change > 1:
                                report += f"  📈 Рост +{change:.1f}п.п.\n"
                            elif change < -1:
                                report += f"  📉 Спад {change:.1f}п.п.\n"
            
            report += "\n"
    else:
        report += "❌ **Не удалось рассчитать финансовые коэффициенты**\n\n"
    
    # Сводные выводы
    report += "💡 **ОБЩИЕ ВЫВОДЫ:**\n\n"
    
    # Анализ динамики выручки
    revenue_data = []
    for period, data in periods_data.items():
        if data and 'выручка' in data:
            revenue_data.append(data['выручка'])
    
    if len(revenue_data) >= 2:
        revenue_growth = ((revenue_data[-1] - revenue_data[0]) / revenue_data[0] * 100) if revenue_data[0] != 0 else 0
        if revenue_growth > 15:
            report += "• 🚀 Высокий рост выручки\n"
        elif revenue_growth > 5:
            report += "• 📈 Умеренный рост бизнеса\n"
        elif revenue_growth > 0:
            report += "• ⚠️ Незначительный рост\n"
        else:
            report += "• ❌ Снижение выручки\n"
    
    # Анализ рентабельности
    last_period = list(periods_ratios.keys())[-1] if periods_ratios else None
    if last_period and last_period in periods_ratios:
        last_ratios = periods_ratios[last_period]
        if 'Рентабельность активов (ROA)' in last_ratios:
            roa = last_ratios['Рентабельность активов (ROA)']
            if roa > 10:
                report += "• 💎 Высокая рентабельность\n"
            elif roa > 5:
                report += "• ✅ Средняя рентабельность\n"
            else:
                report += "• 🔴 Низкая рентабельность\n"
    
    # Рекомендации
    report += "\n💡 **РЕКОМЕНДАЦИИ:**\n"
    report += "• Регулярно отслеживайте динамику ключевых показателей\n"
    report += "• Сравнивайте с отраслевыми нормативами\n"
    report += "• Планируйте мероприятия по улучшению слабых показателей\n"
    
    return report

def generate_liquidity_analysis_report(periods_data):
    """Генерирует отчет по анализу ликвидности"""
    report = "💧 **АНАЛИЗ ЛИКВИДНОСТИ**\n\n"
    
    periods_ratios = {}
    for period, data in periods_data.items():
        if data:
            periods_ratios[period] = calculate_financial_ratios_for_period(data)
    
    # Анализ коэффициентов ликвидности
    liquidity_ratios = ['Коэффициент текущей ликвидности', 'Коэффициент абсолютной ликвидности', 'Коэффициент срочной ликвидности']
    
    for ratio_name in liquidity_ratios:
        ratio_values = []
        for period, ratios in periods_ratios.items():
            if ratio_name in ratios:
                ratio_values.append((period, ratios[ratio_name]))
        
        if ratio_values:
            report += f"**{ratio_name}:**\n"
            for period, value in ratio_values:
                report += f"• {period}: {value:.2f}\n"
                
                # Оценка значения
                if ratio_name == 'Коэффициент текущей ликвидности':
                    if value >= 2.0:
                        report += "  ✅ Отличная ликвидность\n"
                    elif value >= 1.5:
                        report += "  ⚠️ Нормальная ликвидность\n"
                    elif value >= 1.0:
                        report += "  🟡 Пониженная ликвидность\n"
                    else:
                        report += "  ❌ Критическая ликвидность\n"
                
                elif ratio_name == 'Коэффициент абсолютной ликвидности':
                    if value >= 0.2:
                        report += "  ✅ Хорошая абсолютная ликвидность\n"
                    else:
                        report += "  ⚠️ Низкая абсолютная ликвидность\n"
            
            # Анализ тренда
            if len(ratio_values) >= 2:
                first_val = ratio_values[0][1]
                last_val = ratio_values[-1][1]
                change = last_val - first_val
                if change > 0.1:
                    report += f"  📈 Улучшение +{change:.2f}\n"
                elif change < -0.1:
                    report += f"  📉 Ухудшение {change:.2f}\n"
            
            report += "\n"
    
    # Рекомендации по ликвидности
    report += "💡 **РЕКОМЕНДАЦИИ ПО ЛИКВИДНОСТИ:**\n"
    last_period = list(periods_ratios.keys())[-1]
    if last_period in periods_ratios:
        last_ratios = periods_ratios[last_period]
        if 'Коэффициент текущей ликвидности' in last_ratios:
            cr = last_ratios['Коэффициент текущей ликвидности']
            if cr < 1.5:
                report += "• Увеличить объем оборотных активов\n"
                report += "• Сократить краткосрочные обязательства\n"
                report += "• Оптимизировать управление запасами\n"
            else:
                report += "• Ликвидность в норме, поддерживать текущий уровень\n"
    
    return report

def generate_profitability_analysis_report(periods_data):
    """Генерирует отчет по анализу рентабельности"""
    report = "💎 **АНАЛИЗ РЕНТАБЕЛЬНОСТИ**\n\n"
    
    periods_ratios = {}
    for period, data in periods_data.items():
        if data:
            periods_ratios[period] = calculate_financial_ratios_for_period(data)
    
    # Анализ коэффициентов рентабельности
    profitability_ratios = ['Рентабельность продаж (ROS)', 'Рентабельность активов (ROA)', 'Рентабельность капитала (ROE)', 'Валовая рентабельность']
    
    for ratio_name in profitability_ratios:
        ratio_values = []
        for period, ratios in periods_ratios.items():
            if ratio_name in ratios:
                ratio_values.append((period, ratios[ratio_name]))
        
        if ratio_values:
            report += f"**{ratio_name}:**\n"
            for period, value in ratio_values:
                report += f"• {period}: {value:.1f}%\n"
                
                # Оценка значения
                if 'ROA' in ratio_name or 'ROE' in ratio_name:
                    if value >= 15:
                        report += "  🚀 Высокая рентабельность\n"
                    elif value >= 8:
                        report += "  ✅ Хорошая рентабельность\n"
                    elif value >= 5:
                        report += "  ⚠️ Средняя рентабельность\n"
                    else:
                        report += "  ❌ Низкая рентабельность\n"
                elif 'ROS' in ratio_name:
                    if value >= 10:
                        report += "  🚀 Высокая маржа\n"
                    elif value >= 5:
                        report += "  ✅ Хорошая маржа\n"
                    else:
                        report += "  ⚠️ Низкая маржа\n"
            
            # Анализ тренда
            if len(ratio_values) >= 2:
                first_val = ratio_values[0][1]
                last_val = ratio_values[-1][1]
                change = last_val - first_val
                if change > 1:
                    report += f"  📈 Рост +{change:.1f}п.п.\n"
                elif change < -1:
                    report += f"  📉 Спад {change:.1f}п.п.\n"
            
            report += "\n"
    
    # Рекомендации по рентабельности
    report += "💡 **РЕКОМЕНДАЦИИ ПО РЕНТАБЕЛЬНОСТИ:**\n"
    last_period = list(periods_ratios.keys())[-1]
    if last_period in periods_ratios:
        last_ratios = periods_ratios[last_period]
        if 'Рентабельность продаж (ROS)' in last_ratios:
            ros = last_ratios['Рентабельность продаж (ROS)']
            if ros < 10:
                report += "• Повысить цены реализации\n"
                report += "• Снизить себестоимость продаж\n"
                report += "• Оптимизировать операционные расходы\n"
    
    return report

def generate_stability_analysis_report(periods_data):
    """Генерирует отчет по анализу финансовой устойчивости"""
    report = "🏛️ **АНАЛИЗ ФИНАНСОВОЙ УСТОЙЧИВОСТИ**\n\n"
    
    periods_ratios = {}
    for period, data in periods_data.items():
        if data:
            periods_ratios[period] = calculate_financial_ratios_for_period(data)
    
    # Анализ коэффициентов устойчивости
    stability_ratios = ['Коэффициент автономии', 'Коэффициент финансового левериджа']
    
    for ratio_name in stability_ratios:
        ratio_values = []
        for period, ratios in periods_ratios.items():
            if ratio_name in ratios:
                ratio_values.append((period, ratios[ratio_name]))
        
        if ratio_values:
            report += f"**{ratio_name}:**\n"
            for period, value in ratio_values:
                if ratio_name == 'Коэффициент автономии':
                    report += f"• {period}: {value:.2f}\n"
                    if value >= 0.5:
                        report += "  ✅ Высокая автономия\n"
                    elif value >= 0.3:
                        report += "  ⚠️ Средняя автономия\n"
                    else:
                        report += "  ❌ Низкая автономия\n"
                else:  # Леверидж
                    report += f"• {period}: {value:.2f}\n"
                    if value <= 1.0:
                        report += "  ✅ Низкий леверидж\n"
                    elif value <= 2.0:
                        report += "  ⚠️ Умеренный леверидж\n"
                    else:
                        report += "  ❌ Высокий леверидж\n"
            
            report += "\n"
    
    # Рекомендации по устойчивости
    report += "💡 **РЕКОМЕНДАЦИИ ПО УСТОЙЧИВОСТИ:**\n"
    last_period = list(periods_ratios.keys())[-1]
    if last_period in periods_ratios:
        last_ratios = periods_ratios[last_period]
        if 'Коэффициент автономии' in last_ratios:
            autonomy = last_ratios['Коэффициент автономии']
            if autonomy < 0.5:
                report += "• Увеличить собственный капитал\n"
                report += "• Реинвестировать прибыль\n"
                report += "• Сократить зависимость от заемных средств\n"
    
    return report

def generate_forecast_report(periods_data):
    """Генерирует отчет с прогнозами"""
    report = "🔮 **ПРОГНОЗ ФИНАНСОВЫХ ТЕНДЕНЦИЙ**\n\n"
    
    # Анализ трендов ключевых показателей
    key_indicators = ['выручка', 'чистая прибыль', 'активы всего', 'капитал']
    
    for indicator in key_indicators:
        values = []
        periods_list = []
        
        for period, data in periods_data.items():
            if data and indicator in data:
                values.append(data[indicator])
                periods_list.append(period)
        
        if len(values) >= 2:
            # Простой линейный прогноз
            growth_rate = (values[-1] - values[0]) / values[0] if values[0] != 0 else 0
            forecast_value = values[-1] * (1 + growth_rate)
            
            report += f"📈 **{indicator.title()}:**\n"
            report += f"• Исторический рост: {growth_rate*100:+.1f}%\n"
            report += f"• Прогноз на след. период: {forecast_value:,.0f} руб.\n"
            
            if growth_rate > 0.1:
                report += "• 🚀 Высокие темпы роста\n"
            elif growth_rate > 0.05:
                report += "• 📈 Умеренный рост\n"
            elif growth_rate > 0:
                report += "• ⚠️ Незначительный рост\n"
            else:
                report += "• 📉 Снижение показателя\n"
            
            report += "\n"
    
    # Прогноз финансовых коэффициентов
    report += "📊 **ПРОГНОЗ КОЭФФИЦИЕНТОВ:**\n\n"
    
    periods_ratios = {}
    for period, data in periods_data.items():
        if data:
            periods_ratios[period] = calculate_financial_ratios_for_period(data)
    
    key_ratios = ['Коэффициент текущей ликвидности', 'Рентабельность продаж (ROS)', 'Коэффициент автономии']
    
    for ratio_name in key_ratios:
        ratio_values = []
        for period, ratios in periods_ratios.items():
            if ratio_name in ratios:
                ratio_values.append(ratios[ratio_name])
        
        if len(ratio_values) >= 2:
            current_value = ratio_values[-1]
            avg_growth = (ratio_values[-1] - ratio_values[0]) / len(ratio_values) if len(ratio_values) > 1 else 0
            
            if ratio_name == 'Рентабельность продаж (ROS)':
                forecast_value = current_value + avg_growth
                report += f"**{ratio_name}:** {current_value:.1f}% → прогноз: {forecast_value:.1f}%\n"
            else:
                forecast_value = current_value + avg_growth
                report += f"**{ratio_name}:** {current_value:.2f} → прогноз: {forecast_value:.2f}\n"
            
            report += "\n"
    
    # Общие выводы и рекомендации
    report += "💡 **СТРАТЕГИЧЕСКИЕ РЕКОМЕНДАЦИИ:**\n"
    
    # Анализ общего тренда
    revenue_values = []
    for period, data in periods_data.items():
        if data and 'выручка' in data:
            revenue_values.append(data['выручка'])
    
    if len(revenue_values) >= 2:
        overall_growth = (revenue_values[-1] - revenue_values[0]) / revenue_values[0] if revenue_values[0] != 0 else 0
        
        if overall_growth > 0.15:
            report += "• 🚀 Компания в стадии активного роста\n"
            report += "• Рассмотреть возможности для инвестирования\n"
        elif overall_growth > 0.05:
            report += "• 📈 Стабильное развитие бизнеса\n"
            report += "• Продолжать текущую стратегию\n"
        else:
            report += "• ⚠️ Требуется пересмотр бизнес-модели\n"
            report += "• Искать новые источники роста\n"
    
    return report

def generate_selective_analysis_report(periods_data, selected_groups):
    """Генерирует отчет для выборочного анализа"""
    report = f"🎯 **ВЫБОРОЧНЫЙ АНАЛИЗ**\n\n"
    report += f"📋 **Выбранные группы:** {', '.join(selected_groups)}\n\n"
    
    # Основные показатели по выбранным группам
    for group in selected_groups:
        report += f"📊 **{group.upper()}:**\n"
        indicators = INDICATOR_GROUPS.get(group, [])
        
        for indicator in indicators:
            values = []
            for period, data in periods_data.items():
                if data and indicator in data:
                    values.append((period, data[indicator]))
            
            if values:
                report += f"• {indicator.title()}:\n"
                for period, value in values:
                    report += f"  {period}: {value:,.0f} руб.\n"
                
                # Анализ динамики
                if len(values) >= 2:
                    first_val = values[0][1]
                    last_val = values[-1][1]
                    change_abs = last_val - first_val
                    change_rel = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0
                    trend = "📈" if change_rel > 0 else "📉" if change_rel < 0 else "➡️"
                    report += f"  {trend} Изменение: {change_abs:+,.0f} руб. ({change_rel:+.1f}%)\n"
                
                report += "\n"
    
    return report

def generate_industry_comparison_report(ratios, industry_data, period):
    """Генерирует отчет сравнения с отраслевыми нормативами"""
    report = f"🏭 **СРАВНЕНИЕ С ОТРАСЛЕВЫМИ НОРМАТИВАМИ**\n\n"
    report += f"📊 Отрасль: **{industry_data['name']}**\n"
    report += f"📅 Период: {period}\n\n"
    
    standards = industry_data['standards']
    
    for ratio_name, (min_std, max_std) in standards.items():
        if ratio_name in ratios:
            value = ratios[ratio_name]
            report += f"**{ratio_name}:** {value:.2f}\n"
            
            if value < min_std:
                report += f"❌ **НИЖЕ НОРМЫ** (норма: {min_std:.1f}-{max_std:.1f})\n"
                if ratio_name == 'Коэффициент текущей ликвидности':
                    report += "   💡 Рекомендация: увеличить оборотные активы\n"
                elif 'рентабельность' in ratio_name.lower():
                    report += "   💡 Рекомендация: оптимизировать затраты\n"
            elif value > max_std:
                report += f"⚠️ **ВЫШЕ НОРМЫ** (норма: {min_std:.1f}-{max_std:.1f})\n"
                if ratio_name == 'Коэффициент текущей ликвидности':
                    report += "   💡 Возможно избыточная ликвидность\n"
            else:
                report += f"✅ **В НОРМЕ** (норма: {min_std:.1f}-{max_std:.1f})\n"
            
            report += "\n"
        else:
            report += f"**{ratio_name}:** ❌ нет данных\n\n"
    
    # Общая оценка
    matching_standards = sum(1 for ratio_name in standards if ratio_name in ratios and 
                           min_std <= ratios[ratio_name] <= max_std)
    total_comparable = sum(1 for ratio_name in standards if ratio_name in ratios)
    
    if total_comparable > 0:
        compliance_rate = (matching_standards / total_comparable) * 100
        report += f"📈 **СООТВЕТСТВИЕ НОРМАТИВАМ:** {compliance_rate:.1f}%\n\n"
        
        if compliance_rate >= 80:
            report += "🎉 **Отличное соответствие** отраслевым нормативам!\n"
        elif compliance_rate >= 60:
            report += "✅ **Хорошее соответствие** большинству нормативов\n"
        elif compliance_rate >= 40:
            report += "⚠️ **Среднее соответствие**, есть области для улучшения\n"
        else:
            report += "❌ **Низкое соответствие**, требуется оптимизация\n"
    
    return report

# === ОСНОВНЫЕ ФУНКЦИИ АНАЛИЗА ===

async def perform_full_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполнение полного анализа"""
    user_id = update.message.from_user.id
    
    # Загружаем данные с возвратом к файловому хранилищу
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    await update.message.reply_text("🔍 Выполняю полный финансовый анализ...")
    
    periods_data = context.user_data['periods_data']
    report = generate_period_analysis_report(periods_data)
    
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = "полный анализ"
    
    if len(report) > 4000:
        parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(report)
    
    await update.message.reply_text("✅ Полный анализ завершен!")

async def perform_liquidity_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ ликвидности"""
    user_id = update.message.from_user.id
    
    # Загружаем данные с возвратом к файловому хранилищу
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    await update.message.reply_text("💧 Анализирую ликвидность...")
    
    periods_data = context.user_data['periods_data']
    report = generate_liquidity_analysis_report(periods_data)
    
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = "анализ ликвидности"
    
    await update.message.reply_text(report)

async def perform_profitability_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ рентабельности"""
    user_id = update.message.from_user.id
    
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    await update.message.reply_text("💎 Анализирую рентабельность...")
    
    periods_data = context.user_data['periods_data']
    report = generate_profitability_analysis_report(periods_data)
    
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = "анализ рентабельности"
    
    await update.message.reply_text(report)

async def perform_stability_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Анализ финансовой устойчивости"""
    user_id = update.message.from_user.id
    
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    await update.message.reply_text("🏛️ Анализирую финансовую устойчивость...")
    
    periods_data = context.user_data['periods_data']
    report = generate_stability_analysis_report(periods_data)
    
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = "анализ финансовой устойчивости"
    
    await update.message.reply_text(report)

async def perform_forecast_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Прогнозирование тенденций"""
    user_id = update.message.from_user.id
    
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    await update.message.reply_text("🔮 Анализирую тенденции и строю прогноз...")
    
    periods_data = context.user_data['periods_data']
    report = generate_forecast_report(periods_data)
    
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = "прогноз тенденций"
    
    await update.message.reply_text(report)

# === ФУНКЦИИ ВЫБОРОЧНОГО АНАЛИЗА ===

async def selective_analysis_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало выборочного анализа"""
    user_id = update.message.from_user.id
    
    # Загружаем данные с возвратом к файловому хранилищу
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    keyboard = [
        [KeyboardButton("Выручка и прибыль"), KeyboardButton("Активы и обязательства")],
        [KeyboardButton("Ликвидность"), KeyboardButton("Рентабельность")],
        [KeyboardButton("Финансовая устойчивость"), KeyboardButton("Оборачиваемость")],
        [KeyboardButton("✅ Начать выборочный анализ"), KeyboardButton("🔙 Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    context.user_data['selected_groups'] = set()
    
    await update.message.reply_text(
        "🎯 **ВЫБОРОЧНЫЙ АНАЛИЗ**\n\n"
        "Выберите группы показателей для анализа:\n\n"
        "• 📈 Выручка и прибыль - динамика доходов\n"
        "• 💼 Активы и обязательства - структура баланса\n"
        "• 💧 Ликвидность - платежеспособность\n"
        "• 💎 Рентабельность - эффективность\n"
        "• 🏛️ Финансовая устойчивость - стабильность\n"
        "• 📊 Оборачиваемость - деловая активность\n\n"
        "✅ Выберите нужные группы и нажмите 'Начать выборочный анализ'",
        reply_markup=reply_markup
    )
    return SELECT_INDICATORS

async def handle_indicator_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора групп показателей"""
    selected_group = update.message.text
    selected_groups = context.user_data.get('selected_groups', set())
    
    if selected_group in selected_groups:
        selected_groups.remove(selected_group)
        status = "❌ Убрано"
    else:
        selected_groups.add(selected_group)
        status = "✅ Выбрано"
    
    context.user_data['selected_groups'] = selected_groups
    
    # Обновляем клавиатуру с отметками выбранных групп
    keyboard = [
        [KeyboardButton(f"{'✅ ' if 'Выручка и прибыль' in selected_groups else ''}Выручка и прибыль"), 
         KeyboardButton(f"{'✅ ' if 'Активы и обязательства' in selected_groups else ''}Активы и обязательства")],
        [KeyboardButton(f"{'✅ ' if 'Ликвидность' in selected_groups else ''}Ликвидность"), 
         KeyboardButton(f"{'✅ ' if 'Рентабельность' in selected_groups else ''}Рентабельность")],
        [KeyboardButton(f"{'✅ ' if 'Финансовая устойчивость' in selected_groups else ''}Финансовая устойчивость"), 
         KeyboardButton(f"{'✅ ' if 'Оборачиваемость' in selected_groups else ''}Оборачиваемость")],
        [KeyboardButton("✅ Начать выборочный анализ"), KeyboardButton("🔙 Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    groups_list = "\n".join([f"• {group}" for group in selected_groups]) if selected_groups else "❌ Не выбрано"
    
    await update.message.reply_text(
        f"🎯 **Выбрано групп: {len(selected_groups)}**\n\n"
        f"{groups_list}\n\n"
        f"Последнее действие: {selected_group} - {status}",
        reply_markup=reply_markup
    )
    return SELECT_INDICATORS

async def start_selective_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск выборочного анализа"""
    selected_groups = context.user_data.get('selected_groups', set())
    
    if not selected_groups:
        await update.message.reply_text("❌ Выберите хотя бы одну группу показателей")
        return SELECT_INDICATORS
    
    await update.message.reply_text("🔍 Выполняю выборочный анализ...")
    
    periods_data = context.user_data['periods_data']
    analysis_type = "выборочный"
    
    # Фильтруем данные по выбранным группам
    filtered_periods_data = {}
    for period, data in periods_data.items():
        filtered_data = {}
        for group in selected_groups:
            indicators = INDICATOR_GROUPS.get(group, [])
            for indicator in indicators:
                if indicator in data:
                    filtered_data[indicator] = data[indicator]
        filtered_periods_data[period] = filtered_data
    
    # Генерируем отчет
    report = generate_selective_analysis_report(filtered_periods_data, selected_groups)
    
    # Сохраняем для возможного экспорта в TXT
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = analysis_type
    
    # Отправляем отчет
    if len(report) > 4000:
        parts = [report[i:i+4000] for i in range(0, len(report), 4000)]
        for part in parts:
            await update.message.reply_text(part)
    else:
        await update.message.reply_text(report)
    
    await update.message.reply_text("✅ Выборочный анализ завершен!")
    await start(update, context)
    return ConversationHandler.END

# === ФУНКЦИИ СРАВНЕНИЯ С НОРМАТИВАМИ ===

async def industry_comparison_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало сравнения с отраслевыми нормативами"""
    user_id = update.message.from_user.id
    
    if not load_user_data_with_fallback(context, user_id):
        await update.message.reply_text("❌ Сначала загрузите файл с данными")
        return
    
    keyboard = [
        [KeyboardButton("Розничная торговля"), KeyboardButton("Производство")],
        [KeyboardButton("Сфера услуг"), KeyboardButton("🔙 Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🏭 **СРАВНЕНИЕ С ОТРАСЛЕВЫМИ НОРМАТИВАМИ**\n\n"
        "Выберите отрасль для сравнения:\n\n"
        "• 🛒 Розничная торговля\n"
        "• 🏭 Производство\n"
        "• 💼 Сфера услуг\n\n"
        "Бот сравнит ваши показатели с отраслевыми benchmarks",
        reply_markup=reply_markup
    )
    return SELECT_INDUSTRY

async def handle_industry_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора отрасли для сравнения"""
    industry_map = {
        "Розничная торговля": "retail",
        "Производство": "manufacturing", 
        "Сфера услуг": "services"
    }
    
    selected_industry = industry_map.get(update.message.text)
    if not selected_industry:
        await update.message.reply_text("❌ Пожалуйста, выберите отрасль из предложенных")
        return SELECT_INDUSTRY
    
    await update.message.reply_text(f"🔍 Сравниваю с нормативами для {update.message.text}...")
    
    periods_data = context.user_data['periods_data']
    industry_data = INDUSTRY_STANDARDS[selected_industry]
    
    # Рассчитываем коэффициенты для последнего периода
    last_period = list(periods_data.keys())[-1]
    last_data = periods_data[last_period]
    ratios = calculate_financial_ratios_for_period(last_data)
    
    # Генерируем отчет сравнения
    report = generate_industry_comparison_report(ratios, industry_data, last_period)
    
    # Сохраняем для TXT
    context.user_data['last_analysis'] = report
    context.user_data['analysis_type'] = f"сравнение с {industry_data['name']}"
    
    await update.message.reply_text(report)
    await start(update, context)
    return ConversationHandler.END

# === ФУНКЦИЯ ЭКСПОРТА В TXT ===

async def export_to_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Экспорт анализа в TXT файл"""
    if 'last_analysis' not in context.user_data:
        await update.message.reply_text("❌ Сначала выполните анализ данных")
        return
    
    await update.message.reply_text("📄 Создаю текстовый отчет...")
    
    try:
        analysis_text = context.user_data['last_analysis']
        analysis_type = context.user_data.get('analysis_type', 'Анализ')
        
        # Создаем TXT файл в памяти
        buffer = io.BytesIO()
        
        # Заголовок
        header = f"ФИНАНСОВЫЙ АНАЛИЗ - {analysis_type.upper()}\n"
        header += "=" * 50 + "\n"
        header += f"Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        
        # Записываем в буфер
        buffer.write(header.encode('utf-8'))
        buffer.write(analysis_text.encode('utf-8'))
        
        buffer.seek(0)
        
        # Отправляем файл
        await update.message.reply_document(
            document=buffer,
            filename=f'финансовый_анализ_{datetime.now().strftime("%Y%m%d_%H%M")}.txt',
            caption=f'📊 Ваш финансовый анализ ({analysis_type}) в текстовом формате'
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка создания файла: {str(e)}")

# === ОБРАБОТЧИК СООБЩЕНИЙ ===

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений с кнопок"""
    text = update.message.text
    
    if text == "📊 Полный анализ":
        await perform_full_analysis(update, context)
    elif text == "🎯 Выборочный анализ":
        await selective_analysis_start(update, context)
    elif text == "📈 Анализ ликвидности":
        await perform_liquidity_analysis(update, context)
    elif text == "💎 Анализ рентабельности":
        await perform_profitability_analysis(update, context)
    elif text == "🏛️ Финансовая устойчивость":
        await perform_stability_analysis(update, context)
    elif text == "📋 Сравнение с нормативами":
        await industry_comparison_start(update, context)
    elif text == "🔮 Прогноз тенденций":
        await perform_forecast_analysis(update, context)
    elif text == "📄 Экспорт в TXT":
        await export_to_txt(update, context)
    elif text == "📁 Загрузить файл":
        await update.message.reply_text("📎 Пожалуйста, загрузите Excel файл с отчетностью")
    elif text == "ℹ️ Помощь":
        await help_command(update, context)
    elif text == "🔙 Назад":
        await start(update, context)

def setup_application():
    """Настраивает и возвращает приложение"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("template", template_command))
    application.add_handler(CommandHandler("sample", sample_command))
    
    # Обработчик документов (Excel файлов)
    application.add_handler(MessageHandler(filters.Document.ALL, receive_document))
    
    # Обработчик текстовых сообщений (кнопки)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # ConversationHandler для выборочного анализа
    selective_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(🎯 Выборочный анализ)$"), selective_analysis_start)],
        states={
            SELECT_INDICATORS: [
                MessageHandler(filters.Regex("^(Выручка и прибыль|Активы и обязательства|Ликвидность|Рентабельность|Финансовая устойчивость|Оборачиваемость)$"), 
                             handle_indicator_selection),
                MessageHandler(filters.Regex("^(✅ Начать выборочный анализ)$"), start_selective_analysis),
                MessageHandler(filters.Regex("^(🔙 Назад)$"), start)
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^(🔙 Назад)$"), start)]
    )
    application.add_handler(selective_conv_handler)
    
    # ConversationHandler для сравнения с нормативами
    industry_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(📋 Сравнение с нормативами)$"), industry_comparison_start)],
        states={
            SELECT_INDUSTRY: [
                MessageHandler(filters.Regex("^(Розничная торговля|Производство|Сфера услуг)$"), handle_industry_selection),
                MessageHandler(filters.Regex("^(🔙 Назад)$"), start)
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^(🔙 Назад)$"), start)]
    )
    application.add_handler(industry_conv_handler)
    
    return application

async def main():
    """Основная асинхронная функция"""
    print("🔧 Инициализация бота...")
    
    # Настраиваем приложение
    application = setup_application()
    
    print("✅ УЛУЧШЕННЫЙ БУХГАЛТЕРСКИЙ АНАЛИЗАТОР ЗАПУЩЕН!")
    print("🎯 Доступны функции:")
    print("   • Интерактивное меню")
    print("   • Выборочный анализ") 
    print("   • Сравнение с нормативами")
    print("   • Прогнозирование тенденций")
    print("   • Экспорт в TXT")
    print("   • Специализированные анализы")
    print("   • Полный финансовый анализ")
    print("🌐 Режим: POLLING")
    print("🚀 Бот готов к работе!")
    
    # Запускаем бота в режиме polling
    await application.run_polling()

# === ЗАПУСК ПРИЛОЖЕНИЯ ===
if __name__ == '__main__':
    try:
        # Запускаем асинхронную main функцию
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
