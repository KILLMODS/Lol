#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NFT-Gift Bot v8.6 — Admin Panel, Extended Analytics & Clan Teaser Release.
- Сохранение базы данных SQLite в локальном хранилище (не сбрасывается при перезапуске).
- Полноценная Админ-Панель для ID 1934988350 и 7459502130 (/admin).
- Полный набор классов, включая GiftDef, ролл предметов и расчёт уровней.
- Переработанный баланс экономики и разделы инвентаря/маркета.
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
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = BASE_DIR / "images"
FONTS_DIR = BASE_DIR / "fonts"
DB_PATH = DATA_DIR / "base.db"

DATA_DIR.mkdir(exist_ok=True)
FONTS_DIR.mkdir(exist_ok=True)
IMAGES_DIR.mkdir(exist_ok=True)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9036416244:AAGrJgI3jzMMU5bn6Q36r8cNBIJqGxniXmo")
ADMIN_IDS = [1934988350, 7459502130]

COOLDOWN_SECONDS = 1 * 60 * 60          # 1 час (3600 секунд)
COOLDOWN_ENABLED = True                 # Ограничение включено: 1 раз в час
CHAT_DROP_CHANCE = 0.85                 # Шанс выпадения подарка в чате (85%)
STAR_RUB_RATE = 1.5                     # 1 Star = 1.5 RUB
TON_RUB_RATE = 100.0                    # 1 TON = 100 RUB

# Состояния для диалогов
WAITING_ADMIN_GIVE_STARS = 1
WAITING_ADMIN_GIVE_GIFT_USER = 2

# Состояния для создания клана
WAITING_CLAN_TAG = 10
WAITING_CLAN_NAME = 11
WAITING_CLAN_DESC = 12
WAITING_CLAN_TYPE = 13
WAITING_CLAN_PRICE = 14

CLAN_CREATE_LEVEL_REQ = 10
CLAN_CREATE_COST = 150_000

# Цены расширения мест в клане: (target_slots, cost)
CLAN_SLOT_UPGRADES = [
    (30, 100_000),
    (45, 500_000),
    (60, 2_000_000),
]

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("nft_bot")

# ---------------------------------------------------------------------------
# Загрузка Unicode-шрифтов
# ---------------------------------------------------------------------------

FONT_REGULAR_PATH = FONTS_DIR / "NotoSans.ttf"
FONT_BOLD_PATH = FONTS_DIR / "NotoSans-Bold.ttf"

def ensure_fonts_exist():
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
# ОПРЕДЕЛЕНИЕ КЛАССА GIFTDEF И ПОДАРКОВ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GiftDef:
    key: str
    name: str
    stars: int          # Цена в Telegram Stars
    chance: float       # Вероятность выпадения
    xp: int             # Опыт за получение
    is_nft: bool = True # Флаг NFT/Обычный предмет

    @property
    def ton(self) -> float:
        return round((self.stars * STAR_RUB_RATE) / TON_RUB_RATE, 3)

    @property
    def rub(self) -> float:
        return round(self.stars * STAR_RUB_RATE, 2)


GIFTS: list[GiftDef] = [
    # Ультра-легендарные (NFT)
    GiftDef("pepe_heart", "Plush Pepe", 455_600, 0.0005, 100_000, is_nft=True),
    GiftDef("trophy_cup", "Algorithm Cup", 81_733, 0.015, 35_000, is_nft=True),
    GiftDef("intelligence_cup", "Intelligence Cup", 83_750, 0.015, 35_000, is_nft=True),
    GiftDef("heart_lock_key", "Heart Locket", 87_100, 0.02, 25_000, is_nft=True),
    GiftDef("hero_figure", "Durov's Figurine", 35_000, 0.03, 20_000, is_nft=True),
    GiftDef("resistance_dog", "Resistance Dog", 34_166, 0.03, 20_000, is_nft=True),
    GiftDef("cap_tg", "Durov's Cap", 28_333, 0.04, 18_000, is_nft=True),
    GiftDef("hockey_mask", "Scared Cat", 19_333, 0.05, 12_000, is_nft=True),
    GiftDef("precious_peach", "Precious Peach", 18_446, 0.06, 11_000, is_nft=True),
    GiftDef("heroic_helmet", "Heroic Helmet", 13_200, 0.08, 9_000, is_nft=True),
    GiftDef("sunglasses", "Durov's Glasses", 9_466, 0.10, 7_500, is_nft=True),
    GiftDef("briefcase", "Loot Bag", 9_322, 0.10, 7_500, is_nft=True),
    GiftDef("nail_bracelet", "Nail Bracelet", 9_233, 0.11, 7_000, is_nft=True),
    GiftDef("gem_crystal", "Astral Shard", 8_666, 0.12, 6_500, is_nft=True),
    GiftDef("perfume_bottle", "Perfume Bottle", 5_833, 0.20, 5_000, is_nft=True),
    GiftDef("ion_gem", "Ion Gem", 5_113, 0.22, 4_500, is_nft=True),
    GiftDef("low_rider", "Low Rider", 4_688, 0.25, 4_000, is_nft=True),
    GiftDef("gem_signet", "Gem Signet", 4_666, 0.25, 4_000, is_nft=True),
    GiftDef("swiss_watch", "Swiss Watch", 3_920, 0.30, 3_500, is_nft=True),
    GiftDef("sharp_tongue", "Sharp Tongue", 3_320, 0.35, 3_000, is_nft=True),
    GiftDef("crystal_eagle", "Rare Bird", 2_000, 0.50, 2_000, is_nft=True),
    GiftDef("khabibs_papakha", "Khabib's Papakha", 1_875, 0.55, 1_800, is_nft=True),

    # Обычные и классические подарки
    GiftDef("crystal_ball", "Crystal Ball", 920, 1.50, 750, is_nft=True),
    GiftDef("jester_hat", "Jester Hat", 900, 1.40, 700, is_nft=True),
    GiftDef("sandcastle", "Sandcastle", 900, 1.40, 700, is_nft=True),
    GiftDef("witch_hat", "Witch Hat", 900, 1.40, 700, is_nft=True),
    GiftDef("sakura_flower", "Sakura Flower", 850, 1.70, 650, is_nft=True),
    GiftDef("teddy_pumpkin", "Mad Pumpkin", 830, 2.00, 600, is_nft=True),
    GiftDef("hex_pot", "Hex Pot", 800, 1.80, 580, is_nft=True),
    GiftDef("lush_bouquet", "Lush Bouquet", 800, 1.80, 580, is_nft=True),
    GiftDef("coffin", "Gravestone", 660, 2.50, 450, is_nft=True),
    GiftDef("spring_basket", "Spring Basket", 650, 2.60, 440, is_nft=True),
    GiftDef("roses", "Roses", 600, 2.80, 400, is_nft=True),

    # Базовые мишки
    GiftDef("teddy_patrick", "Irish Bear", 50, 10.00, 50, is_nft=False),
    GiftDef("teddy_heart_white", "New Year's Bear", 50, 10.00, 50, is_nft=False),
    GiftDef("teddy_santa", "Santa Bear", 50, 10.00, 50, is_nft=False),
    GiftDef("teddy_football", "Football Bear", 50, 10.00, 50, is_nft=False),
    GiftDef("bunny_teddy", "Easter Bear", 50, 10.00, 50, is_nft=False),
    GiftDef("i_love_u_heart", "I love you", 50, 10.00, 50, is_nft=False),
    GiftDef("clown_teddy", "Clown Bear", 50, 10.00, 50, is_nft=False),
    GiftDef("toy_bear", "Toy Bear", 50, 10.00, 50, is_nft=False),
]

GIFTS_BY_KEY = {g.key: g for g in GIFTS}

# ---------------------------------------------------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ---------------------------------------------------------------------------

def normalize_telegram_name(name: str) -> str:
    if not name:
        return "Игрок"
    cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", name).strip()
    if not cleaned:
        cleaned = name.strip()
    normalized = unicodedata.normalize('NFKC', cleaned)
    res = []
    for char in normalized:
        if unicodedata.category(char) in ('So', 'Cn', 'Co'):
            continue
        res.append(char)
    final_str = "".join(res).strip()
    return final_str if final_str else "Игрок"

def fmt_stars_rub(stars: int) -> str:
    rub = round(stars * STAR_RUB_RATE, 1)
    return f"{stars:,} ⭐ (~{rub:,.1f} ₽)"

def fmt_ton(ton: float) -> str:
    return f"{ton:.2f} TON"

def rarity_emoji(chance: float) -> str:
    if chance <= 0.05: return "👑"
    if chance <= 0.20: return "🟣"
    if chance <= 0.90: return "🔷"
    if chance <= 3.00: return "🟢"
    return "⚪"

def rarity_label(chance: float) -> str:
    if chance <= 0.05: return "Ультра-легендарный"
    if chance <= 0.20: return "Эпический"
    if chance <= 0.90: return "Редкий"
    if chance <= 3.00: return "Необычный"
    return "Обычный"

