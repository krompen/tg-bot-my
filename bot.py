import asyncio
import aiosqlite
import logging
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8174433113:AAGsCNLWDI_j8qIi4JI4Bqt2uLuAjO2QM30"
OWNER_ID = 8032626504
DB_NAME = "max_teqqines_bot.db"
GROUP_ID = -1003913420195  # если нужна подписка на группу

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ==================== БАЗА ДАННЫХ ====================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Пользователи
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                balance REAL DEFAULT 0,
                total_earned REAL DEFAULT 0,
                status TEXT DEFAULT 'user',
                slots INTEGER DEFAULT 8,
                is_banned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Номера (основная таблица)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                phone TEXT,
                tariff REAL,
                status TEXT DEFAULT 'в_очереди',
                taken_by INTEGER,
                taken_at TEXT,
                code TEXT,
                verdict TEXT,
                paid INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_confirmation TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Логи действий (сброс каждый день)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                user_id INTEGER,
                action_type TEXT,
                details TEXT,
                emoji TEXT
            )
        """)

        # Тикеты поддержки (из старого кода)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                status TEXT DEFAULT 'open',
                priority INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER,
                user_id INTEGER,
                message TEXT,
                is_admin INTEGER DEFAULT 0,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()
        logger.info("✅ База данных инициализирована")


async def get_number_by_id(num_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM numbers WHERE id = ?", (num_id,))
        return await cursor.fetchone()


async def update_number_status(num_id: int, status: str, **kwargs):
    async with aiosqlite.connect(DB_NAME) as db:
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [num_id]
        await db.execute(f"UPDATE numbers SET status = ?, {set_clause} WHERE id = ?", [status] + values)
        await db.commit()


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================
async def background_tasks():
    while True:
        # Сброс логов каждый день в 00:00
        now = datetime.now()
        if now.hour == 0 and now.minute == 0:
            await clear_daily_logs()
        
        # Проверка подтверждения присутствия (каждые 5 минут)
        await check_presence_confirmations()
        await asyncio.sleep(300)  # 5 минут


async def check_presence_confirmations():
    """Удаляет номера, если пользователь не подтвердил присутствие за 5 минут"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT id, user_id, phone FROM numbers 
            WHERE status IN ('в_очереди', 'онлайн') 
            AND datetime(last_confirmation) < datetime('now', '-5 minutes')
            AND last_confirmation IS NOT NULL
        """)
        to_remove = await cursor.fetchall()

        for num_id, user_id, phone in to_remove:
            await db.execute("UPDATE numbers SET status='удален_по_таймауту' WHERE id=?", (num_id,))
            try:
                await bot.send_message(user_id, f"❌ Номер {phone} удалён из очереди (не подтверждал присутствие 5 минут)")
            except:
                pass
            await log_action(user_id, "timeout_remove", f"Номер #{num_id} удалён по таймауту", "⏰")
        await db.commit()


async def log_action(user_id: int, action_type: str, details: str, emoji: str = "📝"):
    """Логирование всех важных действий"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO action_logs (user_id, action_type, details, emoji) VALUES (?, ?, ?, ?)",
            (user_id, action_type, details, emoji)
        )
        await db.commit()
    logger.info(f"{emoji} {action_type} | user_id={user_id} | {details}")


