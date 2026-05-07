import asyncio
import aiosqlite
import logging
import random
import string
import os
import re
from datetime import datetime, timedelta
from collections import deque
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import UsernameNotOccupiedError

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatJoinRequest, BotCommand
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
MAX_REQUESTS_PER_MINUTE = 18
last_reset = datetime.now()

# ==================== УЛУЧШЕННАЯ ПРОВЕРКА ЮЗЕРНЕЙМА ====================
async def is_username_available(username: str) -> bool:
    try:
        await telethon_client.get_entity(f"@{username}")
        return False
    except UsernameNotOccupiedError:
        pass
    except:
        return False

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://t.me/{username}", timeout=6) as resp:
                if resp.status != 200:
                    return False
                text = await resp.text()
                if "Send Message" in text:
                    return False
                if "This username is available" in text:
                    if await is_fragment_nft(username):
                        return False
                    return True
                return False
    except:
        return False

async def is_fragment_nft(username: str) -> bool:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://fragment.com/username/{username}", timeout=5) as resp:
                if resp.status != 200:
                    return False
                text = await resp.text()
                return "Buy now" in text or "Current bid" in text
    except:
        return False

# ==================== ПРОВЕРКА БАНА ====================
async def is_banned(user_id: int) -> bool:
    user = await get_user(user_id)
    return bool(user[7]) if user and len(user) > 7 else False

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
    
    text = "⚠️ <b>Доступ ограничен</b> ⚠️\n\nЧтобы пользоваться ботом, нужно состоять в нашей супергруппе.\n\nПосле подписки нажми кнопку ниже."
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
        await callback.message.answer("✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\nЗдесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\nВыбирай действие ниже:", reply_markup=main_menu(callback.from_user.id))
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

class PromoActivateState(StatesGroup):
    waiting_code = State()

