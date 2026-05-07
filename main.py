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
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ==================== НАСТРОЙКИ ====================
BOT_TOKEN = "8174433113:AAGsCNLWDI_j8qIi4JI4Bqt2uLuAjO2QM30"
OWNER_ID = 8032626504
API_ID = 30535405
API_HASH = "4b3b138a3bcde9c35b56b5c1b89c840c"
DB_NAME = "username_bot.db"
GROUP_ID = -1003913420195
INVITE_LINK = "https://t.me/+c96NOwKL2_41ZWQx"

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

# ==================== ПРОВЕРКА ЧЕРЕЗ FRAGMENT ====================
async def is_fragment_nft(username: str) -> bool:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://fragment.com/username/{username}"
            async with session.get(url, timeout=6) as resp:
                if resp.status != 200:
                    return False
                text = await resp.text()
                if "This username is available" in text or "not for sale" in text.lower():
                    return False
                if "Buy now" in text or "Current bid" in text:
                    return True
                return False
    except:
        return False

# ==================== ПРОВЕРКА БАНА ====================
async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return user[7] if user and len(user) > 7 else False

# ==================== ПРОВЕРКА ПОДПИСКИ ====================
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=GROUP_ID, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def check_subscription(message: Message = None, callback: CallbackQuery = None):
    user_id = message.from_user.id if message else callback.from_user.id
    if await is_banned(user_id):
        await (message or callback.message).answer("🚫 Вы забанены.")
        return False
    if await is_subscribed(user_id):
        return True
    
    text = (
        "⚠️ <b>Доступ ограничен</b> ⚠️\n\n"
        "Чтобы пользоваться ботом, нужно состоять в нашей супергруппе.\n\n"
        "После подписки нажми кнопку ниже."
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на группу", url=INVITE_LINK)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")]
    ])
    
    if message:
        await message.answer(text, reply_markup=keyboard)
    else:
        try:
            await callback.message.edit_caption(caption=text, reply_markup=keyboard)
        except:
            await callback.message.answer(text, reply_markup=keyboard)
        await callback.answer()
    return False

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.edit_caption(caption="✅ Успешно! Добро пожаловать!")
        await asyncio.sleep(5)
        await callback.message.answer(
            "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\n"
            "Здесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\n"
            "Выбирай действие ниже:",
            reply_markup=main_menu(callback.from_user.id)
        )
    else:
        await callback.answer("❌ Ты всё ещё не подписан на группу.", show_alert=True)

# ==================== АВТО-ОДОБРЕНИЕ ЗАЯВОК ====================
@dp.chat_join_request()
async def approve_join_request(update: ChatJoinRequest):
    try:
        await bot.approve_chat_join_request(chat_id=GROUP_ID, user_id=update.from_user.id)
        await bot.send_message(update.from_user.id, "✅ Заявка одобрена! Теперь ты можешь пользоваться ботом.")
    except Exception as e:
        logger.error(f"Ошибка одобрения заявки: {e}")

# ==================== FSM ====================
class SearchState(StatesGroup):
    choosing_length = State()

class SupportState(StatesGroup):
    waiting_message = State()

class AdminGiveState(StatesGroup):
    waiting_user_id = State()
    waiting_status = State()

class AdminBroadcastState(StatesGroup):
    waiting_text = State()

class AdminTicketReplyState(StatesGroup):
    waiting_reply = State()

class AdminBanState(StatesGroup):
    waiting_user_id = State()

class AdminSetPhotoState(StatesGroup):
    waiting_photo = State()

class AdminCreatePromoState(StatesGroup):
    waiting_code = State()
    waiting_reward = State()

class AdminMassSearchesState(StatesGroup):
    waiting_amount = State()
    waiting_users = State()

