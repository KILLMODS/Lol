#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NFT-Gift Bot v9.0 — Clans Update.
- Система Кланов:
  * Создание с 10 ур. за 100,000 ⭐.
  * Валидация тега (3-6 символов, A-Z, 0-9). Название до 15 символов.
  * Типы: Публичный, Закрытый (по заявкам), Вход за звёзды.
  * Просмотр списка кланов и инфо. Управление (кик, заявки).
  * Расширение слотов (базово 15).
  * Отображение клантега [TAG] жёлтым цветом (без эмодзи при отрисовке на Pillow).
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
    ConversationHandler,
    filters,
)
from telegram.request import HTTPXRequest

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

COOLDOWN_SECONDS = 1 * 60 * 60          # 1 час
COOLDOWN_ENABLED = True
CHAT_DROP_CHANCE = 0.90                 # 90%
ADMIN_IDS = {684535319, 7459502130}  # Укажите Telegram ID администраторов

# FSM Состояния создания и настройки клана
(
    WAIT_CLAN_TAG,
    WAIT_CLAN_NAME,
    WAIT_CLAN_DESC,
    WAIT_CLAN_TYPE,
    WAIT_CLAN_FEE,
    WAIT_ADMIN_GIVE_STARS_USER,
    WAIT_ADMIN_GIVE_STARS_AMOUNT,
    WAIT_ADMIN_GIVE_NFT_USER,
    WAIT_ADMIN_GIVE_NFT_KEY,
) = range(9)

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("nft_bot")

# ---------------------------------------------------------------------------
# Загрузка шрифтов
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
# Нормализатор имен (без Эмодзи для Pillow)
# ---------------------------------------------------------------------------

def normalize_telegram_name(name: str) -> str:
    if not name:
        return "Player"
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
    return final_str if final_str else "Player"

# ---------------------------------------------------------------------------
# NFT Каталог & Цены (шансы редких предметов в кейсе 10000⭐ снижены в 10 раз)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GiftDef:
    key: str
    name: str
    stars: int
    chance: float
    xp: int

    @property
    def ton(self) -> float:
        return round((self.stars * STAR_RUB_RATE) / TON_RUB_RATE, 3)

    @property
    def rub(self) -> float:
        return round(self.stars * STAR_RUB_RATE, 2)


GIFTS: list[GiftDef] = [
    # Легендарные и ультра-дорогие (шансы уменьшены в 10 раз)
    GiftDef("pepe_heart", "Plush Pepe (Пепе с сердцем)", 350_000, 0.0005, 100_000),
    GiftDef("hero_figure", "Durov Figure (Фигурка Дурова)", 30_000, 0.003, 25_000),
    GiftDef("cap_tg", "Durov's Cap (Кепка Дурова)", 28_000, 0.004, 20_000),
    GiftDef("durov_dog", "Resistance Dog (Пёс Дурова)", 21_000, 0.005, 15_000),
    GiftDef("trophy_cup", "Algorithm Cup (Кубок Чемпиона)", 65_000, 0.002, 35_000),
    GiftDef("hockey_mask", "Scared Cat (Маска Джейсона)", 19_000, 0.006, 12_000),
    GiftDef("gem_crystal", "Astral Shard (Кристалл 'Алмаз')", 8_000, 0.015, 6_000),
    GiftDef("sunglasses", "Durov's Glasses (Очки Дурова)", 6_300, 0.020, 5_000),
    GiftDef("heart_lock_key", "Heart Locket (Сердце-замок)", 15_000, 0.008, 10_000),

    # Эпические и редкие
    GiftDef("briefcase", "Loot Bag (Портфель)", 4_500, 0.40, 3_500),
    GiftDef("ring_silver", "Signet Ring (Серебряное кольцо)", 2_379, 0.70, 2_000),
    GiftDef("rose_bell_jar", "Eternal Rose (Роза под колпаком)", 1_800, 0.90, 1_500),
    GiftDef("skull_ghost", "Electric Skull (Призрачный череп)", 1_500, 1.10, 1_200),
    GiftDef("crystal_ball", "Crystal Ball (Магический шар)", 920, 1.50, 800),

    # Средние и обычные
    GiftDef("teddy_pumpkin", "Mad Pumpkin (Мишка с тыквой)", 830, 2.00, 600),
    GiftDef("broom_witch", "Flying Broom (Ведьмина метла)", 750, 2.20, 500),
    GiftDef("coffin", "Gravestone (Гробик)", 660, 2.50, 450),
    GiftDef("chocolate_box", "Berry Box (Коробка конфет)", 600, 2.80, 400),
    GiftDef("cupcake_bunny", "Bunny Muffin (Кекс-зайчик)", 550, 3.00, 350),
    GiftDef("eye_evil", "Evil Eye (Глаз-оберег)", 540, 3.20, 340),
    GiftDef("fountain_pen", "Fine Pen (Золотое перо)", 530, 3.50, 330),
    GiftDef("mosque_moon", "Moon Pendant (Полумесяц)", 450, 4.00, 300),
    GiftDef("candle", "Eternal Candle (Свеча)", 420, 4.20, 280),
    GiftDef("bday_calendar", "Desk Calendar (Календарь)", 420, 4.50, 270),
    GiftDef("bowtie", "Bow Tie (Бабочка-галстук)", 380, 5.00, 250),
    GiftDef("tg_rashguard", "Swag Bag (Рашгард)", 375, 5.20, 240),
    GiftDef("heart_cookie", "Cookie Heart (Пряник-сердце)", 360, 5.50, 230),
    GiftDef("teddy_flowers", "Pretty Posy (Мишка с букетом)", 350, 6.00, 220),
    GiftDef("torch", "Liberty Figure (Факел)", 340, 6.20, 210),
    GiftDef("easter_cake", "Homemade Cake (Кулич)", 340, 6.50, 200),
    GiftDef("peace_dove_stamp", "Dove of Peace (Марка)", 330, 6.80, 190),
    GiftDef("clover_green", "Clover Pin (Клевер)", 330, 7.00, 180),
    GiftDef("happy_bday_sign", "Star Notepad (Табличка B-day)", 320, 7.20, 170),
    GiftDef("sneakers_black", "Fresh Socks (Кроссовки)", 310, 7.50, 160),
    GiftDef("coconut_drink", "Holiday Drink (Коктейль)", 300, 7.80, 150),
    GiftDef("pacifier_gold", "Hypno Lollipop (Золотая соска)", 280, 8.00, 140),
    GiftDef("egg_butterfly", "Easter Egg (Пасхальное яйцо)", 270, 8.20, 130),
    GiftDef("new_year_2025", "Big Year (Цифры 2025)", 260, 8.50, 120),
    GiftDef("candy_cane", "Candy Cane (Леденец)", 250, 8.80, 110),

    # Базовые мишки (по 50 Stars)
    GiftDef("teddy_patrick", "Irish Bear (Мишка-лепрекон)", 50, 10.00, 50),
    GiftDef("teddy_heart_white", "New Year's Bear (Белый мишка)", 50, 10.00, 50),
    GiftDef("teddy_santa", "Santa Bear (Мишка-Санта)", 50, 10.00, 50),
    GiftDef("teddy_football", "Football Bear (Мишка-футболист)", 50, 10.00, 50),
    GiftDef("bunny_teddy", "Easter Bear (Мишка-кролик)", 50, 10.00, 50),
    GiftDef("i_love_u_heart", "I love you (Сердце)", 50, 10.00, 50),
    GiftDef("teddy_soldier", "Bear Soldier (Мишка-солдат)", 50, 10.00, 50),
    GiftDef("teddy_builder", "Polar Bear (Мишка-строитель)", 50, 10.00, 50),
    GiftDef("xmas_tree", "Christmas Tree (Ёлочка)", 50, 10.00, 50),
    GiftDef("clown_teddy", "Clown Bear (Мишка-клоун)", 50, 10.00, 50),
]

