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
from telethon.tl import functions
from telethon.errors import UsernameOccupiedError, UsernameInvalidError, FloodWaitError

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
MAX_REQUESTS_PER_MINUTE = 32
last_reset = datetime.now()
USE_TELETHON = True

async def safe_check_username(username: str) -> bool:
    global last_reset, USE_TELETHON
    if not USE_TELETHON:
        try:
            await bot.get_chat(f"@{username}")
            return False
        except:
            return True
    now = datetime.now()
    if (now - last_reset).total_seconds() > 60:
        request_queue.clear()
        last_reset = now
    if len(request_queue) >= MAX_REQUESTS_PER_MINUTE:
        await asyncio.sleep(3)
    request_queue.append(now)
    try:
        result = await telethon_client(functions.account.CheckUsernameRequest(username=username))
        return result
    except FloodWaitError as e:
        logger.warning(f"FloodWait {e.seconds}s")
        USE_TELETHON = False
        await asyncio.sleep(e.seconds + 5)
        asyncio.create_task(reset_to_telethon())
        return False
    except (UsernameOccupiedError, UsernameInvalidError):
        return False
    except Exception as e:
        logger.error(f"Telethon error: {e}")
        return False

async def reset_to_telethon():
    await asyncio.sleep(300)
    global USE_TELETHON
    USE_TELETHON = True
    logger.info("Вернулись на Telethon")

# ==================== FSM ====================
class SearchState(StatesGroup):
    choosing_length = State()

class SupportState(StatesGroup):
    waiting_message = State()
    waiting_admin_reply = State()

class AdminGiveState(StatesGroup):
    waiting_user_id = State()
    waiting_days = State()

class AdminBroadcastState(StatesGroup):
    waiting_text = State()

class AdminTicketReplyState(StatesGroup):
    waiting_ticket_id = State()
    waiting_reply_text = State()

class AdminBanState(StatesGroup):
    waiting_user_id = State()

# ==================== БАЗА ДАННЫХ ====================
username_cache = {}

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, searches_left INTEGER DEFAULT 10,
            is_premium INTEGER DEFAULT 0, premium_until TEXT, referral_code TEXT,
            referred_by INTEGER, role TEXT DEFAULT 'user', is_banned INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS username_cache (
            username TEXT PRIMARY KEY, is_free INTEGER, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER, user_id INTEGER,
            message TEXT, is_admin INTEGER DEFAULT 0, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
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

async def get_cached_username(username: str):
    if username in username_cache: return username_cache[username]
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_free FROM username_cache WHERE username = ?", (username,))
        row = await cursor.fetchone()
        if row:
            username_cache[username] = bool(row[0])
            return bool(row[0])
    return None

async def cache_username(username: str, is_free: bool):
    username_cache[username] = is_free
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO username_cache (username, is_free) VALUES (?, ?)",
            (username, 1 if is_free else 0))
        await db.commit()

# ==================== ГЕНЕРАЦИЯ ====================
ADJECTIVES = ["cool", "fast", "smart", "wild", "dark", "fire", "gold", "ice", "star", "neo", "ghost", "king", "shadow", "storm", "blade", "silent", "mystic", "royal", "crystal", "phantom", "eagle", "tiger", "dragon", "wolf", "hawk", "fox", "lion", "ninja", "cyber", "quantum", "cosmic", "eternal", "infinite", "prime", "alpha", "omega", "solar", "lunar", "stellar", "void", "neon", "arctic", "inferno", "thunder", "lightning", "frost", "ember", "raven", "phoenix", "serpent", "falcon", "viper", "midnight", "sunset", "aurora", "velvet", "onyx", "ruby", "sapphire", "emerald", "obsidian", "titanium", "platinum", "diamond", "silver", "bronze", "steel", "iron", "blood", "bone", "soul", "spirit", "dream", "night", "dawn", "dusk", "echo", "pulse", "nova", "zenith", "apex", "forge", "spire", "realm", "haven", "sanctum", "citadel", "fortress", "empire", "dynasty", "legacy", "myth", "legend", "saga", "chronos", "aether", "nyx", "gaia", "helios", "selene", "ares", "zeus", "hades", "poseidon", "thor", "odin", "loki", "fenrir", "valkyrie", "ragnarok", "asgard", "midgard"]

