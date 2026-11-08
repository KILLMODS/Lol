#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NFT-Gift Bot v7.1 — Premium Canvas Render & Complete Unicode Engine.
- Автоматическая нормализация математических/жирных Unicode-символов Telegram в никнеймах.
- Исправлена загрузка и конвертация NFT-картинок со всех форматов (WebP, PNG, JPG).
- Очистка лишних топов: оставлен только "ТОП ПО БАЛАНСУ ⭐".
- Добавлена генерация красивого графического банера для Главного Меню.
- Высокая оптимизация расхода ОЗУ (RAM) и автоматическая инициализация базы данных.
- Полная система переводов (/pay, /send_gift) и настройки приватности.
- Ограничение использования команды NFT: 1 раз в 1 час для каждого пользователя.
"""

import asyncio
import io
import logging
import math
import os
import random
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter
import requests

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    InputFile,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Настройки и глобальные пути
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "images"
FONTS_DIR = BASE_DIR / "fonts"
DB_PATH = BASE_DIR / "base.db"

FONTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9036416244:AAGrJgI3jzMMU5bn6Q36r8cNBIJqGxniXmo")

COOLDOWN_SECONDS = 1 * 60 * 60          # 1 час (3600 секунд)
COOLDOWN_ENABLED = True                 # Ограничение включено: 1 раз в час
TRIGGER_WORDS = {"nft", "нфт", "подарок"}
DROP_CHANCE = 0.60                      # Шанс выпадения (60%)
STAR_RUB_RATE = 1.5                     # 1 Star = 1.5 RUB
TON_RUB_RATE = 100.0                    # 1 TON = 100 RUB

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("nft_bot")

# ---------------------------------------------------------------------------
# Загрузка Unicode-шрифтов (Поддержка всех языков и шрифтов)
# ---------------------------------------------------------------------------

FONT_REGULAR_PATH = FONTS_DIR / "NotoSans.ttf"
FONT_BOLD_PATH = FONTS_DIR / "NotoSans-Bold.ttf"

def ensure_fonts_exist():
    """Скачивает NotoSans шрифты для гарантированной поддержки всех языков и кириллицы."""
    if not FONT_REGULAR_PATH.exists():
        log.info("Загрузка шрифта NotoSans-Regular...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                FONT_REGULAR_PATH.write_bytes(r.content)
        except Exception as e:
            log.error("Ошибка скачивания шрифта: %s", e)

    if not FONT_BOLD_PATH.exists():
        log.info("Загрузка шрифта NotoSans-Bold...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                FONT_BOLD_PATH.write_bytes(r.content)
        except Exception as e:
            log.error("Ошибка скачивания шрифта Bold: %s", e)

ensure_fonts_exist()

# ---------------------------------------------------------------------------
# Нормализатор спец-символов и математических шрифтов Telegram
# ---------------------------------------------------------------------------

def normalize_telegram_name(name: str) -> str:
    """
    Преобразует математические жирные, курсивные и редкие символы Unicode 
    (например, 𝑩𝒍𝒂𝒄𝒌𝑪𝒂𝒕 -> BlackCat) в стандартные символы UTF-8.
    """
    if not name:
        return "Игрок"

    # Удаляем клантеги вида [СВО], (СВО), {КЛАН}
    cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", name).strip()
    if not cleaned:
        cleaned = name.strip()

    # Каноническая нормализация Unicode (NFKC разворачивает Math Bold, Script, Sans, etc.)
    normalized = unicodedata.normalize('NFKC', cleaned)

    # Дополнительная очистка от нерасшифровываемых управляющих символов
    res = []
    for char in normalized:
        if unicodedata.category(char) in ('So', 'Cn', 'Co'):
            continue  # Пропуск неизвестных спец-символов
        res.append(char)

    final_str = "".join(res).strip()
    return final_str if final_str else "Игрок"


# ---------------------------------------------------------------------------
# NFT и Начисляемый опыт (XP)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GiftDef:
    key: str
    name: str
    stars: int        # Истинная цена в Stars
    chance: float      # Процент выпадения
    xp: int           # Опыт за получение предмета

    @property
    def ton(self) -> float:
        return round((self.stars * STAR_RUB_RATE) / TON_RUB_RATE, 3)

    @property
    def rub(self) -> float:
        return round(self.stars * STAR_RUB_RATE, 2)


# Каталог NFT
GIFTS: list[GiftDef] = [
    GiftDef("teddy_flowers", "Pretty Posy (мишка с букетом)", 355, 3.5, 350),
    GiftDef("pepe_heart", "Plush Pepe (Пепе с сердцем)", 466_600, 0.01, 50_000),
    GiftDef("teddy_patrick", "Irish Bear (мишка-лепрекон)", 50, 4.76, 100),
    GiftDef("teddy_pumpkin", "Mad Pumpkin (мишка с тыквой)", 831, 1.17, 850),
    GiftDef("ring_signet_tg", "Signet Ring (перстень)", 2379, 0.69, 2_400),
    GiftDef("heart_cookie", "Cookie Heart (пряничное сердце)", 363, 1.77, 360),
    GiftDef("hero_figure", "Mini Oscar (фигурка героя)", 4831, 0.15, 5_000),
    GiftDef("teddy_heart_white", "New Year's Bear (белый мишка)", 50, 4.76, 100),
    GiftDef("ring_box_tg", "Bonded Ring (кольцо в коробочке)", 3014, 0.61, 3_000),
    GiftDef("cupcake_bunny", "Bunny Muffin (кекс-зайчик)", 559, 1.42, 550),
    GiftDef("torch", "Liberty Figure (факел свободы)", 347, 1.81, 350),
    GiftDef("skull_ghost", "Electric Skull (призрачный череп)", 2040, 0.75, 2_000),
    GiftDef("mosque_moon", "Moon Pendant (полумесяц и мечеть)", 459, 1.57, 450),
    GiftDef("teddy_santa", "New Year's Bear (мишка-Санта)", 50, 4.76, 100),
    GiftDef("teddy_football", "Football Bear (мишка-футболист)", 50, 4.76, 100),
    GiftDef("peace_dove_stamp", "Dove of Peace (марка 'Голубь мира')", 333, 1.85, 330),
    GiftDef("cap_tg", "Top Hat (кепка/цилиндр)", 686, 1.29, 700),
    GiftDef("pacifier_gold", "Hypno Lollipop (золотая соска)", 283, 2.00, 300),
    GiftDef("trophy_cup", "Algorithm Cup (кубок чемпиона)", 83_750, 0.05, 25_000),
    GiftDef("eye_evil", "Evil Eye (глаз-оберег)", 547, 1.44, 550),
    GiftDef("clover_green", "Clover Pin (клевер удачи)", 328, 1.86, 330),
    GiftDef("hockey_mask", "Scared Cat (маска Джейсона)", 19_423, 0.08, 15_000),
    GiftDef("broom_witch", "Flying Broom (ведьмина метла)", 879, 1.14, 900),
    GiftDef("ring_silver", "Signet Ring (серебряное кольцо)", 2379, 0.69, 2_400),
    GiftDef("new_year_2025", "Big Year (цифры 2025)", 266, 2.07, 270),
    GiftDef("rose_bell_jar", "Eternal Rose (роза под колпаком)", 1799, 0.79, 1_800),
    GiftDef("bunny_teddy", "Easter Bear (мишка-кролик)", 50, 4.76, 100),
    GiftDef("sneakers_black", "Fresh Socks (чёрные кроссовки)", 313, 1.90, 300),
    GiftDef("i_love_u_heart", "I love you (сердце 'I LOVE U')", 50, 4.76, 100),
    GiftDef("egg_butterfly", "Easter Egg (пасхальное яйцо)", 280, 2.01, 280),
    GiftDef("fountain_pen", "Fine Pen (золотое перо)", 533, 1.46, 530),
    GiftDef("candle", "Eternal Candle (свеча желаний)", 417, 1.65, 420),
    GiftDef("coffin", "Gravestone (гробик)", 667, 1.30, 670),
    GiftDef("teddy_soldier", "Bear Terrorist (мишка-солдат)", 50, 4.76, 100),
    GiftDef("coconut_drink", "Holiday Drink (коктейль в кокосе)", 306, 1.93, 300),
    GiftDef("teddy_builder", "Polar Bear (мишка-строитель)", 50, 4.76, 100),
    GiftDef("bowtie", "Bow Tie (бабочка-галстук)", 377, 1.74, 380),
    GiftDef("xmas_tree", "Christmas Tree (ёлочка)", 50, 4.76, 100),
    GiftDef("candy_cane", "Candy Cane (леденец-трость)", 265, 2.07, 260),
    GiftDef("heart_lock_key", "Heart Locket (сердце-замок)", 87_100, 0.04, 25_000),
    GiftDef("chocolate_box", "Berry Box (коробка конфет)", 627, 1.35, 630),
    GiftDef("first_may", "1 May (1 Мая)", 333, 1.85, 330),
    GiftDef("durov_dog", "Resistance Dog (пёс Дурова)", 34_505, 0.07, 18_000),
    GiftDef("sunglasses", "Durov's Glasses (солнечные очки)", 9_467, 0.12, 10_000),
    GiftDef("crystal_ball", "Crystal Ball (магический шар)", 918, 1.11, 920),
    GiftDef("tg_rashguard", "Swag Bag (рашгард Telegram)", 379, 1.73, 380),
    GiftDef("happy_bday_sign", "Star Notepad (табличка B-day)", 326, 1.87, 330),
    GiftDef("easter_cake", "Homemade Cake (кулич)", 345, 1.81, 350),
    GiftDef("briefcase", "Loot Bag (деловой портфель)", 9_267, 0.15, 9_500),
    GiftDef("clown_teddy", "Clown Bear (мишка-клоун)", 50, 4.76, 100),
    GiftDef("gem_crystal", "Astral Shard (кристалл 'Алмаз')", 8_666, 0.18, 9_000),
    GiftDef("bday_calendar", "Desk Calendar (календарь Б-Day)", 426, 1.63, 430),
]

GIFTS_BY_KEY = {g.key: g for g in GIFTS}
_total_weight = sum(g.chance for g in GIFTS)


def roll_gift() -> GiftDef:
    r = random.uniform(0, _total_weight)
    upto = 0.0
    for g in GIFTS:
        upto += g.chance
        if upto >= r:
            return g
    return GIFTS[-1]


def gift_image_path(key: str) -> Optional[Path]:
    """Универсальный поиск изображения NFT в папке images по всем расширениям."""
    exts = [".webp", ".png", ".jpg", ".jpeg"]
    for ext in exts:
        p = IMAGES_DIR / f"{key}{ext}"
        if p.exists():
            return p
    return None


def rarity_label(chance: float) -> str:
    if chance >= 3.0: return "Обычный"
    if chance >= 1.5: return "Необычный"
    if chance >= 0.5: return "Редкий"
    if chance >= 0.2: return "Эпический"
    return "Легендарный"


def rarity_emoji(chance: float) -> str:
    if chance >= 3.0: return "⚪️"
    if chance >= 1.5: return "🟢"
    if chance >= 0.5: return "🔵"
    if chance >= 0.2: return "🟣"
    return "🟡"


# ---------------------------------------------------------------------------
# Расчет уровня и XP (Прогрессивная шкала)
# ---------------------------------------------------------------------------

def calculate_xp_level_info(total_xp: int) -> Tuple[int, int, int, float]:
    """
    Вычисляет: (текущий уровень, XP в рамках уровня, XP до следующего уровня, процент 0..1)
    Уровень 0: 0 - 1000 XP
    Каждый следующий уровень требует +1500 XP прироста к шагу.
    """
    level = 0
    current_xp = total_xp
    req_xp = 1000

    while current_xp >= req_xp:
        current_xp -= req_xp
        level += 1
        req_xp = int(req_xp + 1500 + (level * 500))

    ratio = min(1.0, max(0.0, current_xp / req_xp))
    return level, current_xp, req_xp, ratio


def fmt_stars_rub(stars: int) -> str:
    return f"{stars:,} ⭐ (~{stars * STAR_RUB_RATE:,.0f} ₽)"


def fmt_ton(ton: float) -> str:
    return f"{ton:.2f} TON (~{ton * TON_RUB_RATE:,.0f} ₽)"


def seconds_to_hms(sec: int) -> str:
    sec = max(0, sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h: return f"{h} ч {m} мин"
    if m: return f"{m} мин {s} сек"
    return f"{s} сек"


# ---------------------------------------------------------------------------
# База данных SQLite
# ---------------------------------------------------------------------------

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def db_init() -> None:
    """Инициализация базы данных."""
    conn = db_connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id_num INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                balance_stars INTEGER NOT NULL DEFAULT 0,
                xp INTEGER NOT NULL DEFAULT 0,
                hide_top INTEGER NOT NULL DEFAULT 0,
                hide_collection INTEGER NOT NULL DEFAULT 0,
                last_drop_ts INTEGER NOT NULL DEFAULT 0,
                last_daily_bonus_ts INTEGER NOT NULL DEFAULT 0,
                total_drops INTEGER NOT NULL DEFAULT 0,
                total_sold INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS collection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                obtained_ts INTEGER NOT NULL,
                is_favorite INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS pending_drops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                created_ts INTEGER NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "id_num" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN id_num INTEGER;")
            users = conn.execute("SELECT user_id FROM users ORDER BY rowid ASC").fetchall()
            for idx, u in enumerate(users, start=1):
                conn.execute("UPDATE users SET id_num=? WHERE user_id=?", (idx, u["user_id"]))
        if "hide_top" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN hide_top INTEGER NOT NULL DEFAULT 0;")
        if "hide_collection" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN hide_collection INTEGER NOT NULL DEFAULT 0;")

        conn.commit()
    finally:
        conn.close()


def get_or_create_user(user_id: int, username: str, first_name: str) -> sqlite3.Row:
    conn = db_connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, xp) VALUES (?, ?, ?, 0)",
                (user_id, username or "", first_name or ""),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        else:
            conn.execute(
                "UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username or "", first_name or "", user_id),
            )
            conn.commit()
        return row
    finally:
        conn.close()


def set_last_drop(user_id: int, ts: int) -> None:
    conn = db_connect()
    try:
        conn.execute(
            "UPDATE users SET last_drop_ts=?, total_drops=total_drops+1 WHERE user_id=?",
            (ts, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def add_to_collection(user_id: int, gift_key: str) -> None:
    g = GIFTS_BY_KEY.get(gift_key)
    add_xp = g.xp if g else 100
    conn = db_connect()
    try:
        conn.execute(
            "INSERT INTO collection (user_id, gift_key, obtained_ts, is_favorite) VALUES (?, ?, ?, 0)",
            (user_id, gift_key, int(time.time())),
        )
        conn.execute(
            "UPDATE users SET xp = xp + ? WHERE user_id = ?",
            (add_xp, user_id)
        )
        conn.commit()
    finally:
        conn.close()


def sell_from_pending(user_id: int, gift_key: str, stars: int) -> None:
    g = GIFTS_BY_KEY.get(gift_key)
    add_xp = (g.xp // 2) if g else 50
    conn = db_connect()
    try:
        conn.execute(
            "UPDATE users SET balance_stars=balance_stars+?, total_sold=total_sold+1, xp=xp+? WHERE user_id=?",
            (stars, add_xp, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_user_collection(user_id: int) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM collection WHERE user_id=? ORDER BY is_favorite DESC, id DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def get_user_by_target(target: str) -> Optional[sqlite3.Row]:
    """Находит пользователя по user_id, id_num или @username."""
    conn = db_connect()
    try:
        target = target.strip()
        if target.startswith("@"):
            uname = target.lstrip("@").lower()
            return conn.execute("SELECT * FROM users WHERE LOWER(username)=?", (uname,)).fetchone()
        elif target.isdigit():
            val = int(target)
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (val,)).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM users WHERE id_num=?", (val,)).fetchone()
            return row
        return None
    finally:
        conn.close()


def toggle_privacy_setting(user_id: int, field: str) -> bool:
    if field not in ("hide_top", "hide_collection"):
        return False
    conn = db_connect()
    try:
        row = conn.execute(f"SELECT {field} FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return False
        new_val = 1 if row[field] == 0 else 0
        conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (new_val, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def get_collection_item(item_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM collection WHERE id=?", (item_id,)).fetchone()
    finally:
        conn.close()


def toggle_favorite(item_id: int, user_id: int) -> bool:
    conn = db_connect()
    try:
        item = conn.execute("SELECT * FROM collection WHERE id=? AND user_id=?", (item_id, user_id)).fetchone()
        if not item:
            return False

        if not item["is_favorite"]:
            fav_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM collection WHERE user_id=? AND is_favorite=1",
                (user_id,)
            ).fetchone()["cnt"]
            if fav_count >= 7:
                return False
            conn.execute("UPDATE collection SET is_favorite=1 WHERE id=?", (item_id,))
        else:
            conn.execute("UPDATE collection SET is_favorite=0 WHERE id=?", (item_id,))

        conn.commit()
        return True
    finally:
        conn.close()


def remove_from_collection(item_id: int, user_id: int) -> None:
    conn = db_connect()
    try:
        conn.execute("DELETE FROM collection WHERE id=? AND user_id=?", (item_id, user_id))
        conn.commit()
    finally:
        conn.close()


def add_user_stars(user_id: int, stars: int) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE users SET balance_stars=balance_stars+? WHERE user_id=?", (stars, user_id))
        conn.commit()
    finally:
        conn.close()


def deduct_user_stars(user_id: int, stars: int) -> bool:
    conn = db_connect()
    try:
        row = conn.execute("SELECT balance_stars FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or row["balance_stars"] < stars:
            return False
        conn.execute("UPDATE users SET balance_stars=balance_stars-? WHERE user_id=?", (stars, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def claim_daily_bonus(user_id: int) -> Optional[int]:
    conn = db_connect()
    try:
        row = conn.execute("SELECT last_daily_bonus_ts FROM users WHERE user_id=?", (user_id,)).fetchone()
        now = int(time.time())
        day_sec = 24 * 3600
        if row and (now - row["last_daily_bonus_ts"] < day_sec):
            return day_sec - (now - row["last_daily_bonus_ts"])

        conn.execute(
            "UPDATE users SET balance_stars=balance_stars+50, xp=xp+250, last_daily_bonus_ts=? WHERE user_id=?",
            (now, user_id),
        )
        conn.commit()
        return None
    finally:
        conn.close()


def get_favorites(user_id: int) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM collection WHERE user_id=? AND is_favorite=1 LIMIT 7",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def get_user_rank(user_id: int) -> int:
    conn = db_connect()
    try:
        rows = conn.execute("SELECT user_id FROM users ORDER BY balance_stars DESC, xp DESC").fetchall()
        for idx, r in enumerate(rows, start=1):
            if r["user_id"] == user_id:
                return idx
        return 1
    finally:
        conn.close()


def get_top_users(limit: int = 10) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE hide_top=0 ORDER BY balance_stars DESC, xp DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()


def create_pending_drop(user_id: int, chat_id: int, gift_key: str) -> int:
    conn = db_connect()
    try:
        cur = conn.execute(
            "INSERT INTO pending_drops (user_id, chat_id, gift_key, created_ts) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, gift_key, int(time.time())),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_pending_drop(drop_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM pending_drops WHERE id=?", (drop_id,)).fetchone()
    finally:
        conn.close()


def resolve_pending_drop(drop_id: int) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE pending_drops SET resolved=1 WHERE id=?", (drop_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# РЕНДЕР КАРТОЧЕК И БАННЕРОВ (Canvas Pillow Engine)
# ---------------------------------------------------------------------------

def draw_rounded_rect(draw, coords, radius, fill=None, outline=None, width=1):
    draw.rounded_rectangle(coords, radius=radius, fill=fill, outline=outline, width=width)


def make_default_avatar(size: int = 200, text: str = "Player") -> Image.Image:
    img = Image.new("RGBA", (size, size), (43, 36, 74, 255))
    draw = ImageDraw.Draw(img)

    head_r = int(size * 0.22)
    cx, cy = size // 2, int(size * 0.38)
    draw.ellipse([cx - head_r, cy - head_r, cx + head_r, cy + head_r], fill=(225, 227, 238, 255))

    body_r = int(size * 0.36)
    bcy = int(size * 0.82)
    draw.ellipse([cx - body_r, bcy - body_r, cx + body_r, bcy + body_r], fill=(225, 227, 238, 255))

    font = None
    if FONT_BOLD_PATH.exists():
        try: font = ImageFont.truetype(str(FONT_BOLD_PATH), 22)
        except: pass
    if not font: font = ImageFont.load_default()

    draw.text((size // 6, size - 36), text[:8], font=font, fill=(255, 255, 255, 230))
    return img


def load_font(size: int, bold: bool = False):
    p = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    if p.exists():
        try:
            return ImageFont.truetype(str(p), size)
        except Exception:
            pass
    return ImageFont.load_default()


async def generate_main_menu_banner() -> io.BytesIO:
    """Генерирует стильное графическое изображение для главного меню."""
    WIDTH, HEIGHT = 1000, 320
    img = Image.new("RGBA", (WIDTH, HEIGHT), (27, 36, 48, 255))
    draw = ImageDraw.Draw(img)

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([300, -100, 700, 300], fill=(45, 55, 85, 180))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    f_title = load_font(54, bold=True)
    f_sub = load_font(24, bold=False)

    draw.text((WIDTH // 2, 110), "New NFT", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 180), "NFT Gift Bot — Выбивай и собирай редчайшие гифты", font=f_sub, fill=(234, 179, 8), anchor="mm")

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.name = "menu.png"
    bio.seek(0)
    return bio


async def generate_profile_card_image(
    user_name: str,
    user_sys_id: int,
    stars_balance: int,
    user_xp: int,
    rank: int,
    favorite_gifts: List[GiftDef],
    avatar_bytes: Optional[bytes] = None,
) -> io.BytesIO:
    WIDTH, HEIGHT = 1000, 560

    clean_name = normalize_telegram_name(user_name)
    base_bg = Image.new("RGBA", (WIDTH, HEIGHT), (27, 36, 48, 255))

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([20, 20, 320, 320], fill=(20, 25, 45, 220))
    glow = glow.filter(ImageFilter.GaussianBlur(35))
    base_bg = Image.alpha_composite(base_bg, glow)

    draw = ImageDraw.Draw(base_bg)

    font_title = load_font(44, bold=True)
    font_sub = load_font(24, bold=True)
    font_small = load_font(20, bold=False)
    font_stat_val = load_font(36, bold=True)
    font_stat_lbl = load_font(18, bold=True)

    av_size = 200
    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = ImageOps.fit(av_img, (av_size, av_size))
        except Exception:
            av_img = make_default_avatar(av_size, clean_name[:10])
    else:
        av_img = make_default_avatar(av_size, clean_name[:10])

    mask = Image.new("L", (av_size, av_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, av_size, av_size], radius=24, fill=255)
    
    av_x, av_y = 55, 75
    base_bg.paste(av_img, (av_x, av_y), mask)

    text_x = 300
    draw.text((text_x, 85), clean_name, font=font_title, fill=(255, 255, 255))

    lvl, cur_xp, req_xp, ratio = calculate_xp_level_info(user_xp)
    draw.text((text_x, 142), f"{lvl} УРОВЕНЬ ({cur_xp}/{req_xp} XP)", font=font_sub, fill=(255, 255, 255))

    bar_x, bar_y, bar_w, bar_h = text_x, 180, 360, 12
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=(55, 65, 80))
    fill_w = max(10, int(bar_w * ratio))
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=6, fill=(234, 179, 8))

    draw.text((820, 90), f"ID: {user_sys_id}", font=font_small, fill=(140, 155, 175))
    draw.line([(text_x, 215), (940, 215)], fill=(45, 57, 74), width=1)

    stats_y = 230
    draw.rectangle([text_x, stats_y, text_x + 4, stats_y + 18], fill=(234, 179, 8))
    draw.text((text_x + 12, stats_y - 2), "ТОП ПО БАЛАНСУ 🪙", font=font_stat_lbl, fill=(140, 155, 175))
    draw.text((text_x + 12, stats_y + 24), f"#{rank}", font=font_stat_val, fill=(255, 255, 255))

    draw.line([(55, 305), (940, 305)], fill=(45, 57, 74), width=1)
    draw.text((55, 320), "СОСТАВ", font=font_stat_lbl, fill=(140, 155, 175))

    slot_y = 348
    slot_w, slot_h = 115, 115
    spacing = 14
    start_x = 55

    for i in range(7):
        cur_x = start_x + i * (slot_w + spacing)
        draw_rounded_rect(draw, [cur_x, slot_y, cur_x + slot_w, slot_y + slot_h], radius=16, fill=(20, 26, 36))

        if i < len(favorite_gifts):
            g = favorite_gifts[i]
            img_p = gift_image_path(g.key)
            if img_p and img_p.exists():
                try:
                    g_img = Image.open(img_p).convert("RGBA")
                    g_img.thumbnail((80, 80))
                    gx = cur_x + (slot_w - g_img.width) // 2
                    gy = slot_y + (slot_h - g_img.height) // 2
                    base_bg.paste(g_img, (gx, gy), g_img)
                except Exception as e:
                    log.warning("Ошибка обработки картинки подарка: %s", e)
        else:
            cx, cy = cur_x + slot_w // 2, slot_y + slot_h // 2
            arm = 16
            thick = 6
            draw.line([(cx - arm, cy - arm), (cx + arm, cy + arm)], fill=(225, 45, 45), width=thick)
            draw.line([(cx + arm, cy - arm), (cx - arm, cy + arm)], fill=(225, 45, 45), width=thick)

    bio = io.BytesIO()
    base_bg.save(bio, "PNG")
    bio.name = "profile.png"
    bio.seek(0)
    return bio


# ---------------------------------------------------------------------------
# Клавиатуры навигации
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection"),
            InlineKeyboardButton("🎰 Кейс (100⭐)", callback_data="nav_opencase"),
        ],
        [
            InlineKeyboardButton("🎁 Ежедневный бонус", callback_data="nav_bonus"),
            InlineKeyboardButton("🏆 ТОП Игроков", callback_data="nav_top"),
        ],
        [
            InlineKeyboardButton("🔒 Приватность", callback_data="nav_privacy_settings"),
            InlineKeyboardButton("📜 Политика", callback_data="nav_policy"),
        ],
        [
            InlineKeyboardButton("🏬 Рынок NFT (Скоро)", callback_data="nav_market"),
        ]
    ])


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в главное меню", callback_data="nav_main")]
    ])


# ---------------------------------------------------------------------------
# Команды и обработчики
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.first_name)
    banner_img = await generate_main_menu_banner()
    await update.message.reply_photo(
        photo=InputFile(banner_img, filename="menu.png"),
        caption=(
            f"👋 <b>Привет, {user.first_name}! Добро пожаловать в New NFT!</b>\n\n"
            "Пиши слово <code>nft</code> или <code>подарок</code> в чатах, "
            "чтобы выбивать редчайшие Telegram Gifts! 🎁\n\n"
            "• Собирай уникальные NFT в коллекцию\n"
            "• Добавляй их в Избранное карточки профиля\n"
            "• Продавай подарки за Stars и открывай Mystery Cases!\n\n"
            "Для управления нажилай на кнопки меню ниже:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username, user.first_name)
    cleaned_name = normalize_telegram_name(user.first_name or "User")

    avatar_bytes = None
    try:
        photos = await context.bot.get_user_profile_photos(user.id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            tg_file = await context.bot.get_file(file_id)
            file_bytes_io = io.BytesIO()
            await tg_file.download_to_memory(file_bytes_io)
            avatar_bytes = file_bytes_io.getvalue()
    except Exception as e:
        log.warning("Аватар недоступен: %s", e)

    fav_rows = get_favorites(user.id)
    fav_gifts = [GIFTS_BY_KEY[r["gift_key"]] for r in fav_rows if r["gift_key"] in GIFTS_BY_KEY]
    rank = get_user_rank(user.id)
    lvl, cur_xp, req_xp, _ = calculate_xp_level_info(db_user["xp"])

    card_img = await generate_profile_card_image(
        cleaned_name,
        db_user["id_num"],
        db_user["balance_stars"],
        db_user["xp"],
        rank,
        fav_gifts,
        avatar_bytes,
    )

    caption = (
        f"👤 <b>Профиль игрока {cleaned_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎖 Уровень: <b>{lvl} Уровень ({cur_xp}/{req_xp} XP)</b>\n"
        f"🏆 ТОП по Звёздам: <b>#{rank}</b>\n"
        f"💰 Баланс Stars: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n"
        f"🎲 Выбито всего NFT: <b>{db_user['total_drops']}</b> шт.\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_photo(
        photo=InputFile(card_img, filename="profile.png"),
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )


async def show_privacy_settings(update_or_query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    hide_top = "✅ Да" if db_user["hide_top"] else "❌ Нет"
    hide_coll = "✅ Да" if db_user["hide_collection"] else "❌ Нет"

    text = (
        "⚙️ <b>Настройки приватности профиля</b>\n\n"
        f"• Скрывать из ТОПа: <b>{hide_top}</b>\n"
        f"• Скрывать коллекцию: <b>{hide_coll}</b>\n\n"
        "Нажмите кнопку ниже, чтобы изменить параметр:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ТОП: {hide_top}", callback_data="toggle_privacy:hide_top")],
        [InlineKeyboardButton(f"Коллекция: {hide_coll}", callback_data="toggle_privacy:hide_collection")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
    ])

    if hasattr(update_or_query, "message") and update_or_query.message:
        if update_or_query.message.photo:
            await update_or_query.message.delete()
            await update_or_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await update_or_query.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    policy_text = (
        "📜 <b>Политика конфиденциальности & Приватность</b>\n\n"
        "1. <b>Сбор данных:</b> Бот сохраняет только публичные ID, Username и Имя в Telegram для создания профиля и вашей базы инвентаря.\n"
        "2. <b>Защита информации:</b> Данные никогда не передаются третьим лицам.\n"
        "3. <b>Настройки видимости:</b> Вы можете скрыть свой профиль из ТОПа и запретить просмотр вашей коллекции в меню 'Приватность'."
    )
    await update.message.reply_text(policy_text, parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())


async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.effective_user
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ <b>Использование:</b> <code>/pay <ID или @username> <сумма_stars></code>", parse_mode=ParseMode.HTML)
        return

    target_str, amount_str = args[0], args[1]
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await update.message.reply_text("❌ Введите корректную сумму Stars.")
        return

    amount = int(amount_str)
    target_user = get_user_by_target(target_str)

    if not target_user:
        await update.message.reply_text("❌ Игрок не найден в базе данных.")
        return

    if target_user["user_id"] == sender.id:
        await update.message.reply_text("❌ Нельзя переводить Stars самому себе.")
        return

    if not deduct_user_stars(sender.id, amount):
        await update.message.reply_text("❌ Недостаточно Stars на вашем балансе.")
        return

    add_user_stars(target_user["user_id"], amount)
    receiver_name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")
    await update.message.reply_text(
        f"💸 <b>Успешный перевод!</b>\nВы перевели <b>{amount} ⭐</b> игроку <b>{receiver_name}</b>.",
        parse_mode=ParseMode.HTML
    )


async def cmd_send_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.effective_user
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ <b>Использование:</b> <code>/send_gift <ID_предмета> <ID_получателя или @username></code>", parse_mode=ParseMode.HTML)
        return

    item_id_str, target_str = args[0], args[1]
    if not item_id_str.isdigit():
        await update.message.reply_text("❌ Укажите числовой ID предмета из коллекции.")
        return

    item_id = int(item_id_str)
    item = get_collection_item(item_id)
    if not item or item["user_id"] != sender.id:
        await update.message.reply_text("❌ Предмет с таким ID не найден в вашей коллекции.")
        return

    target_user = get_user_by_target(target_str)
    if not target_user:
        await update.message.reply_text("❌ Игрок-получатель не найден в базе.")
        return

    if target_user["user_id"] == sender.id:
        await update.message.reply_text("❌ Нельзя отправлять подарок самому себе.")
        return

    g = GIFTS_BY_KEY.get(item["gift_key"])
    remove_from_collection(item_id, sender.id)
    add_to_collection(target_user["user_id"], item["gift_key"])

    receiver_name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")
    await update.message.reply_text(
        f"🎁 <b>Подарок передан!</b>\nВы успешно отправили <b>{g.name if g else item['gift_key']}</b> игроку <b>{receiver_name}</b>!",
        parse_mode=ParseMode.HTML
    )


async def show_collection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    items = get_user_collection(user.id)

    if not items:
        await update.message.reply_text(
            "🗂 <b>Твоя коллекция пока пуста.</b>\n\n"
            "Напиши <code>nft</code> в группе или открой Mystery Case за Stars!",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )
        return

    buttons = []
    for item in items[:20]:
        g = GIFTS_BY_KEY.get(item["gift_key"])
        if not g:
            continue
        fav_star = "⭐ " if item["is_favorite"] else ""
        btn_text = f"{fav_star}{rarity_emoji(g.chance)} {g.name} ({g.stars}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_item:{item['id']}")])

    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")])
    kb = InlineKeyboardMarkup(buttons)

    text = f"🗂 <b>Твоя NFT-Коллекция ({len(items)} шт.):</b>\nНажми на предмет для подробностей:"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def show_collection_from_callback(query, user_id: int) -> None:
    items = get_user_collection(user_id)

    if not items:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Открыть кейс (100⭐)", callback_data="nav_opencase")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
        ])
        msg_text = (
            "🗂 <b>Твоя коллекция пока пуста.</b>\n\n"
            "Выбей свой первый NFT-подарок командой <code>nft</code>!"
        )
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    buttons = []
    for item in items[:20]:
        g = GIFTS_BY_KEY.get(item["gift_key"])
        if not g:
            continue
        fav_star = "⭐ " if item["is_favorite"] else ""
        btn_text = f"{fav_star}{rarity_emoji(g.chance)} {g.name} ({g.stars}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_item:{item['id']}")])

    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")])
    kb = InlineKeyboardMarkup(buttons)
    text = f"🗂 <b>Твоя NFT-Коллекция ({len(items)} шт.):</b>\nВыбери NFT для просмотра:"

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or msg.text is None:
        return

    text_lower = msg.text.strip().lower()

    if text_lower in ("профиль", "profile", "кто я"):
        await show_profile(update, context)
        return
    if text_lower in ("коллекция", "collection", "инвентарь"):
        await show_collection(update, context)
        return

    is_trigger = any(trig in text_lower for trig in TRIGGER_WORDS)
    if not is_trigger:
        return

    user = update.effective_user
    row = get_or_create_user(user.id, user.username, user.first_name)

    now = int(time.time())
    if COOLDOWN_ENABLED:
        remaining = row["last_drop_ts"] + COOLDOWN_SECONDS - now
        if remaining > 0:
            await msg.reply_text(f"⏳ Рано! Команду NFT можно использовать только 1 раз в час.\nПопробуй снова через {seconds_to_hms(remaining)}.")
            return

    set_last_drop(user.id, now)

    if random.random() > DROP_CHANCE:
        await msg.reply_text("💨 Увы, в этот раз ничего не выпало. Попробуй ещё раз через час!")
        return

    gift = roll_gift()
    drop_id = create_pending_drop(user.id, update.effective_chat.id, gift.key)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Сохранить в коллекцию", callback_data=f"keep:{drop_id}"),
            InlineKeyboardButton("💰 Продать за Stars", callback_data=f"sell:{drop_id}"),
        ]
    ])

    caption = (
        f"🎉 <b>{user.first_name}</b>, тебе выпал NFT-подарок!\n\n"
        f"{rarity_emoji(gift.chance)} <b>{gift.name}</b>\n"
        f"• Редкость: <b>{rarity_label(gift.chance)}</b> ({gift.chance:.2f}%)\n"
        f"• Награда XP: <b>+{gift.xp} XP</b>\n"
        f"• Оценка: {fmt_stars_rub(gift.stars)} / {fmt_ton(gift.ton)}\n\n"
        f"Выбери действие ниже:"
    )

    img_path = gift_image_path(gift.key)
    sent_photo = False
    if img_path:
        try:
            with open(img_path, "rb") as f:
                await msg.reply_photo(
                    photo=InputFile(f, filename=img_path.name),
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            sent_photo = True
        except Exception as e:
            log.error("Ошибка отправки фото подарка: %s", e)

    if not sent_photo:
        await msg.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    user = query.from_user

    if query.message.chat.type != "private" and data in ("nav_opencase", "nav_top", "nav_market", "nav_privacy_settings"):
        await query.answer("⚠️ Эта функция доступна только в личных сообщениях с ботом!", show_alert=True)
        return

    if data == "nav_main":
        banner_img = await generate_main_menu_banner()
        if query.message.photo:
            await query.message.delete()
        await query.message.reply_photo(
            photo=InputFile(banner_img, filename="menu.png"),
            caption="🏠 <b>Главное меню:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )
        return

    if data == "nav_privacy_settings":
        await show_privacy_settings(query, user.id)
        return

    if data == "nav_policy":
        policy_text = (
            "📜 <b>Политика конфиденциальности & Приватность</b>\n\n"
            "1. <b>Сбор данных:</b> Бот сохраняет только публичные ID, Username и Имя в Telegram для создания профиля и вашей базы инвентаря.\n"
            "2. <b>Защита информации:</b> Данные никогда не передаются третьим лицам.\n"
            "3. <b>Настройки видимости:</b> Вы можете скрыть свой профиль из ТОПа и запретить просмотр вашей коллекции в меню 'Приватность'."
        )
        kb = back_to_main_keyboard()
        if query.message.photo:
            await query.message.reply_text(policy_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(policy_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("toggle_privacy:"):
        field = data.split(":", 1)[1]
        toggle_privacy_setting(user.id, field)
        await show_privacy_settings(query, user.id)
        return

    if data == "nav_market":
        kb = back_to_main_keyboard()
        msg_text = (
            "🚧 <b>Раздел 'Рынок NFT' в разработке!</b>\n\n"
            "Совсем скоро здесь можно будет выставлять свои подарки на продажу за Stars "
            "и покупать эксклюзивы у других игроков!"
        )
        if query.message.photo:
            await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "nav_collection":
        await show_collection_from_callback(query, user.id)
        return

    if data == "nav_bonus":
        remaining = claim_daily_bonus(user.id)
        if remaining is None:
            text = "🎁 <b>Поздравляем!</b> Ты получил бонус: <b>+50 Stars ⭐</b> и <b>+250 XP ⚡️</b>!"
        else:
            text = f"⏳ Ежедневный бонус уже получен. Следующий доступен через {seconds_to_hms(remaining)}."

        kb = back_to_main_keyboard()
        if query.message.photo:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "nav_top":
        top_users = get_top_users(10)
        lines = ["🏆 <b>Глобальный ТОП Игроков по Балансу Stars</b>\n━━━━━━━━━━━━━━━━━━"]
        for idx, u in enumerate(top_users, start=1):
            medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"<b>#{idx}</b>"
            name = normalize_telegram_name(u['first_name'] or u['username'] or 'Игрок')
            lvl, _, _, _ = calculate_xp_level_info(u['xp'])
            lines.append(f"{medal} <b>{name}</b> — <b>{u['balance_stars']:,} ⭐</b> (Ур. {lvl})")
        lines.append("━━━━━━━━━━━━━━━━━━")

        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
        else:
            await query.edit_message_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
        return

    if data == "nav_opencase":
        case_price = 100
        if not deduct_user_stars(user.id, case_price):
            msg_text = (
                f"❌ <b>Недостаточно Stars!</b>\nСтоимость открытия кейса: <b>{case_price} ⭐</b>.\n"
                f"Забери ежедневный бонус или продай NFT из коллекции!"
            )
            if query.message.photo:
                await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
            else:
                await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
            return

        won_gift = roll_gift()
        add_to_collection(user.id, won_gift.key)

        cap = (
            f"🎰 <b>Открытие Mystery Case!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎉 Тебе выпал: {rarity_emoji(won_gift.chance)} <b>{won_gift.name}</b>!\n"
            f"• Редкость: <b>{rarity_label(won_gift.chance)}</b>\n"
            f"• Награда: <b>+{won_gift.xp} XP</b>\n"
            f"• Стоимость: {fmt_stars_rub(won_gift.stars)}\n\n"
            f"✅ Предмет автоматически добавлен в твою коллекцию!"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Открыть еще раз (100⭐)", callback_data="nav_opencase")],
            [InlineKeyboardButton("🗂 Перейти в коллекцию", callback_data="nav_collection")],
            [InlineKeyboardButton("⬅️ Меню", callback_data="nav_main")],
        ])

        img_p = gift_image_path(won_gift.key)
        if img_p:
            try:
                with open(img_p, "rb") as f:
                    await query.message.reply_photo(photo=InputFile(f, filename=img_p.name), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                return
            except Exception as e:
                log.error("Fallback кейса: %s", e)

        await query.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if ":" in data:
        action, arg = data.split(":", 1)

        if action in ("keep", "sell"):
            drop_id = int(arg)
            drop = get_pending_drop(drop_id)
            if not drop or drop["user_id"] != user.id:
                await query.answer("❌ Это не твой подарок!", show_alert=True)
                return
            if drop["resolved"]:
                await query.answer("⚠️ Этот подарок уже обработан!", show_alert=True)
                return

            gift = GIFTS_BY_KEY.get(drop["gift_key"])
            resolve_pending_drop(drop_id)

            if action == "keep":
                add_to_collection(user.id, gift.key)
                res = f"✅ <b>{gift.name}</b> сохранён в вашей коллекции! (+{gift.xp} XP)"
            else:
                sell_from_pending(user.id, gift.key, gift.stars)
                res = f"💰 Вы продали <b>{gift.name}</b> за {fmt_stars_rub(gift.stars)}! (+{gift.xp // 2} XP)"

            if query.message.photo:
                await query.edit_message_caption(caption=res, parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text(res, parse_mode=ParseMode.HTML)
            return

        if action == "view_item":
            item_id = int(arg)
            item = get_collection_item(item_id)
            if not item or item["user_id"] != user.id:
                await query.answer("Предмет не найден.", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            fav_text = "❌ Убрать из Избранного" if item["is_favorite"] else "⭐ В избранное профиля"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav:{item_id}")],
                [
                    InlineKeyboardButton("🔄 Обменять (Скоро)", callback_data=f"trade_item:{item_id}"),
                    InlineKeyboardButton("💰 Продать", callback_data=f"sell_item:{item_id}")
                ],
                [InlineKeyboardButton("⬅️ Назад в коллекцию", callback_data="nav_collection")]
            ])

            cap = (
                f"{rarity_emoji(g.chance)} <b>{g.name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• Редкость: <b>{rarity_label(g.chance)}</b> ({g.chance:.2f}%)\n"
                f"• Ценность XP: <b>+{g.xp} XP</b>\n"
                f"• Стоимость в Stars: {fmt_stars_rub(g.stars)}\n"
                f"• Стоимость в TON: {fmt_ton(g.ton)}\n"
                f"• В Избранном карточки: <b>{'Да ⭐' if item['is_favorite'] else 'Нет'}</b>\n"
                f"━━━━━━━━━━━━━━━━━━"
            )

            img_p = gift_image_path(g.key)
            if img_p:
                try:
                    with open(img_p, "rb") as f:
                        await query.message.reply_photo(
                            photo=InputFile(f, filename=img_p.name),
                            caption=cap,
                            parse_mode=ParseMode.HTML,
                            reply_markup=kb,
                        )
                    await query.message.delete()
                    return
                except Exception as e:
                    log.error("Error photo item view: %s", e)

            await query.edit_message_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        if action == "toggle_fav":
            item_id = int(arg)
            success = toggle_favorite(item_id, user.id)
            if success:
                await query.answer("Избранное обновлено!")
                item = get_collection_item(item_id)
                g = GIFTS_BY_KEY.get(item["gift_key"])
                fav_text = "❌ Убрать из Избранного" if item["is_favorite"] else "⭐ В избранное профиля"
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav:{item_id}")],
                    [
                        InlineKeyboardButton("🔄 Обменять (Скоро)", callback_data=f"trade_item:{item_id}"),
                        InlineKeyboardButton("💰 Продать", callback_data=f"sell_item:{item_id}")
                    ],
                    [InlineKeyboardButton("⬅️ Назад в коллекцию", callback_data="nav_collection")]
                ])
                cap = (
                    f"{rarity_emoji(g.chance)} <b>{g.name}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"• Редкость: <b>{rarity_label(g.chance)}</b> ({g.chance:.2f}%)\n"
                    f"• Ценность XP: <b>+{g.xp} XP</b>\n"
                    f"• Стоимость в Stars: {fmt_stars_rub(g.stars)}\n"
                    f"• Стоимость в TON: {fmt_ton(g.ton)}\n"
                    f"• В Избранном карточки: <b>{'Да ⭐' if item['is_favorite'] else 'Нет'}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                if query.message.photo:
                    await query.edit_message_caption(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                else:
                    await query.edit_message_text(caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await query.answer("Максимум 7 предметов в Избранном!", show_alert=True)
            return

        if action == "sell_item":
            item_id = int(arg)
            item = get_collection_item(item_id)
            if not item or item["user_id"] != user.id:
                await query.answer("Ошибка продажи.", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            remove_from_collection(item_id, user.id)
            add_user_stars(user.id, g.stars)

            await query.message.reply_text(
                f"💸 <b>Продано!</b>\nТы продал <b>{g.name}</b> за {fmt_stars_rub(g.stars)}!",
                parse_mode=ParseMode.HTML,
                reply_markup=back_to_main_keyboard()
            )
            await query.message.delete()
            return

        if action == "trade_item":
            await query.answer("🚧 Раздел обмена в разработке!", show_alert=True)
            return


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

def main() -> None:
    db_init()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", show_profile))
    app.add_handler(CommandHandler("collection", show_collection))
    app.add_handler(CommandHandler("privacy", cmd_privacy))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("send_gift", cmd_send_gift))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_group_message))

    log.info("Бот успешно запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()