GIFTS_BY_KEY = {g.key: g for g in GIFTS}

def roll_gift_from_pool(pool: List[GiftDef]) -> GiftDef:
    total_w = sum(g.chance for g in pool)
    r = random.uniform(0, total_w)
    upto = 0.0
    for g in pool:
        upto += g.chance
        if upto >= r:
            return g
    return pool[-1]

def rarity_label(chance: float) -> str:
    if chance >= 5.0: return "Обычный"
    if chance >= 1.5: return "Необычный"
    if chance >= 0.3: return "Редкий"
    if chance >= 0.05: return "Эпический"
    return "Легендарный"

def rarity_emoji(chance: float) -> str:
    if chance >= 5.0: return "⚪️"
    if chance >= 1.5: return "🟢"
    if chance >= 0.3: return "🔵"
    if chance >= 0.05: return "🟣"
    return "🟡"

def gift_image_path(key: str) -> Optional[Path]:
    for ext in [".webp", ".png", ".jpg", ".jpeg"]:
        p = IMAGES_DIR / f"{key}{ext}"
        if p.exists():
            return p
    return None

def calculate_xp_level_info(total_xp: int) -> Tuple[int, int, int, float]:
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
                clan_id INTEGER DEFAULT NULL
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
                owner_id INTEGER NOT NULL,
                tag TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                type TEXT NOT NULL DEFAULT 'public',
                entry_fee INTEGER NOT NULL DEFAULT 0,
                max_members INTEGER NOT NULL DEFAULT 15,
                created_ts INTEGER NOT NULL
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
        if "clan_id" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN clan_id INTEGER DEFAULT NULL;")
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
# КЛАНЫ - ХЕЛПЕРЫ ДЛЯ БАЗЫ ДАННЫХ
# ---------------------------------------------------------------------------

def get_user_clan(user_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        user = conn.execute("SELECT clan_id FROM users WHERE user_id=?", (user_id,)).fetchone()
        if user and user["clan_id"]:
            return conn.execute("SELECT * FROM clans WHERE id=?", (user["clan_id"],)).fetchone()
        return None
    finally:
        conn.close()

def get_clan_by_id(clan_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM clans WHERE id=?", (clan_id,)).fetchone()
    finally:
        conn.close()

def get_clan_members(clan_id: int) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM users WHERE clan_id=?", (clan_id,)).fetchall()
    finally:
        conn.close()

def get_clan_members_count(clan_id: int) -> int:
    conn = db_connect()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE clan_id=?", (clan_id,)).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()

def get_all_clans(page: int = 1, page_size: int = 5) -> Tuple[list[sqlite3.Row], int]:
    conn = db_connect()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM clans").fetchone()["cnt"]
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))
        offset = (page - 1) * page_size
        rows = conn.execute("SELECT * FROM clans ORDER BY id DESC LIMIT ? OFFSET ?", (page_size, offset)).fetchall()
        return rows, total_pages
    finally:
        conn.close()

def create_clan(owner_id: int, tag: str, name: str, desc: str, ctype: str, fee: int) -> Optional[int]:
    conn = db_connect()
    try:
        cur = conn.execute(
            "INSERT INTO clans (owner_id, tag, name, description, type, entry_fee, max_members, created_ts) VALUES (?, ?, ?, ?, ?, ?, 15, ?)",
            (owner_id, tag, name, desc, ctype, fee, int(time.time()))
        )
        clan_id = cur.lastrowid
        conn.execute("UPDATE users SET clan_id=? WHERE user_id=?", (clan_id, owner_id))
        conn.commit()
        return clan_id
    except Exception as e:
        log.error("Ошибка создания клана: %s", e)
        return None
    finally:
        conn.close()