# ==================== БАЗА ДАННЫХ ====================
user_found_tags = {}

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Основная таблица пользователей
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, searches_left INTEGER DEFAULT 10,
            status TEXT DEFAULT 'user', premium_until TEXT, referral_code TEXT,
            referred_by INTEGER, is_banned INTEGER DEFAULT 0, total_found INTEGER DEFAULT 0)""")
        
        # Таблица для кэша юзернеймов
        await db.execute("""CREATE TABLE IF NOT EXISTS username_cache (
            username TEXT PRIMARY KEY, is_free INTEGER, checked_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        
        # Таблица тикетов поддержки
        await db.execute("""CREATE TABLE IF NOT EXISTS support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, status TEXT DEFAULT 'open',
            priority INTEGER DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        
        # Таблица сообщений тикетов
        await db.execute("""CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id INTEGER, user_id INTEGER,
            message TEXT, is_admin INTEGER DEFAULT 0, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        
        # Таблица настроек
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        
        # Таблица промокодов
        await db.execute("""CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY, uses_left INTEGER, max_uses INTEGER,
            reward_type TEXT, reward_value INTEGER, created_by INTEGER,
            expires_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        
        # Таблица активаций промокодов
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

async def get_user_searches_left(user_id: int) -> int:
    user = await get_user(user_id)
    if not user:
        return 0
    status = user[4]
    if status == "premium":
        return 999999  # Бесконечно
    return user[2] if user else 10

# ==================== ПАТТЕРНЫ ====================
GOOD_PATTERNS = [
    ("teqq", "teqq"), ("tekki", "tekki"), ("teqqin", "teqqin"), ("teqqy", "teqqy"),
    ("tekkin", "tekkin"), ("teqqer", "teqqer"), ("teqqon", "teqqon"), ("teqqar", "teqqar"),
    ("teqqen", "teqqen"), ("teqqix", "teqqix"), ("teqqor", "teqqor"), ("teqqun", "teqqun"),
    ("teqqal", "teqqal"), ("teqqex", "teqqex"), ("teqqyn", "teqqyn"), ("teqqur", "teqqur"),
    ("teqqis", "teqqis"), ("teqqox", "teqqox"), ("teqqyn", "teqqyn"), ("teqqar", "teqqar"),
    ("teqq", "ines"), ("tek", "kines"), ("teq", "qines"), ("tek", "kine"), ("teq", "qine"),
    ("teqq", "ines"), ("tekki", "nes"), ("teqqi", "nes"), ("teqq", "ine"), ("tek", "kines"),
    ("teqq", "ar"), ("teqq", "er"), ("teqq", "on"), ("teqq", "al"), ("teqq", "ex"),
    ("teqq", "yn"), ("teqq", "ur"), ("teqq", "is"), ("teqq", "ox"), ("teqq", "yn"),
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
    ("infinite", "king"), ("prime", "lord"), ("alpha", "king"), ("omega", "lord"),
    ("king", "s"), ("king", "x"), ("king", "z"), ("king", "q"), ("king", "v"),
    ("lord", "s"), ("lord", "x"), ("lord", "z"), ("lord", "q"), ("lord", "v"),
    ("star", "s"), ("star", "x"), ("star", "z"), ("star", "q"), ("star", "v"),
    ("void", "s"), ("void", "x"), ("void", "z"), ("void", "q"), ("void", "v"),
    ("neon", "s"), ("neon", "x"), ("neon", "z"), ("neon", "q"), ("neon", "v"),
    ("fire", "s"), ("fire", "x"), ("fire", "z"), ("fire", "q"), ("fire", "v"),
    ("ice", "s"), ("ice", "x"), ("ice", "z"), ("ice", "q"), ("ice", "v"),
    ("soul", "s"), ("soul", "x"), ("soul", "z"), ("soul", "q"), ("soul", "v"),
    ("blood", "s"), ("blood", "x"), ("blood", "z"), ("blood", "q"), ("blood", "v"),
    ("iron", "s"), ("iron", "x"), ("iron", "z"), ("iron", "q"), ("iron", "v"),
    ("steel", "s"), ("steel", "x"), ("steel", "z"), ("steel", "q"), ("steel", "v"),
    ("raven", "s"), ("raven", "x"), ("raven", "z"), ("raven", "q"), ("raven", "v"),
    ("dragon", "s"), ("dragon", "x"), ("dragon", "z"), ("dragon", "q"), ("dragon", "v"),
    ("wolf", "s"), ("wolf", "x"), ("wolf", "z"), ("wolf", "q"), ("wolf", "v"),
    ("hawk", "s"), ("hawk", "x"), ("hawk", "z"), ("hawk", "q"), ("hawk", "v"),
    ("fox", "s"), ("fox", "x"), ("fox", "z"), ("fox", "q"), ("fox", "v"),
    ("lion", "s"), ("lion", "x"), ("lion", "z"), ("lion", "q"), ("lion", "v"),
    ("eagle", "s"), ("eagle", "x"), ("eagle", "z"), ("eagle", "q"), ("eagle", "v"),
    ("serpent", "s"), ("serpent", "x"), ("serpent", "z"), ("serpent", "q"), ("serpent", "v"),
    ("falcon", "s"), ("falcon", "x"), ("falcon", "z"), ("falcon", "q"), ("falcon", "v"),
    ("viper", "s"), ("viper", "x"), ("viper", "z"), ("viper", "q"), ("viper", "v"),
    ("tiger", "s"), ("tiger", "x"), ("tiger", "z"), ("tiger", "q"), ("tiger", "v"),
    ("bear", "s"), ("bear", "x"), ("bear", "z"), ("bear", "q"), ("bear", "v"),
    ("night", "s"), ("night", "x"), ("night", "z"), ("night", "q"), ("night", "v"),
    ("cosmic", "s"), ("cosmic", "x"), ("cosmic", "z"), ("cosmic", "q"), ("cosmic", "v"),
    ("nebula", "s"), ("nebula", "x"), ("nebula", "z"), ("nebula", "q"), ("nebula", "v"),
    ("galaxy", "s"), ("galaxy", "x"), ("galaxy", "z"), ("galaxy", "q"), ("galaxy", "v"),
    ("orbit", "s"), ("orbit", "x"), ("orbit", "z"), ("orbit", "q"), ("orbit", "v"),
    ("pulse", "s"), ("pulse", "x"), ("pulse", "z"), ("pulse", "q"), ("pulse", "v"),
    ("echo", "s"), ("echo", "x"), ("echo", "z"), ("echo", "q"), ("echo", "v"),
    ("nova", "s"), ("nova", "x"), ("nova", "z"), ("nova", "q"), ("nova", "v"),
    ("zenith", "s"), ("zenith", "x"), ("zenith", "z"), ("zenith", "q"), ("zenith", "v"),
    ("apex", "s"), ("apex", "x"), ("apex", "z"), ("apex", "q"), ("apex", "v"),
    ("forge", "s"), ("forge", "x"), ("forge", "z"), ("forge", "q"), ("forge", "v"),
    ("spire", "s"), ("spire", "x"), ("spire", "z"), ("spire", "q"), ("spire", "v"),
    ("realm", "s"), ("realm", "x"), ("realm", "z"), ("realm", "q"), ("realm", "v"),
    ("haven", "s"), ("haven", "x"), ("haven", "z"), ("haven", "q"), ("haven", "v"),
    ("sanctum", "s"), ("sanctum", "x"), ("sanctum", "z"), ("sanctum", "q"), ("sanctum", "v"),
    ("citadel", "s"), ("citadel", "x"), ("citadel", "z"), ("citadel", "q"), ("citadel", "v"),
    ("fortress", "s"), ("fortress", "x"), ("fortress", "z"), ("fortress", "q"), ("fortress", "v"),
    ("empire", "s"), ("empire", "x"), ("empire", "z"), ("empire", "q"), ("empire", "v"),
    ("dynasty", "s"), ("dynasty", "x"), ("dynasty", "z"), ("dynasty", "q"), ("dynasty", "v"),
    ("legacy", "s"), ("legacy", "x"), ("legacy", "z"), ("legacy", "q"), ("legacy", "v"),
    ("myth", "s"), ("myth", "x"), ("myth", "z"), ("myth", "q"), ("myth", "v"),
    ("legend", "s"), ("legend", "x"), ("legend", "z"), ("legend", "q"), ("legend", "v"),
    ("saga", "s"), ("saga", "x"), ("saga", "z"), ("saga", "q"), ("saga", "v"),
    ("silent", "s"), ("silent", "x"), ("silent", "z"), ("silent", "q"), ("silent", "v"),
    ("mystic", "s"), ("mystic", "x"), ("mystic", "z"), ("mystic", "q"), ("mystic", "v"),
    ("royal", "s"), ("royal", "x"), ("royal", "z"), ("royal", "q"), ("royal", "v"),
    ("crystal", "s"), ("crystal", "x"), ("crystal", "z"), ("crystal", "q"), ("crystal", "v"),
    ("phantom", "s"), ("phantom", "x"), ("phantom", "z"), ("phantom", "q"), ("phantom", "v"),
    ("eternal", "s"), ("eternal", "x"), ("eternal", "z"), ("eternal", "q"), ("eternal", "v"),
    ("infinite", "s"), ("infinite", "x"), ("infinite", "z"), ("infinite", "q"), ("infinite", "v"),
    ("prime", "s"), ("prime", "x"), ("prime", "z"), ("prime", "q"), ("prime", "v"),
    ("alpha", "s"), ("alpha", "x"), ("alpha", "z"), ("alpha", "q"), ("alpha", "v"),
    ("omega", "s"), ("omega", "x"), ("omega", "z"), ("omega", "q"), ("omega", "v"),
]

def generate_nice_username(length: int) -> str:
    adj, noun = random.choice(GOOD_PATTERNS)
    if length == 5:
        return (adj[:3] + noun[:2]).lower()
    else:
        combined = adj + noun
        return combined[:6].lower() if len(combined) > 6 else combined.lower()

async def find_free_username(length: int, max_attempts: int = 150, user_id: int = None) -> tuple:
    for attempt in range(max_attempts):
        username = generate_nice_username(length)
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute("SELECT is_free FROM username_cache WHERE username = ?", (username,))
            cached = await cursor.fetchone()
            if cached and cached[0] == 0:
                continue
        is_available = await is_username_available(username)
        if is_available:
            if await is_fragment_nft(username):
                continue
            if user_id and username in user_found_tags.get(user_id, []):
                continue
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("INSERT OR REPLACE INTO username_cache (username, is_free) VALUES (?, 1)", (username,))
                await db.commit()
            return username, "free"
        else:
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("INSERT OR REPLACE INTO username_cache (username, is_free) VALUES (?, 0)", (username,))
                await db.commit()
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
        [InlineKeyboardButton(text="📊 Возможности статусов", callback_data="status_benefits"),
         InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promo_activate")],
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
    
    text = "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\nЗдесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\nВыбирай действие ниже:"
    
    photo_id = await get_welcome_photo()
    
    if photo_id:
        await bot.send_photo(chat_id=message.chat.id, photo=photo_id, caption=text, reply_markup=main_menu(message.from_user.id))
    else:
        await message.answer(text, reply_markup=main_menu(message.from_user.id))

@dp.message(Command("search"))
async def search_command(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    await message.answer("🔍 <b>Поиск свободного тега</b> 🔍\n\nВыбери длину:", reply_markup=search_length_menu())

@dp.message(Command("profile"))
async def profile_command(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    user = await get_user(message.from_user.id)
    status = user[4] if user else "user"
    status_name = {"user": "Обычный пользователь", "sponsor": "💎 Спонсор", "partner": "🤝 Партнёр", "premium": "👑 Премиум"}.get(status, "Обычный пользователь")
    searches_left = await get_user_searches_left(message.from_user.id)
    text = f"👤 <b>Твой профиль</b> 👤\n\n🏷️ Статус: <b>{status_name}</b>\n🔍 Поисков осталось: <b>{searches_left}</b>\n📊 Всего найдено тегов: <b>{user[9] if user and len(user) > 9 else 0}</b>\n"
    await message.answer(text, reply_markup=main_menu(message.from_user.id))

@dp.message(Command("referrals"))
async def referrals_command(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    user = await get_user(message.from_user.id)
    ref_code = user[5] if user else ""
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={ref_code}"
    text = f"👥 <b>Реферальная программа</b> 👥\n\nПриглашай друзей и получай бонусы!\n\n🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\nЗа каждого приглашённого: +5 поисков"
    await message.answer(text, reply_markup=main_menu(message.from_user.id))

@dp.message(Command("support"))
async def support_command(message: Message):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        return
    if not await check_subscription(message=message):
        return
    await message.answer("🛠 <b>Поддержка</b> 🛠\n\nОпиши свою проблему. Мы ответим в ближайшее время.")

@dp.message(Command("status"))
async def status_command(message: Message):
    await status_benefits(message)

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
    
    user_status = await get_user_status(callback.from_user.id)
    searches_left = await get_user_searches_left(callback.from_user.id)
    
    if searches_left <= 0 and user_status != "premium":
        text = "❌ <b>Лимит поисков исчерпан!</b>\n\nКупи премиум для безлимитного поиска"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить Premium", url="https://t.me/teqqines")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
        await callback.message.answer(text, reply_markup=keyboard)
        return
    
    length = int(callback.data.split("_")[1])
    await callback.answer("⏳ Ищу свободный тег...")
    
    progress_msg = await callback.message.answer("🔄 Ищу свободный тег... (до 40 секунд)")
    
    try:
        free_username, status = await asyncio.wait_for(find_free_username(length, user_id=callback.from_user.id), timeout=38.0)
    except asyncio.TimeoutError:
        await progress_msg.delete()
        await callback.message.answer("⏰ Поиск занял слишком много времени. Попробуй ещё раз.")
        return
    
    await progress_msg.delete()
    
    if free_username:
        if callback.from_user.id not in user_found_tags:
            user_found_tags[callback.from_user.id] = []
        user_found_tags[callback.from_user.id].append(free_username)
        
        stars = get_rarity_stars(free_username)
        status_emoji = get_status_emoji(status)
        
        text = f"✅ <b>НИК НАЙДЕН!</b> ✅\n\n@{free_username}\n📏 {length} букв\n\n⭐ Редкость: {stars}\n{status_emoji}"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Перейти к тегу", url=f"https://t.me/{free_username}")],
            [InlineKeyboardButton(text="🔄 Следующий поиск", callback_data=f"search_{length}")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
        await increment_found(callback.from_user.id)
        
        # Вычитаем поиск если не премиум
        if user_status != "premium":
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("UPDATE users SET searches_left = searches_left - 1 WHERE user_id = ?", (callback.from_user.id,))
                await db.commit()
        
        await callback.message.answer(text, reply_markup=keyboard)
    else:
        text = "❌ <b>Свободных тегов не найдено</b>\n\nПопробуй ещё раз или купи премиум"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать ещё раз", callback_data=f"search_{length}")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")]
        ])
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
    status_name = {"user": "Обычный пользователь", "sponsor": "💎 Спонсор", "partner": "🤝 Партнёр", "premium": "👑 Премиум"}.get(status, "Обычный пользователь")
    searches_left = await get_user_searches_left(callback.from_user.id)
    text = f"👤 <b>Твой профиль</b> 👤\n\n🏷️ Статус: <b>{status_name}</b>\n🔍 Поисков осталось: <b>{searches_left}</b>\n📊 Всего найдено тегов: <b>{user[9] if user and len(user) > 9 else 0}</b>\n"
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
    text = f"👥 <b>Реферальная программа</b> 👥\n\nПриглашай друзей и получай бонусы!\n\n🔗 Твоя ссылка:\n<code>{ref_link}</code>\n\nЗа каждого приглашённого: +5 поисков"
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
    priority = 3 if user_status == "premium" else (2 if user_status == "partner" else (1 if user_status == "sponsor" else 0))
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("INSERT INTO support_tickets (user_id, priority) VALUES (?, ?) RETURNING id", (message.from_user.id, priority))
        ticket_id = (await cursor.fetchone())[0]
        await db.execute("INSERT INTO support_messages (ticket_id, user_id, message) VALUES (?, ?, ?)", (ticket_id, message.from_user.id, message.text))
        await db.commit()
    
    await message.answer("✅ Тикет создан! Мы ответим в ближайшее время.")
    await state.clear()
    
    try:
        await bot.send_message(OWNER_ID, f"🎟 Новый тикет #{ticket_id} от @{message.from_user.username} (приоритет: {priority})")
    except: pass

# ==================== ПРОМОКОДЫ (ТОЛЬКО ЧЕРЕЗ FSM) ====================
@dp.callback_query(F.data == "promo_activate")
async def promo_activate_start(callback: CallbackQuery, state: FSMContext):
    if await is_banned(callback.from_user.id):
        await callback.answer("🚫 Вы забанены.", show_alert=True)
        return
    if not await check_subscription(callback=callback):
        return
    await state.set_state(PromoActivateState.waiting_code)
    text = "🎟 <b>Введи промокод:</b>\n\nПример: TEQQ2026"
    try:
        await callback.message.edit_caption(caption=text)
    except:
        await callback.message.answer(text)
    await callback.answer()

@dp.message(PromoActivateState.waiting_code)
async def promo_activate_final(message: Message, state: FSMContext):
    if await is_banned(message.from_user.id):
        await message.answer("🚫 Вы забанены.")
        await state.clear()
        return
    
    code = message.text.strip().upper()
    
    if not (4 <= len(code) <= 20) or not re.match(r'^[A-Z0-9]+$', code):
        await message.answer("❌ Неверный формат промокода. Введи код из 4-20 символов (буквы и цифры).")
        await state.clear()
        return
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
        promo = await cursor.fetchone()
        
        if not promo:
            await message.answer("❌ Промокод не существует или закончился.")
            await state.clear()
            return
        
        if promo[2] <= 0:
            await message.answer("❌ Этот промокод закончился.")
            await state.clear()
            return
        
        cursor = await db.execute("SELECT * FROM promo_activations WHERE code = ? AND user_id = ?", (code, message.from_user.id))
        if await cursor.fetchone():
            await message.answer("❌ Вы уже активировали этот промокод.")
            await state.clear()
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
    
    await state.clear()

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
            await bot.send_message(user_id, f"🎁 <b>Вам начислено {amount} поисков!</b>\n\nСпасибо за сотрудничество 🤝\n\nby @teqqines")
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
    
    log_text = f"✅ <b>Статус успешно выдан!</b>\n\n👤 ID: <code>{user_id}</code>\n🏷️ Статус: <b>{new_status}</b>\n\nСпасибо за сотрудничество 🤝"
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
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id FROM support_tickets WHERE id = ?", (ticket_id,))
        row = await cursor.fetchone()
        if row:
            user_id = row[0]
            try:
                await bot.send_message(user_id, f"🎟 <b>Ваш тикет #{ticket_id} взят в работу!</b>\n\nАгент поддержки уже работает над вашим вопросом.\nОжидайте ответ в ближайшее время! 🙏")
            except:
                pass
    
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
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("""INSERT OR REPLACE INTO settings (key, value) VALUES ('welcome_photo', ?)""", (file_id,))
        await db.commit()
    
    await message.answer("✅ Фото установлено!")
    await state.clear()

@dp.callback_query(F.data == "status_benefits")
async def status_benefits(callback: CallbackQuery):
    text = "📊 <b>Возможности статусов</b> 📊\n\n👤 <b>Обычный пользователь</b>\n• 10 поисков\n• Обычный приоритет\n\n💎 <b>Спонсор</b>\n• 50 поисков\n• Приоритет в тикетах\n\n🤝 <b>Партнёр</b>\n• 100 поисков\n• Приоритет в тикетах\n• +10 поисков за реферала\n\n👑 <b>Премиум</b>\n• <b>Бесконечные поиски</b>\n• Высочайший приоритет\n• Эксклюзивные паттерны\n• Приоритет в тикетах\n\nХочешь получить статус? Пиши в поддержку!"
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
    text = "✨ <b>Добро пожаловать в бот поиска свободных тегов!</b> ✨\n\nЗдесь ты найдёшь самые красивые и редкие Telegram-юзернеймы.\nВыбирай действие ниже:"
    try:
        await callback.message.edit_caption(caption=text, reply_markup=main_menu(callback.from_user.id))
    except:
        await callback.message.answer(text, reply_markup=main_menu(callback.from_user.id))
    await callback.answer()

# ==================== ЗАПУСК ====================
async def main():
    await init_db()
    await telethon_client.start()
    # УБИРАЕМ ВСЕ КОМАНДЫ ИЗ МЕНЮ, ОСТАВЛЯЕМ ТОЛЬКО /start
    await bot.set_my_commands([
        BotCommand(command="start", description="🚀 Старт")
    ])
    logger.info("✅ ФИНАЛЬНЫЙ БОТ ЗАПУЩЕН (всё исправлено + отдельные таблицы + премиум функции)")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())