def seconds_to_hms(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}ч {m}м {s}с"
    if m > 0:
        return f"{m}м {s}с"
    return f"{s}с"

def calculate_xp_level_info(xp: int) -> Tuple[int, int, int, float]:
    lvl = 1
    req = 500
    acc = 0
    while xp >= acc + req:
        acc += req
        lvl += 1
        req = int(req * 1.25)
    cur_xp = xp - acc
    ratio = min(1.0, max(0.0, cur_xp / req))
    return lvl, cur_xp, req, ratio

def gift_image_path(gift_key: str) -> Optional[Path]:
    for ext in (".png", ".jpg", ".webp"):
        p = IMAGES_DIR / f"{gift_key}{ext}"
        if p.exists():
            return p
    return None

def roll_gift_from_pool(pool: List[GiftDef]) -> GiftDef:
    weights = [1.0 / (g.chance + 0.0001) for g in pool]
    return random.choices(pool, weights=weights, k=1)[0]

def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
    return ImageFont.load_default()

def draw_rounded_rect(draw: ImageDraw.ImageDraw, xy: list, radius: int, fill: tuple):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)

def make_default_avatar(size: int, text: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), (45, 55, 72, 255))
    draw = ImageDraw.Draw(img)
    f = load_font(int(size * 0.4), bold=True)
    draw.text((size // 2, size // 2), text[:2].upper(), font=f, fill=(255, 255, 255), anchor="mm")
    return img

async def generate_main_menu_banner() -> io.BytesIO:
    WIDTH, HEIGHT = 1000, 320
    img = Image.new("RGBA", (WIDTH, HEIGHT), (20, 26, 38, 255))
    
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([200, -80, 800, 380], fill=(40, 70, 130, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img, glow)
    
    draw = ImageDraw.Draw(img)
    f_title = load_font(52, bold=True)
    f_sub = load_font(24, bold=False)

    draw.text((WIDTH // 2, 110), "NEW NFT MARKET & BOT", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 180), "Collect Gifts, Earn Stars and Build Your Empire", font=f_sub, fill=(234, 179, 8), anchor="mm")

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.name = "menu.png"
    bio.seek(0)
    return bio

async def generate_market_banner() -> io.BytesIO:
    WIDTH, HEIGHT = 1000, 320
    img = Image.new("RGBA", (WIDTH, HEIGHT), (20, 30, 45, 255))
    
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([250, -50, 750, 350], fill=(50, 80, 140, 160))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img, glow)
    
    draw = ImageDraw.Draw(img)
    f_title = load_font(52, bold=True)
    f_sub = load_font(24, bold=False)

    draw.text((WIDTH // 2, 110), "NFT & GIFT MARKET", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 180), "Trade and Collect Exclusive Items for Stars", font=f_sub, fill=(234, 179, 8), anchor="mm")

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.name = "market.png"
    bio.seek(0)
    return bio

# ---------------------------------------------------------------------------
# База данных SQLite (Фиксированное сохранение в data/base.db)
# ---------------------------------------------------------------------------

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def db_init() -> None:
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
                auto_sell INTEGER NOT NULL DEFAULT 0,
                max_inventory INTEGER NOT NULL DEFAULT 25,
                last_drop_ts INTEGER NOT NULL DEFAULT 0,
                last_daily_bonus_ts INTEGER NOT NULL DEFAULT 0,
                total_drops INTEGER NOT NULL DEFAULT 0,
                total_sold INTEGER NOT NULL DEFAULT 0,
                cases_opened INTEGER NOT NULL DEFAULT 0
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

            CREATE TABLE IF NOT EXISTS clans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER UNIQUE NOT NULL,
                tag TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                clan_type TEXT NOT NULL DEFAULT 'public', -- 'public', 'private', 'paid'
                join_price INTEGER NOT NULL DEFAULT 0,
                max_members INTEGER NOT NULL DEFAULT 15,
                created_ts INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clan_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER NOT NULL,
                user_id INTEGER UNIQUE NOT NULL,
                joined_ts INTEGER NOT NULL,
                FOREIGN KEY (clan_id) REFERENCES clans(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS clan_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clan_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_ts INTEGER NOT NULL,
                UNIQUE(clan_id, user_id)
            );
            """
        )
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "id_num" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN id_num INTEGER;")
        if "hide_top" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN hide_top INTEGER NOT NULL DEFAULT 0;")
        if "hide_collection" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN hide_collection INTEGER NOT NULL DEFAULT 0;")
        if "auto_sell" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN auto_sell INTEGER NOT NULL DEFAULT 0;")
        if "max_inventory" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN max_inventory INTEGER NOT NULL DEFAULT 25;")
        if "cases_opened" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN cases_opened INTEGER NOT NULL DEFAULT 0;")

        conn.commit()
    finally:
        conn.close()

def get_or_create_user(user_id: int, username: str, first_name: str) -> sqlite3.Row:
    conn = db_connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO users (user_id, username, first_name, xp, max_inventory) VALUES (?, ?, ?, 0, 25)",
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

def add_to_collection(user_id: int, gift_key: str) -> bool:
    g = GIFTS_BY_KEY.get(gift_key)
    add_xp = g.xp if g else 100
    conn = db_connect()
    try:
        user = conn.execute("SELECT max_inventory FROM users WHERE user_id=?", (user_id,)).fetchone()
        count = conn.execute("SELECT COUNT(*) as cnt FROM collection WHERE user_id=?", (user_id,)).fetchone()["cnt"]
        
        max_inv = user["max_inventory"] if user else 25
        if count >= max_inv:
            return False

        conn.execute(
            "INSERT INTO collection (user_id, gift_key, obtained_ts, is_favorite) VALUES (?, ?, ?, 0)",
            (user_id, gift_key, int(time.time())),
        )
        conn.execute("UPDATE users SET xp = xp + ? WHERE user_id = ?", (add_xp, user_id))
        conn.commit()
        return True
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

def sell_all_non_favorites(user_id: int) -> Tuple[int, int]:
    conn = db_connect()
    try:
        items = conn.execute("SELECT id, gift_key FROM collection WHERE user_id=? AND is_favorite=0", (user_id,)).fetchall()
        if not items:
            return 0, 0

        total_stars = 0
        ids_to_del = []
        for item in items:
            g = GIFTS_BY_KEY.get(item["gift_key"])
            if g:
                total_stars += g.stars
            ids_to_del.append(item["id"])

        conn.executemany("DELETE FROM collection WHERE id=?", [(i,) for i in ids_to_del])
        conn.execute("UPDATE users SET balance_stars=balance_stars+?, total_sold=total_sold+? WHERE user_id=?", 
                     (total_stars, len(ids_to_del), user_id))
        conn.commit()
        return len(ids_to_del), total_stars
    finally:
        conn.close()

def toggle_user_setting(user_id: int, field: str) -> bool:
    if field not in ("hide_top", "hide_collection", "auto_sell"):
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

def upgrade_inventory_capacity(user_id: int, cost: int, add_slots: int) -> bool:
    conn = db_connect()
    try:
        row = conn.execute("SELECT balance_stars, max_inventory FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or row["balance_stars"] < cost:
            return False
        conn.execute("UPDATE users SET balance_stars=balance_stars-?, max_inventory=max_inventory+? WHERE user_id=?",
                     (cost, add_slots, user_id))
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
            "UPDATE users SET balance_stars=balance_stars+25, xp=xp+150, last_daily_bonus_ts=? WHERE user_id=?",
            (now, user_id),
        )
        conn.commit()
        return None
    finally:
        conn.close()

def increment_cases_opened(user_id: int) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE users SET cases_opened=cases_opened+1 WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()

def get_admin_global_stats() -> dict:
    conn = db_connect()
    try:
        total_users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        total_stars = conn.execute("SELECT SUM(balance_stars) as s FROM users").fetchone()["s"] or 0
        total_items = conn.execute("SELECT COUNT(*) as cnt FROM collection").fetchone()["cnt"]
        total_drops = conn.execute("SELECT SUM(total_drops) as s FROM users").fetchone()["s"] or 0
        total_sold = conn.execute("SELECT SUM(total_sold) as s FROM users").fetchone()["s"] or 0
        total_cases = conn.execute("SELECT SUM(cases_opened) as s FROM users").fetchone()["s"] or 0

        items = conn.execute("SELECT gift_key FROM collection").fetchall()
        inventory_market_cap = 0
        for it in items:
            g = GIFTS_BY_KEY.get(it["gift_key"])
            if g:
                inventory_market_cap += g.stars

        total_market_cap = total_stars + inventory_market_cap

        return {
            "total_users": total_users,
            "total_stars": total_stars,
            "total_items": total_items,
            "total_drops": total_drops,
            "total_sold": total_sold,
            "total_cases": total_cases,
            "inventory_market_cap": inventory_market_cap,
            "total_market_cap": total_market_cap,
        }
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

def get_user_by_target(target: str) -> Optional[sqlite3.Row]:
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

def get_top_users_page(page: int = 1, page_size: int = 10) -> Tuple[list[sqlite3.Row], int]:
    conn = db_connect()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE hide_top=0").fetchone()["cnt"]
        total_pages = max(1, math.ceil(total / page_size))
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM users WHERE hide_top=0 ORDER BY balance_stars DESC, xp DESC LIMIT ? OFFSET ?",
            (page_size, offset)
        ).fetchall()
        return rows, total_pages
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
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ КЛАНОВ
# ---------------------------------------------------------------------------

def get_user_clan(user_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            """
            SELECT c.*, cm.joined_ts 
            FROM clan_members cm 
            JOIN clans c ON cm.clan_id = c.id 
            WHERE cm.user_id = ?
            """,
            (user_id,)
        ).fetchone()
    finally:
        conn.close()

def get_clan_members_count(clan_id: int) -> int:
    conn = db_connect()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM clan_members WHERE clan_id=?", (clan_id,)).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()

def get_clan_by_id(clan_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM clans WHERE id=?", (clan_id,)).fetchone()
    finally:
        conn.close()

def get_all_clans(page: int = 1, page_size: int = 8) -> Tuple[List[sqlite3.Row], int]:
    conn = db_connect()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM clans").fetchone()["cnt"]
        total_pages = max(1, math.ceil(total / page_size))
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        rows = conn.execute("SELECT * FROM clans ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset)).fetchall()
        return rows, total_pages
    finally:
        conn.close()

def create_clan_in_db(owner_id: int, tag: str, name: str, desc: str, clan_type: str, join_price: int) -> Optional[int]:
    conn = db_connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO clans (owner_id, tag, name, description, clan_type, join_price, max_members, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, 15, ?)
            """,
            (owner_id, tag.upper(), name, desc, clan_type, join_price, int(time.time()))
        )
        clan_id = cur.lastrowid
        conn.execute("INSERT INTO clan_members (clan_id, user_id, joined_ts) VALUES (?, ?, ?)", (clan_id, owner_id, int(time.time())))
        conn.commit()
        return clan_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def join_clan_user(clan_id: int, user_id: int) -> bool:
    conn = db_connect()
    try:
        clan = conn.execute("SELECT max_members FROM clans WHERE id=?", (clan_id,)).fetchone()
        if not clan:
            return False
        cnt = conn.execute("SELECT COUNT(*) as cnt FROM clan_members WHERE clan_id=?", (clan_id,)).fetchone()["cnt"]
        if cnt >= clan["max_members"]:
            return False

        conn.execute("INSERT INTO clan_members (clan_id, user_id, joined_ts) VALUES (?, ?, ?)", (clan_id, user_id, int(time.time())))
        conn.execute("DELETE FROM clan_requests WHERE user_id=?", (user_id,))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def leave_clan_user(user_id: int) -> bool:
    conn = db_connect()
    try:
        clan_member = conn.execute("SELECT clan_id FROM clan_members WHERE user_id=?", (user_id,)).fetchone()
        if not clan_member:
            return False
        clan = conn.execute("SELECT owner_id FROM clans WHERE id=?", (clan_member["clan_id"],)).fetchone()
        if clan and clan["owner_id"] == user_id:
            # Если владелец выходит - клан удаляется
            conn.execute("DELETE FROM clans WHERE id=?", (clan_member["clan_id"],))
        else:
            conn.execute("DELETE FROM clan_members WHERE user_id=?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# РЕНДЕР КАРТОЧЕК И БАННЕРОВ (Canvas Engine)
# ---------------------------------------------------------------------------

async def generate_clans_banner() -> io.BytesIO:
    WIDTH, HEIGHT = 1000, 320
    img = Image.new("RGBA", (WIDTH, HEIGHT), (22, 28, 42, 255))
    
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([250, -50, 750, 350], fill=(60, 40, 110, 180))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img, glow)
    
    draw = ImageDraw.Draw(img)
    f_title = load_font(52, bold=True)
    f_sub = load_font(24, bold=False)

    # Без эмодзи, чтобы не вызывать багов с квадратиками в Pillow
    draw.text((WIDTH // 2, 110), "CLANS & GUILDS", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 180), "Unite, Expand Slots and Dominate Top Ranks", font=f_sub, fill=(234, 179, 8), anchor="mm")

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.name = "clans.png"
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
    clan_tag: Optional[str] = None
) -> io.BytesIO:
    WIDTH, HEIGHT = 1000, 560

    clean_name = normalize_telegram_name(user_name)
    if clan_tag:
        clean_name = f"[{clan_tag.upper()}] {clean_name}"

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
    name_color = (234, 179, 8) if clan_tag else (255, 255, 255)
    draw.text((text_x, 85), clean_name, font=font_title, fill=name_color)

    lvl, cur_xp, req_xp, ratio = calculate_xp_level_info(user_xp)
    draw.text((text_x, 142), f"{lvl} УРОВЕНЬ ({cur_xp}/{req_xp} XP)", font=font_sub, fill=(255, 255, 255))

    bar_x, bar_y, bar_w, bar_h = text_x, 180, 360, 12
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=(55, 65, 80))
    fill_w = max(10, int(bar_w * ratio))
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + fill_w, bar_y + fill_w if fill_w < 12 else bar_y + bar_h], radius=6, fill=(234, 179, 8))

    draw.text((820, 90), f"ID: {user_sys_id}", font=font_small, fill=(140, 155, 175))
    draw.line([(text_x, 215), (940, 215)], fill=(45, 57, 74), width=1)

    stats_y = 230
    draw.rectangle([text_x, stats_y, text_x + 4, stats_y + 18], fill=(234, 179, 8))
    draw.text((text_x + 12, stats_y - 2), "ТОП ПО БАЛАНСУ", font=font_stat_lbl, fill=(140, 155, 175))
    draw.text((text_x + 12, stats_y + 24), f"#{rank}", font=font_stat_val, fill=(255, 255, 255))

    draw.line([(55, 305), (940, 305)], fill=(45, 57, 74), width=1)
    draw.text((55, 320), "СОСТАВ (ИЗБРАННОЕ)", font=font_stat_lbl, fill=(140, 155, 175))

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
                    log.warning("Ошибка обработки подарка: %s", e)
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
# КЛАВИАТУРЫ И СТИЛИЗАЦИЯ КНОПОК TELEGRAM
# ---------------------------------------------------------------------------

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Профиль", callback_data="nav_profile"),
            InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1"),
        ],
        [
            InlineKeyboardButton("🎰 Mystery Cases", callback_data="nav_cases_hub"),
            InlineKeyboardButton("🛒 Маркет", callback_data="market_main"),
        ],
        [
            InlineKeyboardButton("🏆 ТОП 100", callback_data="nav_top_page:1"),
            InlineKeyboardButton("🛡 Кланы (Скоро)", callback_data="nav_clans"),
        ],
        [
            InlineKeyboardButton("🎁 Бонус 24ч", callback_data="nav_bonus"),
            InlineKeyboardButton("🛍 Улучшения", callback_data="nav_shop"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="nav_settings"),
            InlineKeyboardButton("ℹ️ Инфо", callback_data="nav_info"),
        ]
    ])