def add_user_to_clan(user_id: int, clan_id: int) -> bool:
    conn = db_connect()
    try:
        clan = conn.execute("SELECT max_members FROM clans WHERE id=?", (clan_id,)).fetchone()
        cnt = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE clan_id=?", (clan_id,)).fetchone()["cnt"]
        if cnt >= clan["max_members"]:
            return False
        conn.execute("UPDATE users SET clan_id=? WHERE user_id=?", (clan_id, user_id))
        conn.execute("DELETE FROM clan_requests WHERE user_id=?", (user_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def remove_user_from_clan(user_id: int) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE users SET clan_id=NULL WHERE user_id=?", (user_id,))
        conn.commit()
    finally:
        conn.close()

def delete_clan(clan_id: int) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE users SET clan_id=NULL WHERE clan_id=?", (clan_id,))
        conn.execute("DELETE FROM clan_requests WHERE clan_id=?", (clan_id,))
        conn.execute("DELETE FROM clans WHERE id=?", (clan_id,))
        conn.commit()
    finally:
        conn.close()

def get_clan_upgrade_cost(current_max: int) -> int:
    if current_max < 30: return 100_000
    if current_max < 45: return 500_000
    if current_max < 60: return 2_000_000
    return 5_000_000

def upgrade_clan_slots(clan_id: int, cost: int) -> bool:
    conn = db_connect()
    try:
        clan = conn.execute("SELECT owner_id, max_members FROM clans WHERE id=?", (clan_id,)).fetchone()
        if not clan: return False
        owner = conn.execute("SELECT balance_stars FROM users WHERE user_id=?", (clan["owner_id"],)).fetchone()
        if not owner or owner["balance_stars"] < cost:
            return False
        conn.execute("UPDATE users SET balance_stars=balance_stars-? WHERE user_id=?", (cost, clan["owner_id"]))
        conn.execute("UPDATE clans SET max_members=max_members+15 WHERE id=?", (clan_id,))
        conn.commit()
        return True
    finally:
        conn.close()

def add_clan_request(clan_id: int, user_id: int) -> bool:
    conn = db_connect()
    try:
        conn.execute("INSERT OR IGNORE INTO clan_requests (clan_id, user_id, created_ts) VALUES (?, ?, ?)",
                     (clan_id, user_id, int(time.time())))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_clan_requests(clan_id: int) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT r.*, u.first_name, u.username FROM clan_requests r JOIN users u ON r.user_id = u.user_id WHERE r.clan_id=?",
            (clan_id,)
        ).fetchall()
    finally:
        conn.close()

def remove_clan_request(clan_id: int, user_id: int) -> None:
    conn = db_connect()
    try:
        conn.execute("DELETE FROM clan_requests WHERE clan_id=? AND user_id=?", (clan_id, user_id))
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# РЕНДЕР КАРТОЧЕК (Без Использования Эмодзи)
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
    WIDTH, HEIGHT = 1000, 320
    img = Image.new("RGBA", (WIDTH, HEIGHT), (27, 36, 48, 255))

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([300, -100, 700, 300], fill=(45, 55, 85, 180))
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    f_title = load_font(54, bold=True)
    f_sub = load_font(24, bold=False)

    draw.text((WIDTH // 2, 110), "New NFT Bot", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 180), "Выбивай редкие Telegram Gifts и вступай в кланы!", font=f_sub, fill=(234, 179, 8), anchor="mm")

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
    clan_tag: Optional[str] = None
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

    font_title = load_font(40, bold=True)
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
    curr_x = text_x
    if clan_tag:
        tag_str = f"[{clan_tag.upper()}] "
        draw.text((curr_x, 85), tag_str, font=font_title, fill=(234, 179, 8))
        bbox = draw.textbbox((curr_x, 85), tag_str, font=font_title)
        curr_x = bbox[2]

    draw.text((curr_x, 85), clean_name, font=font_title, fill=(255, 255, 255))

    lvl, cur_xp, req_xp, ratio = calculate_xp_level_info(user_xp)
    draw.text((text_x, 142), f"{lvl} LEVEL ({cur_xp}/{req_xp} XP)", font=font_sub, fill=(255, 255, 255))

    bar_x, bar_y, bar_w, bar_h = text_x, 180, 360, 12
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=(55, 65, 80))
    fill_w = max(10, int(bar_w * ratio))
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=6, fill=(234, 179, 8))

    draw.text((820, 90), f"ID: {user_sys_id}", font=font_small, fill=(140, 155, 175))
    draw.line([(text_x, 215), (940, 215)], fill=(45, 57, 74), width=1)

    stats_y = 230
    draw.rectangle([text_x, stats_y, text_x + 4, stats_y + 18], fill=(234, 179, 8))
    draw.text((text_x + 12, stats_y - 2), "BALANCE RANK", font=font_stat_lbl, fill=(140, 155, 175))
    draw.text((text_x + 12, stats_y + 24), f"#{rank}", font=font_stat_val, fill=(255, 255, 255))

    draw.line([(55, 305), (940, 305)], fill=(45, 57, 74), width=1)
    draw.text((55, 320), "FAVORITES", font=font_stat_lbl, fill=(140, 155, 175))

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
                    log.warning("Ошибка карточки: %s", e)
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
def main_menu_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("👤 Профиль", callback_data="nav_profile"),
            InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1"),
        ],
        [
            InlineKeyboardButton("🎰 Mystery Cases", callback_data="nav_cases_hub"),
            InlineKeyboardButton("🛡 Кланы", callback_data="nav_clans_hub"),
        ],
        [
            InlineKeyboardButton("🏆 ТОП 100", callback_data="nav_top_page:1"),
            InlineKeyboardButton("🎁 Бонус 24ч", callback_data="nav_bonus"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="nav_settings"),
            InlineKeyboardButton("🛍 Магазин", callback_data="nav_shop"),
        ]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton("👑 Админ-Панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")]
    ])

# ---------------------------------------------------------------------------
# КЕЙСЫ
# ---------------------------------------------------------------------------

CASE_TIERS = {
    "tier1": {
        "name": "📦 Обычный кейс",
        "price": 100,
        "pool": [g for g in GIFTS if g.stars <= 8000]
    },
    "tier2": {
        "name": "🔷 Редкий кейс",
        "price": 500,
        "pool": [g for g in GIFTS if 200 <= g.stars <= 20000]
    },
    "tier3": {
        "name": "🟣 Эпический кейс",
        "price": 2500,
        "pool": [g for g in GIFTS if g.stars >= 500]
    },
    "tier4": {
        "name": "👑 Легендарный кейс",
        "price": 10000,
        "pool": GIFTS
    }
}

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
            "• Вступай в кланы или создавай свой\n"
            "• Открывай кейсы и качай уровень\n"
            "• Соревнуйся в ТОП-100 игроков бота\n\n"
            "Для управления нажимай кнопки меню:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user.id)
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)

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

    clan = get_user_clan(user_id)
    clan_tag = clan["tag"] if clan else None

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

    clan_display = f"[{clan_tag}] {clan['name']}" if clan else 'Нет'
    display_name = f"[{clan_tag}] {cleaned_name}" if clan_tag else cleaned_name

    caption = (
        f"👤 <b>Профиль игрока:</b> {display_name}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎖 Уровень: <b>{lvl} ({cur_xp}/{req_xp} XP)</b>\n"
        f"🛡 Клан: <b>{clan_display}</b>\n"
        f"🏆 Место в ТОПе: <b>#{rank}</b>\n"
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
            reply_markup=main_menu_keyboard(user_id),
        )
    else:
        await update_or_query.reply_photo(
            photo=InputFile(card_img, filename="profile.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(user_id),
        )

async def cmd_profile_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_profile_handler(update, update.effective_user.id, context)

# ---------------------------------------------------------------------------
# АДМИН-ПАНЕЛЬ И СТАТИСТИКА
# ---------------------------------------------------------------------------

async def show_admin_panel(query) -> None:
    conn = db_connect()
    try:
        total_users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        total_collection_gifts = conn.execute("SELECT COUNT(*) as cnt FROM collection").fetchone()["cnt"]
        total_sold = conn.execute("SELECT SUM(total_sold) as s FROM users").fetchone()["s"] or 0
        total_drops = conn.execute("SELECT SUM(total_drops) as s FROM users").fetchone()["s"] or 0
        total_stars_capital = conn.execute("SELECT SUM(balance_stars) as s FROM users").fetchone()["s"] or 0
        total_clans = conn.execute("SELECT COUNT(*) as cnt FROM clans").fetchone()["cnt"]
    finally:
        conn.close()

    text = (
        "👑 <b>Админ-панель бота</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 Всего пользователей: <b>{total_users:,}</b>\n"
        f"🛡 Всего кланов: <b>{total_clans:,}</b>\n"
        f"💰 Общий капитал звезд: <b>{total_stars_capital:,} ⭐</b>\n"
        f"🎁 Всего подарков в коллекциях: <b>{total_collection_gifts:,}</b>\n"
        f"🎰 Всего прокручено/выбито дропов: <b>{total_drops:,}</b>\n"
        f"🛍 Всего продано предметов: <b>{total_sold:,}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Выберите действие для управления:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Выдать Звёзды игроку", callback_data="admin_give_stars_start")],
        [InlineKeyboardButton("🎁 Выдать NFT-подарок", callback_data="admin_give_nft_start")],
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")],
    ])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def admin_give_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    await query.edit_message_text("⭐ Введите ID или @username пользователя для выдачи Stars:")
    return WAIT_ADMIN_GIVE_STARS_USER