async def clear_daily_logs():
    """Сброс логов после каждого рабочего дня (в 00:00)"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM action_logs")
        await db.commit()
    logger.info("🗑 Логи за день очищены")


# ==================== FSM ====================
class SubmitNumberState(StatesGroup):
    choosing_tariff = State()
    entering_numbers = State()

class OperatorState(StatesGroup):
    viewing_queue = State()
    taking_number = State()
    waiting_verdict = State()

# ==================== МЕНЮ ====================
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📱 Сдать аккаунт", callback_data="submit_number")],
        [InlineKeyboardButton(text="📡 MAX | QR code", callback_data="max_qr"),
         InlineKeyboardButton(text="⏳ В очереди", callback_data="queue_menu")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
         InlineKeyboardButton(text="💰 Вывод средств", callback_data="withdraw")],
        [InlineKeyboardButton(text="📁 Архив", callback_data="archive"),
         InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions")],
        [InlineKeyboardButton(text="💸 Выплаты", callback_data="payouts"),
         InlineKeyboardButton(text="🛠 Техподдержка", callback_data="support")]
    ])


# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start(message: Message):
    user = await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
        "✨ <b>Добро пожаловать в Max teqqines bot</b> ✨\n\n"
        "Здесь ты сдаёшь номера Максу и зарабатываешь.\n"
        "Выбирай действие ниже:",
        reply_markup=main_menu()
    )
    await log_action(message.from_user.id, "start_bot", "Пользователь запустил бота", "🚀")


async def get_or_create_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = await cursor.fetchone()
        if not user:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username or "", first_name or "")
            )
            await db.commit()
            await log_action(user_id, "new_user", f"Зарегистрирован новый пользователь @{username}", "👤")
        return user


@dp.callback_query(F.data == "submit_number")
async def submit_number_start(callback: CallbackQuery, state: FSMContext):
    text = (
        "📱 <b>Сдача номера</b>\n\n"
        "Выбери тариф:\n\n"
        "🔹 <b>Обычная очередь</b> — 4$\n"
        "🔹 <b>Без очереди</b> — 3.5$ (приоритет)"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обычная очередь (4$)", callback_data="tariff_normal")],
        [InlineKeyboardButton(text="Без очереди (3.5$)", callback_data="tariff_priority")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)
    await state.set_state(SubmitNumberState.choosing_tariff)


@dp.callback_query(F.data.startswith("tariff_"))
async def choose_tariff(callback: CallbackQuery, state: FSMContext):
    tariff = 4.0 if callback.data == "tariff_normal" else 3.5
    await state.update_data(tariff=tariff)
    await state.set_state(SubmitNumberState.entering_numbers)
    
    text = (
        f"✅ Тариф выбран: <b>{tariff}$</b>\n\n"
        "Теперь отправь номер(а) в формате:\n"
        "<code>+79121234567</code>\n\n"
        "Можно до 5 номеров (по одному на строку).\n"
        "Чтобы выйти — напиши /done"
    )
    await callback.message.edit_text(text)


@dp.message(SubmitNumberState.entering_numbers)
async def process_numbers(message: Message, state: FSMContext):
    if message.text == "/done":
        await state.clear()
        await message.answer("✅ Вы вышли из режима сдачи номеров.", reply_markup=main_menu())
        return

    data = await state.get_data()
    tariff = data.get("tariff", 4.0)
    numbers = [n.strip() for n in message.text.split("\n") if n.strip()][:5]

    async with aiosqlite.connect(DB_NAME) as db:
        for phone in numbers:
            await db.execute(
                "INSERT INTO numbers (user_id, phone, tariff, status) VALUES (?, ?, ?, 'в_очереди')",
                (message.from_user.id, phone, tariff)
            )
        await db.commit()

    await message.answer(f"✅ Добавлено {len(numbers)} номер(ов) в очередь по тарифу {tariff}$")
    await log_action(message.from_user.id, "submit_numbers", f"Добавлено {len(numbers)} номеров по {tariff}$", "📱")
    await state.clear()


# ==================== ОПЕРАТОРСКАЯ ПАНЕЛЬ ====================
@dp.message(Command("operator"))
async def operator_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("🚫 Доступ только для оператора.")
    
    text = "🛠 <b>Панель оператора</b>\n\nВыбери действие:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Посмотреть очередь", callback_data="operator_queue")],
        [InlineKeyboardButton(text="📊 Статистика за сегодня", callback_data="operator_stats")],
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "operator_queue")
async def show_operator_queue(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, phone, tariff, user_id FROM numbers WHERE status = 'в_очереди' ORDER BY created_at LIMIT 20"
        )
        numbers = await cursor.fetchall()

    if not numbers:
        return await callback.message.edit_text("📭 Очередь пуста.")

    text = "📋 <b>Очередь номеров</b>\n\n"
    keyboard_buttons = []
    for num_id, phone, tariff, user_id in numbers:
        text += f"#{num_id} | {phone} | {tariff}$ | user:{user_id}\n"
        keyboard_buttons.append([InlineKeyboardButton(text=f"Взять #{num_id}", callback_data=f"take_{num_id}")])

    keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="operator_panel")])
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons))


@dp.callback_query(F.data.startswith("take_"))
async def take_number(callback: CallbackQuery):
    num_id = int(callback.data.split("_")[1])
    operator_id = callback.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE numbers SET status='в_обработке', taken_by=?, taken_at=? WHERE id=?",
            (operator_id, datetime.now().isoformat(), num_id)
        )
        await db.commit()

        cursor = await db.execute("SELECT user_id, phone, tariff FROM numbers WHERE id=?", (num_id,))
        row = await cursor.fetchone()

    if row:
        user_id, phone, tariff = row
        await bot.send_message(
            user_id,
            f"📲 <b>Ваш номер взяли!</b>\n\n"
            f"Номер: <code>{phone}</code>\n"
            f"ID: #{num_id}\n\n"
            "Подтверди, что ты на связи:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить я тут", callback_data=f"confirm_{num_id}")],
                [InlineKeyboardButton(text="❌ Номер недействителен (скип)", callback_data=f"skip_{num_id}")]
            ])
        )
        await log_action(operator_id, "take_number", f"Взял номер #{num_id} ({phone}) у пользователя {user_id}", "📥")

    await callback.message.edit_text(f"✅ Номер #{num_id} взят в работу.")


# ==================== ВЕРДИКТ ОПЕРАТОРА ====================
@dp.callback_query(F.data.startswith("verdict_"))
async def operator_verdict(callback: CallbackQuery):
    parts = callback.data.split("_")
    num_id = int(parts[1])
    verdict = parts[2]  # vstal, error, skip

    number = await get_number_by_id(num_id)
    if not number:
        return await callback.answer("Номер не найден")

    user_id = number[1]
    phone = number[2]
    tariff = number[3]

    if verdict == "vstal":
        # Успешно — начисляем деньги
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ?, total_earned = total_earned + ? WHERE user_id = ?",
                (tariff, tariff, user_id)
            )
            await db.execute(
                "UPDATE numbers SET status='встал', verdict='встал', paid=0 WHERE id=?",
                (num_id,)
            )
            await db.commit()

        await bot.send_message(
            user_id,
            f"🎉 <b>Отлично!</b> Номер <code>{phone}</code> успешно встал!\n\n"
            f"Начислено: <b>{tariff}$</b>\n"
            f"Баланс можно вывести в разделе «Вывод средств»."
        )
        await log_action(callback.from_user.id, "verdict_vstal", f"Номер #{num_id} встал. Пользователь {user_id} получил {tariff}$", "✅")

    elif verdict == "error":
        await update_number_status(num_id, "ошибка", verdict="ошибка")
        await bot.send_message(user_id, f"❌ Номер <code>{phone}</code> не подошёл (ошибка).")
        await log_action(callback.from_user.id, "verdict_error", f"Номер #{num_id} — ошибка", "❌")

    elif verdict == "skip":
        await update_number_status(num_id, "скипнут_оператором", verdict="скип")
        await bot.send_message(user_id, f"⚠️ Номер <code>{phone}</code> был пропущен оператором.")
        await log_action(callback.from_user.id, "verdict_skip", f"Номер #{num_id} скипнут оператором", "⏭")

    await callback.message.edit_text(f"✅ Вердикт по номеру #{num_id} сохранён: {verdict}")


# ==================== ПОДТВЕРЖДЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ ====================
@dp.callback_query(F.data.startswith("confirm_"))
async def user_confirm_presence(callback: CallbackQuery):
    num_id = int(callback.data.split("_")[1])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE numbers SET last_confirmation=?, status='онлайн' WHERE id=?",
            (datetime.now().isoformat(), num_id)
        )
        await db.commit()

    await callback.message.edit_text("✅ Спасибо! Ты подтвердил присутствие. Жди запроса кода.")
    await log_action(callback.from_user.id, "confirm_presence", f"Подтвердил присутствие по номеру #{num_id}", "✅")


# ==================== ПРОФИЛЬ ====================
@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT balance, total_earned, slots FROM users WHERE user_id = ?",
            (callback.from_user.id,)
        )
        row = await cursor.fetchone()
        balance = row[0] if row else 0
        total_earned = row[1] if row else 0
        slots = row[2] if row else 8

        cursor = await db.execute(
            "SELECT COUNT(*) FROM numbers WHERE user_id = ? AND status = 'встал'",
            (callback.from_user.id,)
        )
        successful = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM numbers WHERE user_id = ? AND status IN ('в_очереди', 'в_обработке', 'онлайн')",
            (callback.from_user.id,)
        )
        in_queue = (await cursor.fetchone())[0]

    text = (
        f"👤 <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n\n"
        f"Имя: {callback.from_user.first_name} @{callback.from_user.username or '—'}\n"
        f"Юзернейм: @{callback.from_user.username or '—'}\n"
        f"ID: <code>{callback.from_user.id}</code>\n\n"
        f"💰 <b>ФИНАНСОВАЯ СТАТИСТИКА</b>\n"
        f"Баланс: <b>{balance}$</b>\n"
        f"Заработано: <b>{total_earned}$</b>\n"
        f"Выведено: <b>0.00$</b>\n"
        f"Выплаты: 🟢 Авто (CryptoBot)\n\n"
        f"📱 <b>СДАННЫЕ АККАУНТЫ</b>\n"
        f"MAX аккаунтов: <b>{successful}</b>\n"
        f"Доступно слотов: <b>{slots} из 8</b>\n\n"
        f"⏳ <b>ТЕКУЩИЕ ЗАЯВКИ</b>\n"
        f"В очереди: <b>{in_queue} шт.</b>\n"
        f"В обработке: <b>0 шт.</b>\n"
        f"Ожидают код: <b>0 шт.</b>"
    )
    await callback.message.edit_text(text, reply_markup=main_menu())


@dp.callback_query(F.data == "queue_menu")
async def queue_menu(callback: CallbackQuery):
    text = "⏳ <b>МЕНЮ ОЧЕРЕДИ</b>\n\nВыберите, что вы хотите посмотреть:"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Вся очередь номеров", callback_data="all_queue")],
        [InlineKeyboardButton(text="📱 Моя очередь номеров", callback_data="my_queue")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data == "all_queue")
async def all_queue(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, phone, tariff, status FROM numbers WHERE status IN ('в_очереди','в_обработке','онлайн') ORDER BY created_at LIMIT 15"
        )
        nums = await cursor.fetchall()

    if not nums:
        text = "📭 Очередь пуста."
    else:
        text = "🌐 <b>Вся очередь номеров</b>\n\n"
        for n in nums:
            text += f"#{n[0]} | {n[1]} | {n[2]}$ | {n[3]}\n"

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="queue_menu")]]))


@dp.callback_query(F.data == "my_queue")
async def my_queue(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, phone, tariff, status FROM numbers WHERE user_id = ? AND status IN ('в_очереди','в_обработке','онлайн') ORDER BY created_at",
            (callback.from_user.id,)
        )
        nums = await cursor.fetchall()

    if not nums:
        text = "📭 У вас нет номеров в очереди."
    else:
        text = "📱 <b>Моя очередь номеров</b>\n\n"
        for n in nums:
            text += f"#{n[0]} | {n[1]} | {n[2]}$ | {n[3]}\n"

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="queue_menu")]]))


@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='встал' THEN 1 ELSE 0 END), SUM(CASE WHEN status='ошибка' THEN 1 ELSE 0 END) FROM numbers WHERE user_id = ?",
            (callback.from_user.id,)
        )
        total, successful, errors = await cursor.fetchone() or (0, 0, 0)

        cursor = await db.execute(
            "SELECT SUM(tariff) FROM numbers WHERE user_id = ? AND status = 'встал'",
            (callback.from_user.id,)
        )
        earned = (await cursor.fetchone())[0] or 0

    text = (
        f"📊 <b>СТАТИСТИКА ПОСТАВЩИКА</b>\n\n"
        f"Сдано всего: <b>{total}</b>\n"
        f"✅ Успешных: <b>{successful}</b> ({round(successful/total*100,1) if total > 0 else 0}%)\n"
        f"❌ Слётов: <b>{errors}</b>\n"
        f"💰 Заработано: <b>{earned}$</b>"
    )
    await callback.message.edit_text(text, reply_markup=main_menu())


@dp.callback_query(F.data == "withdraw")
async def withdraw(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (callback.from_user.id,))
        balance = (await cursor.fetchone())[0] or 0

    if balance < 1:
        text = (
            f"💰 <b>Вывод средств</b>\n\n"
            f"❌ Недостаточно средств для вывода.\n"
            f"Минимальная сумма: <b>1.00$</b>\n"
            f"Ваш баланс: <b>{balance}$</b>"
        )
    else:
        text = f"💰 <b>Вывод средств</b>\n\nВаш баланс: <b>{balance}$</b>\n\nНапиши сумму для вывода (мин 1$):"

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]]))


@dp.callback_query(F.data == "archive")
async def archive(callback: CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id, phone, status, tariff FROM numbers WHERE user_id = ? AND status IN ('встал','ошибка','скипнут_оператором') ORDER BY created_at DESC LIMIT 10",
            (callback.from_user.id,)
        )
        nums = await cursor.fetchall()

    if not nums:
        text = "📁 <b>АРХИВ ЗАЯВОК</b>\n\nАрхив пуст."
    else:
        text = "📁 <b>АРХИВ ЗАЯВОК</b>\n\n"
        for n in nums:
            text += f"#{n[0]} | {n[1]} | {n[2]} | {n[3]}$\n"

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Пред", callback_data="archive_prev"),
         InlineKeyboardButton(text="След ▶️", callback_data="archive_next")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ]))


@dp.callback_query(F.data == "instructions")
async def instructions(callback: CallbackQuery):
    text = (
        "📖 <b>ИНСТРУКЦИЯ</b>\n\n"
        "Выберите раздел:\n\n"
        "1️⃣ Как сдать номер\n"
        "2️⃣ Очередь и слоты\n"
        "3️⃣ Приём кодов\n"
        "4️⃣ Оплата и вывод\n"
        "5️⃣ Штрафы и АФК\n"
        "6️⃣ FAQ"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1. Как сдать номер", callback_data="instr_1"),
         InlineKeyboardButton(text="2. Очередь и слоты", callback_data="instr_2")],
        [InlineKeyboardButton(text="3. Приём кодов", callback_data="instr_3"),
         InlineKeyboardButton(text="4. Оплата и вывод", callback_data="instr_4")],
        [InlineKeyboardButton(text="5. Штрафы и АФК", callback_data="instr_5"),
         InlineKeyboardButton(text="6. FAQ", callback_data="instr_6")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("instr_"))
async def instruction_section(callback: CallbackQuery):
    section = callback.data.split("_")[1]
    texts = {
        "1": "📱 <b>Как сдать номер</b>\n\nПросто отправь номер в формате +7... в режиме сдачи. Можно до 5 номеров сразу.",
        "2": "⏳ <b>Очередь и слоты</b>\n\nУ каждого пользователя 8 слотов. Номера в очереди ждут своего оператора.",
        "3": "🔑 <b>Приём кодов</b>\n\nКогда оператор запросит код — выйди из режима сдачи и ответь на сообщение с кодом.",
        "4": "💰 <b>Оплата и вывод</b>\n\nЗа каждый успешный номер начисляется 3.5$ или 4$. Минимальный вывод — 1$.",
        "5": "⚠️ <b>Штрафы и АФК</b>\n\nЕсли не подтверждаешь присутствие 5 минут — номер удаляется из очереди.",
        "6": "❓ <b>FAQ</b>\n\n• Как вывести деньги? — В разделе «Вывод средств»\n• Сколько платят? — 3.5$ или 4$ за номер\n• Что такое MAX? — Менеджер в РФ"
    }
    await callback.message.edit_text(texts.get(section, "Раздел не найден"), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="instructions")]]))


@dp.callback_query(F.data == "max_qr")
async def max_qr(callback: CallbackQuery):
    text = (
        "📡 <b>СДАЧА MAX АККАУНТОВ ПО QR-КОДУ</b>\n\n"
        "Если вы хотите сдавать MAX аккаунты по QR CODE, заходите к нам в группу!\n\n"
        "Ежедневно принимаем 1000+ номеров по QR.\n\n"
        "🔗 Ссылка: скоро будет"
    )
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]]))


@dp.callback_query(F.data == "payouts")
async def payouts(callback: CallbackQuery):
    text = "💸 <b>Выплаты</b>\n\nИстория выплат пока пуста.\n\nВыплаты производятся вручную в ТГК."
    await callback.message.edit_text(text, reply_markup=main_menu())


@dp.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    text = "🛠 <b>Техподдержка</b>\n\nОпиши свою проблему. Мы ответим в ближайшее время."
    await callback.message.edit_text(text)
    # Здесь можно добавить FSM для создания тикета (как в старом коде)


# ==================== ПОДТВЕРЖДЕНИЕ ВЫПЛАТЫ ОПЕРАТОРОМ ====================
@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        return await callback.answer("Только админ может подтверждать выплаты.")

    num_id = int(callback.data.split("_")[2])
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE numbers SET paid=1 WHERE id=?", (num_id,))
        await db.commit()

    await callback.message.edit_text(f"✅ Выплата по номеру #{num_id} подтверждена.")
    await log_action(callback.from_user.id, "payment_confirmed", f"Подтверждена выплата по номеру #{num_id}", "💰")


# ==================== ЗАПУСК БОТА ====================
async def main():
    await init_db()
    asyncio.create_task(background_tasks())
    logger.info("🚀 Max teqqines bot запущен (с логами и ежедневным сбросом)")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())


# ==================== ЗАПУСК ====================
async def main():
    await init_db()
    logger.info("🚀 Max teqqines bot запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())