def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")]
    ])

# ---------------------------------------------------------------------------
# КЕЙСЫ (4 Тира)
# ---------------------------------------------------------------------------

CASE_TIERS = {
    "tier1": {
        "name": "📦 Обычный кейс",
        "price": 100,
        "max_stars": 8000,
        "desc": "Выпадает: от базового мишки (50⭐) до Astral Shard (8,666⭐).",
        "pool": [g for g in GIFTS if g.stars <= 9000]
    },
    "tier2": {
        "name": "🔷 Редкий кейс",
        "price": 500,
        "max_stars": 20000,
        "desc": "Выпадает: от редкого декора до Scared Cat (19,333⭐).",
        "pool": [g for g in GIFTS if 200 <= g.stars <= 20000]
    },
    "tier3": {
        "name": "🟣 Эпический кейс",
        "price": 2500,
        "max_stars": 90000,
        "desc": "Выпадает: топовые эксклюзивы, включая Кепку Дурова и Locket (87,000⭐).",
        "pool": [g for g in GIFTS if g.stars >= 500]
    },
    "tier4": {
        "name": "👑 Легендарный кейс",
        "price": 10000,
        "max_stars": 455600,
        "desc": "Увеличенный шанс на Plush Pepe (455,600⭐) и Раритеты!",
        "pool": GIFTS
    }
}

# ---------------------------------------------------------------------------
# ФУНКЦИОНАЛ МАРКЕТА (ПОДАРКИ И NFT С ПАГИНАЦИЕЙ)
# ---------------------------------------------------------------------------