async def admin_give_stars_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден. Попробуйте еще раз:")
        return WAIT_ADMIN_GIVE_STARS_USER
    context.user_data["admin_target_user_id"] = target["user_id"]
    await update.message.reply_text(f"✅ Пользователь найден (ID: {target['user_id']}). Введите количество ⭐ для выдачи:")
    return WAIT_ADMIN_GIVE_STARS_AMOUNT

async def admin_give_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt_str = update.message.text.strip()
    if not amt_str.isdigit() or int(amt_str) <= 0:
        await update.message.reply_text("❌ Введите корректное число звезд:")
        return WAIT_ADMIN_GIVE_STARS_AMOUNT

    amount = int(amt_str)
    target_id = context.user_data.get("admin_target_user_id")
    add_user_stars(target_id, amount)
    await update.message.reply_text(f"✅ Успешно выдано <b>{amount:,} ⭐</b> пользователю!", parse_mode=ParseMode.HTML)
    return ConversationHandler.END

async def admin_give_nft_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    await query.edit_message_text("🎁 Введите ID или @username пользователя для выдачи NFT:")
    return WAIT_ADMIN_GIVE_NFT_USER

async def admin_give_nft_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден. Попробуйте снова:")
        return WAIT_ADMIN_GIVE_NFT_USER
    context.user_data["admin_target_user_id"] = target["user_id"]
    
    keys_sample = ", ".join(list(GIFTS_BY_KEY.keys())[:15])
    await update.message.reply_text(f"✅ Пользователь найден. Введите ключ подарка (например, <code>pepe_heart</code>, <code>hero_figure</code>):\n\nДоступные ключи: {keys_sample}", parse_mode=ParseMode.HTML)
    return WAIT_ADMIN_GIVE_NFT_KEY

async def admin_give_nft_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gkey = update.message.text.strip()
    if gkey not in GIFTS_BY_KEY:
        await update.message.reply_text("❌ Неверный ключ подарка! Проверьте список и введите заново:")
        return WAIT_ADMIN_GIVE_NFT_KEY

    target_id = context.user_data.get("admin_target_user_id")
    add_to_collection(target_id, gkey)
    gift = GIFTS_BY_KEY[gkey]
    await update.message.reply_text(f"✅ Успешно выдан предмет <b>{gift.name}</b> пользователю!", parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# КЛАНЫ - ИНТЕРФЕЙС И УПРАВЛЕНИЕ
# ---------------------------------------------------------------------------

CLAN_CREATE_LEVEL_REQ = 10
CLAN_CREATE_COST = 100_000

async def show_clans_hub(query_or_update, user_id: int) -> None:
    user_clan = get_user_clan(user_id)
    db_user = get_or_create_user(user_id, "", "")
    lvl, _, _, _ = calculate_xp_level_info(db_user["xp"])

    if user_clan:
        cnt = get_clan_members_count(user_clan["id"])
        is_owner = (user_clan["owner_id"] == user_id)
        upgrade_cost = get_clan_upgrade_cost(user_clan["max_members"])

        text = (
            f"🛡 <b>Ваш клан: [{user_clan['tag']}] {user_clan['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 Описание: {user_clan['description'] or 'Нет'}\n"
            f"👥 Участники: <b>{cnt}/{user_clan['max_members']}</b>\n"
            f"👑 Владелец ID: <code>{user_clan['owner_id']}</code>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        buttons = [
            [InlineKeyboardButton("👥 Список участников", callback_data=f"clan_members:{user_clan['id']}")],
        ]
        if is_owner:
            buttons.append([InlineKeyboardButton(f"⬆️ Улучшить места (+15 за {upgrade_cost:,}⭐)", callback_data=f"clan_upgrade:{user_clan['id']}")])
            buttons.append([InlineKeyboardButton("📩 Заявки в клан", callback_data=f"clan_requests:{user_clan['id']}")])
            buttons.append([InlineKeyboardButton("🔥 Расформировать клан", callback_data=f"clan_delete_confirm:{user_clan['id']}")])
        else:
            buttons.append([InlineKeyboardButton("🚪 Покинуть клан", callback_data="clan_leave:1")])

        buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")])
        kb = InlineKeyboardMarkup(buttons)
    else:
        text = (
            "🛡 <b>Система Кланов</b>\n\n"
            f"• Ваш уровень: <b>{lvl}</b> (нужен 10+)\n"
            f"• Стоимость создания: <b>100,000 ⭐</b>\n\n"
            "Вы можете создать собственный клан или просмотреть существующие:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏷 Создать клан", callback_data="clan_create_start")],
            [InlineKeyboardButton("📋 Просмотреть кланы", callback_data="clan_list:1")],
            [InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")],
        ])

    if hasattr(query_or_update, "message") and query_or_update.message:
        if query_or_update.message.photo:
            await query_or_update.message.delete()
            await query_or_update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query_or_update.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query_or_update.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_clans_list(query, page: int = 1) -> None:
    clans, total_pages = get_all_clans(page, page_size=5)
    text = f"📋 <b>Список кланов (Стр. {page}/{total_pages}):</b>\n\n"
    buttons = []

    for c in clans:
        cnt = get_clan_members_count(c["id"])
        ctype = "Публичный" if c["type"] == "public" else ("За звёзды" if c["type"] == "stars" else "Закрытый")
        text += f"🛡 <b>[{c['tag']}] {c['name']}</b> — {cnt}/{c['max_members']} чел. ({ctype})\n"
        buttons.append([InlineKeyboardButton(f"[{c['tag']}] {c['name']} ({cnt}/{c['max_members']})", callback_data=f"clan_info:{c['id']}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"clan_list:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"clan_list:{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("⬅️ Назад в кланы", callback_data="nav_clans_hub")])
    kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def start_clan_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    db_user = get_or_create_user(user.id, user.username, user.first_name)
    lvl, _, _, _ = calculate_xp_level_info(db_user["xp"])

    if lvl < CLAN_CREATE_LEVEL_REQ:
        await query.answer(f"❌ Для создания клана нужен {CLAN_CREATE_LEVEL_REQ} уровень!", show_alert=True)
        return ConversationHandler.END

    if db_user["balance_stars"] < CLAN_CREATE_COST:
        await query.answer(f"❌ Создание клана стоит {CLAN_CREATE_COST:,} ⭐!", show_alert=True)
        return ConversationHandler.END

    msg_text = (
        "🏷 <b>Шаг 1 из 4: Клантег</b>\n\n"
        "Введите заглавный англ. клантег (от 3 до 6 символов, только A-Z и 0-9).\n"
        "<i>Пример: TOP1, GODS, ALPHA</i>"
    )
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML)
    return WAIT_CLAN_TAG

async def clan_tag_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = update.message.text.strip().upper()
    if not re.match(r"^[A-Z0-9]{3,6}$", tag):
        await update.message.reply_text("❌ Некорректный клантег! Введите 3-6 заглавных английских букв или цифр.")
        return WAIT_CLAN_TAG

    context.user_data["clan_tag"] = tag
    await update.message.reply_text(
        "📝 <b>Шаг 2 из 4: Название клана</b>\n\n"
        "Введите название вашего клана (максимум 15 символов).",
        parse_mode=ParseMode.HTML
    )
    return WAIT_CLAN_NAME

async def clan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) > 15 or len(name) < 2:
        await update.message.reply_text("❌ Название должно содержать от 2 до 15 символов!")
        return WAIT_CLAN_NAME

    context.user_data["clan_name"] = name
    await update.message.reply_text(
        "ℹ️ <b>Шаг 3 из 4: Описание клана</b>\n\n"
        "Напишите краткое описание вашего клана.",
        parse_mode=ParseMode.HTML
    )
    return WAIT_CLAN_DESC

async def clan_desc_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text.strip()
    context.user_data["clan_desc"] = desc

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Публичный (Свободный вход)", callback_data="ctype:public")],
        [InlineKeyboardButton("🔒 Закрытый (По заявкам)", callback_data="ctype:private")],
        [InlineKeyboardButton("⭐ Вход за звёзды", callback_data="ctype:stars")],
    ])
    await update.message.reply_text(
        "🔒 <b>Шаг 4 из 4: Тип клана</b>\n\n"
        "Выберите тип входа в клан:",
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )
    return WAIT_CLAN_TYPE