# ==================== БАЗА ДАННЫХ ====================
user_found_tags = {}

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, searches_left INTEGER DEFAULT 10,
            status TEXT DEFAULT 'user', premium_until TEXT, referral_code TEXT,
            referred_by INTEGER, is_banned INTEGER DEFAULT 0, total_found INTEGER DEFAULT 0)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS username_cache (
            username TEXT PRIMARY KEY, is_free INTEGER, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER, user_id INTEGER,
            message TEXT, is_admin INTEGER DEFAULT 0, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY, uses_left INTEGER, max_uses INTEGER,
            reward_type TEXT, reward_value INTEGER, created_by INTEGER,
            expires_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, user_id INTEGER,
            activated_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return await cursor.fetchone()

async def create_user(user_id: int, username: str, referred_by: int = None):
    ref_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""INSERT OR IGNORE INTO users 
            (user_id, username, referral_code, referred_by, status) VALUES (?, ?, ?, ?, 'user')""",
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

async def get_user_status(user_id: int) -> str:
    user = await get_user(user_id)
    return user[4] if user else 'user'

async def add_searches(user_id: int, amount: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET searches_left = searches_left + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

# ==================== МАКСИМАЛЬНЫЙ СПИСОК СЛОВ ====================
GOOD_PATTERNS = [
    ("teqq", "teqq"), ("tekki", "tekki"), ("teqqin", "teqqin"), ("teqqy", "teqqy"),
    ("tekkin", "tekkin"), ("teqqer", "teqqer"), ("teqqon", "teqqon"), ("teqqar", "teqqar"),
    ("teqqen", "teqqen"), ("teqqix", "teqqix"), ("teqqor", "teqqor"), ("teqqun", "teqqun"),
    ("teqqal", "teqqal"), ("teqqex", "teqqex"), ("teqqyn", "teqqyn"), ("teqqur", "teqqur"),
    ("teqqis", "teqqis"), ("teqqox", "teqqox"), ("teqqyn", "teqqyn"), ("teqqar", "teqqar"),
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
    ("eternal", "flame"), ("infinite", "sky"), ("prime", "valley"), ("alpha", "wave"), ("omega", "star"),
    ("dark", "knight"), ("golden", "eagle"), ("silver", "wolf"), ("crystal", "phoenix"), ("storm", "rider"),
    ("ghost", "walker"), ("fire", "born"), ("ice", "king"), ("star", "lord"), ("void", "emperor"),
    ("dream", "king"), ("soul", "hunter"), ("blood", "knight"), ("iron", "wolf"), ("steel", "phoenix"),
    ("raven", "lord"), ("dragon", "born"), ("wolf", "king"), ("hawk", "lord"), ("fox", "spirit"),
    ("lion", "heart"), ("eagle", "eye"), ("serpent", "king"), ("falcon", "lord"), ("viper", "born"),
    ("tiger", "spirit"), ("bear", "king"), ("night", "walker"), ("void", "lord"), ("star", "emperor"),
    ("cosmic", "king"), ("nebula", "lord"), ("galaxy", "born"), ("orbit", "king"), ("pulse", "lord"),
    ("echo", "king"), ("nova", "lord"), ("zenith", "king"), ("apex", "lord"), ("forge", "king"),
    ("spire", "lord"), ("realm", "king"), ("haven", "lord"), ("sanctum", "king"), ("citadel", "lord"),
    ("fortress", "king"), ("empire", "lord"), ("dynasty", "king"), ("legacy", "lord"), ("myth", "king"),
    ("legend", "lord"), ("saga", "king"), ("silent", "king"), ("mystic", "lord"), ("royal", "king"),
    ("crystal", "lord"), ("phantom", "king"), ("eternal", "lord"), ("infinite", "king"), ("prime", "lord"),
    ("alpha", "king"), ("omega", "lord"), ("dark", "lord"), ("golden", "king"), ("silver", "lord"),
    ("storm", "king"), ("ghost", "lord"), ("fire", "lord"), ("ice", "king"), ("star", "king"),
    ("void", "king"), ("dream", "lord"), ("soul", "king"), ("blood", "lord"), ("iron", "king"),
    ("steel", "lord"), ("raven", "king"), ("dragon", "lord"), ("wolf", "lord"), ("hawk", "king"),
    ("fox", "lord"), ("lion", "lord"), ("eagle", "king"), ("serpent", "lord"), ("falcon", "king"),
    ("viper", "lord"), ("tiger", "king"), ("bear", "lord"), ("night", "king"), ("void", "lord"),
    ("star", "lord"), ("cosmic", "lord"), ("nebula", "king"), ("galaxy", "lord"), ("orbit", "lord"),
    ("pulse", "king"), ("echo", "lord"), ("nova", "king"), ("zenith", "lord"), ("apex", "king"),
    ("forge", "lord"), ("spire", "king"), ("realm", "lord"), ("haven", "king"), ("sanctum", "lord"),
    ("citadel", "king"), ("fortress", "lord"), ("empire", "king"), ("dynasty", "lord"), ("legacy", "king"),
    ("myth", "lord"), ("legend", "king"), ("saga", "lord"), ("silent", "lord"), ("mystic", "king"),
    ("royal", "lord"), ("crystal", "king"), ("phantom", "lord"), ("eternal", "lord"), ("infinite", "lord"),
    ("prime", "king"), ("alpha", "lord"), ("omega", "king"), ("dark", "lord"), ("golden", "lord"),
    ("silver", "king"), ("storm", "lord"), ("ghost", "king"), ("fire", "lord"), ("ice", "king"),
    ("star", "lord"), ("void", "lord"), ("dream", "lord"), ("soul", "king"), ("blood", "lord"),
    ("iron", "lord"), ("steel", "king"), ("raven", "lord"), ("dragon", "king"), ("wolf", "lord"),
    ("hawk", "king"), ("fox", "lord"), ("lion", "lord"), ("eagle", "king"), ("serpent", "lord"),
    ("falcon", "king"), ("viper", "lord"), ("tiger", "king"), ("bear", "lord"), ("night", "lord"),
    ("void", "lord"), ("star", "king"), ("cosmic", "lord"), ("nebula", "king"), ("galaxy", "lord"),
    ("orbit", "lord"), ("pulse", "king"), ("echo", "lord"), ("nova", "lord"), ("zenith", "lord"),
    ("apex", "king"), ("forge", "lord"), ("spire", "king"), ("realm", "lord"), ("haven", "king"),
    ("sanctum", "lord"), ("citadel", "king"), ("fortress", "lord"), ("empire", "king"), ("dynasty", "lord"),
    ("legacy", "king"), ("myth", "lord"), ("legend", "king"), ("saga", "lord"), ("silent", "lord"),
    ("mystic", "king"), ("royal", "lord"), ("crystal", "king"), ("phantom", "lord"), ("eternal", "lord"),
    ("infinite", "king"), ("prime", "lord"), ("alpha", "king"), ("omega", "lord")
]

def generate_nice_username(length: int) -> str:
    adj, noun = random.choice(GOOD_PATTERNS)
    if length == 5:
        return (adj[:3] + noun[:2]).lower()
    else:
        combined = adj + noun
        return combined[:6].lower() if len(combined) > 6 else combined.lower()

async def find_free_username(length: int, max_attempts: int = 120, user_id: int = None, user_status: str = "user") -> tuple:
    for attempt in range(max_attempts):
        username = generate_nice_username(length)
        is_free = await safe_check_username(username)
        if is_free:
            is_nft = await is_fragment_nft(username)
            if is_nft:
                continue
            if len(set(username)) < 5 or username.count(username[0]) > 2:
                continue
            if any(c in username for c in ['q', 'x', 'z']) and len(set(username)) < 6:
                continue
            if user_id and username in user_found_tags.get(user_id, []):
                continue
            if user_status in ["premium", "partner", "sponsor"] and attempt > 40:
                return username, "free"
            elif user_status == "user" and attempt > 80:
                return username, "free"
            elif attempt > 60:
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

# ==================== МЕНЮ ====================
def main_menu(user_id: int = None):
    buttons = [
        [InlineKeyboardButton(text="🔍 Поиск свободного тега ✨", callback_data="search_menu")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="🛒 Купить у @teqqines", url="https://t.me/teqqines")],
        [InlineKeyboardButton(text="👥 Рефералы", callback_data="referrals"),
         InlineKeyboardButton(text="🛠 Поддержка", callback_data="support")],
        [InlineKeyboardButton(text="📊 Возможности статусов", callback_data="status_benefits")]
    ]
    if user_id == OWNER_ID:
        buttons.append([InlineKeyboardButton(text="🔧 Админ-панель ⚙️", callback_data="admin_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="👥 Рефералы"), KeyboardButton(text="🛠 Поддержка")],
            [KeyboardButton(text="📊 Возможности статусов"), KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )

def search_length_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 букв (редкий) 🔥", callback_data="search_5")],
        [InlineKeyboardButton(text="6 букв (красивый) 💎", callback_data="search_6")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Выдать/Снять Статус", callback_data="admin_give_status"),
         InlineKeyboardButton(text="🎟 Создать Промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="🎁 Раздать Пакеты Поисков", callback_data="admin_mass_searches"),
         InlineKeyboardButton(text="🚫 Забанить/Разбанить", callback_data="admin_ban_menu")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
         InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎟 Все тикеты", callback_data="admin_all_tickets"),
         InlineKeyboardButton(text="🖼 Установить фото", callback_data="admin_set_photo")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

# ==================== ХЕНДЛЕРЫ ====================
@dp.message(CommandStart())
async def start(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    
    user = await get_user(message.from_user.id)
    if not user:
        await create_user(message.from_user.id, message.from_user.username or "")
    
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
    
    await message.answer("Меню:", reply_markup=reply_menu())

@dp.message(F.text == "❓ Помощь")
async def help_command(message: Message):
    text = (
        "📖 <b>Помощь по боту</b>\n\n"
        "🔍 /search — поиск тега\n"
        "👤 /profile — твой профиль\n"
        "👥 /referrals — реферальная программа\n"
        "🛠 /support — поддержка\n"
        "📊 /status — возможности статусов\n\n"
        "Просто нажми на кнопку в меню ниже!"
    )
    await message.answer(text)

@dp.message(F.text == "🔍 Поиск")
async def search_button(message: Message):
    await search_menu_from_button(message)

@dp.message(F.text == "👤 Профиль")
async def profile_button(message: Message):
    await profile_from_button(message)

@dp.message(F.text == "👥 Рефералы")
async def referrals_button(message: Message):
    await referrals_from_button(message)

@dp.message(F.text == "🛠 Поддержка")
async def support_button(message: Message):
    await support_from_button(message)

@dp.message(F.text == "📊 Возможности статусов")
async def status_button(message: Message):
    await status_benefits(message)

async def search_menu_from_button(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    text = "🔍 <b>Поиск свободного тега</b> 🔍\n\nВыбери длину:"
    await message.answer(text, reply_markup=search_length_menu())

async def profile_from_button(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    user = await get_user(message.from_user.id)
    status = user[4] if user else "user"
    status_name = {
        "user": "Обычный пользователь",
        "sponsor": "💎 Спонсор",
        "partner": "🤝 Партнёр",
        "premium": "👑 Премиум"
    }.get(status, "Обычный пользователь")
    
    text = (
        f"👤 <b>Твой профиль</b> 👤\n\n"
        f"🏷️ Статус: <b>{status_name}</b>\n"
        f"🔍 Поисков осталось: <b>{user[2] if user else 10}</b>\n"
        f"📊 Всего найдено тегов: <b>{user[9] if user and len(user) > 9 else 0}</b>\n"
    )
    await message.answer(text, reply_markup=main_menu(message.from_user.id))

async def referrals_from_button(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    user = await get_user(message.from_user.id)
    ref_code = user[5] if user else ""
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={ref_code}"
    
    text = (
        f"👥 <b>Реферальная программа</b> 👥\n\n"
        f"Приглашай друзей и получай бонусы!\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"За каждого приглашённого: +5 поисков"
    )
    await message.answer(text, reply_markup=main_menu(message.from_user.id))

async def support_from_button(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    await message.answer("🛠 <b>Поддержка</b> 🛠\n\nОпиши свою проблему. Мы ответим в ближайшее время.")

@dp.callback_query(F.data == "search_menu")
async def search_menu(callback: CallbackQuery):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    text = "🔍 <b>Поиск свободного тега</b> 🔍\n\nВыбери длину. Чем меньше — тем реже и красивее:"
    try:
        await callback.message.edit_caption(caption=text, reply_markup=search_length_menu())
    except:
        await callback.message.answer(text, reply_markup=search_length_menu())
    await callback.answer()

@dp.callback_query(F.data.startswith("search_"))
async def do_search(callback: CallbackQuery):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    length = int(callback.data.split("_")[1])
    await callback.answer("⏳ Ищу свободный тег...")
    
    text = "⏳ <b>Ищу свободный тег...</b>\n\nЭто может занять несколько секунд."
    try:
        await callback.message.edit_caption(caption=text)
    except:
        pass
    
    user_status = await get_user_status(callback.from_user.id)
    free_username, status = await find_free_username(length, user_id=callback.from_user.id, user_status=user_status)
    
    if free_username:
        if callback.from_user.id not in user_found_tags:
            user_found_tags[callback.from_user.id] = []
        user_found_tags[callback.from_user.id].append(free_username)
        
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
        await increment_found(callback.from_user.id)
    else:
        text = "😔 <b>Не удалось найти свободный тег.</b>\n\nПопробуй ещё раз или выбери другую длину."
        keyboard = main_menu(callback.from_user.id)
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=keyboard)
    except:
        await callback.message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    user = await get_user(callback.from_user.id)
    status = user[4] if user else "user"
    status_name = {
        "user": "Обычный пользователь",
        "sponsor": "💎 Спонсор",
        "partner": "🤝 Партнёр",
        "premium": "👑 Премиум"
    }.get(status, "Обычный пользователь")
    
    text = (
        f"👤 <b>Твой профиль</b> 👤\n\n"
        f"🏷️ Статус: <b>{status_name}</b>\n"
        f"🔍 Поисков осталось: <b>{user[2] if user else 10}</b>\n"
        f"📊 Всего найдено тегов: <b>{user[9] if user and len(user) > 9 else 0}</b>\n"
    )
    try:
        await callback.message.edit_caption(caption=text, reply_markup=main_menu(callback.from_user.id))
    except:
        await callback.message.answer(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "referrals")
async def referrals(callback: CallbackQuery):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    user = await get_user(callback.from_user.id)
    ref_code = user[5] if user else ""
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={ref_code}"
    
    text = (
        f"👥 <b>Реферальная программа</b> 👥\n\n"
        f"Приглашай друзей и получай бонусы!\n\n"
        f"🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\n"
        f"За каждого приглашённого: +5 поисков"
    )
    try:
        await callback.message.edit_caption(caption=text, reply_markup=main_menu(callback.from_user.id))
    except:
        await callback.message.answer(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_start(callback: CallbackQuery, state: FSMContext):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    await state.set_state(SupportState.waiting_message)
    text = "🛠 <b>Поддержка</b> 🛠\n\nОпиши свою проблему. Мы ответим в ближайшее время."
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

@dp.message(SupportState.waiting_message)
async def support_save(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    user_status = await get_user_status(message.from_user.id)
    priority = 2 if user_status in ["premium", "partner"] else (1 if user_status == "sponsor" else 0)
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "INSERT INTO support_tickets (user_id, priority) VALUES (?, ?) RETURNING id",
            (message.from_user.id, priority)
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
        await bot.send_message(OWNER_ID, f"🎟 Новый тикет #{ticket_id} от @{message.from_user.username} (приоритет: {priority})")
    except: pass

# ==================== ПРОМОКОДЫ ====================
@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminCreatePromoState.waiting_code)
    text = "🎟 Введите код промокода (например: TEQQ2026):"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

@dp.message(AdminCreatePromoState.waiting_code)
async def admin_create_promo_code(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    code = message.text.strip().upper()
    await state.update_data(code=code)
    await state.set_state(AdminCreatePromoState.waiting_reward)
    await message.answer("🎁 Введите награду в формате:\nsearches:50\nили status:premium\nили premium_days:30")

@dp.message(AdminCreatePromoState.waiting_reward)
async def admin_create_promo_final(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    code = data["code"]
    reward = message.text.strip()
    
    try:
        reward_type, reward_value = reward.split(":")
        reward_value = int(reward_value)
    except:
        await message.answer("❌ Неверный формат. Пример: searches:50 или status:premium")
        await state.clear()
        return
    
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute("""INSERT INTO promo_codes 
                (code, uses_left, max_uses, reward_type, reward_value, created_by, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (code, 100, 100, reward_type, reward_value, message.from_user.id, 
                 (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")))
            await db.commit()
            await message.answer(f"✅ Промокод <code>{code}</code> создан!\n\nПерешлите это сообщение в чат:\n\n🎁 Активируй промокод: <code>{code}</code>\n\nНапиши боту этот код, чтобы получить награду!")
        except:
            await message.answer("❌ Такой промокод уже существует.")
    await state.clear()

@dp.message(F.text.regexp(r'^[A-Z0-9]{4,20}$'))
async def activate_promo(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    code = message.text.strip().upper()
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
        promo = await cursor.fetchone()
        
        if not promo:
            return
        
        if promo[2] <= 0:
            await message.answer("❌ Этот промокод закончился.")
            return
        
        cursor = await db.execute("SELECT * FROM promo_activations WHERE code = ? AND user_id = ?", (code, message.from_user.id))
        if await cursor.fetchone():
            await message.answer("❌ Вы уже активировали этот промокод.")
            return
        
        await db.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        await db.execute("INSERT INTO promo_activations (code, user_id) VALUES (?, ?)", (code, message.from_user.id))
        
        reward_type = promo[4]
        reward_value = promo[5]
        
        if reward_type == "searches":
            await db.execute("UPDATE users SET searches_left = searches_left + ? WHERE user_id = ?", (reward_value, message.from_user.id))
            await message.answer(f"🎁 <b>Промокод активирован!</b>\n\nВам начислено <b>{reward_value} поисков</b>!\n\nСпасибо за сотрудничество 🤝")
        elif reward_type == "status":
            await db.execute("UPDATE users SET status = ? WHERE user_id = ?", (reward_value, message.from_user.id))
            await message.answer(f"🎁 <b>Промокод активирован!</b>\n\nВам выдан статус <b>{reward_value}</b>!\n\nСпасибо за сотрудничество 🤝")
        elif reward_type == "premium_days":
            until = (datetime.now() + timedelta(days=reward_value)).strftime("%Y-%m-%d")
            await db.execute("UPDATE users SET status = 'premium', premium_until = ? WHERE user_id = ?", (until, message.from_user.id))
            await message.answer(f"🎁 <b>Промокод активирован!</b>\n\nВам выдан <b>Премиум на {reward_value} дней</b>!\n\nСпасибо за сотрудничество 🤝")
        
        await db.commit()

# ==================== МАССОВАЯ РАЗДАЧА ====================
@dp.callback_query(F.data == "admin_mass_searches")
async def admin_mass_searches_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminMassSearchesState.waiting_amount)
    text = "🎁 Введите количество поисков для раздачи:"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

@dp.message(AdminMassSearchesState.waiting_amount)
async def admin_mass_searches_amount(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        amount = int(message.text)
        await state.update_data(amount=amount)
        await state.set_state(AdminMassSearchesState.waiting_users)
        await message.answer("👥 Введите ID пользователей через пробел (или 'all' для всех):")
    except:
        await message.answer("❌ Введите число.")

@dp.message(AdminMassSearchesState.waiting_users)
async def admin_mass_searches_final(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    amount = data["amount"]
    users_input = message.text.strip()
    
    if users_input.lower() == "all":
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT user_id FROM users WHERE is_banned = 0")
            users = [row[0] for row in await cursor.fetchall()]
    else:
        try:
            users = [int(x) for x in users_input.split()]
        except:
            await message.answer("❌ Неверный формат ID.")
            await state.clear()
            return
    
    count = 0
    for user_id in users:
        try:
            await add_searches(user_id, amount)
            await bot.send_message(user_id, 
                f"🎁 <b>Вам начислено {amount} поисков!</b>\n\n"
                f"Спасибо за сотрудничество 🤝\n\n"
                f"by @teqqines")
            count += 1
        except:
            pass
    
    await message.answer(f"✅ Пакеты поисков выданы {count} пользователям!")
    await state.clear()

# ==================== АДМИН ПАНЕЛЬ ====================
@dp.callback_query(F.data == "admin_menu")
async def admin_menu_handler(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    text = "🔧 <b>Админ-панель</b> ⚙️"
    try:
        await callback.message.edit_caption(caption=text, reply_markup=admin_menu())
    except:
        await callback.message.answer(text, reply_markup=admin_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_give_status")
async def admin_give_status_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminGiveState.waiting_user_id)
    text = "👑 Введите ID пользователя:"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

@dp.message(AdminGiveState.waiting_user_id)
async def admin_give_status_user(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    try:
        user_id = int(message.text)
        await state.update_data(user_id=user_id)
        await state.set_state(AdminGiveState.waiting_status)
        await message.answer("👑 Выбери статус:\nuser / sponsor / partner / premium\n(или 'remove' чтобы снять)")
    except:
        await message.answer("❌ Неверный ID.")

@dp.message(AdminGiveState.waiting_status)
async def admin_give_status_final(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    user_id = data["user_id"]
    new_status = message.text.lower().strip()
    
    if new_status not in ["user", "sponsor", "partner", "premium", "remove"]:
        await message.answer("❌ Неверный статус. Используй: user / sponsor / partner / premium / remove")
        await state.clear()
        return
    
    async with aiosqlite.connect(DB_NAME) as db:
        if new_status == "remove":
            await db.execute("UPDATE users SET status = 'user' WHERE user_id = ?", (user_id,))
        else:
            await db.execute("UPDATE users SET status = ? WHERE user_id = ?", (new_status, user_id))
        await db.commit()
    
    log_text = (
        f"✅ <b>Статус успешно выдан!</b>\n\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"🏷️ Статус: <b>{new_status}</b>\n\n"
        f"Спасибо за сотрудничество 🤝"
    )
    await message.answer(log_text)
    
    try:
        await bot.send_message(user_id, log_text)
    except: pass
    await state.clear()

@dp.callback_query(F.data == "admin_all_tickets")
async def admin_all_tickets(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID: return
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT id, user_id, status, priority FROM support_tickets WHERE status != 'closed' ORDER BY priority DESC, id DESC LIMIT 20")
        tickets = await cursor.fetchall()
    
    if not tickets:
        text = "🎟 Нет открытых тикетов."
        keyboard = admin_menu()
    else:
        text = "🎟 <b>Все открытые тикеты</b> (сортировка по приоритету)\n\n"
        keyboard_buttons = []
        for ticket_id, user_id, status, priority in tickets:
            prio_text = "🔥 ВЫСОКИЙ" if priority >= 2 else ("⚡ СРЕДНИЙ" if priority == 1 else "Обычный")
            text += f"#{ticket_id} | ID: {user_id} | {prio_text}\n"
            keyboard_buttons.append([InlineKeyboardButton(text=f"Принять тикет #{ticket_id}", callback_data=f"accept_ticket_{ticket_id}")])
        keyboard_buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_menu")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    try:
        await callback.message.edit_caption(caption=text, reply_markup=keyboard)
    except:
        await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("accept_ticket_"))
async def accept_ticket(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    ticket_id = int(callback.data.split("_")[2])
    await state.set_state(AdminTicketReplyState.waiting_reply)
    await state.update_data(ticket_id=ticket_id)
    await callback.message.edit_text("✍️ Напиши ответ пользователю:")

@dp.message(AdminTicketReplyState.waiting_reply)
async def send_ticket_reply(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID: return
    data = await state.get_data()
    ticket_id = data["ticket_id"]
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM support_tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        if not row:
            await message.answer("❌ Тикет не найден.")
            await state.clear()
            return
        user_id = row[0]
        await db.execute("UPDATE support_tickets SET status = 'closed' WHERE id = ?", (ticket_id,))
        await db.execute("INSERT INTO support_messages (ticket_id, user_id, message, is_admin) VALUES (?, ?, ?, 1)", (ticket_id, message.from_user.id, message.text))
        await db.commit()
    
    try:
        await bot.send_message(user_id, f"📩 <b>Ответ от поддержки:</b>\n\n{message.text}\n\nТикет закрыт. Спасибо!")
        await message.answer("✅ Ответ отправлен, тикет закрыт.")
    except:
        await message.answer("❌ Не удалось отправить.")
    await state.clear()

@dp.callback_query(F.data == "admin_ban_menu")
async def admin_ban_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminBanState.waiting_user_id)
    text = "🚫 Введите ID пользователя для бана/разбана:"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

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
        is_banned = user[7] if len(user) > 7 else 0
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
    text = "📢 <b>Грандиозная рассылка</b>\n\nВведи текст для рассылки:"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

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
    try:
        await callback.message.edit_caption(caption=text, reply_markup=admin_menu())
    except:
        await callback.message.answer(text, reply_markup=admin_menu())
    await callback.answer()

@dp.callback_query(F.data == "admin_set_photo")
async def admin_set_photo_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID: return
    await state.set_state(AdminSetPhotoState.waiting_photo)
    text = "🖼 Отправь фото для приветствия:"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

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

@dp.callback_query(F.data == "status_benefits")
async def status_benefits(callback: CallbackQuery):
    text = (
        "📊 <b>Возможности статусов</b> 📊\n\n"
        "👤 <b>Обычный пользователь</b>\n"
        "• 10 поисков\n"
        "• Обычный приоритет\n\n"
        "💎 <b>Спонсор</b>\n"
        "• 50 поисков\n"
        "• Приоритет в тикетах\n\n"
        "🤝 <b>Партнёр</b>\n"
        "• 100 поисков\n"
        "• Приоритет в тикетах\n"
        "• +10 поисков за реферала\n\n"
        "👑 <b>Премиум</b>\n"
        "• <b>Бесконечные поиски</b>\n"
        "• Высочайший приоритет\n"
        "• Эксклюзивные паттерны\n"
        "• Приоритет в тикетах\n\n"
        "Хочешь получить статус? Пиши в поддержку!"
    )
    try:
        await callback.message.edit_caption(caption=text, reply_markup=main_menu(callback.from_user.id))
    except:
        await callback.message.answer(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    text = (
        "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\n"
        "Здесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\n"
        "Выбирай действие ниже:"
    )
    try:
        await callback.message.edit_caption(caption=text, reply_markup=main_menu(callback.from_user.id))
    except:
        await callback.message.answer(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

# ==================== ЗАПУСК ====================
async def main():
    await init_db()
    await telethon_client.start()
    logger.info("ФИНАЛЬНЫЙ БОТ ЗАПУЩЕН (всё проверено + промокоды + красивые логи + массовые пакеты)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())