async def show_market_main(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    banner_img = await generate_market_banner()
    text = (
        f"🛒 <b>Добро пожаловать в NFT & Gift Market!</b>\n\n"
        f"💰 Твой баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
        "Здесь ты можешь приобрести любые подарки и коллекционные NFT напрямую за Stars ⭐.\n"
        "Выбери категорию каталога:"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ NFT Подарки", callback_data="market_cat:nft:1"),
            InlineKeyboardButton("🎁 Обычные Подарки", callback_data="market_cat:reg:1"),
        ],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
    ])

    if query.message.photo:
        await query.message.delete()
    await query.message.reply_photo(
        photo=InputFile(banner_img, filename="market.png"),
        caption=text,
        parse_mode=ParseMode.HTML,
        reply_markup=kb,
    )

async def show_market_category(query, category: str, page: int = 1) -> None:
    is_nft = (category == "nft")
    pool = [g for g in GIFTS if g.is_nft == is_nft]
    cat_title = "✨ NFT Подарки" if is_nft else "🎁 Обычные Подарки"

    items_per_page = 8
    total_pages = max(1, math.ceil(len(pool) / items_per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * items_per_page
    page_items = pool[start_idx : start_idx + items_per_page]

    buttons = []
    for g in page_items:
        btn_text = f"{rarity_emoji(g.chance)} {g.name} — {g.stars:,}⭐"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"market_view:{g.key}:{category}:{page}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"market_cat:{category}:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"Стр. {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"market_cat:{category}:{page+1}"))

    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("⬅️ В категории маркета", callback_data="market_main")])

    kb = InlineKeyboardMarkup(buttons)
    text = (
        f"🛒 <b>Каталог: {cat_title}</b> (Стр. {page}/{total_pages})\n\n"
        "Нажмите на подарок для подробного просмотра и покупки:"
    )

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_market_item(query, gift_key: str, category: str, page: int) -> None:
    g = GIFTS_BY_KEY.get(gift_key)
    if not g:
        return

    text = (
        f"{rarity_emoji(g.chance)} <b>{g.name}</b> {'(NFT ✨)' if g.is_nft else '(Обычный 🎁)'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• Редкость: <b>{rarity_label(g.chance)}</b>\n"
        f"• Дает опыта: <b>+{g.xp} XP</b>\n"
        f"• Стоимость в Stars: <b>{fmt_stars_rub(g.stars)}</b>\n"
        f"• Стоимость в TON: <b>{fmt_ton(g.ton)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💳 Купить за {g.stars:,} ⭐", callback_data=f"market_buy:{g.key}:{category}:{page}")],
        [InlineKeyboardButton("⬅️ Назад в каталог", callback_data=f"market_cat:{category}:{page}")],
    ])

    img_p = gift_image_path(g.key)
    if img_p:
        try:
            with open(img_p, "rb") as f:
                await query.message.reply_photo(
                    photo=InputFile(f, filename=img_p.name),
                    caption=text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=kb,
                )
            await query.message.delete()
            return
        except Exception as e:
            log.error("Ошибка показа подарка в маркете: %s", e)

    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# ОБРАБОТЧИКИ КОМАНД
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.first_name)
    banner_img = await generate_main_menu_banner()
    await update.message.reply_photo(
        photo=InputFile(banner_img, filename="menu.png"),
        caption=(
            f"👋 <b>Привет, {user.first_name}! Добро пожаловать в New NFT!</b>\n\n"
            "Пиши слово <code>NFT</code> в группах, чтобы выбивать редчайшие Telegram Gifts! 🎁\n\n"
            "• Открывай кейсы разной ценности\n"
            "• Покупай редкие подарки на Маркете\n"
            "• Улучшай вместимость коллекции\n"
            "• Соревнуйся в ТОП-100 игроков бота\n\n"
            "Для управления нажимай кнопки меню:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard()
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)

async def cmd_profile_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_profile_handler(update, update.effective_user.id, context)

async def show_info_page(query) -> None:
    text = (
        "ℹ️ <b>Информация о боте New NFT Bot</b>\n\n"
        "• Пишите слово <code>NFT</code> в групповых чатах, чтобы получать подарки!\n"
        "• Подарки имеют разную ценность и редкость (от обычных мишек до Plush Pepe).\n"
        "• Нажмите <b>Маркет</b>, чтобы продавать или за Stars покупать редкие эксклюзивные предметы.\n"
        "• Открывайте <b>Mystery Cases</b> для получения случайных наград.\n"
        "• Переводите Stars или Подарки другим игрокам с помощью команд <code>/pay</code> и <code>/send_gift</code>."
    )
    kb = back_to_main_keyboard()
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_settings_page(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    hide_top_str = "✅ Включено" if db_user["hide_top"] else "❌ Выключено"
    auto_sell_str = "✅ Включено" if db_user["auto_sell"] else "❌ Выключено"

    text = (
        "⚙️ <b>Настройки приватности и авто-продажи</b>\n\n"
        f"• Скрывать из ТОП-100: <b>{hide_top_str}</b>\n"
        f"• Авто-продажа выпавших предметов: <b>{auto_sell_str}</b>\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"👁 Скрывать из ТОПа: {hide_top_str}", callback_data="toggle_set:hide_top")],
        [InlineKeyboardButton(f"💰 Авто-продажа из кейсов: {auto_sell_str}", callback_data="toggle_set:auto_sell")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
    ])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_shop_page(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    text = (
        "🛍 <b>Магазин улучшений</b>\n\n"
        f"Текущая вместимость коллекции: <b>{db_user['max_inventory']} предметов</b>\n"
        f"Твой баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
        "Доступные улучшения:\n"
        "• <b>+10 Слотов коллекции</b> — Цена: <b>300 ⭐</b>\n"
        "• <b>+25 Слотов коллекции</b> — Цена: <b>650 ⭐</b>\n"
        "• <b>+50 Слотов коллекции</b> — Цена: <b>1,200 ⭐</b>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 +10 Слотов (300⭐)", callback_data="buy_slots:10:300")],
        [InlineKeyboardButton("📦 +25 Слотов (650⭐)", callback_data="buy_slots:25:650")],
        [InlineKeyboardButton("📦 +50 Слотов (1200⭐)", callback_data="buy_slots:50:1200")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
    ])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_profile_handler(update_or_query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update_or_query.effective_user if hasattr(update_or_query, "effective_user") else update_or_query.from_user
    db_user = get_or_create_user(user_id, user.username, user.first_name)
    cleaned_name = normalize_telegram_name(user.first_name or "User")

    avatar_bytes = None
    try:
        photos = await context.bot.get_user_profile_photos(user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            tg_file = await context.bot.get_file(file_id)
            file_bytes_io = io.BytesIO()
            await tg_file.download_to_memory(file_bytes_io)
            avatar_bytes = file_bytes_io.getvalue()
    except Exception as e:
        log.warning("Аватар недоступен: %s", e)

    fav_rows = get_favorites(user_id)
    fav_gifts = [GIFTS_BY_KEY[r["gift_key"]] for r in fav_rows if r["gift_key"] in GIFTS_BY_KEY]
    rank = get_user_rank(user_id)
    lvl, cur_xp, req_xp, _ = calculate_xp_level_info(db_user["xp"])

    user_clan = get_user_clan(user_id)
    clan_tag = user_clan["tag"] if user_clan else None

    card_img = await generate_profile_card_image(
        cleaned_name,
        db_user["id_num"],
        db_user["balance_stars"],
        db_user["xp"],
        rank,
        fav_gifts,
        avatar_bytes,
        clan_tag=clan_tag
    )

    clan_str = f"🛡 Клан: <b>[{user_clan['tag']}] {user_clan['name']}</b>\n" if user_clan else ""

    caption = (
        f"👤 <b>Профиль игрока {cleaned_name}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎖 Уровень: <b>{lvl} ({cur_xp}/{req_xp} XP)</b>\n"
        f"🏆 Место в ТОПе: <b>#{rank}</b>\n"
        f"{clan_str}"
        f"💰 Баланс Stars: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n"
        f"📦 Инвентарь: <b>{db_user['max_inventory']} слотов</b>\n"
        f"🎲 Выбито подарков: <b>{db_user['total_drops']}</b> шт.\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_photo(
            photo=InputFile(card_img, filename="profile.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )
    else:
        await update_or_query.reply_photo(
            photo=InputFile(card_img, filename="profile.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )

# ---------------------------------------------------------------------------
# МЕНЮ КЛАНОВ И ЛОГИКА
# ---------------------------------------------------------------------------

async def show_clans_hub(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    user_clan = get_user_clan(user_id)
    banner_img = await generate_clans_banner()

    text = "🛡 <b>Раздел Кланов</b>\n\n"
    buttons = []

    if user_clan:
        cnt = get_clan_members_count(user_clan["id"])
        text += (
            f"Вы состоите в клане <b>[{user_clan['tag']}] {user_clan['name']}</b>!\n"
            f"Участников: <b>{cnt}/{user_clan['max_members']}</b>\n"
            f"Тип входа: <b>{user_clan['clan_type'].upper()}</b>\n\n"
        )
        buttons.append([InlineKeyboardButton("🏰 Мой клан", callback_data=f"clan_view:{user_clan['id']}")])
    else:
        text += (
            "Объединяйтесь с игроками, создавайте уникальный клантег и подсвечивайте своё имя!\n\n"
            "📌 <b>Условия создания клана:</b>\n"
            f"• <b>10 Уровень</b> в игре\n"
            f"• Стоимость: <b>{CLAN_CREATE_COST:,} ⭐</b>\n\n"
        )
        buttons.append([InlineKeyboardButton("➕ Создать клан (100k ⭐)", callback_data="clan_create_start")])

    buttons.append([InlineKeyboardButton("🔍 Просмотреть кланы", callback_data="clan_list:1")])
    buttons.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    if query.message.photo:
        await query.message.delete()
    await query.message.reply_photo(photo=InputFile(banner_img, filename="clans.png"), caption=text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_clans_list(query, page: int = 1) -> None:
    rows, total_pages = get_all_clans(page, 8)
    text = f"🏰 <b>Список существующих Кланов</b> (Стр. {page}/{total_pages})\n━━━━━━━━━━━━━━━━━━\n"
    buttons = []

    if not rows:
        text += "<i>Пока не создано ни одного клана. Станьте первым!</i>\n"
    else:
        for c in rows:
            cnt = get_clan_members_count(c["id"])
            type_lbl = "🔓 Открытый" if c["clan_type"] == "public" else "🔒 Закрытый" if c["clan_type"] == "private" else f"💎 {c['join_price']:,}⭐"
            btn_txt = f"[{c['tag']}] {c['name'][:12]} | 👤 {cnt}/{c['max_members']} | {type_lbl}"
            buttons.append([InlineKeyboardButton(btn_txt, callback_data=f"clan_view:{c['id']}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"clan_list:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"clan_list:{page+1}"))
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("⬅️ К меню кланов", callback_data="nav_clans")])

    kb = InlineKeyboardMarkup(buttons)
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_clan_details(query, clan_id: int, user_id: int) -> None:
    clan = get_clan_by_id(clan_id)
    if not clan:
        await query.answer("❌ Клан не найден!", show_alert=True)
        return

    cnt = get_clan_members_count(clan_id)
    user_clan = get_user_clan(user_id)
    is_owner = (clan["owner_id"] == user_id)
    in_this_clan = (user_clan and user_clan["id"] == clan_id)

    type_str = "Открытый (свободный)" if clan["clan_type"] == "public" else "Закрытый (по заявкам)" if clan["clan_type"] == "private" else f"Платный ({clan['join_price']:,} ⭐)"

    text = (
        f"🏰 <b>Клан [{clan['tag']}] {clan['name']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 Описание: {clan['description'] or 'Отсутствует'}\n"
        f"👤 Участники: <b>{cnt}/{clan['max_members']}</b>\n"
        f"🚪 Тип входа: <b>{type_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if in_this_clan:
        if is_owner:
            buttons.append([InlineKeyboardButton("⚙️ Управление кланом", callback_data=f"clan_manage:{clan_id}")])
            buttons.append([InlineKeyboardButton("🚀 Расширить слоты", callback_data=f"clan_expand:{clan_id}")])
        buttons.append([InlineKeyboardButton("🚪 Выйти из клана", callback_data=f"clan_leave:{clan_id}")])
    elif not user_clan:
        if cnt < clan["max_members"]:
            if clan["clan_type"] == "public":
                buttons.append([InlineKeyboardButton("➕ Вступить в клан", callback_data=f"clan_join:{clan_id}")])
            elif clan["clan_type"] == "paid":
                buttons.append([InlineKeyboardButton(f"💳 Войти за {clan['join_price']:,} ⭐", callback_data=f"clan_join_paid:{clan_id}")])
            else:
                buttons.append([InlineKeyboardButton("📩 Подать заявку", callback_data=f"clan_req:{clan_id}")])

    buttons.append([InlineKeyboardButton("⬅️ К списку кланов", callback_data="clan_list:1")])

    kb = InlineKeyboardMarkup(buttons)
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# ОБРАБОТЧИКИ CALLBACK QUERY
# ---------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    user = query.from_user

    if data == "noop":
        return

    if data == "nav_clans":
        await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_list:"):
        p = int(data.split(":")[1])
        await show_clans_list(query, p)
        return

    if data.startswith("clan_view:"):
        c_id = int(data.split(":")[1])
        await show_clan_details(query, c_id, user.id)
        return

    # Начало создания клана
    if data == "clan_create_start":
        db_user = get_or_create_user(user.id, user.username, user.first_name)
        lvl, _, _, _ = calculate_xp_level_info(db_user["xp"])

        if lvl < CLAN_CREATE_LEVEL_REQ:
            await query.answer(f"❌ Требуется минимум {CLAN_CREATE_LEVEL_REQ} уровень (у вас {lvl})!", show_alert=True)
            return

        if db_user["balance_stars"] < CLAN_CREATE_COST:
            await query.answer(f"❌ Недостаточно Stars! Нужно {CLAN_CREATE_COST:,}⭐", show_alert=True)
            return

        context.user_data["clan_create"] = {}
        context.user_data["clan_state"] = WAITING_CLAN_TAG

        txt = (
            "🛡 <b>Создание нового Клана (1/5)</b>\n\n"
            "Введите <b>КЛАНТЕГ</b> (от 3 до 6 английских букв или цифр).\n"
            "<i>Пример: APEX, LEG3ND, TG</i>"
        )
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(txt, parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text(txt, parse_mode=ParseMode.HTML)
        return

    if data.startswith("clan_set_type:"):
        c_type = data.split(":")[1]
        context.user_data["clan_create"]["type"] = c_type

        if c_type == "paid":
            context.user_data["clan_state"] = WAITING_CLAN_PRICE
            await query.edit_message_text("💰 Введите стоимость входа в клан в Stars (например: 100000):", parse_mode=ParseMode.HTML)
        else:
            context.user_data["clan_create"]["price"] = 0
            # Финализация создания клана
            cdata = context.user_data["clan_create"]
            if deduct_user_stars(user.id, CLAN_CREATE_COST):
                cid = create_clan_in_db(user.id, cdata["tag"], cdata["name"], cdata["desc"], cdata["type"], cdata["price"])
                context.user_data["clan_state"] = None
                context.user_data["clan_create"] = None
                if cid:
                    await query.edit_message_text(f"🎉 <b>Клан [{cdata['tag'].upper()}] {cdata['name']} успешно создан!</b>", parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
                else:
                    add_user_stars(user.id, CLAN_CREATE_COST)
                    await query.edit_message_text("❌ Этот клантег уже занят!", parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
        return

    if data.startswith("clan_join:"):
        c_id = int(data.split(":")[1])
        if join_clan_user(c_id, user.id):
            await query.answer("🎉 Вы успешно вступили в клан!", show_alert=True)
            await show_clan_details(query, c_id, user.id)
        else:
            await query.answer("❌ Клан заполнен или вы уже состоите в клане!", show_alert=True)
        return

    if data.startswith("clan_join_paid:"):
        c_id = int(data.split(":")[1])
        clan = get_clan_by_id(c_id)
        if not clan: return
        if deduct_user_stars(user.id, clan["join_price"]):
            if join_clan_user(c_id, user.id):
                add_user_stars(clan["owner_id"], clan["join_price"])
                await query.answer(f"🎉 Вы заплатили {clan['join_price']:,}⭐ и вступили в клан!", show_alert=True)
                await show_clan_details(query, c_id, user.id)
            else:
                add_user_stars(user.id, clan["join_price"])
                await query.answer("❌ Клан заполнен!", show_alert=True)
        else:
            await query.answer(f"❌ Недостаточно Stars! Нужно {clan['join_price']:,}⭐", show_alert=True)
        return

    if data.startswith("clan_leave:"):
        if leave_clan_user(user.id):
            await query.answer("Вы вышли из клана.", show_alert=True)
            await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_expand:"):
        c_id = int(data.split(":")[1])
        clan = get_clan_by_id(c_id)
        if not clan or clan["owner_id"] != user.id: return

        cur_max = clan["max_members"]
        next_upg = None
        for slots, cost in CLAN_SLOT_UPGRADES:
            if slots > cur_max:
                next_upg = (slots, cost)
                break

        if not next_upg:
            await query.answer("У вас уже максимальное число мест (60)!", show_alert=True)
            return

        target_s, cost = next_upg
        if deduct_user_stars(user.id, cost):
            conn = db_connect()
            conn.execute("UPDATE clans SET max_members=? WHERE id=?", (target_s, c_id))
            conn.commit()
            conn.close()
            await query.answer(f"🎉 Клан расширен до {target_s} мест!", show_alert=True)
            await show_clan_details(query, c_id, user.id)
        else:
            await query.answer(f"❌ Недостаточно Stars! Нужно {cost:,}⭐", show_alert=True)
        return

async def user_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    c_state = context.user_data.get("clan_state")

    if c_state:
        text = update.message.text.strip()
        cdata = context.user_data.get("clan_create", {})

        if c_state == WAITING_CLAN_TAG:
            if not re.match(r"^[A-Za-z0-9]{3,6}$", text):
                await update.message.reply_text("❌ Тег должен содержать от 3 до 6 латинских букв или цифр! Попробуйте снова:")
                return
            cdata["tag"] = text.upper()
            context.user_data["clan_state"] = WAITING_CLAN_NAME
            await update.message.reply_text("🏷 <b>Создание Клана (2/5)</b>\nВведите название клана (максимум 15 символов):", parse_mode=ParseMode.HTML)
            return

        if c_state == WAITING_CLAN_NAME:
            if len(text) > 15:
                await update.message.reply_text("❌ Название слишком длинное! Максимум 15 символов:")
                return
            cdata["name"] = text
            context.user_data["clan_state"] = WAITING_CLAN_DESC
            await update.message.reply_text("📝 <b>Создание Клана (3/5)</b>\nВведите описание клана (до 150 символов):", parse_mode=ParseMode.HTML)
            return

        if c_state == WAITING_CLAN_DESC:
            cdata["desc"] = text[:150]
            context.user_data["clan_state"] = WAITING_CLAN_TYPE
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Открытый (Свободный вход)", callback_data="clan_set_type:public")],
                [InlineKeyboardButton("🔒 Закрытый (По заявкам)", callback_data="clan_set_type:private")],
                [InlineKeyboardButton("💎 Платный (За Stars)", callback_data="clan_set_type:paid")],
            ])
            await update.message.reply_text("🚪 <b>Создание Клана (4/5)</b>\nВыберите тип входа:", parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        if c_state == WAITING_CLAN_PRICE:
            if not text.isdigit() or int(text) <= 0:
                await update.message.reply_text("❌ Введите корректное число Stars!")
                return
            cdata["price"] = int(text)
            if deduct_user_stars(user_id, CLAN_CREATE_COST):
                cid = create_clan_in_db(user_id, cdata["tag"], cdata["name"], cdata["desc"], cdata["type"], cdata["price"])
                context.user_data["clan_state"] = None
                context.user_data["clan_create"] = None
                if cid:
                    await update.message.reply_text(f"🎉 <b>Клан [{cdata['tag']}] {cdata['name']} успешно создан!</b>", parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
                else:
                    add_user_stars(user_id, CLAN_CREATE_COST)
                    await update.message.reply_text("❌ Этот клантег уже занят!", parse_mode=ParseMode.HTML, reply_markup=back_to_main_keyboard())
            return

    # Если администратор
    if user_id in ADMIN_IDS:
        await admin_input_handler(update, context)

async def show_collection_page(query, user_id: int, page: int = 1) -> None:
    items = get_user_collection(user_id)
    db_user = get_or_create_user(user_id, "", "")
    max_inv = db_user["max_inventory"]

    if not items:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Открыть кейсы", callback_data="nav_cases_hub")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
        ])
        msg_text = (
            f"🗂 <b>Твоя коллекция пуста (0/{max_inv}).</b>\n\n"
            "Выбей свой первый NFT-подарок командой <code>NFT</code> в группах или открывай Mystery Cases!"
        )
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    items_per_page = 10
    total_pages = max(1, math.ceil(len(items) / items_per_page))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * items_per_page
    page_items = items[start_idx : start_idx + items_per_page]

    buttons = []
    for item in page_items:
        g = GIFTS_BY_KEY.get(item["gift_key"])
        if not g:
            continue
        fav_star = "⭐ " if item["is_favorite"] else ""
        btn_text = f"{fav_star}{rarity_emoji(g.chance)} {g.name} ({g.stars}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_item:{item['id']}:{page}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"nav_collection_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"Стр. {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"nav_collection_page:{page+1}"))
    buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔥 Продать всё (Кроме Избранных)", callback_data="sell_all_confirm")])
    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    text = (
        f"🗂 <b>Твоя NFT-Коллекция ({len(items)}/{max_inv} предметов):</b>\n"
        f"Страница {page} из {total_pages}\n\n"
        "Нажмите на предмет для управления:"
    )

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_top_page(query, page: int = 1) -> None:
    page_size = 10
    rows, total_pages = get_top_users_page(page, page_size)

    lines = [f"🏆 <b>Глобальный ТОП Игроков (Стр. {page}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━"]
    buttons = []

    start_rank = (page - 1) * page_size + 1
    for idx, u in enumerate(rows, start=start_rank):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}"
        name = normalize_telegram_name(u['first_name'] or u['username'] or 'Игрок')
        lvl, _, _, _ = calculate_xp_level_info(u['xp'])
        lines.append(f"{medal} <b>{name}</b> — <b>{u['balance_stars']:,} ⭐</b> (Ур. {lvl})")
        
        btn_text = f"👤 {medal} {name[:12]} ({u['balance_stars']:,}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_top_user:{u['user_id']}:{page}")])

    lines.append("━━━━━━━━━━━━━━━━━━")

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"nav_top_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"nav_top_page:{page+1}"))
    
    buttons.append(nav_row)
    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    full_text = "\n".join(lines)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(full_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(full_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# ПРОВЕРКА СООБЩЕНИЙ В ГРУППАХ
# ---------------------------------------------------------------------------

async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or msg.text is None:
        return

    text_raw = msg.text.strip()
    text_lower = text_raw.lower()

    if text_lower in ("кто я", "я", "профиль", "profile"):
        await show_profile_handler(update, update.effective_user.id, context)
        return

    if text_lower in ("коллекция", "collection"):
        db_user = get_or_create_user(update.effective_user.id, update.effective_user.username, update.effective_user.first_name)
        items = get_user_collection(update.effective_user.id)
        await msg.reply_text(f"🗂 В твоей коллекции <b>{len(items)}/{db_user['max_inventory']}</b> NFT-подарков. Для детализации используй меню бота.", parse_mode=ParseMode.HTML)
        return

    allowed_words = {"nft", "нфт", "подарок"}
    if text_lower not in allowed_words:
        return

    user = update.effective_user
    row = get_or_create_user(user.id, user.username, user.first_name)

    now = int(time.time())
    if COOLDOWN_ENABLED:
        remaining = row["last_drop_ts"] + COOLDOWN_SECONDS - now
        if remaining > 0:
            await msg.reply_text(f"⏳ Рано! Команду NFT можно использовать 1 раз в час.\nПопробуй через {seconds_to_hms(remaining)}.")
            return

    set_last_drop(user.id, now)

    if random.random() > CHAT_DROP_CHANCE:
        await msg.reply_text("💨 В этот раз ничего не выпало! Попробуй снова через 1 час.")
        return

    gift = roll_gift_from_pool(GIFTS)
    drop_id = create_pending_drop(user.id, update.effective_chat.id, gift.key)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Сохранить", callback_data=f"keep:{drop_id}"),
            InlineKeyboardButton("💰 Продать за Stars", callback_data=f"sell:{drop_id}"),
        ]
    ])

    caption = (
        f"🎉 <b>{user.first_name}</b>, тебе выпал NFT-подарок!\n\n"
        f"{rarity_emoji(gift.chance)} <b>{gift.name}</b>\n"
        f"• Редкость: <b>{rarity_label(gift.chance)}</b>\n"
        f"• Опыт: <b>+{gift.xp} XP</b>\n"
        f"• Ценность: {fmt_stars_rub(gift.stars)} / {fmt_ton(gift.ton)}\n\n"
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
            log.error("Ошибка отправки фото: %s", e)

    if not sent_photo:
        await msg.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)

# ---------------------------------------------------------------------------
# ОБРАБОТЧИКИ CALLBACK QUERY
# ---------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    user = query.from_user

    if data == "noop":
        return

    if query.message.chat.type != "private" and data in ("nav_cases_hub", "nav_top_page:1", "nav_settings", "nav_shop", "market_main"):
        await query.answer("⚠️ Откройте личные сообщения с ботом для этой функции!", show_alert=True)
        return

    if data == "market_main":
        await show_market_main(query, user.id)
        return

    if data.startswith("market_cat:"):
        _, cat, p_str = data.split(":")
        await show_market_category(query, cat, int(p_str))
        return

    if data.startswith("market_view:"):
        _, key, cat, p_str = data.split(":")
        await show_market_item(query, key, cat, int(p_str))
        return

    if data.startswith("market_buy:"):
        _, key, cat, p_str = data.split(":")
        g = GIFTS_BY_KEY.get(key)
        if not g:
            return

        if not deduct_user_stars(user.id, g.stars):
            await query.answer(f"❌ Недостаточно Stars! Требуется {g.stars:,}⭐", show_alert=True)
            return

        added = add_to_collection(user.id, g.key)
        if not added:
            add_user_stars(user.id, g.stars)
            await query.answer("❌ Твой инвентарь переполнен! Купи расширение в Магазине.", show_alert=True)
            return

        await query.answer(f"🎉 Вы успешно купили {g.name} за {g.stars:,} Stars!", show_alert=True)
        await show_market_category(query, cat, int(p_str))
        return

    if data == "nav_main":
        banner_img = await generate_main_menu_banner()
        if query.message.photo:
            await query.message.delete()
        await query.message.reply_photo(
            photo=InputFile(banner_img, filename="menu.png"),
            caption="🏠 <b>Главное меню New NFT Bot:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard()
        )
        return

    if data == "nav_profile":
        await show_profile_handler(query, user.id, context)
        return

    if data == "nav_info":
        await show_info_page(query)
        return

    if data == "nav_settings":
        await show_settings_page(query, user.id)
        return

    if data == "nav_shop":
        await show_shop_page(query, user.id)
        return

    if data.startswith("nav_collection_page:"):
        page = int(data.split(":")[1])
        await show_collection_page(query, user.id, page)
        return

    if data.startswith("nav_top_page:"):
        page = int(data.split(":")[1])
        await show_top_page(query, page)
        return

    if data.startswith("toggle_set:"):
        field = data.split(":", 1)[1]
        toggle_user_setting(user.id, field)
        await show_settings_page(query, user.id)
        return

    if data.startswith("buy_slots:"):
        _, slots_str, cost_str = data.split(":")
        slots, cost = int(slots_str), int(cost_str)
        if upgrade_inventory_capacity(user.id, cost, slots):
            await query.answer(f"✅ Успешно куплено +{slots} слотов!", show_alert=True)
            await show_shop_page(query, user.id)
        else:
            await query.answer("❌ Недостаточно Stars на балансе!", show_alert=True)
        return

    if data == "sell_all_confirm":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Подтвердить продажу", callback_data="sell_all_do"),
                InlineKeyboardButton("❌ Отмена", callback_data="nav_collection_page:1"),
            ]
        ])
        msg_text = "⚠️ <b>Вы уверены, что хотите продать ВСЕ обычные предметы из коллекции?</b>\n(Предметы из Избранного останутся целы)"
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "sell_all_do":
        count, stars = sell_all_non_favorites(user.id)
        await query.answer(f"💰 Продано {count} предметов за {stars} Stars!", show_alert=True)
        await show_collection_page(query, user.id, 1)
        return

    if data == "nav_bonus":
        remaining = claim_daily_bonus(user.id)
        if remaining is None:
            text = "🎁 <b>Поздравляем!</b> Ты получил ежедневный бонус: <b>+25 Stars ⭐</b> и <b>+150 XP ⚡️</b>!"
        else:
            text = f"⏳ Ежедневный бонус уже получен. Попробуй через {seconds_to_hms(remaining)}."

        kb = back_to_main_keyboard()
        if query.message.photo:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "nav_clans":
        text = (
            "🛡 <b>Кланы и Гильдии</b>\n\n"
            "🚧 <b>Раздел находится в разработке!</b>\n\n"
            "В скором времени вы сможете объединяться с другими игроками в кланы, "
            "участвовать в командных турнирах, завоевывать территории и получать эксклюзивные клановые NFT!"
        )
        kb = back_to_main_keyboard()
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ---------------------------------------------------------------------------
    # МЕНЮ КЕЙСОВ
    # ---------------------------------------------------------------------------
    if data == "nav_cases_hub":
        db_user = get_or_create_user(user.id, "", "")
        text = (
            f"🎰 <b>Магазин Mystery Cases</b>\n\n"
            f"Баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
            f"1. 📦 <b>Обычный кейс</b> — 100 ⭐ (Макс: 8,000⭐)\n"
            f"2. 🔷 <b>Редкий кейс</b> — 500 ⭐ (Макс: 20,000⭐)\n"
            f"3. 🟣 <b>Эпический кейс</b> — 2,500 ⭐ (Макс: 50,000⭐)\n"
            f"4. 👑 <b>Легендарный кейс</b> — 10,000 ⭐ (Шанс на Plush Pepe!)\n"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Обычный (100⭐)", callback_data="open_case:tier1")],
            [InlineKeyboardButton("🔷 Редкий (500⭐)", callback_data="open_case:tier2")],
            [InlineKeyboardButton("🟣 Эпический (2500⭐)", callback_data="open_case:tier3")],
            [InlineKeyboardButton("👑 Легендарный (10000⭐)", callback_data="open_case:tier4")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
        ])
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("open_case:"):
        tier_key = data.split(":")[1]
        tier = CASE_TIERS.get(tier_key)
        if not tier:
            return

        db_user = get_or_create_user(user.id, "", "")
        if not deduct_user_stars(user.id, tier["price"]):
            await query.answer(f"❌ Недостаточно Stars! Цена кейса: {tier['price']}⭐", show_alert=True)
            return

        increment_cases_opened(user.id)
        won_gift = roll_gift_from_pool(tier["pool"])

        if db_user["auto_sell"]:
            add_user_stars(user.id, won_gift.stars)
            res_note = f"💰 <b>Авто-продажа:</b> Начислено <b>+{fmt_stars_rub(won_gift.stars)}</b>!"
        else:
            success = add_to_collection(user.id, won_gift.key)
            if not success:
                add_user_stars(user.id, won_gift.stars)
                res_note = f"⚠️ Коллекция переполнена! Предмет автоматически продан за <b>{fmt_stars_rub(won_gift.stars)}</b>."
            else:
                res_note = f"✅ Предмет сохранен в коллекцию! (+{won_gift.xp} XP)"

        cap = (
            f"🎰 <b>Открытие {tier['name']}!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎉 Выпал: {rarity_emoji(won_gift.chance)} <b>{won_gift.name}</b>!\n"
            f"• Редкость: <b>{rarity_label(won_gift.chance)}</b>\n"
            f"• Ценность: <b>{fmt_stars_rub(won_gift.stars)}</b>\n\n"
            f"{res_note}"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎰 Еще раз ({tier['price']}⭐)", callback_data=f"open_case:{tier_key}")],
            [InlineKeyboardButton("🎰 К списку кейсов", callback_data="nav_cases_hub")],
            [InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1")],
        ])

        img_p = gift_image_path(won_gift.key)
        if img_p:
            try:
                with open(img_p, "rb") as f:
                    await query.message.reply_photo(photo=InputFile(f, filename=img_p.name), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                if query.message:
                    await query.message.delete()
                return
            except Exception as e:
                log.error("Fallback кейса: %s", e)

        await query.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    # ---------------------------------------------------------------------------
    # ДЕЙСТВИЯ С ПРЕДМЕТАМИ И ПРОФИЛЯМИ ИГРОКОВ
    # ---------------------------------------------------------------------------
    if ":" in data:
        action, *rest = data.split(":")

        if action in ("keep", "sell"):
            drop_id = int(rest[0])
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
                added = add_to_collection(user.id, gift.key)
                if added:
                    res = f"✅ <b>{gift.name}</b> сохранён в вашей коллекции! (+{gift.xp} XP)"
                else:
                    sell_from_pending(user.id, gift.key, gift.stars)
                    res = f"⚠️ Коллекция заполнена! <b>{gift.name}</b> автоматически продан за {fmt_stars_rub(gift.stars)}!"
            else:
                sell_from_pending(user.id, gift.key, gift.stars)
                res = f"💰 Вы продали <b>{gift.name}</b> за {fmt_stars_rub(gift.stars)}! (+{gift.xp // 2} XP)"

            if query.message.photo:
                await query.edit_message_caption(caption=res, parse_mode=ParseMode.HTML)
            else:
                await query.edit_message_text(res, parse_mode=ParseMode.HTML)
            return

        if action == "view_top_user":
            target_id = int(rest[0])
            back_page = int(rest[1])
            target = get_or_create_user(target_id, "", "")

            if target["hide_top"]:
                await query.answer("🔒 Пользователь скрыл свой профиль в настройках приватности.", show_alert=True)
                return

            name = normalize_telegram_name(target["first_name"] or target["username"] or "Игрок")
            lvl, cur_xp, req_xp, _ = calculate_xp_level_info(target["xp"])
            text = (
                f"👤 <b>Профиль игрока {name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎖 Уровень: <b>{lvl} ({cur_xp}/{req_xp} XP)</b>\n"
                f"💰 Баланс Stars: <b>{fmt_stars_rub(target['balance_stars'])}</b>\n"
                f"📦 Всего выбито NFT: <b>{target['total_drops']}</b>\n"
            )

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад к ТОПу", callback_data=f"nav_top_page:{back_page}")]
            ])

            if query.message.photo:
                await query.message.delete()
                await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        if action == "view_item":
            item_id = int(rest[0])
            page = int(rest[1]) if len(rest) > 1 else 1
            item = get_collection_item(item_id)
            if not item or item["user_id"] != user.id:
                await query.answer("Предмет не найден.", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            fav_text = "❌ Убрать из Избранного" if item["is_favorite"] else "⭐ В избранное профиля"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav:{item_id}:{page}")],
                [InlineKeyboardButton("💰 Продать за Stars", callback_data=f"sell_item:{item_id}:{page}")],
                [InlineKeyboardButton("⬅️ Назад в коллекцию", callback_data=f"nav_collection_page:{page}")]
            ])

            cap = (
                f"{rarity_emoji(g.chance)} <b>{g.name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• Редкость: <b>{rarity_label(g.chance)}</b>\n"
                f"• Опыт: <b>+{g.xp} XP</b>\n"
                f"• Ценность в Stars: {fmt_stars_rub(g.stars)}\n"
                f"• Ценность в TON: {fmt_ton(g.ton)}\n"
                f"• В Избранном профиля: <b>{'Да ⭐' if item['is_favorite'] else 'Нет'}</b>\n"
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
            item_id = int(rest[0])
            page = int(rest[1]) if len(rest) > 1 else 1
            success = toggle_favorite(item_id, user.id)
            if success:
                await query.answer("Избранное обновлено!")
                await show_collection_page(query, user.id, page)
            else:
                await query.answer("Максимум 7 предметов в Избранном!", show_alert=True)
            return

        if action == "sell_item":
            item_id = int(rest[0])
            page = int(rest[1]) if len(rest) > 1 else 1
            item = get_collection_item(item_id)
            if not item or item["user_id"] != user.id:
                await query.answer("Ошибка продажи.", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            remove_from_collection(item_id, user.id)
            add_user_stars(user.id, g.stars)

            await query.answer(f"💰 Продано за {g.stars} Stars!", show_alert=True)
            await show_collection_page(query, user.id, page)
            return

# ---------------------------------------------------------------------------
# КОМАНДЫ ПЕРЕВОДОВ И ПОДАРКОВ
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# АДМИН-ПАНЕЛЬ С РАСШИРЕННОЙ СТАТИСТИКОЙ И ВЫДАЧЕЙ
# ---------------------------------------------------------------------------

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Доступ запрещен!")
        return

    text = (
        "👑 <b>Панель Администратора</b>\n\n"
        "Выберите нужное действие из меню ниже:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Подробная статистика", callback_data="admin_stats")],
        [
            InlineKeyboardButton("➕ Выдать Stars", callback_data="admin_give_stars"),
            InlineKeyboardButton("🎁 Выдать NFT/Подарок", callback_data="admin_give_gift:1"),
        ],
        [InlineKeyboardButton("⬅️ Закрыть", callback_data="nav_main")],
    ])

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    user_id = query.from_user.id

    if user_id not in ADMIN_IDS:
        await query.answer("❌ Нет прав администратора!", show_alert=True)
        return

    if data == "admin_stats":
        stats = get_admin_global_stats()
        text = (
            "📊 <b>Подробная статистика проекта:</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"👥 Всего пользователей: <b>{stats['total_users']:,}</b>\n"
            f"⭐ Всего Stars на руках: <b>{stats['total_stars']:,} ⭐</b> (~{stats['total_stars'] * STAR_RUB_RATE:,.0f} ₽)\n"
            f"📦 Предметов в коллекциях: <b>{stats['total_items']:,} шт.</b>\n"
            f"💎 Рыночная стоимость предметов: <b>{stats['inventory_market_cap']:,} ⭐</b>\n"
            f"🌐 <b>Общая капитализация:</b> <b>{stats['total_market_cap']:,} ⭐</b> (~{stats['total_market_cap'] * STAR_RUB_RATE:,.0f} ₽)\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🎲 Выбито гифтов в чатах: <b>{stats['total_drops']:,}</b>\n"
            f"💰 Продано предметов: <b>{stats['total_sold']:,}</b>\n"
            f"🎰 Открыто кейсов: <b>{stats['total_cases']:,}</b>\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_main")]
        ])
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "admin_main":
        text = "👑 <b>Панель Администратора</b>\n\nВыберите нужную опцию:"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Подробная статистика", callback_data="admin_stats")],
            [
                InlineKeyboardButton("➕ Выдать Stars", callback_data="admin_give_stars"),
                InlineKeyboardButton("🎁 Выдать NFT/Подарок", callback_data="admin_give_gift:1"),
            ],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
        ])
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("admin_give_gift:"):
        page = int(data.split(":")[1])
        items_per_page = 8
        total_pages = max(1, math.ceil(len(GIFTS) / items_per_page))
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * items_per_page
        page_items = GIFTS[start_idx : start_idx + items_per_page]

        buttons = []
        for g in page_items:
            btn_text = f"🎁 {g.name} ({g.stars:,}⭐)"
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"admin_select_gift:{g.key}")])

        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("◀️", callback_data=f"admin_give_gift:{page-1}"))
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("▶️", callback_data=f"admin_give_gift:{page+1}"))
        buttons.append(nav_row)
        buttons.append([InlineKeyboardButton("⬅️ В админ-панель", callback_data="admin_main")])

        kb = InlineKeyboardMarkup(buttons)
        text = "🎁 <b>Выберите предмет для выдачи пользователю:</b>"
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("admin_select_gift:"):
        gift_key = data.split(":")[1]
        context.user_data["admin_gift_key"] = gift_key
        await query.edit_message_text(
            f"🎁 Выбран подарок: <b>{GIFTS_BY_KEY[gift_key].name}</b>\n\n"
            "Введите Telegram ID или @username получателя в чат:",
            parse_mode=ParseMode.HTML
        )
        context.user_data["admin_state"] = WAITING_ADMIN_GIVE_GIFT_USER
        return

    if data == "admin_give_stars":
        await query.edit_message_text(
            "➕ <b>Выдача Stars игроку</b>\n\n"
            "Введите данные в формате:\n<code><ID или @username> <количество_stars></code>\n\n"
            "<i>Пример: 7459502130 50000</i>",
            parse_mode=ParseMode.HTML
        )
        context.user_data["admin_state"] = WAITING_ADMIN_GIVE_STARS
        return