NOUNS = ["wolf", "hawk", "fox", "lion", "eagle", "shadow", "storm", "blade", "ghost", "king", "dragon", "ninja", "phoenix", "raven", "serpent", "falcon", "viper", "tiger", "bear", "night", "void", "star", "cosmos", "nebula", "galaxy", "orbit", "pulse", "echo", "nova", "zenith", "apex", "forge", "spire", "realm", "haven", "sanctum", "citadel", "fortress", "empire", "dynasty", "legacy", "myth", "legend", "saga", "pulse", "echo", "nova", "zenith", "apex", "forge", "spire", "realm", "haven", "sanctum", "citadel", "fortress", "empire", "dynasty", "legacy", "myth", "legend", "saga", "wolfpack", "nightfall", "stormborn", "shadowveil", "fireheart", "iceborn", "starborn", "voidwalker", "dreamweaver", "soulreaver", "bloodmoon", "ironclad", "steelheart", "ravenwing", "phoenixfire", "dragonscale", "wolfspirit", "hawkseye", "foxfire", "lionheart", "eagleclaw", "serpenttongue", "falconwing", "viperstrike", "tigerclaw", "bearstrength", "nightshade", "voidheart", "stardust", "cosmicflow", "nebulacore", "galaxyeye", "orbitfall", "pulsewave", "echosong", "novaburst", "zenithpeak", "apexlord", "forgefire", "spirecrown", "realmwalker", "havenguard", "sanctumseal", "citadelking", "fortresslord", "empireborn", "dynastyrise", "legacyborn", "mythweaver", "legendborn", "sagaborn", "chronoslord", "aetherking", "nyxshadow", "gaiaborn", "heliosfire", "selenelight", "aresblood", "zeuslightning", "hadesveil", "poseidonwave", "thorhammer", "odinraven", "lokishadow", "fenrirhowl", "valkyrieblade", "ragnarokfire", "asgardgate", "midgardborn"]

def generate_nice_username(length: int) -> str:
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    if length == 5:
        return (adj[:3] + noun[:2]).lower()
    else:
        combined = adj + noun
        return combined[:6].lower() if len(combined) > 6 else combined.lower()

async def find_free_username(length: int, max_attempts: int = 50) -> str:
    for _ in range(max_attempts):
        username = generate_nice_username(length)
        if await safe_check_username(username):
            return username
    return None

def get_rarity_stars(username: str) -> str:
    score = len(set(username)) * 2.4 + (20 if len(username) == 5 else 14)
    if score >= 32: return "★★★★★"
    elif score >= 27: return "★★★★☆"
    elif score >= 22: return "★★★☆☆"
    else: return "★★☆☆☆"

# ==================== КРАСИВЫЕ МЕНЮ С КНОПКОЙ НАЗАД ====================
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
         InlineKeyboardButton(text="🚫 Забанить/Разбанить", callback_data="admin_ban_menu")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎟 Ответить на тикет", callback_data="admin_reply_ticket"),
         InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user.id, message.from_user.username or "")
    await message.answer(
        "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\n"
        "Здесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\n"
        "Выбирай действие ниже:",
        reply_markup=main_menu(message.from_user.id)
    )

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
    
    free_username = await find_free_username(length)
    
    if free_username:
        stars = get_rarity_stars(free_username)
        text = (
            f"✅ <b>Свободный тег найден!</b> ✅\n\n"
            f"🎯 <code>@{free_username}</code>\n\n"
            f"⭐ Редкость: {stars}\n"
            f"📏 Длина: {len(free_username)} символов\n"
            f"🟢 Статус: Свободен\n\n"
            f"Можешь сразу забрать его! 👇"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти к тегу", url=f"https://t.me/{free_username}")],
            [InlineKeyboardButton(text="🔄 Следующий поиск", callback_data=f"search_{length}")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
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
            await bot.send_message(user_id, f"👑 <b>Поздравляем!</b>\n\nВам выдан Премиум до {until}")
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

# ==================== ОБРАБОТЧИК КНОПКИ НАЗАД ====================
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
    logger.info("Красивый бот с максимальной защитой запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())