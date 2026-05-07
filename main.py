import asyncio
import aiosqlite
import logging
import random
import string
import os
from datetime import datetime, timedelta
from collections import deque
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8174433113:AAGsCNLWDI_j8qIi4JI4Bqt2uLuAjO2QM30"
OWNER_ID = 8032626504
API_ID = 30535405
API_HASH = "4b3b138a3bcde9c35b56b5c1b89c840c"
DB_NAME = "username_bot.db"

STRING_SESSION = os.getenv("STRING_SESSION") or "1AZWarzQBuyz_YH1t9sBq_W9hLnsRJGId1GrcQ7rhi5VdG5Cre6d1caEkaUmiaj5LmsheepExMlNOTDXMR3NeGjQkBPCNfrfro6EkpTuFGHDkgBCcoaImpUAe6jMezFLoJFguDt0I6LDgBB-8wt9HlTwcX-GVA6n0ME9rOxwRLCzs99ouutSDy6X9b1ogqaILi7gH5BSZX22hF5Oqg3U-5de6-wLnalKfB1XxkQF9DAtoKbqPXtaZ-49rZbD8RuPVuEH2mkQbmAP1t0RUiHXj-70737Ih2M29wn4GhE-3N5TyXrfHw4MjMML4D4xy5YkTMcNaXGSoYTh0xQ4KzhPn_BEnOrejgTw="

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

if STRING_SESSION:
    telethon_client = TelegramClient(StringSession(STRING_SESSION), API_ID, API_HASH)
else:
    telethon_client = TelegramClient("checker_session", API_ID, API_HASH)

# ==================== ЗАЩИТА ОТ БАНА ====================
request_queue = deque()
MAX_REQUESTS_PER_MINUTE = 30
last_reset = datetime.now()

async def safe_check_username(username: str) -> bool:
    global last_reset
    now = datetime.now()
    if (now - last_reset).total_seconds() > 60:
        request_queue.clear()
        last_reset = now
    if len(request_queue) >= MAX_REQUESTS_PER_MINUTE:
        await asyncio.sleep(3)
    request_queue.append(now)
    try:
        await telethon_client.get_entity(f"@{username}")
        return False
    except:
        return True

# ==================== FSM ====================
class SearchState(StatesGroup):
    choosing_length = State()

class SupportState(StatesGroup):
    waiting_message = State()

class AdminGiveState(StatesGroup):
    waiting_user_id = State()
    waiting_days = State()

class AdminBroadcastState(StatesGroup):
    waiting_text = State()

class AdminTicketReplyState(StatesGroup):
    waiting_ticket_id = State()
    waiting_reply_text = State()

class AdminPartnerState(StatesGroup):
    waiting_user_id = State()

class AdminBanState(StatesGroup):
    waiting_user_id = State()

class AdminSetPhotoState(StatesGroup):
    waiting_photo = State()