async def admin_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    state = context.user_data.get("admin_state")
    if not state:
        return

    text = update.message.text.strip()

    if state == WAITING_ADMIN_GIVE_STARS:
        context.user_data["admin_state"] = None
        parts = text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await update.message.reply_text("❌ Неверный формат! Попробуйте снова через /admin.")
            return

        target_user = get_user_by_target(parts[0])
        if not target_user:
            await update.message.reply_text("❌ Пользователь не найден!")
            return

        amount = int(parts[1])
        add_user_stars(target_user["user_id"], amount)
        name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")
        await update.message.reply_text(f"✅ Успешно выдано <b>{amount:,} ⭐</b> игроку <b>{name}</b>!", parse_mode=ParseMode.HTML)
        return

    if state == WAITING_ADMIN_GIVE_GIFT_USER:
        context.user_data["admin_state"] = None
        gift_key = context.user_data.get("admin_gift_key")
        if not gift_key or gift_key not in GIFTS_BY_KEY:
            await update.message.reply_text("❌ Ошибка выбора подарка!")
            return

        target_user = get_user_by_target(text)
        if not target_user:
            await update.message.reply_text("❌ Пользователь не найден в базе!")
            return

        g = GIFTS_BY_KEY[gift_key]
        added = add_to_collection(target_user["user_id"], gift_key)
        name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")
        if added:
            await update.message.reply_text(f"🎁 Предмет <b>{g.name}</b> успешно выдан игроку <b>{name}</b>!", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"⚠️ Инвентарь игрока <b>{name}</b> переполнен!", parse_mode=ParseMode.HTML)
        return

# ---------------------------------------------------------------------------
# ЗАПУСК БОТА
# ---------------------------------------------------------------------------

def main() -> None:
    db_init()

    app = Application.builder().token(BOT_TOKEN).build()

    # Регистрация команд
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile_alias))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("send_gift", cmd_send_gift))
    app.add_handler(CommandHandler("admin", cmd_admin))

    # Обработка текстовых команд
    app.add_handler(MessageHandler(filters.Regex(re.compile(r"^(кто я|я)$", re.IGNORECASE)), cmd_profile_alias))

    # Callback и общие сообщения
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^(admin_|admin_main|admin_stats)"))
    app.add_handler(CallbackQueryHandler(on_callback))
    
    # Обработчики сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, user_input_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_group_message))

    log.info("NFT-Gift Bot v8.6 с поддержкой Кланов запущен успешно!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