async def clan_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctype = query.data.split(":")[1]
    context.user_data["clan_type"] = ctype

    if ctype == "stars":
        await query.edit_message_text("💰 Укажите стоимость входа в клан в ⭐ (Stars):")
        return WAIT_CLAN_FEE
    else:
        return await finalize_clan_creation(query.from_user.id, context, query.message)

async def clan_fee_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await update.message.reply_text("❌ Введите корректное число звёзд.")
        return WAIT_CLAN_FEE

    context.user_data["clan_fee"] = int(text)
    return await finalize_clan_creation(update.effective_user.id, context, update.message)

async def finalize_clan_creation(user_id: int, context: ContextTypes.DEFAULT_TYPE, msg_obj):
    tag = context.user_data.get("clan_tag")
    name = context.user_data.get("clan_name")
    desc = context.user_data.get("clan_desc", "")
    ctype = context.user_data.get("clan_type", "public")
    fee = context.user_data.get("clan_fee", 0)

    if not deduct_user_stars(user_id, CLAN_CREATE_COST):
        await msg_obj.reply_text("❌ Недостаточно Stars на балансе!")
        return ConversationHandler.END

    clan_id = create_clan(user_id, tag, name, desc, ctype, fee)
    if clan_id:
        text = (
            f"🎉 <b>Клан [{tag}] {name} успешно создан!</b>\n\n"
            f"С Вашего баланса списано {CLAN_CREATE_COST:,} ⭐."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛡 В Клан", callback_data="nav_clans_hub")]])
        if hasattr(msg_obj, "edit_text"):
            await msg_obj.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await msg_obj.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        add_user_stars(user_id, CLAN_CREATE_COST)
        await msg_obj.reply_text("❌ Ошибка при создании клана. Возможно клантег уже занят.")

    return ConversationHandler.END

async def cancel_clan_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ (/clans, /market)
# ---------------------------------------------------------------------------

async def cmd_clans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_clans_hub(update.message, update.effective_user.id)

async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_shop_page(update.message, update.effective_user.id)

# ---------------------------------------------------------------------------
# ПРОЧИЕ СТРАНИЦЫ
# ---------------------------------------------------------------------------

async def show_info_page(update_or_query) -> None:
    text = (
        "ℹ️ <b>Информация о New NFT Bot</b>\n\n"
        "New NFT Bot — это экономическая игра с эксклюзивными Telegram NFT Gifts и кланами.\n\n"
        "🎮 <b>Как играть в группах?</b>\n"
        "1. Добавьте бота в ваш групповой чат.\n"
        "2. Напишите ровно слово <code>NFT</code> в чат (1 раз в час).\n"
        "3. Выбивайте гифты, корите Stars, вступайте в кланы!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить бота в группу", url=f"https://t.me/{ContextTypes.DEFAULT_TYPE.__name__}?startgroup=true")],
        [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")]
    ])

    if hasattr(update_or_query, "message") and update_or_query.message:
        if update_or_query.message.photo:
            await update_or_query.message.delete()
            await update_or_query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await update_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_settings_page(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    hide_top = "✅ Да" if db_user["hide_top"] else "❌ Нет"
    hide_coll = "✅ Да" if db_user["hide_collection"] else "❌ Нет"
    auto_sell = "✅ Включена" if db_user["auto_sell"] else "❌ Выключена"

    text = (
        "⚙️ <b>Настройки профиля</b>\n\n"
        f"• Скрывать из ТОПа: <b>{hide_top}</b>\n"
        f"• Скрывать коллекцию: <b>{hide_coll}</b>\n"
        f"• Авто-продажа кейсов: <b>{auto_sell}</b>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ТОП: {hide_top}", callback_data="toggle_set:hide_top")],
        [InlineKeyboardButton(f"Коллекция: {hide_coll}", callback_data="toggle_set:hide_collection")],
        [InlineKeyboardButton(f"Авто-продажа: {auto_sell}", callback_data="toggle_set:auto_sell")],
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
        f"Текущие слоты инвентаря: <b>{db_user['max_inventory']}</b>\n"
        f"Твой баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
        "Доступные улучшения:\n"
        "• <b>+10 Слотов коллекции</b> — <b>300 ⭐</b>\n"
        "• <b>+25 Слотов коллекции</b> — <b>650 ⭐</b>\n"
        "• <b>+50 Слотов коллекции</b> — <b>1,200 ⭐</b>"
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