# ==================== БАЗА ДАННЫХ ====================
username_cache = {}

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, searches_left INTEGER DEFAULT 10,
            is_premium INTEGER DEFAULT 0, premium_until TEXT, referral_code TEXT,
            referred_by INTEGER, role TEXT DEFAULT 'user', is_banned INTEGER DEFAULT 0,
            total_found INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS username_cache (
            username TEXT PRIMARY KEY, is_free INTEGER, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER, user_id INTEGER,
            message TEXT, is_admin INTEGER DEFAULT 0, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

async def create_user(user_id: int, username: str, referred_by: int = None):
    ref_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT OR IGNORE INTO users 
            (user_id, username, referral_code, referred_by, role) VALUES (?, ?, ?, ?, 'user')""",
            (user_id, username, ref_code, referred_by))
        await db.commit()

async def get_welcome_photo():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT value FROM settings WHERE key = 'welcome_photo'")
        row = await cursor.fetchone()
        return row[0] if row else None

async def increment_found(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET total_found = total_found + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

# ==================== УЛУЧШЕННАЯ ГЕНЕРАЦИЯ ТЕГОВ ====================
GOOD_PATTERNS = [
    ("cool", "wolf"), ("shadow", "blade"), ("neon", "fox"), ("fire", "heart"), ("ice", "born"),
    ("star", "born"), ("void", "walker"), ("dream", "weaver"), ("soul", "reaver"), ("blood", "moon"),
    ("iron", "clad"), ("steel", "heart"), ("raven", "wing"), ("phoenix", "fire"), ("dragon", "scale"),
    ("wolf", "spirit"), ("hawk", "eye"), ("fox", "fire"), ("lion", "heart"), ("eagle", "claw"),
    ("serpent", "tongue"), ("falcon", "wing"), ("viper", "strike"), ("tiger", "claw"), ("bear", "strength"),
    ("night", "shade"), ("void", "heart"), ("star", "dust"), ("cosmic", "flow"), ("nebula", "core"),
    ("galaxy", "eye"), ("orbit", "fall"), ("pulse", "wave"), ("echo", "song"), ("nova", "burst"),
    ("zenith", "peak"), ("apex", "lord"), ("forge", "fire"), ("spire", "crown"), ("realm", "walker"),
    ("haven", "guard"), ("sanctum", "seal"), ("citadel", "king"), ("fortress", "lord"), ("empire", "born"),
    ("dynasty", "rise"), ("legacy", "born"), ("myth", "weaver"), ("legend", "born"), ("saga", "born"),
    ("silent", "storm"), ("mystic", "river"), ("royal", "flame"), ("crystal", "dawn"), ("phantom", "echo"),
    ("eternal", "flame"), ("infinite", "sky"), ("prime", "valley"), ("alpha", "wave"), ("omega", "star")
]

def generate_nice_username(length: int) -> str:
    if length == 5:
        adj, noun = random.choice(GOOD_PATTERNS)
        return (adj[:3] + noun[:2]).lower()
    else:
        adj, noun = random.choice(GOOD_PATTERNS)
        combined = adj + noun
        return combined[:6].lower() if len(combined) > 6 else combined.lower()

async def find_free_username(length: int, max_attempts: int = 70) -> tuple:
    for _ in range(max_attempts):
        username = generate_nice_username(length)
        is_free = await safe_check_username(username)
        if is_free:
            # Усиленная проверка на NFT-подобность
            if len(set(username)) < 5 or username.count(username[0]) > 2:
                continue
            if any(c in username for c in ['q', 'x', 'z']) and len(set(username)) < 6:
                continue
            return username, "free"
    return None, "none"

def get_rarity_stars(username: str) -> str:
    score = len(set(username)) * 2.4 + (20 if len(username) == 5 else 14)
    if score >= 32: return "★★★★★"
    elif score >= 27: return "★★★★☆"
    elif score >= 22: return "★★★☆☆"
    else: return "★★☆☆☆"

def get_status_emoji(status: str) -> str:
    if status == "free": return "✅ Свободен"
    elif status == "nft": return "⚠️ Вероятно NFT"
    else: return "❌ Занят"

# ==================== КРАСИВЫЕ МЕНЮ ====================
def main_menu(user_id: int = None):
    buttons = [
        [InlineKeyboardButton(text="🔍 Поиск свободного тега ✨", callback_data="search_menu")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🛒 Магазин", callback_data="shop")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
         InlineKeyboardButton(text="🛠 Поддержка", callback_data="support")]
    ]
    if user_id == OWNER_ID:
        buttons.append([InlineKeyboardButton(text="🔧 Админ-панель ⚙️", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def search_length_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 букв (редкий) 🔥", callback_data="search_5")],
        [InlineKeyboardButton(text="6 букв (красивый) 💎", callback_data="search_6")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Выдать Премиум", callback_data="admin_give_premium"),
         InlineKeyboardButton(text="🤝 Выдать/Забрать Партнёра", callback_data="admin_partner_menu")],
        [InlineKeyboardButton(text="🚫 Забанить/Разбанить", callback_data="admin_ban_menu"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
         InlineKeyboardButton(text="🎟 Ответить на тикет", callback_data="admin_reply_ticket")],
        [InlineKeyboardButton(text="🖼 Установить фото", callback_data="admin_set_photo")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user.id, message.from_user.username or "")
        # Уведомление админу о новом пользователе
        try:
            await bot.send_message(OWNER_ID, f"👋 Новый пользователь: @{message.from_user.username or message.from_user.id}")
        except: pass
    
    text = (
        "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\n"
        "Здесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\n"
        "Выбирай действие ниже:"
    )
    
    photo_id = await get_welcome_photo()
    
    if photo_id:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_id,
            caption=text,
            reply_markup=main_menu(message.from_user.id)
        )
    else:
        await message.answer(text, reply_markup=main_menu(message.from_user.id))

@dp.callback_query(F.data == "search_menu")
async def search_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔍 <b>Поиск свободного тега</b> 🔍\n\n"
        "Выбери длину. Чем меньше — тем реже и красивее:",
        reply_markup=search_length_menu()
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("search_"))
async def do_search(callback: CallbackQuery):
    length = int(callback.data.split("_")[1])
    await callback.answer("⏳ Ищу свободный тег...")
    await callback.message.edit_text("⏳ <b>Ищу свободный тег...</b>\n\nЭто может занять несколько секунд.")
    
    free_username, status = await find_free_username(length)
    
    if free_username:
        stars = get_rarity_stars(free_username)
        status_emoji = get_status_emoji(status)
        text = (
            f"✅ <b>Свободный тег найден!</b> ✅\n\n"
            f"🎯 <code>@{free_username}</code>\n\n"
            f"⭐ Редкость: {stars}\n"
            f"📏 Длина: {len(free_username)} символов\n"
            f"{status_emoji}\n\n"
            f"Можешь сразу забрать его! 👇"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти к тегу", url=f"https://t.me/{free_username}")],
            [InlineKeyboardButton(text="🔄 Следующий поиск", callback_data=f"search_{length}")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
        
        # Увеличиваем счётчик найденных
        await increment_found(callback.from_user.id)
    else:
        text = "😔 <b>Не удалось найти свободный тег.</b>\n\nПопробуй ещё раз или выбери другую длину."
        keyboard = main_menu(callback.from_user.id)
    
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    role = user[7] if user else "user"
    role_name = {
        "user": "Обычный пользователь",
        "premium": "💎 Премиум",
        "partner": "🤝 Партнёр",
        "developer": "👑 Разработчик"
    }.get(role, "Обычный пользователь")
    
    text = (
        f"👤 <b>Твой профиль</b> 👤\n\n"
        f"🏷️ Привилегия: <b>{role_name}</b>\n"
        f"🔍 Поисков осталось: <b>{user[2]}</b>\n"
        f"📊 Всего найдено тегов: <b>{user[10] if len(user) > 10 else 0}</b>\n"
    )
    if user[3]:
        text += f"👑 Премиум до: <b>{user[4]}</b>\n"
    
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "shop")
async def shop(callback: CallbackQuery):
    await callback.message.edit_text(
        "🛒 <b>Магазин Премиума</b> 🛒\n\n"
        "Выбери подписку. Чем дольше — тем выгоднее:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 день — 25 ⭐", callback_data="buy_premium_1")],
            [InlineKeyboardButton(text="3 дня — 65 ⭐", callback_data="buy_premium_3")],
            [InlineKeyboardButton(text="7 дней — 140 ⭐", callback_data="buy_premium_7")],
            [InlineKeyboardButton(text="30 дней — 450 ⭐", callback_data="buy_premium_30")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "referrals")
async def referrals(callback: CallbackQuery):
    user = await get_user(callback.from_user.id)
    ref_code = user[5] if user else ""
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={ref_code}"
    
    text = (
        f"👥 <b>Реферальная программа</b> 👥\n\n"
        f"Приглашай друзей и получай бонусы!\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"За каждого приглашённого: +5 поисков"
    )
    await callback.message.edit_text(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SupportState.waiting_message)
    await callback.message.edit_text(
        "🛠 <b>Поддержка</b> 🛠\n\n"
        "Опиши свою проблему. Мы ответим в ближайшее время."
    )
    await callback.answer()

@dp.message(SupportState.waiting_message)
async def support_save(message: Message, state: FSMContext):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO support_tickets (user_id) VALUES (?) RETURNING id",
            (message.from_user.id,)
        )
        ticket_id = (await cursor.fetchone())[0]
        await db.execute(
            "INSERT INTO support_messages (ticket_id, user_id, message) VALUES (?, ?, ?)",
            (ticket_id, message.from_user.id, message.text)
        )
        await db.commit()
    
    await message.answer("✅ Тикет создан! Мы ответим в ближайшее время.")
    await state.clear()
    
    try:
        await bot.send_message(OWNER_ID, f"🎟 Новый тикет #{ticket_id} от @{message.from_user.username}")
    except: pass

# ==================== АДМИН ПАНЕЛЬ ====================
@dp.callback_query(F.data == "admin_menu")
async def admin_menu_handler(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    await callback.message.edit_text("🔧 <b>Админ-панель</b> ⚙️", reply_markup=admin_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_give_premium")
async def admin_give_premium_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminGiveState.waiting_user_id)
    await callback.message.edit_text("👑 Введите ID пользователя:")

@dp.message(AdminGiveState.waiting_user_id)
async def admin_give_premium_user(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await state.set_state(AdminGiveState.waiting_days)
        await message.answer("👑 На сколько дней выдать Премиум?")
    except:
        await message.answer("❌ Неверный ID.")

@dp.message(AdminGiveState.waiting_days)
async def admin_give_premium_days(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    user_id = data["user_id"]
    try:
        days = int(message.text)
        until = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET is_premium = 1, premium_until = ?, role = 'premium' WHERE user_id = ?", (until, user_id))
            await db.commit()
        await message.answer(f"✅ Премиум выдан пользователю {user_id} на {days} дней")
        try:
            await bot.send_message(user_id, f"👑 <b>Поздравляем!</b> Вам выдан Премиум до {until}")
        except: pass
    except:
        await message.answer("❌ Ошибка.")
    await state.clear()

@dp.callback_query(F.data == "admin_partner_menu")
async def admin_partner_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminPartnerState.waiting_user_id)
    await callback.message.edit_text("🤝 Введите ID пользователя для выдачи/забора Партнёра:")

@dp.message(AdminPartnerState.waiting_user_id)
async def admin_partner_action(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(message.text)
        user = await get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            await state.clear()
            return
        
        current_role = user[7]
        if current_role == "partner":
            new_role = "user"
            action = "забран"
        else:
            new_role = "partner"
            action = "выдан"
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET role = ? WHERE user_id = ?", (new_role, user_id))
            await db.commit()
        
        await message.answer(f"✅ Партнёр {action} пользователю {user_id}.")
        try:
            await bot.send_message(user_id, f"🤝 <b>Вам {'выдана' if action == 'выдан' else 'забрана'} роль Партнёра!</b>")
        except: pass
    except:
        await message.answer("❌ Ошибка.")
    await state.clear()

@dp.callback_query(F.data == "admin_ban_menu")
async def admin_ban_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminBanState.waiting_user_id)
    await callback.message.edit_text("🚫 Введите ID пользователя для бана/разбана:")

@dp.message(AdminBanState.waiting_user_id)
async def admin_ban_action(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(message.text)
        user = await get_user(user_id)
        if not user:
            await message.answer("❌ Пользователь не найден.")
            await state.clear()
            return
        is_banned = user[9] if len(user) > 9 else 0
        action = "разбанить" if is_banned else "забанить"
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (0 if is_banned else 1, user_id))
            await db.commit()
        await message.answer(f"✅ Пользователь {user_id} успешно {action}.")
        try:
            await bot.send_message(user_id, f"⚠️ Ваш аккаунт был {'разбанен' if is_banned else 'забанен'} администратором.")
        except: pass
    except:
        await message.answer("❌ Ошибка.")
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminBroadcastState.waiting_text)
    await callback.message.edit_text("📢 <b>Грандиозная рассылка</b>\n\nВведи текст для рассылки:")

@dp.message(AdminBroadcastState.waiting_text)
async def do_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
        users = await cursor.fetchall()
    count = 0
    for (user_id,) in users:
        try:
            text = f"📢 <b>Важное сообщение от админа</b> 📢\n\n{message.text}\n\nby @teqqines"
            photo_id = await get_welcome_photo()
            if photo_id:
                await bot.send_photo(user_id, photo=photo_id, caption=text)
            else:
                await bot.send_message(user_id, text)
            count += 1
            await asyncio.sleep(0.03)
        except: pass
    await message.answer(f"✅ Рассылка отправлена {count} пользователям!")
    await state.clear()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned = (await cursor.fetchone())[0]
    text = f"📊 <b>Статистика</b>\n\n👥 Всего пользователей: <b>{total}</b>\n🚫 Забанено: <b>{banned}</b>"
    await callback.message.edit_text(text, reply_markup=admin_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_set_photo")
async def admin_set_photo_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminSetPhotoState.waiting_photo)
    await callback.message.edit_text("🖼 Отправь фото для приветствия:")

@dp.message(AdminSetPhotoState.waiting_photo, F.photo)
async def admin_set_photo_save(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    photo = message.photo[-1]
    file_id = photo.file_id
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("""INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)""", (file_id,))
        await db.commit()
    
    await message.answer("✅ Фото установлено!")
    await state.clear()

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\n"
        "Здесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\n"
        "Выбирай действие ниже:",
        reply_markup=main_menu(callback.from_user.id)
    )
    await callback.answer()

# ==================== ЗАПУСК ====================
async def main():
    await init_db()
    await telethon_client.start()
    logger.info("Финальный бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())