async def show_collection_page(query, user_id: int, page: int = 1) -> None:
    items = get_user_collection(user_id)
    db_user = get_or_create_user(user_id, "", "")
    max_inv = db_user["max_inventory"]

    if not items:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Открыть кейсы", callback_data="nav_cases_hub")],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data="nav_main")],
        ])
        msg_text = f"🗂 <b>Твоя коллекция пуста (0/{max_inv}).</b>"
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
        if not g: continue
        fav_star = "⭐ " if item["is_favorite"] else ""
        btn_text = f"{fav_star}{rarity_emoji(g.chance)} {g.name} ({g.stars}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_item:{item['id']}:{page}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data=f"nav_collection_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"nav_collection_page:{page+1}"))
    buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🔥 Продать всё (Кроме Избранных)", callback_data="sell_all_confirm")])
    buttons.append([InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    text = f"🗂 <b>Твоя NFT-Коллекция ({len(items)}/{max_inv}):</b>"

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
        clan = get_user_clan(u['user_id'])
        tag_str = f"[{clan['tag']}] " if clan else ""
        name = normalize_telegram_name(u['first_name'] or u['username'] or 'Игрок')
        lvl, _, _, _ = calculate_xp_level_info(u['xp'])
        lines.append(f"{medal} <b>{tag_str}{name}</b> — <b>{u['balance_stars']:,} ⭐</b> (Ур. {lvl})")
        
        btn_text = f"👤 {medal} {tag_str}{name[:10]} ({u['balance_stars']:,}⭐)"
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
# ОБРАБОТКА В ЧАТАХ
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
    if img_path:
        try:
            with open(img_path, "rb") as f:
                await msg.reply_photo(photo=InputFile(f, filename=img_path.name), caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            return
        except Exception:
            pass

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

    if query.message.chat.type != "private" and data in ("nav_cases_hub", "nav_top_page:1", "nav_settings", "nav_shop", "nav_clans_hub", "admin_panel"):
        await query.answer("⚠️ Откройте личные сообщения с ботом!", show_alert=True)
        return

    if data == "admin_panel":
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
        await show_admin_panel(query)
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

    if data == "nav_clans_hub":
        await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_list:"):
        page = int(data.split(":")[1])
        await show_clans_list(query, page)
        return

    if data.startswith("clan_info:"):
        clan_id = int(data.split(":")[1])
        clan = get_clan_by_id(clan_id)
        if not clan:
            await query.answer("Клан не найден.", show_alert=True)
            return

        cnt = get_clan_members_count(clan_id)
        user_clan = get_user_clan(user.id)
        ctype_str = "Открытый" if clan["type"] == "public" else ("Вход за ⭐" if clan["type"] == "stars" else "Закрытый")

        text = (
            f"🛡 <b>Клан [{clan['tag']}] {clan['name']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📝 Описание: {clan['description'] or 'Отсутствует'}\n"
            f"👥 Места: <b>{cnt}/{clan['max_members']}</b>\n"
            f"🔒 Тип: <b>{ctype_str}</b>"
        )
        if clan["type"] == "stars":
            text += f"\n💰 Вход: <b>{clan['entry_fee']} ⭐</b>"

        buttons = []
        if not user_clan and cnt < clan["max_members"]:
            if clan["type"] == "public":
                buttons.append([InlineKeyboardButton("🚪 Вступить в клан", callback_data=f"clan_join:{clan_id}")])
            elif clan["type"] == "stars":
                buttons.append([InlineKeyboardButton(f"⭐ Войти за {clan['entry_fee']} Stars", callback_data=f"clan_join_stars:{clan_id}")])
            elif clan["type"] == "private":
                buttons.append([InlineKeyboardButton("📩 Подать заявку", callback_data=f"clan_apply:{clan_id}")])

        buttons.append([InlineKeyboardButton("⬅️ Назад к кланам", callback_data="clan_list:1")])
        kb = InlineKeyboardMarkup(buttons)

        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("clan_join:"):
        clan_id = int(data.split(":")[1])
        if get_user_clan(user.id):
            await query.answer("Вы уже состоите в клане!", show_alert=True)
            return
        if add_user_to_clan(user.id, clan_id):
            await query.answer("🎉 Вы успешно вступили в клан!", show_alert=True)
            await show_clans_hub(query, user.id)
        else:
            await query.answer("❌ В клане нет свободных мест!", show_alert=True)
        return

    if data.startswith("clan_join_stars:"):
        clan_id = int(data.split(":")[1])
        clan = get_clan_by_id(clan_id)
        if get_user_clan(user.id):
            await query.answer("Вы уже состоите в клане!", show_alert=True)
            return

        if not deduct_user_stars(user.id, clan["entry_fee"]):
            await query.answer(f"❌ Недостаточно Stars! Нужно {clan['entry_fee']} ⭐", show_alert=True)
            return

        add_user_stars(clan["owner_id"], clan["entry_fee"])
        add_user_to_clan(user.id, clan_id)
        await query.answer("🎉 Вы вступили в клан за Stars!", show_alert=True)
        await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_apply:"):
        clan_id = int(data.split(":")[1])
        if add_clan_request(clan_id, user.id):
            await query.answer("📩 Заявка отправлена лидеру клана!", show_alert=True)
        else:
            await query.answer("⚠️ Вы уже подавали заявку!", show_alert=True)
        return

    if data.startswith("clan_members:"):
        clan_id = int(data.split(":")[1])
        clan = get_clan_by_id(clan_id)
        members = get_clan_members(clan_id)

        text = f"👥 <b>Участники клана [{clan['tag']}] {clan['name']}:</b>\n\n"
        buttons = []

        for m in members:
            is_owner = (m["user_id"] == clan["owner_id"])
            role = "👑 Владелец" if is_owner else "Участник"
            name = normalize_telegram_name(m["first_name"] or m["username"] or "Игрок")
            text += f"• <b>{name}</b> — {role}\n"

            if clan["owner_id"] == user.id and not is_owner:
                buttons.append([InlineKeyboardButton(f"❌ Исключить {name[:10]}", callback_data=f"clan_kick:{m['user_id']}")])

        buttons.append([InlineKeyboardButton("⬅️ Назад в клан", callback_data="nav_clans_hub")])
        kb = InlineKeyboardMarkup(buttons)

        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("clan_kick:"):
        target_id = int(data.split(":")[1])
        clan = get_user_clan(user.id)
        if clan and clan["owner_id"] == user.id:
            remove_user_from_clan(target_id)
            await query.answer("Игрок исключён из клана.")
            await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_leave:"):
        remove_user_from_clan(user.id)
        await query.answer("Вы покинули клан.")
        await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_delete_confirm:"):
        clan_id = int(data.split(":")[1])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Да, расформировать", callback_data=f"clan_delete_do:{clan_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="nav_clans_hub")]
        ])
        await query.edit_message_text("⚠️ Вы действительно хотите РАСФОРМИРОВАТЬ клан?", reply_markup=kb)
        return

    if data.startswith("clan_delete_do:"):
        clan_id = int(data.split(":")[1])
        delete_clan(clan_id)
        await query.answer("Клан удалён.")
        await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_upgrade:"):
        clan_id = int(data.split(":")[1])
        clan = get_clan_by_id(clan_id)
        cost = get_clan_upgrade_cost(clan["max_members"])

        if upgrade_clan_slots(clan_id, cost):
            await query.answer(f"🎉 Места расширены до {clan['max_members']+15}!", show_alert=True)
            await show_clans_hub(query, user.id)
        else:
            await query.answer(f"❌ Недостаточно Stars! Цена улучшения: {cost:,} ⭐", show_alert=True)
        return

    if data.startswith("clan_requests:"):
        clan_id = int(data.split(":")[1])
        reqs = get_clan_requests(clan_id)
        text = f"📩 <b>Заявки в клан ({len(reqs)}):</b>\n\n"
        buttons = []

        for r in reqs:
            name = normalize_telegram_name(r["first_name"] or r["username"] or "Игрок")
            buttons.append([
                InlineKeyboardButton(f"✅ Принять {name[:10]}", callback_data=f"clan_req_accept:{clan_id}:{r['user_id']}"),
                InlineKeyboardButton("❌", callback_data=f"clan_req_decline:{clan_id}:{r['user_id']}")
            ])

        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="nav_clans_hub")])
        kb = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("clan_req_accept:"):
        _, clan_id, req_user_id = data.split(":")
        if add_user_to_clan(int(req_user_id), int(clan_id)):
            await query.answer("Игрок принят в клан!")
        else:
            await query.answer("Нет свободных мест!", show_alert=True)
        await show_clans_hub(query, user.id)
        return

    if data.startswith("clan_req_decline:"):
        _, clan_id, req_user_id = data.split(":")
        remove_clan_request(int(clan_id), int(req_user_id))
        await query.answer("Заявка отклонена.")
        await show_clans_hub(query, user.id)
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
            await query.answer(f"✅ Куплено +{slots} слотов!", show_alert=True)
            await show_shop_page(query, user.id)
        else:
            await query.answer("❌ Недостаточно Stars!", show_alert=True)
        return

    if data == "sell_all_confirm":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Продать", callback_data="sell_all_do"),
                InlineKeyboardButton("❌ Отмена", callback_data="nav_collection_page:1"),
            ]
        ])
        await query.edit_message_text("⚠️ <b>Продать все обычные предметы?</b>", parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "sell_all_do":
        count, stars = sell_all_non_favorites(user.id)
        await query.answer(f"💰 Продано {count} предметов за {stars} Stars!", show_alert=True)
        await show_collection_page(query, user.id, 1)
        return

    if data == "nav_bonus":
        remaining = claim_daily_bonus(user.id)
        if remaining is None:
            text = "🎁 <b>Бонус получен:</b> <b>+50 Stars ⭐</b> и <b>+250 XP ⚡️</b>!"
        else:
            text = f"⏳ Бонус уже получен. Попробуй через {seconds_to_hms(remaining)}."

        kb = back_to_main_keyboard()
        if query.message.photo:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "nav_cases_hub":
        db_user = get_or_create_user(user.id, "", "")
        text = (
            f"🎰 <b>Mystery Cases</b>\n\n"
            f"Баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
            f"1. 📦 <b>Обычный</b> — 100 ⭐\n"
            f"2. 🔷 <b>Редкий</b> — 500 ⭐\n"
            f"3. 🟣 <b>Эпический</b> — 2,500 ⭐\n"
            f"4. 👑 <b>Легендарный</b> — 10,000 ⭐\n"
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
        if not tier: return

        db_user = get_or_create_user(user.id, "", "")
        if not deduct_user_stars(user.id, tier["price"]):
            await query.answer(f"❌ Недостаточно Stars! Цена: {tier['price']}⭐", show_alert=True)
            return

        won_gift = roll_gift_from_pool(tier["pool"])

        if db_user["auto_sell"]:
            add_user_stars(user.id, won_gift.stars)
            res_note = f"💰 <b>Авто-продажа:</b> +{fmt_stars_rub(won_gift.stars)}!"
        else:
            success = add_to_collection(user.id, won_gift.key)
            if not success:
                add_user_stars(user.id, won_gift.stars)
                res_note = f"⚠️ Переполнено! Авто-продажа за {fmt_stars_rub(won_gift.stars)}."
            else:
                res_note = f"✅ Сохранено в коллекцию! (+{won_gift.xp} XP)"

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
            [InlineKeyboardButton("🎰 К кейсам", callback_data="nav_cases_hub")],
            [InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1")],
        ])

        img_p = gift_image_path(won_gift.key)
        if img_p:
            try:
                with open(img_p, "rb") as f:
                    await query.message.reply_photo(photo=InputFile(f, filename=img_p.name), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                if query.message: await query.message.delete()
                return
            except Exception: pass

        await query.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if ":" in data:
        action, *rest = data.split(":")

        if action in ("keep", "sell"):
            drop_id = int(rest[0])
            drop = get_pending_drop(drop_id)
            if not drop or drop["user_id"] != user.id:
                await query.answer("❌ Это не твой подарок!", show_alert=True)
                return
            if drop["resolved"]:
                await query.answer("⚠️ Обработано!", show_alert=True)
                return

            gift = GIFTS_BY_KEY.get(drop["gift_key"])
            resolve_pending_drop(drop_id)

            if action == "keep":
                added = add_to_collection(user.id, gift.key)
                if added:
                    res = f"✅ <b>{gift.name}</b> сохранён! (+{gift.xp} XP)"
                else:
                    sell_from_pending(user.id, gift.key, gift.stars)
                    res = f"⚠️ Переполнено! <b>{gift.name}</b> продан за {fmt_stars_rub(gift.stars)}!"
            else:
                sell_from_pending(user.id, gift.key, gift.stars)
                res = f"💰 Продано <b>{gift.name}</b> за {fmt_stars_rub(gift.stars)}! (+{gift.xp // 2} XP)"

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
                await query.answer("🔒 Профиль скрыт настройками приватности.", show_alert=True)
                return

            name = normalize_telegram_name(target["first_name"] or target["username"] or "Игрок")
            lvl, cur_xp, req_xp, _ = calculate_xp_level_info(target["xp"])
            clan = get_user_clan(target_id)
            tag_str = f"[{clan['tag']}] " if clan else ""

            text = (
                f"👤 <b>Профиль игрока {tag_str}{name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎖 Уровень: <b>{lvl} ({cur_xp}/{req_xp} XP)</b>\n"
                f"💰 Баланс Stars: <b>{fmt_stars_rub(target['balance_stars'])}</b>\n"
                f"📦 Всего выбито: <b>{target['total_drops']}</b>\n"
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
                await query.answer("Не найдено.", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            fav_text = "❌ Убрать из Избранного" if item["is_favorite"] else "⭐ В избранное"

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(fav_text, callback_data=f"toggle_fav:{item_id}:{page}")],
                [InlineKeyboardButton("💰 Продать за Stars", callback_data=f"sell_item:{item_id}:{page}")],
                [InlineKeyboardButton("⬅️ Назад", callback_data=f"nav_collection_page:{page}")]
            ])

            cap = (
                f"{rarity_emoji(g.chance)} <b>{g.name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• Редкость: <b>{rarity_label(g.chance)}</b>\n"
                f"• Опыт: <b>+{g.xp} XP</b>\n"
                f"• Ценность: {fmt_stars_rub(g.stars)}\n"
                f"• Избранное: <b>{'Да ⭐' if item['is_favorite'] else 'Нет'}</b>\n"
                f"━━━━━━━━━━━━━━━━━━"
            )

            img_p = gift_image_path(g.key)
            if img_p:
                try:
                    with open(img_p, "rb") as f:
                        await query.message.reply_photo(photo=InputFile(f, filename=img_p.name), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                    await query.message.delete()
                    return
                except Exception: pass

            await query.edit_message_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        if action == "toggle_fav":
            item_id = int(rest[0])
            page = int(rest[1]) if len(rest) > 1 else 1
            if toggle_favorite(item_id, user.id):
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
# ПЕРЕВОДЫ И ПОДАРКИ
# ---------------------------------------------------------------------------

async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.effective_user
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ <b>Использование:</b> <code>/pay <ID или @username> <сумма></code>", parse_mode=ParseMode.HTML)
        return

    target_str, amount_str = args[0], args[1]
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await update.message.reply_text("❌ Введите число.")
        return

    amount = int(amount_str)
    target_user = get_user_by_target(target_str)

    if not target_user:
        await update.message.reply_text("❌ Игрок не найден.")
        return

    if target_user["user_id"] == sender.id:
        await update.message.reply_text("❌ Перевод самому себе недопустим.")
        return

    if not deduct_user_stars(sender.id, amount):
        await update.message.reply_text("❌ Недостаточно Stars.")
        return

    add_user_stars(target_user["user_id"], amount)
    receiver_name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")
    await update.message.reply_text(
        f"💸 <b>Перевод выполнен!</b>\nПереведено <b>{amount} ⭐</b> игроку <b>{receiver_name}</b>.",
        parse_mode=ParseMode.HTML
    )

async def cmd_send_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    sender = update.effective_user
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ <b>Использование:</b> <code>/send_gift <ID_предмета> <ID получателя></code>", parse_mode=ParseMode.HTML)
        return

    item_id_str, target_str = args[0], args[1]
    if not item_id_str.isdigit():
        await update.message.reply_text("❌ Укажите ID предмета.")
        return

    item_id = int(item_id_str)
    item = get_collection_item(item_id)
    if not item or item["user_id"] != sender.id:
        await update.message.reply_text("❌ Предмет не найден.")
        return

    target_user = get_user_by_target(target_str)
    if not target_user or target_user["user_id"] == sender.id:
        await update.message.reply_text("❌ Ошибка получателя.")
        return

    g = GIFTS_BY_KEY.get(item["gift_key"])
    remove_from_collection(item_id, sender.id)
    add_to_collection(target_user["user_id"], item["gift_key"])

    receiver_name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")
    await update.message.reply_text(
        f"🎁 <b>Подарок передан!</b>\nПредмет <b>{g.name if g else item['gift_key']}</b> отправлен игроку <b>{receiver_name}</b>!",
        parse_mode=ParseMode.HTML
    )

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    db_init()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    clan_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_clan_creation, pattern="^clan_create_start$")],
        states={
            WAIT_CLAN_TAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_tag_received)],
            WAIT_CLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_name_received)],
            WAIT_CLAN_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_desc_received)],
            WAIT_CLAN_TYPE: [CallbackQueryHandler(clan_type_selected, pattern="^ctype:")],
            WAIT_CLAN_FEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_fee_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_clan_creation)],
    )

    admin_give_stars_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_give_stars_start, pattern="^admin_give_stars_start$")],
        states={
            WAIT_ADMIN_GIVE_STARS_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_stars_user)],
            WAIT_ADMIN_GIVE_STARS_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_stars_amount)],
        },
        fallbacks=[CommandHandler("cancel", cancel_clan_creation)],
    )

    admin_give_nft_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_give_nft_start, pattern="^admin_give_nft_start$")],
        states={
            WAIT_ADMIN_GIVE_NFT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_nft_user)],
            WAIT_ADMIN_GIVE_NFT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_nft_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel_clan_creation)],
    )

    app.add_handler(clan_conv)
    app.add_handler(admin_give_stars_conv)
    app.add_handler(admin_give_nft_conv)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile_alias))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("send_gift", cmd_send_gift))
    app.add_handler(CommandHandler("clans", cmd_clans))
    app.add_handler(CommandHandler("market", cmd_market))

    app.add_handler(MessageHandler(filters.Regex(re.compile(r"^(кто я|я)$", re.IGNORECASE)), cmd_profile_alias))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_group_message))

    log.info("NFT-Gift Bot v9.3 запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
