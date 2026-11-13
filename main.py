#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
New NFT Gift Telegram Bot v12.0 (Ultimate Clans & Clean Heraldry Edition)
- Поддержка: @mkrartem (https://t.me/mkrartem)
- Полная система Кланов с гербами/аватарками (загрузка фото владельцем или автогенерация геральдического герба).
- Карточка профиля клана (как у игрока: аватарка, ID, уровень клана, полоса XP, казна, участники, бонус, 7 избранных подарков).
- Единая сквозная нумерация ID между игроками и кланами (никто из людей не может занять ID клана).
- Общая казна клана: детальный список балансов каждого участника и сумма всех звезд клана.
- Прокачка уровня клана (от 0 до 100):
  * Уровень 0: +1% к шансу выигрыша
  * Уровень 100: +45% к шансу выигрыша
  * Переход на 1 уровень: 10,000 XP
  * Ежедневное пассивное начисление XP при казне от 5,000,000 ⭐
  * Пополнение казны звездами (800 XP за 1,000,000 ⭐) и пожертвование подарков
- Избранные подарки клана (до 7 слотов, отображаются прямо на карточке клана).
- Полное отсутствие смайликов на всех генерируемых изображениях Pillow (устранены квадратики/глифы).
- Система блокировки нарушителей (Бан по ID / юзернейму) с таймером в часах, причиной и кнопкой поддержки.
- Фильтры по стоимости и моделям Telegram Gifts в Маркете и Админ-панели.
"""

import asyncio
import atexit
import base64
import datetime
import html
import io
import json
import logging
import math
import os
import random
import re
import shutil
import signal
import sqlite3
import threading
import time
import unicodedata
import zlib
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

# Попытка импорта Firebase Admin SDK (Cloud Firestore)
try:
    import firebase_admin
    from firebase_admin import credentials as fb_credentials, firestore as fb_firestore
    FIREBASE_ADMIN_AVAILABLE = True
except ImportError:
    firebase_admin = None
    fb_credentials = None
    fb_firestore = None
    FIREBASE_ADMIN_AVAILABLE = False

# ---------------------------------------------------------------------------
# Настройки и глобальные пути
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "images"
PLUSHPEPE_MODELS_DIR = IMAGES_DIR / "plushpepe_models"
BACKGROUNDS_DIR = IMAGES_DIR / "backgrounds"
CLAN_AVATARS_DIR = IMAGES_DIR / "clan_avatars"
FONTS_DIR = BASE_DIR / "fonts"
DB_PATH = BASE_DIR / "base.db"

FONTS_DIR.mkdir(parents=True, exist_ok=True)
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
PLUSHPEPE_MODELS_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
CLAN_AVATARS_DIR.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9036416244:AAGrJgI3jzMMU5bn6Q36r8cNBIJqGxniXmo")
SUPPORT_URL = os.environ.get("SUPPORT_URL", "https://t.me/mkrartem")
SUPPORT_HANDLE = "@mkrartem"

COOLDOWN_SECONDS = 1 * 60 * 60          # 1 час между выбиванием NFT в группах
COOLDOWN_ENABLED = True
CHAT_DROP_CHANCE = 0.90                 # 90% шанс дропа при слове NFT
STAR_RUB_RATE = 1.5                     # 1 Star = 1.5 RUB
TON_RUB_RATE = 100.0                    # 1 TON = 100 RUB
ADMIN_IDS = {684535319, 7459502130}     # Telegram ID администраторов

UPGRADE_COST_STARS = 150_000            # Стоимость улучшения Plush Pepe
MARKET_FEE_RATE = 0.15                  # Комиссия маркета 15%
MARKET_MIN_PRICE = 1_000                # Минимальная цена лота на маркете
MARKET_MAX_PRICE = 100_000_000_000      # Максимальная цена лота (100 млрд звёзд)

# ---------------------------------------------------------------------------
# Firebase Cloud Database Storage (Интеграция с проектом proar-5a642)
# Автоматическая синхронизация файла base.db для хостинга bot host.ru
# ---------------------------------------------------------------------------

FIREBASE_SERVICE_ACCOUNT_CONFIG = {
    "type": "service_account",
    "project_id": "proar-5a642",
    "private_key_id": "4a144f7704aac1ceaa190705283f7b484fbff96a",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQC+/pKlE0760J18\nCnIZJPrKb1aPkY+pUio7Pm6PnBmXqMT21Mr6KC7z6VIXedW8SA9aDjHLlPd1adYa\nFnBjoeMZQVkd0YJrfBWdUgqt2/17zPSbU0VRTdKPWlxgJVJFqJ9Ucgmm1dE+lTl4\nHsq0+I0U6GekkXyXaLtR/u4bTzOUrL0bTMV67lAXr2sKw1SHqeGeQ0ugABYyr0UK\nWgXdvxWiaoQ1TXQJ7R4TzvB4SAFv1X1XMsWQntX2Ntu3WKHrhwtwUAyFJ1FrdcQR\nleeFRkiepSnZ5iC7aT7O81xy5gPHMFajFgMLtzMTa4uVCXmN5W05+ubXMSucXN/9\nY1YatGO7AgMBAAECggEAFoBVdH8+2cvEEf4FDTNPHJRbZVSn0THt6cbkLaUdWsG2\nWsIdG7WqOnAtjLh81s7CiECN20c0lC+g2rf0C7jh0XLideHd9J3MyhkFSxBU38X4\nt2frDbYWbW8e3PDorW49PyykOHSOT0ozWBSAmyuBK4pp03iUbh4Xm4RmNu9wyz4O\nYag5X2AH8UTh39P332nYvILhOMKFuQITUsiZ/PFBVrqn6ss1EJyqpj/kKgDqbM0O\nsSRsYTPkWLqpa4rgZIb2Y8WNRwOFYx7npzXWDS6pDhApdolQWMW4tPHCJb82J9yk\nQ3hEmrrjT8pBktHTEriciTNXV77GS8OTo/PSgJjgsQKBgQDrRfCaK4EmmOvk3Sx0\nAzEshNrUP1riPUyP4gDCM7E6LQdY0ST3+83QuUWqMmshspZsuCZCR1zcprr3ZYj6\nWOGjHSA38b6nlkblRAuyiWcGj7ZLvf7H22S3CkYheldguEdFWMSxG6jVd56GpjZL\nmXxXuWDXCB1X1g40W7/c4vOKMwKBgQDP0gY6HHwjYmvBLDw0UvH9AOKXBUZknUvA\nomZNZOpFbTspWpJj/VqksLEMYqxJJxC6rGg0t9M2qYlINnsCNXcOx01e/BcNab81\nEmOrrtOLxiXSx4+4B+cJ2gOQ/q3fmWk+6OMBqpPJC7fBBrepzwVGYYnUjkDAsR/o\nF0uHISlIWQKBgFaIGr4ZUh8ID3rVfgwNQIDHPFTkGGEteoNQ9EZ5DK4A8brQ8W/j\nxQcHnX/Dm3OBY6II+MlXxefByvJC/eZV2mdLxxXMa/rnYpvgMw0vTB01ri6dap/H\nKXvI45JclNaV8GCpDW62ZZpdrIiJiV60zO7W168+5MvxhrfrJt3u+vPRAoGAcvz8\noQ69yT5d7Oay8Sir6JeiyHkMuAMotQ+ml1AtJ/kGcR1CPr0ieFmjvPyj414QLZnT\nlsfXwDkSUriCW3iFxdGVB+doQe2u9IiWSZpURtR+fSAab3M/7P2KV6HzRvM1fq+R\nW4ysdONc6xryaKy5eHXjs456WaQnyV2KVtyMYRECgYBM6+chPRK3ZFTSJP4i6Hl9\nHGv5ThpKfpdlHApHEg8eLBU1soRjOCBphuJFvtMjmg2LTeJZMfQqi5PcAIOCP4gV\nbapVqGmG9cHNlVacFJdJbbWHPUs+Hw5hJGjd6ckHRO4REYY9725bhKeORKsRYmoo\nkz/3vSS/ygQ0Ma2sfXTVfQ==\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-fbsvc@proar-5a642.iam.gserviceaccount.com",
    "client_id": "103737744652283306114",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40proar-5a642.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

class FirebaseStorageManager:
    """
    Управляет безопасным хранением базы SQLite (base.db) в Cloud Firestore (100% бесплатно).
    Коллекция: telegram_bot_data, документ: sqlite_database.
    Гарантирует сохранение данных при перезапусках контейнера bot host.ru и защищает от затирания.
    """
    SQLITE_HEADER = b"SQLite format 3\x00"

    def __init__(self):
        self.app = None
        self.db = None
        self.project_id = "proar-5a642"
        self.collection_name = os.environ.get("FIREBASE_COLLECTION", "telegram_bot_data")
        self.document_name = os.environ.get("FIREBASE_DOCUMENT", "sqlite_database")
        self.initialized = False
        self.last_sync_ts: float = 0.0
        self.last_sync_size: int = 0
        self.last_sync_status: str = "Ожидает первой синхронизации"
        self.last_error: str = ""
        self._lock = threading.Lock()
        self._sync_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dirty = False
        self._startup_download_error = False
        self._cloud_doc_missing = False
        self.active_key_id: str = ""
        self.key_source: str = "embedded"

    def _load_credentials_dict(self) -> dict:
        cred_dict = None
        source_label = "встроенный конфиг"
        # 1. Из переменных окружения (если настроены на хостинге)
        for env_key in ("FIREBASE_CREDENTIALS_JSON", "FIREBASE_SERVICE_ACCOUNT_JSON"):
            raw_env = os.environ.get(env_key, "").strip()
            if raw_env:
                try:
                    cred_dict = json.loads(raw_env)
                    source_label = f"env:{env_key}"
                    break
                except Exception as e:
                    log.warning(f"[Firebase] Не удалось распарсить {env_key}: {e}")

        # 2. Из файла JSON в папке бота (включая любые скачанные .json ключи Firebase)
        if cred_dict is None:
            candidates = [
                BASE_DIR / "firebase-service-account.json",
                BASE_DIR / "firebase_credentials.json",
                BASE_DIR / "serviceAccountKey.json",
            ]
            env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
            if env_path:
                candidates.insert(0, Path(env_path))
            candidates.extend(sorted(BASE_DIR.glob("*firebase-adminsdk*.json")))
            candidates.extend(sorted(BASE_DIR.glob("*.json")))

            seen_paths = set()
            for candidate in candidates:
                resolved = str(candidate)
                if resolved in seen_paths:
                    continue
                seen_paths.add(resolved)
                if candidate.exists() and candidate.is_file():
                    try:
                        with open(candidate, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                        if (
                            isinstance(loaded, dict)
                            and loaded.get("type") == "service_account"
                            and "private_key" in loaded
                            and "client_email" in loaded
                        ):
                            cred_dict = loaded
                            source_label = f"файл {candidate.name}"
                            log.info(f"[Firebase] Найден файл ключа: {candidate.name}")
                            break
                    except Exception as e:
                        log.warning(f"[Firebase] Ошибка чтения {candidate}: {e}")

        # 3. Встроенный конфиг как запасной вариант
        if cred_dict is None:
            cred_dict = dict(FIREBASE_SERVICE_ACCOUNT_CONFIG)
        else:
            cred_dict = dict(cred_dict)

        if isinstance(cred_dict.get("private_key"), str):
            cred_dict["private_key"] = cred_dict["private_key"].replace("\\n", "\n")

        if cred_dict.get("project_id"):
            self.project_id = cred_dict["project_id"]

        self.active_key_id = str(cred_dict.get("private_key_id", ""))[:12]
        self.key_source = source_label
        return cred_dict

    def _format_error(self, err: Exception) -> str:
        msg = str(err)
        if "Invalid JWT Signature" in msg or "invalid_grant" in msg:
            kid = f" (ключ {self.active_key_id}..., {self.key_source})" if self.active_key_id else ""
            return (
                f"Ключ Firebase отозван/недействителен{kid}. "
                "Загрузите новый .json ключ через админку («🔑 Загрузить ключ Firebase») или положите .json в папку с ботом."
            )
        return msg

    def init_app(self, force_reinit: bool = False) -> bool:
        if not FIREBASE_ADMIN_AVAILABLE:
            log.warning("[Firebase] Библиотека firebase-admin не установлена. На bot host.ru выполните: pip install firebase-admin")
            self.last_sync_status = "Ошибка: firebase-admin не установлен"
            return False

        if self.initialized and self.db is not None and not force_reinit:
            return True

        try:
            if force_reinit:
                try:
                    existing_app = firebase_admin.get_app()
                    firebase_admin.delete_app(existing_app)
                except ValueError:
                    pass
                self.app = None
                self.db = None
                self.initialized = False

            cred_dict = self._load_credentials_dict()
            cred = fb_credentials.Certificate(cred_dict)

            try:
                self.app = firebase_admin.get_app()
            except ValueError:
                self.app = firebase_admin.initialize_app(cred)

            self.db = fb_firestore.client(app=self.app)
            self.initialized = True
            self.last_error = ""
            log.info(f"[Firestore] ✅ Инициализирован клиент {self.project_id} ({self.collection_name}/{self.document_name}, {self.key_source}, kid={self.active_key_id})")
            return True
        except Exception as e:
            err_txt = self._format_error(e)
            log.error(f"[Firestore] ❌ Ошибка подключения к Firebase Firestore: {err_txt}")
            self.last_error = err_txt
            self.last_sync_status = f"Ошибка инициализации: {err_txt}"
            self.initialized = False
            return False

    def reinit(self) -> bool:
        return self.init_app(force_reinit=True)

    @staticmethod
    def is_valid_sqlite(path: Path) -> bool:
        if not path.exists() or path.stat().st_size < 100:
            return False
        try:
            with open(path, "rb") as f:
                header = f.read(16)
                return header == b"SQLite format 3\x00"
        except Exception:
            return False

    @classmethod
    def _decode_sqlite_payload(cls, raw_val, compression_hint: str = "") -> Optional[bytes]:
        raw_bytes: Optional[bytes] = None
        if isinstance(raw_val, (bytes, bytearray)):
            raw_bytes = bytes(raw_val)
        elif isinstance(raw_val, str) and len(raw_val) > 60:
            try:
                raw_bytes = base64.b64decode(raw_val)
            except Exception:
                return None
        else:
            return None

        if raw_bytes.startswith(cls.SQLITE_HEADER):
            return raw_bytes

        try:
            decomp = zlib.decompress(raw_bytes)
            if decomp.startswith(cls.SQLITE_HEADER):
                return decomp
        except Exception:
            pass

        if compression_hint == "zlib":
            try:
                decomp = zlib.decompress(raw_bytes)
                if decomp.startswith(cls.SQLITE_HEADER):
                    return decomp
            except Exception:
                pass
        return None

    def _extract_sqlite_from_doc(self, doc_ref, doc_dict: dict) -> Optional[bytes]:
        if not isinstance(doc_dict, dict):
            return None

        compression_hint = str(doc_dict.get("compression", "")).lower()

        # 1. Поддержка чанкованного хранения (если база выросла > 900 КБ)
        if doc_dict.get("chunked") or (isinstance(doc_dict.get("chunk_count"), int) and doc_dict.get("chunk_count", 0) > 0):
            chunk_count = int(doc_dict.get("chunk_count", 0))
            parts: list[bytes] = []
            # Сначала пробуем подколлекцию chunks
            chunk_docs = list(doc_ref.collection("chunks").stream())
            if chunk_docs:
                indexed = []
                for cd in chunk_docs:
                    cdata = cd.to_dict() or {}
                    idx = cdata.get("index")
                    if idx is None:
                        m = re.search(r"(\d+)$", cd.id)
                        idx = int(m.group(1)) if m else 0
                    val = cdata.get("data") or cdata.get("chunk") or cdata.get("content") or b""
                    if isinstance(val, str):
                        val = base64.b64decode(val)
                    indexed.append((int(idx), bytes(val)))
                indexed.sort(key=lambda x: x[0])
                parts = [p for _, p in indexed]
            elif chunk_count > 0:
                for idx in range(chunk_count):
                    val = doc_dict.get(f"chunk_{idx}", b"")
                    if isinstance(val, str):
                        val = base64.b64decode(val)
                    parts.append(bytes(val))

            if parts:
                joined = b"".join(parts)
                res = self._decode_sqlite_payload(joined, compression_hint)
                if res:
                    return res

        # 2. Одиночный документ — автоопределение любого известного или произвольного поля
        priority_keys = [
            "data", "db_data", "sqlite_db", "db_bytes", "db_b64",
            "base64", "sqlite_base64", "content", "file", "payload", "db", "sqlite",
        ]
        checked = set()
        for k in priority_keys + list(doc_dict.keys()):
            if k in checked or k not in doc_dict:
                continue
            checked.add(k)
            res = self._decode_sqlite_payload(doc_dict[k], compression_hint)
            if res:
                return res
        return None

    @staticmethod
    def _count_local_users(path: Path) -> int:
        if not path.exists():
            return 0
        try:
            c = sqlite3.connect(path)
            cnt = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            c.close()
            return int(cnt)
        except Exception:
            return 0

    def download_db_on_startup(self) -> bool:
        """
        Скачивает сохраненную base.db из Cloud Firestore (telegram_bot_data/sqlite_database) ПЕРЕД запуском базы.
        Никогда не удаляет существующую базу в Firestore при ошибке.
        """
        if not self.init_app():
            self._startup_download_error = True
            return False

        try:
            doc_ref = self.db.collection(self.collection_name).document(self.document_name)
            doc = doc_ref.get()
            if not doc.exists:
                log.info(f"[Firestore] ℹ️ Документ {self.collection_name}/{self.document_name} пока не создан. Будет инициализирована новая база.")
                self.last_sync_status = "База еще не выгружалась в Firestore"
                self._cloud_doc_missing = True
                self._startup_download_error = False
                return False

            self._cloud_doc_missing = False
            doc_dict = doc.to_dict() or {}
            sqlite_bytes = self._extract_sqlite_from_doc(doc_ref, doc_dict)
            if not sqlite_bytes or len(sqlite_bytes) < 100:
                log.warning("[Firestore] ⚠️ Документ существует, но не содержит корректных данных SQLite. Облако защищено от перезаписи.")
                self.last_sync_status = "Ошибка: неверный формат данных в Firestore"
                self._startup_download_error = True
                return False

            tmp_path = BASE_DIR / "base.db.tmp_download"
            tmp_path.write_bytes(sqlite_bytes)

            if not self.is_valid_sqlite(tmp_path):
                log.error("[Firestore] ❌ Скачанный файл поврежден. Отмена замены базы.")
                if tmp_path.exists():
                    tmp_path.unlink()
                self._startup_download_error = True
                return False

            if DB_PATH.exists():
                try:
                    shutil.copy2(DB_PATH, BASE_DIR / "base.db.backup_local")
                except Exception:
                    pass

            shutil.move(tmp_path, DB_PATH)
            remote_size = len(sqlite_bytes)
            self.last_sync_ts = time.time()
            self.last_sync_size = remote_size
            self.last_error = ""
            self._startup_download_error = False
            self.last_sync_status = f"Восстановлена из Firestore ({remote_size:,} байт)"
            log.info(f"[Firestore] ✅ База base.db успешно восстановлена из {self.collection_name}/{self.document_name} ({remote_size:,} байт)!")
            return True
        except Exception as e:
            err_txt = self._format_error(e)
            log.error(f"[Firestore] Ошибка при скачивании base.db: {err_txt}")
            self.last_error = err_txt
            self.last_sync_status = f"Ошибка скачивания: {err_txt}"
            self._startup_download_error = True
            return False

    def upload_db_to_cloud(self, force: bool = False) -> bool:
        """
        Выгружает локальный base.db в Cloud Firestore (telegram_bot_data/sqlite_database).
        СТРОГАЯ ЗАЩИТА: Ни в коем случае не перезаписывает облако пустой или поврежденной базой,
        а также не перезаписывает существующий документ при ошибке скачивания на старте.
        """
        if not self.init_app():
            return False

        with self._lock:
            try:
                if self._startup_download_error:
                    log.warning("[Firestore] 🛑 Защита Anti-Wipe: при старте была ошибка чтения облака, выгрузка заблокирована для защиты базы.")
                    self.last_error = "Anti-Wipe: сначала восстановите/проверьте чтение из Firestore"
                    return False

                if not DB_PATH.exists() or DB_PATH.stat().st_size < 100:
                    log.warning("[Firestore] 🛑 Отмена выгрузки: локальный base.db пуст или не существует. Защита от очистки активна!")
                    return False

                if not self.is_valid_sqlite(DB_PATH):
                    log.error("[Firestore] 🛑 Отмена выгрузки: локальный base.db поврежден. Облако защищено от затирания.")
                    return False

                doc_ref = self.db.collection(self.collection_name).document(self.document_name)

                # Дополнительная защита: если локально 0 пользователей, а в Firestore уже есть документ — не затираем!
                if self._count_local_users(DB_PATH) == 0:
                    existing_snap = doc_ref.get()
                    if existing_snap.exists:
                        existing_bytes = self._extract_sqlite_from_doc(doc_ref, existing_snap.to_dict() or {})
                        if existing_bytes and len(existing_bytes) > 100:
                            log.warning("[Firestore] 🛑 Anti-Wipe: локальная база содержит 0 игроков, а в облаке уже есть данные. Отмена перезаписи!")
                            self.last_error = "Anti-Wipe: локальная база пуста (0 игроков), облако защищено!"
                            return False

                current_size = DB_PATH.stat().st_size
                if not force and self.last_sync_ts > 0 and (time.time() - self.last_sync_ts < 15):
                    return True

                snapshot_path = BASE_DIR / "base.db.upload_snapshot"
                try:
                    src_conn = sqlite3.connect(DB_PATH)
                    dst_conn = sqlite3.connect(snapshot_path)
                    src_conn.backup(dst_conn)
                    dst_conn.close()
                    src_conn.close()
                    target_file = snapshot_path
                except Exception:
                    target_file = DB_PATH

                raw_bytes = Path(target_file).read_bytes()
                current_size = len(raw_bytes)
                compressed = zlib.compress(raw_bytes, level=6)
                now_ts = int(time.time())

                if snapshot_path.exists():
                    try:
                        snapshot_path.unlink()
                    except Exception:
                        pass

                # Firestore ограничивает размер одного документа ~1 МБ (1,048,576 байт)
                if len(compressed) <= 900_000:
                    doc_ref.set({
                        "data": compressed,
                        "compression": "zlib",
                        "raw_size": current_size,
                        "compressed_size": len(compressed),
                        "chunked": False,
                        "chunk_count": 0,
                        "updated_ts": now_ts,
                    })
                else:
                    chunk_size = 700_000
                    chunks = [compressed[i : i + chunk_size] for i in range(0, len(compressed), chunk_size)]
                    chunks_col = doc_ref.collection("chunks")
                    for idx, chunk_bytes in enumerate(chunks):
                        chunks_col.document(f"chunk_{idx}").set({
                            "index": idx,
                            "data": chunk_bytes,
                        })
                    # Удаляем лишние старые чанки, если база уменьшилась
                    for old_doc in chunks_col.stream():
                        m = re.search(r"(\d+)$", old_doc.id)
                        if m and int(m.group(1)) >= len(chunks):
                            old_doc.reference.delete()
                    doc_ref.set({
                        "compression": "zlib",
                        "raw_size": current_size,
                        "compressed_size": len(compressed),
                        "chunked": True,
                        "chunk_count": len(chunks),
                        "updated_ts": now_ts,
                    })

                self.last_sync_ts = time.time()
                self.last_sync_size = current_size
                self.last_error = ""
                self._startup_download_error = False
                self._cloud_doc_missing = False
                self.last_sync_status = f"Синхронизировано в {datetime.datetime.now().strftime('%H:%M:%S')} ({current_size:,} байт)"
                self._dirty = False
                log.info(f"[Firestore] ☁️ База base.db сохранена в {self.collection_name}/{self.document_name} ({current_size:,} байт, сжато до {len(compressed):,} байт)")
                return True
            except Exception as e:
                err_txt = self._format_error(e)
                log.error(f"[Firestore] Ошибка выгрузки base.db: {err_txt}")
                self.last_error = err_txt
                self.last_sync_status = f"Ошибка выгрузки: {err_txt}"
                return False

    def schedule_sync(self):
        """Отмечает базу как измененную для фоновой синхронизации."""
        self._dirty = True

    def start_periodic_sync(self, interval_seconds: int = 60):
        """Запускает фоновый поток периодической синхронизации."""
        if self._sync_thread and self._sync_thread.is_alive():
            return

        def _worker():
            while not self._stop_event.is_set():
                self._stop_event.wait(interval_seconds)
                if self._stop_event.is_set():
                    break
                try:
                    self.upload_db_to_cloud(force=False)
                except Exception as e:
                    log.error(f"[Firestore Worker] Ошибка: {e}")

        self._sync_thread = threading.Thread(target=_worker, daemon=True, name="FirestoreSyncWorker")
        self._sync_thread.start()
        log.info(f"[Firestore] Фоновая синхронизация базы активирована (интервал: {interval_seconds} сек)")

    def stop(self):
        self._stop_event.set()
        if self.initialized:
            self.upload_db_to_cloud(force=False)

firebase_manager = FirebaseStorageManager()

def _on_shutdown():
    try:
        firebase_manager.upload_db_to_cloud(force=False)
    except Exception:
        pass

atexit.register(_on_shutdown)

# FSM Состояния
(
    WAIT_CLAN_TAG,
    WAIT_CLAN_NAME,
    WAIT_CLAN_DESC,
    WAIT_CLAN_TYPE,
    WAIT_CLAN_FEE,
    WAIT_ADMIN_GIVE_STARS_USER,
    WAIT_ADMIN_GIVE_STARS_AMOUNT,
    WAIT_ADMIN_GIVE_NFT_USER,
    WAIT_PROFILE_BG,
    WAIT_ADMIN_BAN_USER,
    WAIT_ADMIN_BAN_HOURS,
    WAIT_ADMIN_BAN_REASON,
    WAIT_ADMIN_UNBAN_USER,
    WAIT_CLAN_AVATAR,
    WAIT_CLAN_DONATE_STARS,
    WAIT_MARKET_OFFER_PRICE,
    WAIT_GIFT_TRANSFER_USER,
    WAIT_ADMIN_FIREBASE_KEY,
) = range(18)

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
            log.warning("Не удалось скачать шрифт Regular: %s", e)

    if not FONT_BOLD_PATH.exists():
        log.info("Загрузка шрифта NotoSans-Bold...")
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Bold.ttf"
        try:
            r = requests.get(url, timeout=15)
            if r.status_code == 200:
                FONT_BOLD_PATH.write_bytes(r.content)
        except Exception as e:
            log.warning("Не удалось скачать шрифт Bold: %s", e)

ensure_fonts_exist()

# ---------------------------------------------------------------------------
# Очистка строк и удаление эмодзи для генерации картинок Pillow
# ---------------------------------------------------------------------------

def clean_html(text: Optional[str]) -> str:
    """Безопасное экранирование спецсимволов HTML для Telegram."""
    if not text:
        return ""
    return html.escape(str(text))

def strip_all_emojis_for_image(text: str) -> str:
    """
    Полное удаление эмодзи и спец-символов Unicode, чтобы на генерируемых
    картинках Pillow не появлялись пустые квадратики (tofu).
    """
    if not text:
        return "Unknown"

    emoji_pattern = re.compile(
        "["
        "\U00010000-\U0010FFFF"
        "\u200d"
        "\ufe0f"
        "\ufe0e"
        "\u2600-\u27bf"
        "\u2300-\u23ff"
        "\u2b50"
        "\u2b06"
        "\u2190-\u21ff"
        "\u2934-\u2935"
        "\u3297"
        "\u3299"
        "\u3030"
        "\u00a9"
        "\u00ae"
        "]+",
        flags=re.UNICODE
    )
    cleaned = emoji_pattern.sub("", text)

    res = []
    for char in unicodedata.normalize('NFKC', cleaned):
        cat = unicodedata.category(char)
        if cat in ('So', 'Cn', 'Co', 'Sk', 'Cs'):
            continue
        res.append(char)
    final_str = "".join(res).strip()
    return final_str if final_str else "Unknown"

def normalize_telegram_name(name: str) -> str:
    if not name:
        return "Player"
    cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", name).strip()
    if not cleaned:
        cleaned = name.strip()
    return cleaned if cleaned else "Player"

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
# NFT Каталог & Модели подарков (Без «редкостей», как в Telegram)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GiftDef:
    key: str
    name: str
    stars: int
    chance: float
    xp: int
    model_group: str     # Модель: 'animals', 'figures', 'artifacts', 'mystic', 'festive'
    model_name: str      # Название модели для интерфейса

    @property
    def ton(self) -> float:
        return round((self.stars * STAR_RUB_RATE) / TON_RUB_RATE, 3)

    @property
    def rub(self) -> float:
        return round(self.stars * STAR_RUB_RATE, 2)


GIFTS: list[GiftDef] = [
    # 1. Животные и маскоты (animals)
    GiftDef("pepe_heart", "Plush Pepe (Пепе с сердцем)", 350_000, 0.0005, 100_000, "animals", "Животные и маскоты"),
    GiftDef("durov_dog", "Resistance Dog (Пёс Дурова)", 21_000, 0.005, 15_000, "animals", "Животные и маскоты"),
    GiftDef("hockey_mask", "Scared Cat (Маска кота)", 19_000, 0.006, 12_000, "animals", "Животные и маскоты"),
    GiftDef("teddy_patrick", "Irish Bear (Мишка-лепрекон)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("teddy_heart_white", "New Year's Bear (Белый мишка)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("teddy_santa", "Santa Bear (Мишка-Санта)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("teddy_football", "Football Bear (Мишка-футболист)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("bunny_teddy", "Easter Bear (Мишка-кролик)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("teddy_soldier", "Bear Soldier (Мишка-солдат)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("teddy_builder", "Polar Bear (Мишка-строитель)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("clown_teddy", "Clown Bear (Мишка-клоун)", 50, 10.00, 50, "animals", "Животные и маскоты"),
    GiftDef("teddy_flowers", "Pretty Posy (Мишка с букетом)", 350, 6.00, 220, "animals", "Животные и маскоты"),

    # 2. Фигурки и трофеи (figures)
    GiftDef("hero_figure", "Durov Figure (Фигурка Дурова)", 30_000, 0.003, 25_000, "figures", "Фигурки и трофеи"),
    GiftDef("trophy_cup", "Algorithm Cup (Кубок Чемпиона)", 65_000, 0.002, 35_000, "figures", "Фигурки и трофеи"),
    GiftDef("cap_tg", "Durov's Cap (Кепка Дурова)", 28_000, 0.004, 20_000, "figures", "Фигурки и трофеи"),
    GiftDef("sunglasses", "Durov's Glasses (Очки Дурова)", 6_300, 0.020, 5_000, "figures", "Фигурки и трофеи"),
    GiftDef("torch", "Liberty Figure (Факел Свободы)", 340, 6.20, 210, "figures", "Фигурки и трофеи"),

    # 3. Артефакты и украшения (artifacts)
    GiftDef("heart_lock_key", "Heart Locket (Сердце-замок)", 15_000, 0.008, 10_000, "artifacts", "Артефакты и украшения"),
    GiftDef("gem_crystal", "Astral Shard (Кристалл Алмаз)", 8_000, 0.015, 6_000, "artifacts", "Артефакты и украшения"),
    GiftDef("ring_silver", "Signet Ring (Серебряное кольцо)", 2_379, 0.70, 2_000, "artifacts", "Артефакты и украшения"),
    GiftDef("rose_bell_jar", "Eternal Rose (Роза под колпаком)", 1_800, 0.90, 1_500, "artifacts", "Артефакты и украшения"),
    GiftDef("crystal_ball", "Crystal Ball (Магический шар)", 920, 1.50, 800, "artifacts", "Артефакты и украшения"),
    GiftDef("mosque_moon", "Moon Pendant (Полумесяц)", 450, 4.00, 300, "artifacts", "Артефакты и украшения"),
    GiftDef("clover_green", "Clover Pin (Значок Клевер)", 330, 7.00, 180, "artifacts", "Артефакты и украшения"),
    GiftDef("pacifier_gold", "Hypno Lollipop (Золотая соска)", 280, 8.00, 140, "artifacts", "Артефакты и украшения"),

    # 4. Мистика и Хэллоуин (mystic)
    GiftDef("skull_ghost", "Electric Skull (Призрачный череп)", 1_500, 1.10, 1_200, "mystic", "Мистика и Хэллоуин"),
    GiftDef("teddy_pumpkin", "Mad Pumpkin (Тыква Хэллоуин)", 830, 2.00, 600, "mystic", "Мистика и Хэллоуин"),
    GiftDef("broom_witch", "Flying Broom (Ведьмина метла)", 750, 2.20, 500, "mystic", "Мистика и Хэллоуин"),
    GiftDef("coffin", "Gravestone (Гробница)", 660, 2.50, 450, "mystic", "Мистика и Хэллоуин"),
    GiftDef("eye_evil", "Evil Eye (Глаз-оберег)", 540, 3.20, 340, "mystic", "Мистика и Хэллоуин"),

    # 5. Праздничные сувениры (festive)
    GiftDef("briefcase", "Loot Bag (Дипломат)", 4_500, 0.40, 3_500, "festive", "Праздничные сувениры"),
    GiftDef("chocolate_box", "Berry Box (Коробка конфет)", 600, 2.80, 400, "festive", "Праздничные сувениры"),
    GiftDef("cupcake_bunny", "Bunny Muffin (Кекс-зайчик)", 550, 3.00, 350, "festive", "Праздничные сувениры"),
    GiftDef("fountain_pen", "Fine Pen (Золотое перо)", 530, 3.50, 330, "festive", "Праздничные сувениры"),
    GiftDef("candle", "Eternal Candle (Свеча)", 420, 4.20, 280, "festive", "Праздничные сувениры"),
    GiftDef("bday_calendar", "Desk Calendar (Календарь)", 420, 4.50, 270, "festive", "Праздничные сувениры"),
    GiftDef("bowtie", "Bow Tie (Бабочка)", 380, 5.00, 250, "festive", "Праздничные сувениры"),
    GiftDef("tg_rashguard", "Swag Bag (Рашгард)", 375, 5.20, 240, "festive", "Праздничные сувениры"),
    GiftDef("heart_cookie", "Cookie Heart (Пряник-сердце)", 360, 5.50, 230, "festive", "Праздничные сувениры"),
    GiftDef("easter_cake", "Homemade Cake (Кулич)", 340, 6.50, 200, "festive", "Праздничные сувениры"),
    GiftDef("peace_dove_stamp", "Dove of Peace (Марка мира)", 330, 6.80, 190, "festive", "Праздничные сувениры"),
    GiftDef("happy_bday_sign", "Star Notepad (Блокнот B-day)", 320, 7.20, 170, "festive", "Праздничные сувениры"),
    GiftDef("sneakers_black", "Fresh Socks (Кроссовки)", 310, 7.50, 160, "festive", "Праздничные сувениры"),
    GiftDef("coconut_drink", "Holiday Drink (Коктейль)", 300, 7.80, 150, "festive", "Праздничные сувениры"),
    GiftDef("egg_butterfly", "Easter Egg (Пасхальное яйцо)", 270, 8.20, 130, "festive", "Праздничные сувениры"),
    GiftDef("new_year_2025", "Big Year (Цифры 2025)", 260, 8.50, 120, "festive", "Праздничные сувениры"),
    GiftDef("candy_cane", "Candy Cane (Леденец)", 250, 8.80, 110, "festive", "Праздничные сувениры"),
    GiftDef("i_love_u_heart", "I Love You (Сердце)", 50, 10.00, 50, "festive", "Праздничные сувениры"),
    GiftDef("xmas_tree", "Christmas Tree (Ёлочка)", 50, 10.00, 50, "festive", "Праздничные сувениры"),
]

GIFTS_BY_KEY = {g.key: g for g in GIFTS}

MODEL_GROUPS = {
    "animals": "Животные и маскоты",
    "figures": "Фигурки и трофеи",
    "artifacts": "Артефакты и украшения",
    "mystic": "Мистика и Хэллоуин",
    "festive": "Праздничные сувениры",
}

PRICE_TIERS = {
    "low": ("До 500 ⭐", 0, 500),
    "mid": ("500 — 2,000 ⭐", 501, 2000),
    "high": ("2,000 — 15,000 ⭐", 2001, 15000),
    "ultra": ("От 15,000 ⭐", 15001, 10000000),
}

def get_gifts_filtered(filter_type: str, filter_key: str) -> List[GiftDef]:
    if filter_type == "model":
        if filter_key in MODEL_GROUPS:
            return [g for g in GIFTS if g.model_group == filter_key]
    elif filter_type == "price":
        if filter_key in PRICE_TIERS:
            _, min_p, max_p = PRICE_TIERS[filter_key]
            return [g for g in GIFTS if min_p <= g.stars <= max_p]
    return GIFTS

def roll_gift_from_pool(pool: List[GiftDef], bonus_pct: float = 0.0) -> GiftDef:
    """
    Ролл подарка с учетом кланового бонуса к выигрышу дорогих подарков (+1%..+45%).
    Бонус повышает вероятность выпадения ценных подарков.
    """
    total_w = 0.0
    weights = []
    bonus_multiplier = 1.0 + (bonus_pct / 100.0)

    for g in pool:
        # Для подарков свыше 1,000 звёзд шанс усиливается клановым бонусом
        if g.stars >= 1000:
            w = g.chance * bonus_multiplier
        else:
            w = g.chance
        weights.append(w)
        total_w += w

    r = random.uniform(0, total_w)
    upto = 0.0
    for idx, g in enumerate(pool):
        upto += weights[idx]
        if upto >= r:
            return g
    return pool[-1]

def gift_image_path(key: str) -> Optional[Path]:
    for ext in [".webp", ".png", ".jpg", ".jpeg"]:
        p = IMAGES_DIR / f"{key}{ext}"
        if p.exists():
            return p
    return None

# ---------------------------------------------------------------------------
# КАТАЛОГ МОДЕЛЕЙ И ФОНОВ ДЛЯ УЛУЧШЕНИЯ PLUSH PEPE (50 МОДЕЛЕЙ + 60 ФОНОВ)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlushModelDef:
    name: str
    filename: str
    rarity_pct: float
    price_mult: float


@dataclass(frozen=True)
class BackdropDef:
    key: str
    name: str
    palette: str
    center_hex: str
    edge_hex: str
    chance_pct: float
    price_mult: float
    rarity_label: str


PLUSHPEPE_MODELS: list[PlushModelDef] = [
    PlushModelDef("Amalgam", "Amalgam.webp", 1.2, 1.32),
    PlushModelDef("Aqua Plush", "Aqua Plush.webp", 2.0, 1.12),
    PlushModelDef("Barcelona", "Barcelona.webp", 2.0, 1.15),
    PlushModelDef("Bavaria", "Bavaria.webp", 2.0, 1.14),
    PlushModelDef("Birmingham", "Birmingham.webp", 2.0, 1.12),
    PlushModelDef("Christmas", "Christmas.webp", 2.0, 1.15),
    PlushModelDef("Cold Heart", "Cold Heart.webp", 1.4, 1.28),
    PlushModelDef("Cozy Galaxy", "Cozy Galaxy.webp", 1.2, 1.34),
    PlushModelDef("Donatello", "Donatello.webp", 2.0, 1.16),
    PlushModelDef("Eggplant", "Eggplant.webp", 2.2, 1.08),
    PlushModelDef("Emerald Plush", "Emerald Plush.webp", 1.6, 1.22),
    PlushModelDef("Emo Boi", "Emo Boi.webp", 1.5, 1.25),
    PlushModelDef("Fifty Shades", "Fifty Shades.webp", 1.1, 1.35),
    PlushModelDef("Frozen", "Frozen.webp", 1.8, 1.20),
    PlushModelDef("Gucci Leap", "Gucci Leap.webp", 1.3, 1.30),
    PlushModelDef("Gummy Frog", "Gummy Frog.webp", 2.2, 1.08),
    PlushModelDef("Hothead", "Hothead.webp", 2.0, 1.14),
    PlushModelDef("Hue Jester", "Hue Jester.webp", 2.0, 1.12),
    PlushModelDef("Kung Fu Pepe", "Kung Fu Pepe.webp", 1.8, 1.20),
    PlushModelDef("Leonardo", "Leonardo.webp", 2.0, 1.16),
    PlushModelDef("Louis Vuittoad", "Louis Vuittoad.webp", 1.2, 1.33),
    PlushModelDef("Magnate", "Magnate.webp", 1.6, 1.24),
    PlushModelDef("Marble", "Marble.webp", 1.7, 1.22),
    PlushModelDef("Midas Pepe", "Midas Pepe.webp", 1.0, 1.36),
    PlushModelDef("Milano", "Milano.webp", 2.0, 1.14),
    PlushModelDef("Ninja Mike", "Ninja Mike.webp", 2.0, 1.16),
    PlushModelDef("Pepe La Rana", "Pepe La Rana.webp", 2.2, 1.10),
    PlushModelDef("Pepemint", "Pepemint.webp", 2.2, 1.08),
    PlushModelDef("Pink Galaxy", "Pink Galaxy.webp", 1.5, 1.25),
    PlushModelDef("Pink Latex", "Pink Latex.webp", 1.8, 1.18),
    PlushModelDef("Poison Dart", "Poison Dart.webp", 1.9, 1.16),
    PlushModelDef("Polka Dots", "Polka Dots.webp", 2.4, 1.06),
    PlushModelDef("Princess", "Princess.webp", 2.0, 1.12),
    PlushModelDef("Pumpkin", "Pumpkin.webp", 2.1, 1.10),
    PlushModelDef("Puppy Pug", "Puppy Pug.webp", 2.2, 1.08),
    PlushModelDef("Raphael", "Raphael.webp", 2.0, 1.16),
    PlushModelDef("Red Menace", "Red Menace.webp", 1.8, 1.18),
    PlushModelDef("Red Pepple", "Red Pepple.webp", 2.1, 1.10),
    PlushModelDef("Santa Pepe", "Santa Pepe.webp", 2.0, 1.14),
    PlushModelDef("Sketchy", "Sketchy.webp", 1.7, 1.22),
    PlushModelDef("Spectrum", "Spectrum.webp", 1.5, 1.26),
    PlushModelDef("Steel Frog", "Steel Frog.webp", 1.4, 1.28),
    PlushModelDef("Stripes", "Stripes.webp", 2.3, 1.06),
    PlushModelDef("Sunset", "Sunset.webp", 2.1, 1.10),
    PlushModelDef("Toading...", "Toading....webp", 1.9, 1.17),
    PlushModelDef("Tropical", "Tropical.webp", 2.3, 1.06),
    PlushModelDef("Two Face", "Two Face.webp", 1.3, 1.30),
    PlushModelDef("X-Ray", "X-Ray.webp", 1.1, 1.35),
    PlushModelDef("Yellow Hug", "Yellow Hug.webp", 2.4, 1.05),
    PlushModelDef("Yellow Purp", "Yellow Purp.webp", 2.3, 1.06),
]

PLUSHPEPE_MODELS_BY_NAME = {m.name: m for m in PLUSHPEPE_MODELS}

# 60 официальных фонов (сумм. шанс = 100.00%):
# Чёрные / тёмные / серые — минимальные шансы (0.15%–0.65%) и максимальный множитель цены.
# Яркие, неоновые и пастельные — высокие шансы (2.00%–3.10%).
PLUSHPEPE_BACKDROPS: list[BackdropDef] = [
    # Ультра-редкие чёрные и серые (0.15% - 0.45%)
    BackdropDef("black", "Black", "Глубокий чёрный", "#1F1F23", "#0A0A0C", 0.15, 12.5, "Ультра-редкий"),
    BackdropDef("onyx_black", "Onyx Black", "Ониксовый чёрный", "#4C5153", "#2B2E30", 0.20, 11.5, "Ультра-редкий"),
    BackdropDef("obsidian", "Obsidian", "Обсидиановый тёмный", "#34363D", "#17181C", 0.25, 10.8, "Ультра-редкий"),
    BackdropDef("dark_graphite", "Dark Graphite", "Тёмный графит", "#4A4E57", "#222429", 0.30, 10.0, "Ультра-редкий"),
    BackdropDef("charcoal", "Charcoal", "Угольно-серый", "#545861", "#2D3036", 0.35, 9.2, "Ультра-редкий"),
    BackdropDef("pure_gold", "Pure Gold", "Чистое золото", "#DFB852", "#8E6B1A", 0.35, 9.5, "Ультра-редкий"),
    BackdropDef("battleship_grey", "Battleship Grey", "Стальной серый", "#7B838A", "#4E545A", 0.40, 8.5, "Ультра-редкий"),
    BackdropDef("roman_silver", "Roman Silver", "Римское серебро", "#A2A9B2", "#6B717A", 0.45, 8.0, "Ультра-редкий"),

    # Редкие тёмные и металлические (0.50% - 0.90%)
    BackdropDef("satin_gold", "Satin Gold", "Сатиновое золото", "#BE9B47", "#856A29", 0.50, 7.5, "Редкий"),
    BackdropDef("midnight_blue", "Midnight Blue", "Полуночный синий", "#5B6884", "#2E384D", 0.55, 7.2, "Редкий"),
    BackdropDef("gunmetal", "Gunmetal", "Оружейный металл", "#6A737D", "#3B4148", 0.60, 6.8, "Редкий"),
    BackdropDef("platinum", "Platinum", "Платиновый серый", "#BAC2CC", "#7C838C", 0.65, 6.5, "Редкий"),
    BackdropDef("old_gold", "Old Gold", "Античное золото", "#C7A44E", "#7A6021", 0.70, 6.2, "Редкий"),
    BackdropDef("indigo_dye", "Indigo Dye", "Глубокий индиго", "#4D5F8E", "#263254", 0.75, 5.8, "Редкий"),
    BackdropDef("burgundy", "Burgundy", "Благородный бордо", "#8E3B4E", "#521D29", 0.80, 5.5, "Редкий"),
    BackdropDef("dark_violet", "Dark Violet", "Тёмный фиолет", "#6E4F8E", "#3B2652", 0.85, 5.2, "Редкий"),
    BackdropDef("pine_green", "Pine Green", "Тёмно-хвойный", "#3E6E5B", "#1E4234", 0.85, 5.0, "Редкий"),
    BackdropDef("deep_bronze", "Deep Bronze", "Тёмная бронза", "#9B6D49", "#5E3E24", 0.90, 4.8, "Редкий"),

    # Средне-редкие насыщенные (1.00% - 1.70%)
    BackdropDef("sapphire", "Sapphire", "Сапфировый синий", "#4675C0", "#254885", 1.00, 4.5, "Необычный"),
    BackdropDef("emerald", "Emerald", "Изумрудный", "#3BA87A", "#1E6B4B", 1.05, 4.4, "Необычный"),
    BackdropDef("carmine", "Carmine", "Карминовый красный", "#B83B52", "#7A1E30", 1.10, 4.3, "Необычный"),
    BackdropDef("cobalt_blue", "Cobalt Blue", "Кобальтовый синий", "#486EE0", "#2744A1", 1.15, 4.2, "Необычный"),
    BackdropDef("celtic_blue", "Celtic Blue", "Кельтский синий", "#4980B8", "#285382", 1.20, 4.1, "Необычный"),
    BackdropDef("deep_cyan", "Deep Cyan", "Глубокий циан", "#3A94A3", "#1D5E69", 1.25, 4.0, "Необычный"),
    BackdropDef("chestnut", "Chestnut", "Каштановый", "#A15B47", "#6B3626", 1.30, 3.9, "Необычный"),
    BackdropDef("chocolate", "Chocolate", "Шоколадный", "#8E624A", "#573827", 1.35, 3.8, "Необычный"),
    BackdropDef("plum", "Plum", "Сливовый", "#8F4E87", "#592A53", 1.40, 3.7, "Необычный"),
    BackdropDef("steel_blue", "Steel Blue", "Стальной синий", "#6185A8", "#3A5673", 1.45, 3.6, "Необычный"),
    BackdropDef("hunter_green", "Hunter Green", "Лесной зелёный", "#4B8A5C", "#295735", 1.50, 3.5, "Необычный"),
    BackdropDef("copper", "Copper", "Медный", "#C47A53", "#874B2C", 1.55, 3.4, "Необычный"),
    BackdropDef("crimson", "Crimson", "Малиново-алый", "#D64561", "#94253B", 1.60, 3.3, "Необычный"),
    BackdropDef("royal_purple", "Royal Purple", "Королевский пурпур", "#8257C9", "#4F2E8C", 1.70, 3.2, "Необычный"),

    # Яркие и частые фоны (2.00% - 3.10%)
    BackdropDef("cyberpunk", "Cyberpunk", "Неоновый киберпанк", "#858DF2", "#694FD6", 2.00, 3.0, "Обычный"),
    BackdropDef("electric_indigo", "Electric Indigo", "Электрический индиго", "#7B68EE", "#4E3BC4", 2.00, 3.0, "Обычный"),
    BackdropDef("electric_purple", "Electric Purple", "Электрический фиолет", "#B266FF", "#7C32D6", 2.10, 2.9, "Обычный"),
    BackdropDef("neon_blue", "Neon Blue", "Неоновый синий", "#4DA6FF", "#2171D6", 2.10, 2.9, "Обычный"),
    BackdropDef("azure_blue", "Azure Blue", "Яркий лазурный", "#52B2F5", "#267CC2", 2.20, 2.8, "Обычный"),
    BackdropDef("amber", "Amber", "Яркий янтарный", "#F5A623", "#C4760C", 2.20, 2.8, "Обычный"),
    BackdropDef("jade_green", "Jade Green", "Яркий нефритовый", "#49C495", "#268C64", 2.25, 2.8, "Обычный"),
    BackdropDef("aquamarine", "Aquamarine", "Яркий аквамарин", "#5CE0C8", "#2B9E8A", 2.30, 2.7, "Обычный"),
    BackdropDef("turquoise", "Turquoise", "Яркий бирюзовый", "#45D3D3", "#1F9191", 2.35, 2.7, "Обычный"),
    BackdropDef("lavender", "Lavender", "Лавандовый", "#B49DF2", "#7F66C9", 2.40, 2.7, "Обычный"),
    BackdropDef("periwinkle", "Periwinkle", "Барвинковый", "#95A9F5", "#6076C9", 2.45, 2.6, "Обычный"),
    BackdropDef("sky_blue", "Sky Blue", "Небесно-голубой", "#75C8FF", "#3C95D6", 2.50, 2.6, "Обычный"),
    BackdropDef("mint_green", "Mint Green", "Яркая мята", "#6EEB9E", "#35AB62", 2.55, 2.6, "Обычный"),
    BackdropDef("coral_red", "Coral Red", "Яркий коралловый", "#FF786B", "#CF4538", 2.60, 2.5, "Обычный"),
    BackdropDef("strawberry", "Strawberry", "Клубничный", "#FF6B8B", "#CC3757", 2.65, 2.5, "Обычный"),
    BackdropDef("hot_pink", "Hot Pink", "Ярко-розовый", "#FF6EC7", "#C93892", 2.70, 2.5, "Обычный"),
    BackdropDef("magenta", "Magenta", "Яркая маджента", "#F05BD9", "#B52C9F", 2.75, 2.5, "Обычный"),
    BackdropDef("fuchsia", "Fuchsia", "Яркая фуксия", "#FF54B0", "#C2277B", 2.80, 2.4, "Обычный"),
    BackdropDef("tangerine", "Tangerine", "Яркий мандариновый", "#FF9945", "#CC6418", 2.80, 2.4, "Обычный"),
    BackdropDef("sunset_orange", "Sunset Orange", "Закатный оранж", "#FF8559", "#CC5129", 2.85, 2.4, "Обычный"),
    BackdropDef("flamingo", "Flamingo", "Розовый фламинго", "#FF8EB8", "#CF5784", 2.90, 2.4, "Обычный"),
    BackdropDef("bubblegum", "Bubblegum", "Яркий бабл-гам", "#FF9EE0", "#CC62AB", 2.95, 2.3, "Обычный"),
    BackdropDef("peach", "Peach", "Персиковый", "#FFB07D", "#D47742", 3.00, 2.3, "Обычный"),
    BackdropDef("mango", "Mango", "Сочный манго", "#FFBF47", "#D18715", 3.00, 2.3, "Обычный"),
    BackdropDef("sunny_yellow", "Sunny Yellow", "Солнечно-жёлтый", "#FFE04D", "#CFA617", 2.85, 2.2, "Обычный"),
    BackdropDef("lemon", "Lemon", "Лимонный", "#F2EE57", "#BFB822", 2.85, 2.2, "Обычный"),
    BackdropDef("lime_green", "Lime Green", "Ярко-лаймовый", "#A8EE4D", "#6EB51B", 2.85, 2.2, "Обычный"),
    BackdropDef("acid_green", "Acid Green", "Кислотно-салатовый", "#84FF5C", "#45C223", 2.85, 2.2, "Обычный"),
]

BACKDROPS_BY_KEY = {b.key: b for b in PLUSHPEPE_BACKDROPS}

MARKET_PRICE_TIERS = {
    "m1": ("1,000 — 500,000 ⭐", 1_000, 500_000),
    "m2": ("500,000 — 2,000,000 ⭐", 500_001, 2_000_000),
    "m3": ("2,000,000 — 10,000,000 ⭐", 2_000_001, 10_000_000),
    "m4": ("От 10,000,000 ⭐", 10_000_001, 100_000_000_000),
}

def plush_model_image_path(filename: str) -> Optional[Path]:
    if not filename:
        return None
    p = PLUSHPEPE_MODELS_DIR / filename
    if p.exists():
        return p
    return None

def roll_plush_model() -> PlushModelDef:
    available = [m for m in PLUSHPEPE_MODELS if plush_model_image_path(m.filename) is not None]
    pool = available if available else PLUSHPEPE_MODELS
    return random.choice(pool)

def roll_backdrop() -> BackdropDef:
    weights = [b.chance_pct for b in PLUSHPEPE_BACKDROPS]
    return random.choices(PLUSHPEPE_BACKDROPS, weights=weights, k=1)[0]

def calculate_upgraded_stars(base_stars: int, model: PlushModelDef, backdrop: BackdropDef) -> int:
    raw = base_stars * backdrop.price_mult * model.price_mult
    return max(500_000, int(round(raw / 10_000) * 10_000))

def parse_hex_rgb(hex_str: str, fallback: Tuple[int, int, int] = (40, 48, 64)) -> Tuple[int, int, int]:
    try:
        s = (hex_str or "").strip().lstrip("#")
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        pass
    return fallback

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

# ---------------------------------------------------------------------------
# ПРОКАЧКА И УРОВНИ КЛАНОВ (ОТ 0 ДО 100 УРОВНЯ, +1% ДО +45% БОНУС)
# ---------------------------------------------------------------------------

def calculate_clan_level_info(total_xp: int) -> Tuple[int, int, int, float, float]:
    """
    Возвращает (level, current_xp, req_xp, ratio, drop_bonus_pct).
    - Уровень 0: +1.0% к выигрышу.
    - Уровень 100: +45.0% к выигрышу (максимум).
    - Для перехода с 0 на 1 уровень нужно 10,000 XP.
    """
    level = 0
    current_xp = max(0, total_xp)
    req_xp = 10000

    while current_xp >= req_xp and level < 100:
        current_xp -= req_xp
        level += 1
        req_xp = int(10000 + (level * 1800) + (level ** 1.85 * 60))

    if level >= 100:
        level = 100
        ratio = 1.0
        req_xp = current_xp
    else:
        ratio = min(1.0, max(0.0, current_xp / req_xp)) if req_xp > 0 else 1.0

    # Процент бонуса: 0 уровень -> 1.0%, 100 уровень -> 45.0%
    bonus_pct = round(1.0 + (level / 100.0) * 44.0, 1)
    return level, current_xp, req_xp, ratio, bonus_pct

# ---------------------------------------------------------------------------
# База данных SQLite с единой сквозной нумерацией ID и клановым банком
# ---------------------------------------------------------------------------

def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    firebase_manager.schedule_sync()
    return conn

def db_init() -> None:
    conn = db_connect()
    try:
        conn.executescript(
            """
            -- Единый глобальный счетчик ID для игроков и кланов
            CREATE TABLE IF NOT EXISTS global_id_seq (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id_num INTEGER UNIQUE NOT NULL,
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
                clan_id INTEGER DEFAULT NULL,
                bg_image_path TEXT DEFAULT NULL,
                is_banned INTEGER NOT NULL DEFAULT 0,
                ban_until_ts INTEGER NOT NULL DEFAULT 0,
                ban_reason TEXT NOT NULL DEFAULT '',
                ban_hours INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS collection (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                obtained_ts INTEGER NOT NULL,
                is_favorite INTEGER NOT NULL DEFAULT 0,
                is_upgraded INTEGER NOT NULL DEFAULT 0,
                model_name TEXT DEFAULT NULL,
                model_file TEXT DEFAULT NULL,
                model_rarity REAL NOT NULL DEFAULT 0.0,
                bg_name TEXT DEFAULT NULL,
                bg_palette TEXT DEFAULT NULL,
                bg_center_hex TEXT DEFAULT NULL,
                bg_edge_hex TEXT DEFAULT NULL,
                bg_rarity REAL NOT NULL DEFAULT 0.0,
                estimated_stars INTEGER NOT NULL DEFAULT 0,
                upgraded_ts INTEGER NOT NULL DEFAULT 0,
                is_listed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS market_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_file TEXT NOT NULL,
                model_rarity REAL NOT NULL DEFAULT 0.0,
                bg_name TEXT NOT NULL,
                bg_palette TEXT NOT NULL,
                bg_center_hex TEXT NOT NULL,
                bg_edge_hex TEXT NOT NULL,
                bg_rarity REAL NOT NULL DEFAULT 0.0,
                estimated_stars INTEGER NOT NULL DEFAULT 0,
                price_stars INTEGER NOT NULL,
                created_ts INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
            );

            CREATE TABLE IF NOT EXISTS market_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER NOT NULL,
                collection_id INTEGER NOT NULL,
                seller_id INTEGER NOT NULL,
                buyer_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                model_name TEXT NOT NULL,
                bg_name TEXT NOT NULL,
                price_stars INTEGER NOT NULL,
                fee_stars INTEGER NOT NULL,
                seller_payout INTEGER NOT NULL,
                sold_ts INTEGER NOT NULL
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
                id_num INTEGER UNIQUE,
                owner_id INTEGER NOT NULL,
                tag TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                type TEXT NOT NULL DEFAULT 'public',
                entry_fee INTEGER NOT NULL DEFAULT 0,
                max_members INTEGER NOT NULL DEFAULT 15,
                xp INTEGER NOT NULL DEFAULT 0,
                donated_stars INTEGER NOT NULL DEFAULT 0,
                avatar_path TEXT DEFAULT NULL,
                favorite_keys TEXT DEFAULT '',
                last_daily_xp_ts INTEGER NOT NULL DEFAULT 0,
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

        # Миграция колонок collection
        coll_cols = [row["name"] for row in conn.execute("PRAGMA table_info(collection)").fetchall()]
        coll_migrations = [
            ("is_upgraded", "INTEGER NOT NULL DEFAULT 0"),
            ("model_name", "TEXT DEFAULT NULL"),
            ("model_file", "TEXT DEFAULT NULL"),
            ("model_rarity", "REAL NOT NULL DEFAULT 0.0"),
            ("bg_name", "TEXT DEFAULT NULL"),
            ("bg_palette", "TEXT DEFAULT NULL"),
            ("bg_center_hex", "TEXT DEFAULT NULL"),
            ("bg_edge_hex", "TEXT DEFAULT NULL"),
            ("bg_rarity", "REAL NOT NULL DEFAULT 0.0"),
            ("estimated_stars", "INTEGER NOT NULL DEFAULT 0"),
            ("upgraded_ts", "INTEGER NOT NULL DEFAULT 0"),
            ("is_listed", "INTEGER NOT NULL DEFAULT 0"),
        ]
        for col_name, col_def in coll_migrations:
            if col_name not in coll_cols:
                conn.execute(f"ALTER TABLE collection ADD COLUMN {col_name} {col_def};")

        # Миграция колонок clans
        clan_cols = [row["name"] for row in conn.execute("PRAGMA table_info(clans)").fetchall()]
        if "id_num" not in clan_cols:
            conn.execute("ALTER TABLE clans ADD COLUMN id_num INTEGER DEFAULT NULL;")
        if "xp" not in clan_cols:
            conn.execute("ALTER TABLE clans ADD COLUMN xp INTEGER NOT NULL DEFAULT 0;")
        if "donated_stars" not in clan_cols:
            conn.execute("ALTER TABLE clans ADD COLUMN donated_stars INTEGER NOT NULL DEFAULT 0;")
        if "avatar_path" not in clan_cols:
            conn.execute("ALTER TABLE clans ADD COLUMN avatar_path TEXT DEFAULT NULL;")
        if "favorite_keys" not in clan_cols:
            conn.execute("ALTER TABLE clans ADD COLUMN favorite_keys TEXT DEFAULT '';")
        if "last_daily_xp_ts" not in clan_cols:
            conn.execute("ALTER TABLE clans ADD COLUMN last_daily_xp_ts INTEGER NOT NULL DEFAULT 0;")

        # Миграция колонок users
        user_cols = [row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()]
        if "id_num" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN id_num INTEGER DEFAULT NULL;")
        if "clan_id" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN clan_id INTEGER DEFAULT NULL;")
        if "bg_image_path" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN bg_image_path TEXT DEFAULT NULL;")
        if "is_banned" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER NOT NULL DEFAULT 0;")
        if "ban_until_ts" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN ban_until_ts INTEGER NOT NULL DEFAULT 0;")
        if "ban_reason" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN ban_reason TEXT NOT NULL DEFAULT '';")
        if "ban_hours" not in user_cols:
            conn.execute("ALTER TABLE users ADD COLUMN ban_hours INTEGER NOT NULL DEFAULT 0;")

        # Инициализация сквозной нумерации для существующих кланов и игроков без id_num
        unlinked_clans = conn.execute("SELECT id FROM clans WHERE id_num IS NULL").fetchall()
        for c in unlinked_clans:
            cur = conn.execute("INSERT INTO global_id_seq (entity_type) VALUES ('clan')")
            conn.execute("UPDATE clans SET id_num=? WHERE id=?", (cur.lastrowid, c["id"]))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clans_id_num ON clans(id_num);")

        unlinked_users = conn.execute("SELECT user_id FROM users WHERE id_num IS NULL").fetchall()
        for u in unlinked_users:
            cur = conn.execute("INSERT INTO global_id_seq (entity_type) VALUES ('user')")
            conn.execute("UPDATE users SET id_num=? WHERE user_id=?", (cur.lastrowid, u["user_id"]))
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id_num ON users(id_num);")

        conn.commit()
    finally:
        conn.close()

def get_next_global_id(entity_type: str = "entity") -> int:
    """Генерирует следующий единый сквозной ID для пользователей и кланов."""
    conn = db_connect()
    try:
        cur = conn.execute("INSERT INTO global_id_seq (entity_type) VALUES (?)", (entity_type,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def get_or_create_user(user_id: int, username: str, first_name: str) -> sqlite3.Row:
    conn = db_connect()
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            # Получаем единый сквозной ID
            sys_id = get_next_global_id("user")
            conn.execute(
                "INSERT INTO users (id_num, user_id, username, first_name, xp, max_inventory) VALUES (?, ?, ?, ?, 0, 25)",
                (sys_id, user_id, username or "", first_name or ""),
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

# ---------------------------------------------------------------------------
# СИСТЕМА БАНОВ
# ---------------------------------------------------------------------------

def is_user_banned(user_id: int) -> Tuple[bool, int, str, int]:
    conn = db_connect()
    try:
        row = conn.execute("SELECT is_banned, ban_until_ts, ban_reason, ban_hours FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or not row["is_banned"]:
            return False, 0, "", 0

        now = int(time.time())
        until_ts = row["ban_until_ts"]
        if until_ts > 0 and now >= until_ts:
            conn.execute("UPDATE users SET is_banned=0, ban_until_ts=0, ban_reason='', ban_hours=0 WHERE user_id=?", (user_id,))
            conn.commit()
            return False, 0, "", 0

        return True, row["ban_until_ts"], row["ban_reason"], row["ban_hours"]
    finally:
        conn.close()

def ban_user(user_id: int, hours: int, reason: str) -> bool:
    now = int(time.time())
    until_ts = now + (hours * 3600) if hours > 0 else 0
    conn = db_connect()
    try:
        conn.execute(
            "UPDATE users SET is_banned=1, ban_until_ts=?, ban_reason=?, ban_hours=? WHERE user_id=?",
            (until_ts, reason, hours, user_id)
        )
        conn.commit()
        return True
    except Exception as e:
        log.error("Ошибка при бане пользователя: %s", e)
        return False
    finally:
        conn.close()

def unban_user(user_id: int) -> bool:
    conn = db_connect()
    try:
        conn.execute("UPDATE users SET is_banned=0, ban_until_ts=0, ban_reason='', ban_hours=0 WHERE user_id=?", (user_id,))
        conn.commit()
        return True
    except Exception as e:
        log.error("Ошибка при разбане пользователя: %s", e)
        return False
    finally:
        conn.close()

def format_ban_message(ban_until_ts: int, ban_reason: str, ban_hours: int) -> Tuple[str, InlineKeyboardMarkup]:
    if ban_until_ts > 0:
        dt_str = datetime.datetime.fromtimestamp(ban_until_ts, tz=datetime.timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        time_text = f"• Время блокировки: <b>{ban_hours} ч.</b>\n• Заблокирован до: <b>{dt_str}</b>"
    else:
        time_text = "• Время блокировки: <b>Навсегда</b>"

    text = (
        "⛔️ <b>Доступ заблокирован!</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Вы получили бан в системе бота и не можете использовать команды.\n\n"
        f"{time_text}\n"
        f"• Причина: <b>{clean_html(ban_reason or 'Нарушение правил')}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Если вы считаете блокировку ошибочной, обратитесь в поддержку: {SUPPORT_HANDLE}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Поддержка", url=SUPPORT_URL)]
    ])
    return text, kb

# ---------------------------------------------------------------------------
# ПРОЧИЕ ОПЕРАЦИИ С БАЗОЙ ДАННЫХ
# ---------------------------------------------------------------------------

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

def set_user_background(user_id: int, bg_path: Optional[str]) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE users SET bg_image_path=? WHERE user_id=?", (bg_path, user_id))
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
        items = conn.execute(
            "SELECT id, gift_key FROM collection WHERE user_id=? AND is_favorite=0 AND is_upgraded=0 AND is_listed=0",
            (user_id,),
        ).fetchall()
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

# ---------------------------------------------------------------------------
# ОПЕРАЦИИ УЛУЧШЕНИЯ, БЕСПЛАТНОЙ ПЕРЕДАЧИ И P2P МАРКЕТА
# ---------------------------------------------------------------------------

def upgrade_collection_item(
    item_id: int,
    user_id: int,
    cost: int,
    model: PlushModelDef,
    backdrop: BackdropDef,
    est_stars: int,
) -> Tuple[bool, str]:
    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        user_row = conn.execute("SELECT balance_stars FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not user_row or user_row["balance_stars"] < cost:
            conn.rollback()
            return False, f"Недостаточно Stars! Нужно {cost:,} ⭐"

        item = conn.execute("SELECT * FROM collection WHERE id=? AND user_id=?", (item_id, user_id)).fetchone()
        if not item:
            conn.rollback()
            return False, "Подарок не найден в вашей коллекции."
        if item["gift_key"] != "pepe_heart":
            conn.rollback()
            return False, "Улучшение доступно только для обычного Plush Pepe!"
        if item["is_upgraded"]:
            conn.rollback()
            return False, "Этот Plush Pepe уже улучшен!"
        if item["is_listed"]:
            conn.rollback()
            return False, "Предмет сейчас выставлен на маркет!"

        conn.execute("UPDATE users SET balance_stars=balance_stars-?, xp=xp+25000 WHERE user_id=?", (cost, user_id))
        conn.execute(
            """
            UPDATE collection
            SET is_upgraded=1,
                model_name=?,
                model_file=?,
                model_rarity=?,
                bg_name=?,
                bg_palette=?,
                bg_center_hex=?,
                bg_edge_hex=?,
                bg_rarity=?,
                estimated_stars=?,
                upgraded_ts=?
            WHERE id=? AND user_id=?
            """,
            (
                model.name,
                model.filename,
                model.rarity_pct,
                backdrop.name,
                backdrop.palette,
                backdrop.center_hex,
                backdrop.edge_hex,
                backdrop.chance_pct,
                est_stars,
                int(time.time()),
                item_id,
                user_id,
            ),
        )
        conn.commit()
        return True, "OK"
    except Exception as e:
        conn.rollback()
        log.error("Ошибка улучшения подарка: %s", e)
        return False, "Ошибка базы данных при улучшении."
    finally:
        conn.close()

def transfer_collection_item(item_id: int, sender_id: int, recipient_id: int) -> Tuple[bool, str]:
    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        item = conn.execute("SELECT * FROM collection WHERE id=? AND user_id=?", (item_id, sender_id)).fetchone()
        if not item:
            conn.rollback()
            return False, "Предмет не найден в вашей коллекции."
        if item["is_listed"]:
            conn.rollback()
            return False, "Нельзя передать предмет, пока он выставлен на маркете."

        rec = conn.execute("SELECT max_inventory FROM users WHERE user_id=?", (recipient_id,)).fetchone()
        if not rec:
            conn.rollback()
            return False, "Получатель не найден."
        cnt = conn.execute("SELECT COUNT(*) as cnt FROM collection WHERE user_id=?", (recipient_id,)).fetchone()["cnt"]
        if cnt >= rec["max_inventory"]:
            conn.rollback()
            return False, "У получателя переполнен инвентарь!"

        conn.execute(
            "UPDATE collection SET user_id=?, is_favorite=0, obtained_ts=? WHERE id=? AND user_id=?",
            (recipient_id, int(time.time()), item_id, sender_id),
        )
        conn.commit()
        return True, "OK"
    except Exception as e:
        conn.rollback()
        log.error("Ошибка передачи подарка: %s", e)
        return False, "Ошибка при передаче подарка."
    finally:
        conn.close()

def create_market_listing(item_id: int, seller_id: int, price_stars: int) -> Tuple[bool, int, str]:
    if price_stars < MARKET_MIN_PRICE or price_stars > MARKET_MAX_PRICE:
        return False, 0, f"Цена должна быть от {MARKET_MIN_PRICE:,} до {MARKET_MAX_PRICE:,} ⭐!"
    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        item = conn.execute("SELECT * FROM collection WHERE id=? AND user_id=?", (item_id, seller_id)).fetchone()
        if not item:
            conn.rollback()
            return False, 0, "Предмет не найден в вашей коллекции."
        if not item["is_upgraded"]:
            conn.rollback()
            return False, 0, "На маркет можно выставлять только улучшенные подарки!"
        if item["is_listed"]:
            conn.rollback()
            return False, 0, "Этот подарок уже выставлен на маркете."

        conn.execute("UPDATE collection SET is_listed=1, is_favorite=0 WHERE id=?", (item_id,))
        cur = conn.execute(
            """
            INSERT INTO market_listings (
                collection_id, seller_id, gift_key, model_name, model_file, model_rarity,
                bg_name, bg_palette, bg_center_hex, bg_edge_hex, bg_rarity,
                estimated_stars, price_stars, created_ts, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            """,
            (
                item["id"],
                seller_id,
                item["gift_key"],
                item["model_name"] or "Plush Pepe",
                item["model_file"] or "",
                item["model_rarity"] or 2.0,
                item["bg_name"] or "Black",
                item["bg_palette"] or "Тёмный",
                item["bg_center_hex"] or "#4C5153",
                item["bg_edge_hex"] or "#2B2E30",
                item["bg_rarity"] or 1.0,
                item["estimated_stars"] or 500_000,
                price_stars,
                int(time.time()),
            ),
        )
        listing_id = cur.lastrowid
        conn.commit()
        return True, listing_id, "OK"
    except Exception as e:
        conn.rollback()
        log.error("Ошибка создания лота: %s", e)
        return False, 0, "Ошибка при создании лота."
    finally:
        conn.close()

def get_market_listings_filtered(ftype: str, fkey: str, page: int = 1, page_size: int = 8) -> Tuple[list[sqlite3.Row], int, int]:
    conn = db_connect()
    try:
        where = "WHERE status='active'"
        params: list = []
        if ftype == "price" and fkey in MARKET_PRICE_TIERS:
            _, min_p, max_p = MARKET_PRICE_TIERS[fkey]
            where += " AND price_stars BETWEEN ? AND ?"
            params.extend([min_p, max_p])
        elif ftype == "model":
            if fkey == "rare_dark":
                where += " AND bg_rarity <= 0.9"
            elif fkey in MODEL_GROUPS:
                keys = [g.key for g in GIFTS if g.model_group == fkey]
                if keys:
                    placeholders = ",".join("?" for _ in keys)
                    where += f" AND gift_key IN ({placeholders})"
                    params.extend(keys)
                else:
                    return [], 1, 0

        total = conn.execute(f"SELECT COUNT(*) as cnt FROM market_listings {where}", params).fetchone()["cnt"]
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM market_listings {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, page_size, offset],
        ).fetchall()
        return rows, total_pages, total
    finally:
        conn.close()

def get_market_listing(listing_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute("SELECT * FROM market_listings WHERE id=?", (listing_id,)).fetchone()
    finally:
        conn.close()

def get_market_listing_by_item(item_id: int) -> Optional[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM market_listings WHERE collection_id=? AND status='active' ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
    finally:
        conn.close()

def get_user_market_listings(user_id: int) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM market_listings WHERE seller_id=? AND status='active' ORDER BY id DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

def cancel_market_listing(listing_id: int, user_id: int) -> Tuple[bool, str]:
    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        lot = conn.execute("SELECT * FROM market_listings WHERE id=? AND seller_id=?", (listing_id, user_id)).fetchone()
        if not lot or lot["status"] != "active":
            conn.rollback()
            return False, "Активный лот не найден."
        conn.execute("UPDATE market_listings SET status='cancelled' WHERE id=?", (listing_id,))
        conn.execute("UPDATE collection SET is_listed=0 WHERE id=?", (lot["collection_id"],))
        conn.commit()
        return True, "OK"
    except Exception as e:
        conn.rollback()
        log.error("Ошибка отмены лота: %s", e)
        return False, "Ошибка отмены лота."
    finally:
        conn.close()

def buy_market_listing(listing_id: int, buyer_id: int) -> Tuple[bool, dict, str]:
    conn = db_connect()
    try:
        conn.execute("BEGIN IMMEDIATE;")
        lot = conn.execute("SELECT * FROM market_listings WHERE id=?", (listing_id,)).fetchone()
        if not lot or lot["status"] != "active":
            conn.rollback()
            return False, {}, "Лот уже продан или снят с продажи."
        if lot["seller_id"] == buyer_id:
            conn.rollback()
            return False, {}, "Нельзя купить собственный лот!"

        buyer = conn.execute("SELECT balance_stars, max_inventory FROM users WHERE user_id=?", (buyer_id,)).fetchone()
        if not buyer:
            conn.rollback()
            return False, {}, "Профиль покупателя не найден."

        price = lot["price_stars"]
        if buyer["balance_stars"] < price:
            conn.rollback()
            return False, {}, f"Недостаточно Stars! Нужно {price:,} ⭐"

        cnt = conn.execute("SELECT COUNT(*) as cnt FROM collection WHERE user_id=?", (buyer_id,)).fetchone()["cnt"]
        if cnt >= buyer["max_inventory"]:
            conn.rollback()
            return False, {}, "Ваш инвентарь переполнен! Расширьте слоты в «🛍 Улучшения»."

        fee_stars = int(round(price * MARKET_FEE_RATE))
        seller_payout = max(0, price - fee_stars)
        now = int(time.time())

        conn.execute("UPDATE users SET balance_stars=balance_stars-? WHERE user_id=?", (price, buyer_id))
        conn.execute(
            "UPDATE users SET balance_stars=balance_stars+?, total_sold=total_sold+1 WHERE user_id=?",
            (seller_payout, lot["seller_id"]),
        )
        conn.execute(
            "UPDATE collection SET user_id=?, is_listed=0, is_favorite=0, obtained_ts=? WHERE id=?",
            (buyer_id, now, lot["collection_id"]),
        )
        conn.execute("UPDATE market_listings SET status='sold' WHERE id=?", (listing_id,))
        conn.execute(
            """
            INSERT INTO market_history (
                listing_id, collection_id, seller_id, buyer_id, gift_key,
                model_name, bg_name, price_stars, fee_stars, seller_payout, sold_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing_id,
                lot["collection_id"],
                lot["seller_id"],
                buyer_id,
                lot["gift_key"],
                lot["model_name"],
                lot["bg_name"],
                price,
                fee_stars,
                seller_payout,
                now,
            ),
        )
        conn.commit()
        return True, {
            "lot": dict(lot),
            "price": price,
            "fee": fee_stars,
            "payout": seller_payout,
        }, "OK"
    except Exception as e:
        conn.rollback()
        log.error("Ошибка покупки на маркете: %s", e)
        return False, {}, "Ошибка при проведении сделки."
    finally:
        conn.close()

def get_market_history_rows(user_id: int, limit: int = 12) -> list[sqlite3.Row]:
    conn = db_connect()
    try:
        return conn.execute(
            "SELECT * FROM market_history WHERE seller_id=? OR buyer_id=? ORDER BY id DESC LIMIT ?",
            (user_id, user_id, limit),
        ).fetchall()
    finally:
        conn.close()

def get_market_stats() -> Tuple[int, int]:
    conn = db_connect()
    try:
        active_cnt = conn.execute("SELECT COUNT(*) as cnt FROM market_listings WHERE status='active'").fetchone()["cnt"]
        deals_cnt = conn.execute("SELECT COUNT(*) as cnt FROM market_history").fetchone()["cnt"]
        return active_cnt, deals_cnt
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
        page = max(1, min(page, total_pages))
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
# КЛАНЫ — БАЗА ДАННЫХ И КАЗНА
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

def get_clan_treasury_and_members(clan_id: int) -> Tuple[int, int, list[sqlite3.Row]]:
    """
    Возвращает:
    - total_treasury: общая казна (сумма балансов Stars всех участников клана)
    - donated_bank: банк пожертвований звезд клана
    - members: отсортированный список участников с балансами
    """
    conn = db_connect()
    try:
        members = conn.execute(
            "SELECT user_id, first_name, username, balance_stars FROM users WHERE clan_id=? ORDER BY balance_stars DESC",
            (clan_id,)
        ).fetchall()
        total_treasury = sum(m["balance_stars"] for m in members)
        clan = conn.execute("SELECT donated_stars FROM clans WHERE id=?", (clan_id,)).fetchone()
        donated_bank = clan["donated_stars"] if clan else 0
        return total_treasury, donated_bank, members
    finally:
        conn.close()

def check_and_award_clan_daily_xp(clan_id: int) -> Optional[int]:
    """
    Каждые 24 часа начисляет клану XP в зависимости от размера общей казны.
    XP начисляется только если казна >= 5,000,000 Stars.
    """
    conn = db_connect()
    try:
        clan = conn.execute("SELECT last_daily_xp_ts, xp FROM clans WHERE id=?", (clan_id,)).fetchone()
        if not clan:
            return None
        now = int(time.time())
        last_ts = clan["last_daily_xp_ts"] or 0
        if now - last_ts < 24 * 3600:
            return None

        # Суммируем казну участников
        members = conn.execute("SELECT balance_stars FROM users WHERE clan_id=?", (clan_id,)).fetchall()
        treasury = sum(m["balance_stars"] for m in members)

        if treasury < 5_000_000:
            conn.execute("UPDATE clans SET last_daily_xp_ts=? WHERE id=?", (now, clan_id))
            conn.commit()
            return None

        # Сбалансированная формула: базовая 500 XP за 5 млн + рост с казной
        millions = treasury / 1_000_000
        awarded_xp = int(500 + 450 * math.log2(millions / 5 + 1))
        conn.execute("UPDATE clans SET xp=xp+?, last_daily_xp_ts=? WHERE id=?", (awarded_xp, now, clan_id))
        conn.commit()
        return awarded_xp
    finally:
        conn.close()

def donate_stars_to_clan(user_id: int, clan_id: int, stars: int) -> Tuple[bool, int]:
    """
    Пополнение казны звездами:
    - Списывает звезды у игрока
    - Добавляет в банк клана
    - Начисляет клану XP (800 XP за 1,000,000 ⭐)
    """
    if not deduct_user_stars(user_id, stars):
        return False, 0
    xp_earned = max(1, int(stars * 0.0008))
    conn = db_connect()
    try:
        conn.execute("UPDATE clans SET donated_stars=donated_stars+?, xp=xp+? WHERE id=?", (stars, xp_earned, clan_id))
        conn.commit()
        return True, xp_earned
    finally:
        conn.close()

def set_clan_avatar(clan_id: int, avatar_path: Optional[str]) -> None:
    conn = db_connect()
    try:
        conn.execute("UPDATE clans SET avatar_path=? WHERE id=?", (avatar_path, clan_id))
        conn.commit()
    finally:
        conn.close()

def get_clan_favorites(clan: sqlite3.Row) -> List[GiftDef]:
    keys_str = clan["favorite_keys"] if "favorite_keys" in clan.keys() and clan["favorite_keys"] else ""
    fav_keys = [k.strip() for k in keys_str.split(",") if k.strip() and k.strip() in GIFTS_BY_KEY]
    return [GIFTS_BY_KEY[k] for k in fav_keys[:7]]

def toggle_clan_favorite_gift(clan_id: int, gift_key: str) -> bool:
    clan = get_clan_by_id(clan_id)
    if not clan:
        return False
    keys_str = clan["favorite_keys"] if "favorite_keys" in clan.keys() and clan["favorite_keys"] else ""
    fav_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    if gift_key in fav_keys:
        fav_keys.remove(gift_key)
    else:
        if len(fav_keys) >= 7:
            return False
        fav_keys.append(gift_key)
    new_str = ",".join(fav_keys)
    conn = db_connect()
    try:
        conn.execute("UPDATE clans SET favorite_keys=? WHERE id=?", (new_str, clan_id))
        conn.commit()
        return True
    finally:
        conn.close()

def get_all_clans(page: int = 1, page_size: int = 5) -> Tuple[list[sqlite3.Row], int]:
    conn = db_connect()
    try:
        total = conn.execute("SELECT COUNT(*) as cnt FROM clans").fetchone()["cnt"]
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))
        offset = (page - 1) * page_size
        rows = conn.execute("SELECT * FROM clans ORDER BY xp DESC, id DESC LIMIT ? OFFSET ?", (page_size, offset)).fetchall()
        return rows, total_pages
    finally:
        conn.close()

def create_clan(owner_id: int, tag: str, name: str, desc: str, ctype: str, fee: int) -> Optional[int]:
    clan_sys_id = get_next_global_id("clan")
    conn = db_connect()
    try:
        cur = conn.execute(
            "INSERT INTO clans (id_num, owner_id, tag, name, description, type, entry_fee, max_members, xp, donated_stars, last_daily_xp_ts, created_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 15, 0, 0, ?, ?)",
            (clan_sys_id, owner_id, tag, name, desc, ctype, fee, int(time.time()), int(time.time()))
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
# РЕНДЕР КАРТОЧЕК И БАННЕРОВ (БЕЗ СМАЙЛИКОВ И КВАДРАТОВ)
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

    font = load_font(22, bold=True)
    clean_txt = strip_all_emojis_for_image(text)[:8]
    draw.text((size // 6, size - 36), clean_txt, font=font, fill=(255, 255, 255, 230))
    return img

def make_default_clan_avatar(size: int = 190, tag: str = "CLAN", name: str = "Clan") -> Image.Image:
    """Генерация стильного геральдического герба клана, если аватарка не загружена."""
    img = Image.new("RGBA", (size, size), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)

    # Внутреннее свечение герба
    draw_rounded_rect(draw, [10, 10, size - 10, size - 10], radius=32, fill=(30, 41, 59, 255), outline=(234, 179, 8, 230), width=3)
    draw_rounded_rect(draw, [18, 18, size - 18, size - 18], radius=24, fill=(17, 24, 39, 255), outline=(59, 130, 246, 180), width=1)

    f_tag = load_font(34, bold=True)
    f_sub = load_font(16, bold=True)

    clean_tag = strip_all_emojis_for_image(tag)[:6].upper()
    draw.text((size // 2, size // 2 - 12), clean_tag, font=f_tag, fill=(234, 179, 8), anchor="mm")
    draw.text((size // 2, size // 2 + 32), "CLAN", font=f_sub, fill=(156, 163, 175), anchor="mm")
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
    img = Image.new("RGBA", (WIDTH, HEIGHT), (22, 28, 38, 255))

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([250, -120, 750, 280], fill=(59, 130, 246, 120))
    glow_draw.ellipse([100, 100, 450, 400], fill=(234, 179, 8, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(50))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    f_title = load_font(52, bold=True)
    f_sub = load_font(23, bold=False)

    draw.text((WIDTH // 2, 115), "NEW NFT GIFT BOT", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 185), "Telegram Gifts, кланы, кастомизация и торговля", font=f_sub, fill=(234, 179, 8), anchor="mm")

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.name = "menu.png"
    bio.seek(0)
    return bio

async def generate_market_banner() -> io.BytesIO:
    WIDTH, HEIGHT = 1000, 340
    img = Image.new("RGBA", (WIDTH, HEIGHT), (18, 24, 34, 255))

    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([200, -80, 800, 300], fill=(16, 185, 129, 110))
    glow_draw.ellipse([500, 100, 900, 400], fill=(99, 102, 241, 100))
    glow = glow.filter(ImageFilter.GaussianBlur(55))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    f_badge = load_font(18, bold=True)
    f_title = load_font(48, bold=True)
    f_sub = load_font(21, bold=False)

    draw_rounded_rect(draw, [WIDTH // 2 - 110, 45, WIDTH // 2 + 110, 80], radius=10, fill=(16, 185, 129, 60), outline=(16, 185, 129, 200), width=1)
    draw.text((WIDTH // 2, 62), "P2P TRADE EXCHANGE", font=f_badge, fill=(52, 211, 153), anchor="mm")

    draw.text((WIDTH // 2, 135), "NFT MARKETPLACE", font=f_title, fill=(255, 255, 255), anchor="mm")
    draw.text((WIDTH // 2, 205), "Торговая площадка для покупки и продажи улучшенных подарков", font=f_sub, fill=(209, 213, 219), anchor="mm")
    draw.text((WIDTH // 2, 250), "Свободные цены от 1,000 до 100 млрд STARS | Комиссия рынка 15%", font=load_font(18, bold=True), fill=(234, 179, 8), anchor="mm")

    bio = io.BytesIO()
    img.save(bio, "PNG")
    bio.name = "market.png"
    bio.seek(0)
    return bio

def _make_radial_gradient_bg(size: int, center_hex: str, edge_hex: str) -> Image.Image:
    """Создаёт плавный радиальный градиент фона как в коллекционных подарках Telegram."""
    c_rgb = parse_hex_rgb(center_hex, (76, 81, 83))
    e_rgb = parse_hex_rgb(edge_hex, (36, 39, 41))

    # Строим градиент в уменьшенном разрешении и плавно масштабируем для высокой скорости
    small = 160
    grad = Image.new("RGBA", (small, small))
    pixels = grad.load()
    half = small / 2.0
    max_dist = math.hypot(half, half)
    for y in range(small):
        dy = y - half
        for x in range(small):
            dx = x - half
            t = min(1.0, (math.hypot(dx, dy) / (max_dist * 0.85)) ** 1.15)
            r = int(c_rgb[0] * (1.0 - t) + e_rgb[0] * t)
            g = int(c_rgb[1] * (1.0 - t) + e_rgb[1] * t)
            b = int(c_rgb[2] * (1.0 - t) + e_rgb[2] * t)
            pixels[x, y] = (r, g, b, 255)
    return grad.resize((size, size), Image.Resampling.BICUBIC)

async def generate_upgraded_gift_image(
    model_file: str,
    model_name: str,
    bg_name: str,
    bg_center_hex: str,
    bg_edge_hex: str,
    bg_rarity: float,
    item_id: int,
) -> io.BytesIO:
    """Генерация карточки улучшенного Plush Pepe (модель поверх радиального фона)."""
    SIZE = 640
    canvas = _make_radial_gradient_bg(SIZE, bg_center_hex, bg_edge_hex)

    # Лёгкие декоративные кольца и мягкое свечение по центру
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    c_rgb = parse_hex_rgb(bg_center_hex, (100, 116, 139))
    glow_color = (min(255, c_rgb[0] + 65), min(255, c_rgb[1] + 65), min(255, c_rgb[2] + 65), 75)
    od.ellipse([130, 80, 510, 460], fill=glow_color)
    overlay = overlay.filter(ImageFilter.GaussianBlur(42))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas)
    # Тонкая коллекционная рамка и декоративные окружности
    draw_rounded_rect(draw, [14, 14, SIZE - 14, SIZE - 14], radius=34, fill=None, outline=(255, 255, 255, 55), width=2)
    draw.ellipse([120, 75, 520, 475], outline=(255, 255, 255, 32), width=2)

    # Модель Plush Pepe
    model_p = plush_model_image_path(model_file) or gift_image_path("pepe_heart")
    if model_p and model_p.exists():
        try:
            m_img = Image.open(model_p).convert("RGBA")
            m_img.thumbnail((390, 390), Image.Resampling.LANCZOS)
            mx = (SIZE - m_img.width) // 2
            my = 65 + (390 - m_img.height) // 2

            # Мягкая тень под моделью
            shadow = Image.new("RGBA", m_img.size, (0, 0, 0, 0))
            alpha_ch = m_img.split()[3]
            shadow.paste((0, 0, 0, 125), mask=alpha_ch)
            shadow = shadow.filter(ImageFilter.GaussianBlur(14))
            canvas.paste(shadow, (mx, my + 12), shadow)
            canvas.paste(m_img, (mx, my), m_img)
        except Exception as e:
            log.warning("Ошибка рендера модели Plush Pepe %s: %s", model_file, e)

    draw = ImageDraw.Draw(canvas)
    # Верхний бейдж номера
    draw_rounded_rect(draw, [32, 30, 210, 68], radius=14, fill=(10, 15, 25, 155), outline=(255, 255, 255, 70), width=1)
    draw.text((121, 49), f"PLUSH PEPE #{item_id}", font=load_font(16, bold=True), fill=(255, 255, 255), anchor="mm")

    # Нижняя инфо-плашка (без смайликов)
    draw_rounded_rect(draw, [32, 488, SIZE - 32, 608], radius=22, fill=(10, 14, 22, 185), outline=(255, 255, 255, 70), width=1)
    clean_model = strip_all_emojis_for_image(model_name)
    clean_bg = strip_all_emojis_for_image(bg_name)

    draw.text((SIZE // 2, 522), clean_model.upper(), font=load_font(28, bold=True), fill=(255, 255, 255), anchor="mm")
    draw.text(
        (SIZE // 2, 566),
        f"BACKDROP: {clean_bg.upper()} ({bg_rarity:.2f}%)",
        font=load_font(18, bold=True),
        fill=(234, 179, 8),
        anchor="mm",
    )

    bio = io.BytesIO()
    canvas.save(bio, "PNG")
    bio.name = f"plush_pepe_{item_id}.png"
    bio.seek(0)
    return bio

async def generate_profile_card_image(
    user_name: str,
    user_sys_id: int,
    stars_balance: int,
    user_xp: int,
    rank: int,
    favorite_gifts: list,
    avatar_bytes: Optional[bytes] = None,
    clan_tag: Optional[str] = None,
    custom_bg_path: Optional[str] = None,
) -> io.BytesIO:
    """Генерация карточки профиля игрока БЕЗ смайликов."""
    WIDTH, HEIGHT = 1000, 560
    clean_name = strip_all_emojis_for_image(user_name)

    has_custom_bg = False
    if custom_bg_path and Path(custom_bg_path).exists():
        try:
            custom_img = Image.open(custom_bg_path).convert("RGBA")
            base_bg = ImageOps.fit(custom_img, (WIDTH, HEIGHT))
            base_bg = base_bg.filter(ImageFilter.GaussianBlur(10))
            darken_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (12, 16, 24, 195))
            base_bg = Image.alpha_composite(base_bg, darken_overlay)
            has_custom_bg = True
        except Exception as e:
            log.warning("Не удалось обработать кастомный фон пользователя: %s", e)

    if not has_custom_bg:
        base_bg = Image.new("RGBA", (WIDTH, HEIGHT), (24, 32, 44, 255))
        glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse([20, 20, 360, 360], fill=(30, 41, 59, 220))
        glow_draw.ellipse([600, -50, 950, 250], fill=(234, 179, 8, 30))
        glow = glow.filter(ImageFilter.GaussianBlur(40))
        base_bg = Image.alpha_composite(base_bg, glow)

    draw = ImageDraw.Draw(base_bg)

    font_title = load_font(38, bold=True)
    font_sub = load_font(22, bold=True)
    font_small = load_font(18, bold=False)
    font_stat_val = load_font(34, bold=True)
    font_stat_lbl = load_font(16, bold=True)

    av_size = 190
    av_img = None
    if avatar_bytes:
        try:
            loaded_av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = ImageOps.fit(loaded_av, (av_size, av_size))
        except Exception as e:
            log.warning("Ошибка обработки аватара: %s", e)
            av_img = make_default_avatar(av_size, clean_name[:10])
    else:
        av_img = make_default_avatar(av_size, clean_name[:10])

    mask = Image.new("L", (av_size, av_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, av_size, av_size], radius=24, fill=255)

    av_x, av_y = 55, 65
    draw_rounded_rect(draw, [av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3], radius=26, fill=None, outline=(234, 179, 8, 180), width=2)
    base_bg.paste(av_img, (av_x, av_y), mask)

    text_x = 280
    curr_x = text_x
    if clan_tag:
        tag_str = f"[{clan_tag.upper()}] "
        draw.text((curr_x, 70), tag_str, font=font_title, fill=(234, 179, 8))
        bbox = draw.textbbox((curr_x, 70), tag_str, font=font_title)
        curr_x = bbox[2]

    disp_name = clean_name if len(clean_name) <= 16 else (clean_name[:14] + "..")
    draw.text((curr_x, 70), disp_name, font=font_title, fill=(255, 255, 255))

    lvl, cur_xp, req_xp, ratio = calculate_xp_level_info(user_xp)
    draw.text((text_x, 125), f"LEVEL {lvl} ({cur_xp:,} / {req_xp:,} XP)", font=font_sub, fill=(229, 231, 235))

    bar_x, bar_y, bar_w, bar_h = text_x, 160, 380, 12
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=(45, 55, 72, 230))
    fill_w = max(10, int(bar_w * ratio))
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=6, fill=(234, 179, 8))

    draw.text((820, 75), f"ID #{user_sys_id}", font=font_small, fill=(156, 163, 175))
    draw.line([(text_x, 195), (940, 195)], fill=(75, 85, 99, 140), width=1)

    stats_y = 210
    draw.rectangle([text_x, stats_y, text_x + 4, stats_y + 40], fill=(234, 179, 8))
    draw.text((text_x + 14, stats_y - 2), "STARS BALANCE", font=font_stat_lbl, fill=(156, 163, 175))
    draw.text((text_x + 14, stats_y + 16), f"{stars_balance:,} STARS", font=font_stat_val, fill=(255, 255, 255))

    rank_x = text_x + 280
    draw.rectangle([rank_x, stats_y, rank_x + 4, stats_y + 40], fill=(59, 130, 246))
    draw.text((rank_x + 14, stats_y - 2), "GLOBAL RANK", font=font_stat_lbl, fill=(156, 163, 175))
    draw.text((rank_x + 14, stats_y + 16), f"#{rank}", font=font_stat_val, fill=(255, 255, 255))

    draw.line([(55, 290), (945, 290)], fill=(75, 85, 99, 140), width=1)
    draw.text((55, 305), "FAVORITES", font=font_stat_lbl, fill=(156, 163, 175))

    slot_y = 335
    slot_w, slot_h = 113, 113
    spacing = 16
    start_x = 55

    for i in range(7):
        cur_x = start_x + i * (slot_w + spacing)
        if i < len(favorite_gifts):
            fav = favorite_gifts[i]
            is_upg = False
            g_key = None
            m_file = None
            bg_c = None
            bg_e = None
            if isinstance(fav, GiftDef):
                g = fav
                g_key = fav.key
            else:
                g_key = fav["gift_key"]
                g = GIFTS_BY_KEY.get(g_key)
                is_upg = bool(fav["is_upgraded"]) if "is_upgraded" in fav.keys() else False
                m_file = fav["model_file"] if "model_file" in fav.keys() else None
                bg_c = fav["bg_center_hex"] if "bg_center_hex" in fav.keys() else None
                bg_e = fav["bg_edge_hex"] if "bg_edge_hex" in fav.keys() else None

            if is_upg and bg_c and bg_e:
                slot_bg = _make_radial_gradient_bg(slot_w, bg_c, bg_e)
                s_mask = Image.new("L", (slot_w, slot_h), 0)
                ImageDraw.Draw(s_mask).rounded_rectangle([0, 0, slot_w, slot_h], radius=16, fill=255)
                base_bg.paste(slot_bg, (cur_x, slot_y), s_mask)
                draw_rounded_rect(draw, [cur_x, slot_y, cur_x + slot_w, slot_y + slot_h], radius=16, fill=None, outline=(234, 179, 8, 220), width=2)
            else:
                draw_rounded_rect(draw, [cur_x, slot_y, cur_x + slot_w, slot_y + slot_h], radius=16, fill=(15, 23, 42, 210), outline=(51, 65, 85, 180), width=1)

            img_p = plush_model_image_path(m_file) if (is_upg and m_file) else (gift_image_path(g_key) if g_key else None)
            if img_p and img_p.exists():
                try:
                    g_img = Image.open(img_p).convert("RGBA")
                    g_img.thumbnail((84 if is_upg else 78, 84 if is_upg else 78))
                    gx = cur_x + (slot_w - g_img.width) // 2
                    gy = slot_y + (slot_h - g_img.height) // 2
                    base_bg.paste(g_img, (gx, gy), g_img)
                except Exception as e:
                    log.warning("Ошибка рендера подарка в карточке: %s", e)
            elif g:
                clean_g_name = g.name.split('(')[0].strip()[:9]
                draw.text((cur_x + slot_w // 2, slot_y + slot_h // 2 - 8), clean_g_name, font=load_font(13, bold=True), fill=(255, 255, 255), anchor="mm")
                draw.text((cur_x + slot_w // 2, slot_y + slot_h - 22), f"{g.stars:,} Stars", font=load_font(11, bold=True), fill=(234, 179, 8), anchor="mm")
        else:
            draw_rounded_rect(draw, [cur_x, slot_y, cur_x + slot_w, slot_y + slot_h], radius=16, fill=(15, 23, 42, 210), outline=(51, 65, 85, 180), width=1)
            cx, cy = cur_x + slot_w // 2, slot_y + slot_h // 2
            arm = 12
            thick = 3
            draw.line([(cx - arm, cy - arm), (cx + arm, cy + arm)], fill=(100, 116, 139, 120), width=thick)
            draw.line([(cx + arm, cy - arm), (cx - arm, cy + arm)], fill=(100, 116, 139, 120), width=thick)

    if has_custom_bg:
        draw_rounded_rect(draw, [55, HEIGHT - 52, 230, HEIGHT - 24], radius=6, fill=(0, 0, 0, 120))
        draw.text((142, HEIGHT - 38), "CUSTOM BACKGROUND", font=load_font(13, bold=True), fill=(229, 231, 235), anchor="mm")

    bio = io.BytesIO()
    base_bg.save(bio, "PNG")
    bio.name = "profile.png"
    bio.seek(0)
    return bio

async def generate_clan_card_image(
    clan_name: str,
    clan_tag: str,
    clan_sys_id: int,
    clan_xp: int,
    treasury_stars: int,
    members_count: int,
    max_members: int,
    favorite_gifts: List[GiftDef],
    avatar_path: Optional[str] = None
) -> io.BytesIO:
    """Генерация графической карточки профиля клана (как у игрока)."""
    WIDTH, HEIGHT = 1000, 560
    clean_name = strip_all_emojis_for_image(clan_name)
    clean_tag = strip_all_emojis_for_image(clan_tag).upper()

    base_bg = Image.new("RGBA", (WIDTH, HEIGHT), (20, 26, 38, 255))
    glow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse([20, 20, 380, 380], fill=(30, 58, 138, 220))
    glow_draw.ellipse([600, -50, 950, 250], fill=(234, 179, 8, 35))
    glow = glow.filter(ImageFilter.GaussianBlur(45))
    base_bg = Image.alpha_composite(base_bg, glow)

    draw = ImageDraw.Draw(base_bg)

    font_title = load_font(38, bold=True)
    font_sub = load_font(22, bold=True)
    font_small = load_font(18, bold=False)
    font_stat_val = load_font(30, bold=True)
    font_stat_lbl = load_font(15, bold=True)

    # 1. Аватарка или герб клана
    av_size = 190
    av_img = None
    if avatar_path and Path(avatar_path).exists():
        try:
            loaded_av = Image.open(avatar_path).convert("RGBA")
            av_img = ImageOps.fit(loaded_av, (av_size, av_size))
        except Exception as e:
            log.warning("Ошибка чтения аватарки клана: %s", e)
            av_img = make_default_clan_avatar(av_size, clean_tag, clean_name)
    else:
        av_img = make_default_clan_avatar(av_size, clean_tag, clean_name)

    mask = Image.new("L", (av_size, av_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, av_size, av_size], radius=26, fill=255)

    av_x, av_y = 55, 65
    draw_rounded_rect(draw, [av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3], radius=28, fill=None, outline=(234, 179, 8, 220), width=2)
    base_bg.paste(av_img, (av_x, av_y), mask)

    # 2. Название, тег, уровень и прогресс XP
    text_x = 280
    tag_str = f"[{clean_tag}] "
    draw.text((text_x, 70), tag_str, font=font_title, fill=(234, 179, 8))
    bbox = draw.textbbox((text_x, 70), tag_str, font=font_title)
    disp_name = clean_name if len(clean_name) <= 15 else (clean_name[:13] + "..")
    draw.text((bbox[2], 70), disp_name, font=font_title, fill=(255, 255, 255))

    lvl, cur_xp, req_xp, ratio, drop_bonus = calculate_clan_level_info(clan_xp)
    draw.text((text_x, 125), f"CLAN LEVEL {lvl} ({cur_xp:,} / {req_xp:,} XP)", font=font_sub, fill=(229, 231, 235))

    bar_x, bar_y, bar_w, bar_h = text_x, 160, 380, 12
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=6, fill=(45, 55, 72, 230))
    fill_w = max(10, int(bar_w * ratio))
    draw_rounded_rect(draw, [bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=6, fill=(234, 179, 8))

    draw.text((810, 75), f"CLAN ID #{clan_sys_id}", font=font_small, fill=(156, 163, 175))
    draw.line([(text_x, 195), (940, 195)], fill=(75, 85, 99, 140), width=1)

    # 3. Статистика казны, участников и бонуса
    stats_y = 210
    draw.rectangle([text_x, stats_y, text_x + 4, stats_y + 40], fill=(234, 179, 8))
    draw.text((text_x + 12, stats_y - 2), "TOTAL TREASURY", font=font_stat_lbl, fill=(156, 163, 175))
    draw.text((text_x + 12, stats_y + 16), f"{treasury_stars:,} STARS", font=font_stat_val, fill=(255, 255, 255))

    col2_x = text_x + 240
    draw.rectangle([col2_x, stats_y, col2_x + 4, stats_y + 40], fill=(59, 130, 246))
    draw.text((col2_x + 12, stats_y - 2), "MEMBERS", font=font_stat_lbl, fill=(156, 163, 175))
    draw.text((col2_x + 12, stats_y + 16), f"{members_count}/{max_members}", font=font_stat_val, fill=(255, 255, 255))

    col3_x = col2_x + 180
    draw.rectangle([col3_x, stats_y, col3_x + 4, stats_y + 40], fill=(16, 185, 129))
    draw.text((col3_x + 12, stats_y - 2), "WIN BONUS", font=font_stat_lbl, fill=(156, 163, 175))
    draw.text((col3_x + 12, stats_y + 16), f"+{drop_bonus}%", font=font_stat_val, fill=(52, 211, 153))

    # 4. Избранные подарки клана (CLAN FAVORITES)
    draw.line([(55, 290), (945, 290)], fill=(75, 85, 99, 140), width=1)
    draw.text((55, 305), "CLAN FAVORITES", font=font_stat_lbl, fill=(156, 163, 175))

    slot_y = 335
    slot_w, slot_h = 113, 113
    spacing = 16
    start_x = 55

    for i in range(7):
        cur_x = start_x + i * (slot_w + spacing)
        draw_rounded_rect(draw, [cur_x, slot_y, cur_x + slot_w, slot_y + slot_h], radius=16, fill=(15, 23, 42, 210), outline=(51, 65, 85, 180), width=1)

        if i < len(favorite_gifts):
            g = favorite_gifts[i]
            img_p = gift_image_path(g.key)
            if img_p and img_p.exists():
                try:
                    g_img = Image.open(img_p).convert("RGBA")
                    g_img.thumbnail((78, 78))
                    gx = cur_x + (slot_w - g_img.width) // 2
                    gy = slot_y + (slot_h - g_img.height) // 2
                    base_bg.paste(g_img, (gx, gy), g_img)
                except Exception as e:
                    log.warning("Ошибка рендера подарка в карточке клана: %s", e)
            else:
                clean_g_name = g.name.split('(')[0].strip()[:9]
                draw.text((cur_x + slot_w // 2, slot_y + slot_h // 2 - 8), clean_g_name, font=load_font(13, bold=True), fill=(255, 255, 255), anchor="mm")
                draw.text((cur_x + slot_w // 2, slot_y + slot_h - 22), f"{g.stars:,} Stars", font=load_font(11, bold=True), fill=(234, 179, 8), anchor="mm")
        else:
            cx, cy = cur_x + slot_w // 2, slot_y + slot_h // 2
            arm = 12
            thick = 3
            draw.line([(cx - arm, cy - arm), (cx + arm, cy + arm)], fill=(100, 116, 139, 120), width=thick)
            draw.line([(cx + arm, cy - arm), (cx - arm, cy + arm)], fill=(100, 116, 139, 120), width=thick)

    bio = io.BytesIO()
    base_bg.save(bio, "PNG")
    bio.name = "clan.png"
    bio.seek(0)
    return bio

# ---------------------------------------------------------------------------
# КЛАВИАТУРЫ
# ---------------------------------------------------------------------------

def main_menu_keyboard(user_id: int = 0) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("👤 Профиль", callback_data="nav_profile"),
            InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1"),
        ],
        [
            InlineKeyboardButton("🛒 NFT Маркет", callback_data="nav_market"),
            InlineKeyboardButton("🎰 Mystery Cases", callback_data="nav_cases_hub"),
        ],
        [
            InlineKeyboardButton("🛡 Кланы", callback_data="nav_clans_hub"),
            InlineKeyboardButton("🏆 ТОП 100", callback_data="nav_top_page:1"),
        ],
        [
            InlineKeyboardButton("🛍 Улучшения", callback_data="nav_shop"),
            InlineKeyboardButton("🎁 Бонус 24ч", callback_data="nav_bonus"),
        ],
        [
            InlineKeyboardButton("⚙️ Настройки", callback_data="nav_settings"),
            InlineKeyboardButton("ℹ️ Инфо", callback_data="nav_info"),
        ]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([InlineKeyboardButton("👑 Админ-Панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def quick_nav_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 Профиль", callback_data="nav_profile"),
            InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1"),
        ],
        [
            InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
        ]
    ])

def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Главное меню", callback_data="nav_main")]
    ])

# ---------------------------------------------------------------------------
# КЕЙСЫ
# ---------------------------------------------------------------------------

CASE_TIERS = {
    "tier1": {
        "name": "📦 Кейс 1",
        "price": 100,
        "pool": [g for g in GIFTS if g.stars <= 8000]
    },
    "tier2": {
        "name": "🔷 Кейс 2",
        "price": 500,
        "pool": [g for g in GIFTS if 200 <= g.stars <= 20000]
    },
    "tier3": {
        "name": "🟣 Кейс 3",
        "price": 2500,
        "pool": [g for g in GIFTS if g.stars >= 500]
    },
    "tier4": {
        "name": "👑 Кейс 4",
        "price": 10000,
        "pool": GIFTS
    }
}

# ---------------------------------------------------------------------------
# ПРОФИЛЬ ИГРОКА
# ---------------------------------------------------------------------------

async def show_profile_handler(update_or_query, target_user_id: int, context: ContextTypes.DEFAULT_TYPE, back_to_top_page: Optional[int] = None) -> None:
    current_viewer_id = (
        update_or_query.effective_user.id
        if hasattr(update_or_query, "effective_user") and update_or_query.effective_user
        else update_or_query.from_user.id
    )

    db_user = get_or_create_user(target_user_id, "", "")
    clean_name = normalize_telegram_name(db_user["first_name"] or db_user["username"] or "Игрок")

    avatar_bytes = None
    try:
        photos = await context.bot.get_user_profile_photos(target_user_id, limit=1)
        if photos.total_count > 0:
            file_id = photos.photos[0][-1].file_id
            tg_file = await context.bot.get_file(file_id)
            file_bytes_io = io.BytesIO()
            await tg_file.download_to_memory(file_bytes_io)
            avatar_bytes = file_bytes_io.getvalue()
    except Exception as e:
        log.warning("Аватар игрока %s недоступен: %s", target_user_id, e)

    fav_rows = [r for r in get_favorites(target_user_id) if r["gift_key"] in GIFTS_BY_KEY]
    rank = get_user_rank(target_user_id)
    lvl, cur_xp, req_xp, _ = calculate_xp_level_info(db_user["xp"])

    clan = get_user_clan(target_user_id)
    clan_tag = clan["tag"] if clan else None

    card_img_io = None
    try:
        card_img_io = await generate_profile_card_image(
            clean_name,
            db_user["id_num"],
            db_user["balance_stars"],
            db_user["xp"],
            rank,
            fav_rows,
            avatar_bytes=avatar_bytes,
            clan_tag=clan_tag,
            custom_bg_path=db_user["bg_image_path"]
        )
    except Exception as e:
        log.error("Ошибка при генерации карточки профиля: %s", e)

    clan_display = f"[{clean_html(clan_tag)}] {clean_html(clan['name'])}" if clan else "Отсутствует"
    display_title = f"[{clean_html(clan_tag)}] {clean_html(clean_name)}" if clan_tag else clean_html(clean_name)

    is_self = (current_viewer_id == target_user_id)

    caption = (
        f"👤 <b>Профиль игрока:</b> {display_title}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎖 Уровень: <b>{lvl} ({cur_xp:,}/{req_xp:,} XP)</b>\n"
        f"🛡 Клан: <b>{clan_display}</b>\n"
        f"🏆 Место в глобальном ТОПе: <b>#{rank}</b>\n"
        f"💰 Баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n"
        f"📦 Вместимость инвентаря: <b>{db_user['max_inventory']} слотов</b>\n"
        f"🎲 Выбито подарков: <b>{db_user['total_drops']}</b> шт.\n"
        f"🛍 Продано предметов: <b>{db_user['total_sold']}</b> шт.\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    buttons = []
    if is_self:
        buttons.append([
            InlineKeyboardButton("🖼 Сменить фон", callback_data="bg_change_start"),
            InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1")
        ])
        if db_user["bg_image_path"]:
            buttons.append([InlineKeyboardButton("🗑 Сбросить фон на стандартный", callback_data="bg_reset")])
        buttons.append([
            InlineKeyboardButton("🎰 Кейсы", callback_data="nav_cases_hub"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
        ])
    else:
        if back_to_top_page:
            buttons.append([InlineKeyboardButton("◀️ Назад в ТОП 100", callback_data=f"nav_top_page:{back_to_top_page}")])
        buttons.append([
            InlineKeyboardButton("🗂 Моя коллекция", callback_data="nav_collection_page:1"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
        ])

    kb = InlineKeyboardMarkup(buttons)

    if hasattr(update_or_query, "message") and update_or_query.message and update_or_query.message.photo:
        try: await update_or_query.message.delete()
        except: pass

    if card_img_io:
        try:
            await context.bot.send_photo(
                chat_id=current_viewer_id,
                photo=InputFile(card_img_io, filename="profile.png"),
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            return
        except Exception as e:
            log.warning("Не удалось отправить фото профиля: %s. Отправка текста.", e)

    await context.bot.send_message(
        chat_id=current_viewer_id,
        text=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )

# ---------------------------------------------------------------------------
# СМЕНА ФОНА ПРОФИЛЯ
# ---------------------------------------------------------------------------

async def bg_change_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    text = (
        "🖼 <b>Установка кастомного фона профиля</b>\n\n"
        "Отправьте любое изображение в этот чат (как фото).\n"
        "Оно будет <b>слегка затемнено и размыто</b> на заднем плане вашей карточки, "
        "чтобы текст оставался абсолютно читаемым без искажений. Новый фон увидят все игроки!\n\n"
        "<i>Для отмены отправьте /cancel или нажмите кнопку ниже.</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="bg_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_PROFILE_BG

async def bg_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте именно фото (картинку), либо напишите /cancel.")
        return WAIT_PROFILE_BG

    photo_file = await update.message.photo[-1].get_file()
    bg_file_path = BACKGROUNDS_DIR / f"bg_{user.id}.jpg"

    try:
        await photo_file.download_to_drive(custom_path=bg_file_path)
        set_user_background(user.id, str(bg_file_path))

        await update.message.reply_text(
            "🎉 <b>Фон профиля успешно сохранен и применен!</b>\n"
            "Ваша карточка обновлена.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 Посмотреть профиль", callback_data="nav_profile")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
            ])
        )
    except Exception as e:
        log.error("Ошибка загрузки фона: %s", e)
        await update.message.reply_text("❌ Ошибка при сохранении изображения. Попробуйте еще раз позже.")

    return ConversationHandler.END

async def bg_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Отменено.")
        await show_profile_handler(query, query.from_user.id, context)
    else:
        await update.message.reply_text("Отменено.", reply_markup=back_to_main_keyboard())
    return ConversationHandler.END

async def bg_reset_handler(query, user_id: int, context: ContextTypes.DEFAULT_TYPE):
    set_user_background(user_id, None)
    bg_file_path = BACKGROUNDS_DIR / f"bg_{user_id}.jpg"
    if bg_file_path.exists():
        try: bg_file_path.unlink()
        except: pass
    await query.answer("🗑 Фон сброшен на стандартный!", show_alert=True)
    await show_profile_handler(query, user_id, context)

# ---------------------------------------------------------------------------
# ПРОФИЛЬ КЛАНА (КАРТОЧКА, КАЗНА, УРОВЕНЬ, ИЗБРАННОЕ И ГЕРБ)
# ---------------------------------------------------------------------------

async def show_clan_profile_handler(update_or_query, clan_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Генерация и отображение графического профиля клана (как у игрока)."""
    current_viewer_id = (
        update_or_query.effective_user.id
        if hasattr(update_or_query, "effective_user") and update_or_query.effective_user
        else update_or_query.from_user.id
    )

    clan = get_clan_by_id(clan_id)
    if not clan:
        if hasattr(update_or_query, "answer"):
            await update_or_query.answer("Клан не найден.", show_alert=True)
        return

    # Проверка ежедневного начисления XP клану от казны
    awarded_xp = check_and_award_clan_daily_xp(clan_id)
    if awarded_xp:
        clan = get_clan_by_id(clan_id) # перечитываем с обновленным XP

    total_treasury, donated_bank, members = get_clan_treasury_and_members(clan_id)
    fav_gifts = get_clan_favorites(clan)

    clan_sys_id = clan["id_num"] if clan["id_num"] else clan["id"]
    lvl, cur_xp, req_xp, ratio, drop_bonus = calculate_clan_level_info(clan["xp"])

    is_owner = (clan["owner_id"] == current_viewer_id)
    user_clan = get_user_clan(current_viewer_id)
    is_member = (user_clan and user_clan["id"] == clan["id"])

    # Получаем никнейм создателя/владельца
    owner_user = get_or_create_user(clan["owner_id"], "", "")
    owner_name = normalize_telegram_name(owner_user["first_name"] or owner_user["username"] or "Создатель")

    # Рендер фото-карточки профиля клана
    clan_card_io = None
    try:
        clan_card_io = await generate_clan_card_image(
            clan["name"],
            clan["tag"],
            clan_sys_id,
            clan["xp"],
            total_treasury,
            len(members),
            clan["max_members"],
            fav_gifts,
            avatar_path=clan["avatar_path"]
        )
    except Exception as e:
        log.error("Ошибка при генерации карточки клана: %s", e)

    ctype_str = "Открытый (свободный вход)" if clan["type"] == "public" else ("Вход за звёзды" if clan["type"] == "stars" else "Закрытый (по заявкам)")
    fee_str = f"\n💰 Стоимость входа: <b>{clan['entry_fee']} ⭐</b>" if clan["type"] == "stars" else ""

    caption = (
        f"🛡 <b>Клан [{clan['tag']}] {clean_html(clan['name'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎖 Уровень клана: <b>{lvl} ({cur_xp:,}/{req_xp:,} XP)</b>\n"
        f"🎲 Клановый бонус к выигрышу: <b>+{drop_bonus}%</b>\n"
        f"👑 Создатель / Владелец: <b>{clean_html(owner_name)}</b>\n"
        f"👥 Состав: <b>{len(members)}/{clan['max_members']}</b> чел.\n"
        f"💰 <b>Общая казна всех участников:</b> <b>{total_treasury:,} ⭐</b> (~{total_treasury * STAR_RUB_RATE:,.0f} ₽)\n"
        f"🏦 Банк пожертвований: <b>{donated_bank:,} ⭐</b>\n"
        f"🔒 Тип входа: <b>{ctype_str}</b>{fee_str}\n"
        f"📝 Описание: <i>{clean_html(clan['description']) or 'Отсутствует'}</i>\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    buttons = [
        [InlineKeyboardButton("👥 Участники и казна каждого", callback_data=f"clan_members_detail:{clan_id}")],
    ]

    if is_member:
        buttons.append([
            InlineKeyboardButton("💰 Пополнить казну звёздами", callback_data=f"clan_donate_stars_start:{clan_id}"),
            InlineKeyboardButton("🎁 Пожертвовать подарок", callback_data=f"clan_donate_gift_menu:{clan_id}")
        ])

    if is_owner:
        upgrade_cost = get_clan_upgrade_cost(clan["max_members"])
        buttons.append([
            InlineKeyboardButton("🖼 Сменить герб клана", callback_data=f"clan_avatar_start:{clan_id}"),
            InlineKeyboardButton("⭐ Избранные подарки клана", callback_data=f"clan_fav_menu:{clan_id}")
        ])
        buttons.append([
            InlineKeyboardButton(f"⬆️ Улучшить места (+15 за {upgrade_cost:,}⭐)", callback_data=f"clan_upgrade:{clan_id}"),
            InlineKeyboardButton("📩 Заявки в клан", callback_data=f"clan_requests:{clan_id}")
        ])
        buttons.append([InlineKeyboardButton("🔥 Расформировать клан", callback_data=f"clan_delete_confirm:{clan_id}")])
    elif is_member:
        buttons.append([InlineKeyboardButton("🚪 Покинуть клан", callback_data="clan_leave:1")])
    elif not user_clan and len(members) < clan["max_members"]:
        if clan["type"] == "public":
            buttons.append([InlineKeyboardButton("🚪 Вступить в клан", callback_data=f"clan_join:{clan_id}")])
        elif clan["type"] == "stars":
            buttons.append([InlineKeyboardButton(f"⭐ Войти за {clan['entry_fee']} Stars", callback_data=f"clan_join_stars:{clan_id}")])
        elif clan["type"] == "private":
            buttons.append([InlineKeyboardButton("📩 Подать заявку в клан", callback_data=f"clan_apply:{clan_id}")])

    buttons.append([
        InlineKeyboardButton("📋 Список кланов", callback_data="clan_list:1"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
    ])

    kb = InlineKeyboardMarkup(buttons)

    if hasattr(update_or_query, "message") and update_or_query.message and update_or_query.message.photo:
        try: await update_or_query.message.delete()
        except: pass

    if clan_card_io:
        try:
            await context.bot.send_photo(
                chat_id=current_viewer_id,
                photo=InputFile(clan_card_io, filename="clan.png"),
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=kb
            )
            return
        except Exception as e:
            log.warning("Не удалось отправить фото карточки клана: %s", e)

    await context.bot.send_message(
        chat_id=current_viewer_id,
        text=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=kb
    )

async def show_clan_members_detail(query, clan_id: int):
    clan = get_clan_by_id(clan_id)
    if not clan:
        await query.answer("Клан не найден.")
        return

    total_treasury, donated_bank, members = get_clan_treasury_and_members(clan_id)

    lines = [
        f"👥 <b>Участники и казна клана [{clan['tag']}] {clean_html(clan['name'])}</b>",
        f"━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Общая казна всех участников:</b> <b>{total_treasury:,} ⭐</b>",
        f"🏦 <b>Банк пожертвований клана:</b> <b>{donated_bank:,} ⭐</b>",
        f"👥 <b>Всего участников:</b> <b>{len(members)}/{clan['max_members']}</b>",
        f"━━━━━━━━━━━━━━━━━━",
        f"<b>Баланс каждого участника:</b>\n"
    ]

    for idx, m in enumerate(members, start=1):
        is_owner = (m["user_id"] == clan["owner_id"])
        role_badge = "👑 Создатель" if is_owner else "Участник"
        mname = normalize_telegram_name(m["first_name"] or m["username"] or "Игрок")
        lines.append(f"{idx}. <b>{clean_html(mname)}</b> ({role_badge}) — <b>{m['balance_stars']:,} ⭐</b>")

    lines.append("\n━━━━━━━━━━━━━━━━━━")
    text = "\n".join(lines)

    buttons = []
    if clan["owner_id"] == query.from_user.id:
        for m in members:
            if m["user_id"] != clan["owner_id"]:
                mname = normalize_telegram_name(m["first_name"] or m["username"] or "Игрок")
                buttons.append([InlineKeyboardButton(f"❌ Исключить {mname[:10]}", callback_data=f"clan_kick:{m['user_id']}")])

    buttons.append([InlineKeyboardButton("⬅️ Назад в профиль клана", callback_data=f"clan_info:{clan_id}")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# АВАТАРКА КЛАНА (FSM)
# ---------------------------------------------------------------------------

async def clan_avatar_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    clan_id = int(query.data.split(":")[1])
    clan = get_clan_by_id(clan_id)

    if not clan or clan["owner_id"] != query.from_user.id:
        await query.answer("❌ Только создатель клана может менять герб!", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    context.user_data["clan_avatar_clan_id"] = clan_id

    text = (
        "🖼 <b>Установка герба (аватарки) клана</b>\n\n"
        "Отправьте изображение в этот чат (как фото).\n"
        "Оно будет установлено как официальный герб вашего клана и будет отображаться на карточке клана!\n\n"
        "<i>Если аватарка не установлена, бот генерирует красивый герб автоматически.</i>\n\n"
        "Отправьте /cancel для отмены."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="clan_avatar_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_CLAN_AVATAR

async def clan_avatar_photo_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте именно фото или /cancel.")
        return WAIT_CLAN_AVATAR

    clan_id = context.user_data.get("clan_avatar_clan_id")
    if not clan_id:
        await update.message.reply_text("Ошибка сессии создания аватарки.")
        return ConversationHandler.END

    photo_file = await update.message.photo[-1].get_file()
    av_path = CLAN_AVATARS_DIR / f"clan_{clan_id}.jpg"

    try:
        await photo_file.download_to_drive(custom_path=av_path)
        set_clan_avatar(clan_id, str(av_path))

        await update.message.reply_text(
            "🎉 <b>Герб клана успешно установлен!</b>\nОн уже отображается на карточке профиля вашего клана.",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛡 В профиль клана", callback_data=f"clan_info:{clan_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
            ])
        )
    except Exception as e:
        log.error("Ошибка сохранения герба клана: %s", e)
        await update.message.reply_text("❌ Ошибка при сохранении герба. Попробуйте еще раз.")

    return ConversationHandler.END

async def clan_avatar_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Отменено.")
        clan_id = context.user_data.get("clan_avatar_clan_id")
        if clan_id:
            await show_clan_profile_handler(query, clan_id, context)
    else:
        await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# ПОПОЛНЕНИЕ КАЗНЫ КЛАНА ЗВЕЗДАМИ (FSM)
# ---------------------------------------------------------------------------

async def clan_donate_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    clan_id = int(query.data.split(":")[1])
    await query.answer()

    context.user_data["donate_clan_id"] = clan_id
    text = (
        "💰 <b>Пополнение казны клана звёздами</b>\n\n"
        "Внесение Stars в казну клана прокачивает его уровень и увеличивает бонус к выигрышу!\n"
        "<i>Курс: 1,000,000 ⭐ даёт клану ~800 XP.</i>\n\n"
        "Введите количество Stars (⭐) для внесения в банк клана:"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="clan_donate_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_CLAN_DONATE_STARS

async def clan_donate_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ Введите положительное число звёзд:")
        return WAIT_CLAN_DONATE_STARS

    amount = int(text)
    clan_id = context.user_data.get("donate_clan_id")
    user = update.effective_user

    success, xp_awarded = donate_stars_to_clan(user.id, clan_id, amount)
    if not success:
        await update.message.reply_text("❌ У вас недостаточно Stars на балансе!")
        return ConversationHandler.END

    clan = get_clan_by_id(clan_id)
    lvl, cur_xp, req_xp, _, bonus = calculate_clan_level_info(clan["xp"])

    await update.message.reply_text(
        f"🎉 <b>Вы успешно внесли {amount:,} ⭐ в казну клана!</b>\n\n"
        f"• Клан получил: <b>+{xp_awarded:,} XP</b>!\n"
        f"• Текущий уровень клана: <b>{lvl}</b> ({cur_xp:,}/{req_xp:,} XP)\n"
        f"• Бонус клана: <b>+{bonus}%</b> к победе!",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡 В профиль клана", callback_data=f"clan_info:{clan_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
        ])
    )
    return ConversationHandler.END

async def clan_donate_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Отменено.")
        clan_id = context.user_data.get("donate_clan_id")
        if clan_id:
            await show_clan_profile_handler(query, clan_id, context)
    else:
        await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# ИЗБРАННЫЕ ПОДАРКИ КЛАНА И ПОЖЕРТВОВАНИЕ ПОДАРКОВ
# ---------------------------------------------------------------------------

async def show_clan_favorites_menu(query, clan_id: int):
    clan = get_clan_by_id(clan_id)
    if not clan or clan["owner_id"] != query.from_user.id:
        await query.answer("Только создатель клана может настраивать избранное!", show_alert=True)
        return

    favs = get_clan_favorites(clan)
    text = (
        f"⭐ <b>Настройка Избранных подарков клана ({len(favs)}/7)</b>\n"
        f"Они отображаются на официальной карточке профиля клана!\n\n"
        f"Нажмите на подарок ниже, чтобы добавить или убрать его из избранного клана:"
    )

    buttons = []
    # Показываем список всех доступных подарков для выбора
    for g in GIFTS[:18]:
        is_in = any(f.key == g.key for f in favs)
        badge = "✅ " if is_in else "➕ "
        buttons.append([InlineKeyboardButton(f"{badge}{g.name} ({g.stars:,}⭐)", callback_data=f"clan_toggle_fav:{clan_id}:{g.key}")])

    buttons.append([InlineKeyboardButton("⬅️ В профиль клана", callback_data=f"clan_info:{clan_id}")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_clan_donate_gift_menu(query, clan_id: int, user_id: int):
    items = [i for i in get_user_collection(user_id) if not i["is_listed"]]
    if not items:
        await query.answer("У вас нет доступных предметов в коллекции для пожертвования!", show_alert=True)
        return

    text = (
        "🎁 <b>Пожертвование подарка в клан</b>\n\n"
        "Пожертвованный подарок приносит клану опыт (XP) в размере ~800 XP за 1,000,000 ⭐ стоимости предмета!\n"
        "Выберите предмет из вашей коллекции для передачи клану:"
    )

    buttons = []
    for item in items[:12]:
        g = GIFTS_BY_KEY.get(item["gift_key"])
        if not g: continue
        val = item["estimated_stars"] if item["is_upgraded"] and item["estimated_stars"] else g.stars
        label = f"✨ Plush Pepe ({item['model_name']})" if item["is_upgraded"] else g.name
        buttons.append([InlineKeyboardButton(f"🎁 {label} ({val:,}⭐)", callback_data=f"clan_donate_gift_do:{clan_id}:{item['id']}")])

    buttons.append([InlineKeyboardButton("⬅️ В профиль клана", callback_data=f"clan_info:{clan_id}")])
    kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def execute_clan_donate_gift(query, clan_id: int, item_id: int, user_id: int):
    item = get_collection_item(item_id)
    if not item or item["user_id"] != user_id:
        await query.answer("Предмет не найден.")
        return
    if item["is_listed"]:
        await query.answer("Предмет выставлен на маркет!", show_alert=True)
        return

    g = GIFTS_BY_KEY.get(item["gift_key"])
    if not g:
        await query.answer("Ошибка подарка.")
        return

    val = item["estimated_stars"] if item["is_upgraded"] and item["estimated_stars"] else g.stars

    # Удаляем из коллекции игрока
    remove_from_collection(item_id, user_id)

    # Начисляем опыт клану и добавляем в банк
    xp_earned = max(1, int(val * 0.0008))
    conn = db_connect()
    try:
        conn.execute("UPDATE clans SET donated_stars=donated_stars+?, xp=xp+? WHERE id=?", (val, xp_earned, clan_id))
        conn.commit()
    finally:
        conn.close()

    await query.answer(f"🎉 Подарок {g.name} пожертвован в клан! (+{xp_earned} XP клану)", show_alert=True)
    await show_clan_profile_handler(query, clan_id, query._bot)

# ---------------------------------------------------------------------------
# РАЗДЕЛ "ИНФО"
# ---------------------------------------------------------------------------

async def show_info_page(query_or_update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_info = await context.bot.get_me()
    bot_user = bot_info.username or "Bot"
    add_group_url = f"https://t.me/{bot_user}?startgroup=true"

    text = (
        "ℹ️ <b>Справочный центр New NFT Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Добро пожаловать в официальную информационную панель бота!\n\n"
        "📌 <b>Основные возможности:</b>\n"
        "• Выбивание редких Telegram Gifts в любых чатах\n"
        "• Торговый NFT Marketplace и Mystery Cases\n"
        "• Кланы с геральдическими гербами, уровнями и казной\n"
        "• Персонализация профилей с кастомными фонами\n"
        f"• Служба поддержки: {SUPPORT_HANDLE}\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Выберите интересующий подраздел:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 Подключение бота к группе и права", callback_data="info_group_guide")],
        [InlineKeyboardButton("📜 Политика конфиденциальности", callback_data="info_privacy")],
        [InlineKeyboardButton("📖 Правила игры и клановые бонусы", callback_data="info_rules")],
        [InlineKeyboardButton("💬 Написать в поддержку", url=SUPPORT_URL)],
        [InlineKeyboardButton("➕ Добавить бота в группу", url=add_group_url)],
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

async def show_group_guide(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_info = await context.bot.get_me()
    bot_user = bot_info.username or "Bot"
    add_group_url = f"https://t.me/{bot_user}?startgroup=true"

    text = (
        "🤖 <b>Подключение бота к вашей группе</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Чтобы участники могли выбивать подарки прямо в чате:\n\n"
        "1️⃣ Нажмите кнопку <b>«➕ Добавить в группу»</b> ниже.\n"
        "2️⃣ Выберите нужный суперчат.\n"
        "3️⃣ <b>Необходимые разрешения для бота:</b>\n"
        "   • <b>Чтение сообщений (Read Messages)</b> — распознавать слово <code>NFT</code>\n"
        "   • <b>Отправка сообщений (Send Messages)</b> — отправлять результаты\n"
        "   • <b>Прикрепление фото/медиа (Send Photos)</b> — карточки подарков и профилей\n"
        "   • <b>Инлайн-кнопки</b> — действия «Сохранить» / «Продать»\n"
        "   ⭐️ <i>Рекомендуется дать права администратора для быстрой доставки ответов.</i>\n\n"
        "4️⃣ После добавления любой участник пишет слово <code>NFT</code> раз в час и получает подарки!"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить бота в группу", url=add_group_url)],
        [InlineKeyboardButton("⬅️ Назад в Инфо", callback_data="nav_info")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_privacy_policy(query) -> None:
    text = (
        "📜 <b>Политика конфиденциальности и безопасность данных</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "1. <b>Собираемые данные:</b>\n"
        "Бот сохраняет исключительно ваш публичный Telegram ID, никнейм (@username) и имя (first_name), "
        "а также игровые показатели (коллекцию подарков, баланс Stars, опыт, клановое членство).\n\n"
        "2. <b>Конфиденциальность:</b>\n"
        "В разделе «⚙️ Настройки» вы в любой момент можете активировать:\n"
        "• <b>Скрытие из ТОП-100</b> — аккаунт не отображается в общих списках лидеров.\n"
        "• <b>Скрытие коллекции</b> — другие игроки не смогут просматривать ваши предметы.\n\n"
        "3. <b>Безопасность:</b>\n"
        "Данные никогда не передаются сторонним сервисам."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в Инфо", callback_data="nav_info")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_rules_page(query) -> None:
    text = (
        "📖 <b>Правила игры и клановые механики</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "• <b>Команда в группах:</b> Напишите слово <code>NFT</code> (раз в 1 час). Шанс дропа — <b>90%</b>.\n"
        "• <b>Прокачка клана:</b>\n"
        "  - 0 уровень даёт <b>+1%</b> к выигрышу дорогих подарков.\n"
        "  - 100 уровень даёт <b>+45%</b> к выигрышу!\n"
        "  - Переход на 1 уровень требует <b>10,000 XP</b>.\n"
        "  - Ежедневно каждые 24 часа начисляется XP за казну от 5,000,000 ⭐.\n"
        "  - Пополнение казны приносит ~800 XP за каждый 1,000,000 ⭐.\n"
        f"• <b>Поддержка:</b> {SUPPORT_HANDLE}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в Инфо", callback_data="nav_info")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# РАЗДЕЛ "NFT МАРКЕТ" (ПОЛНОЦЕННАЯ P2P БИРЖА С КОМИССИЕЙ 15%)
# ---------------------------------------------------------------------------

async def show_market_hub(update_or_query) -> None:
    banner_io = await generate_market_banner()
    active_cnt, deals_cnt = get_market_stats()

    caption = (
        "🛒 <b>NFT Marketplace (Торговая площадка)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Официальная P2P биржа улучшенных подарков Telegram между игроками.\n\n"
        f"• Активных лотов на витрине: <b>{active_cnt:,}</b>\n"
        f"• Завершённых сделок: <b>{deals_cnt:,}</b>\n"
        f"• Диапазон цен: <b>1,000 — 100,000,000,000 ⭐</b>\n"
        f"• Комиссия рынка: <b>15%</b> (списывается при продаже)\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Выставляйте свои улучшенные Plush Pepe или покупайте редкие экземпляры у других игроков:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Выставить подарок (Оффер)", callback_data="market_create_offer")],
        [
            InlineKeyboardButton("💰 Фильтр: По стоимости", callback_data="market_filter_price_menu"),
            InlineKeyboardButton("🧸 Фильтр: По моделям/фонам", callback_data="market_filter_model_menu"),
        ],
        [InlineKeyboardButton(f"📋 Все лоты ({active_cnt})", callback_data="market_view:all:all:1")],
        [
            InlineKeyboardButton("🔍 Мои лоты", callback_data="market_my_offers"),
            InlineKeyboardButton("📊 История сделок", callback_data="market_history"),
        ],
        [
            InlineKeyboardButton("✨ Улучшения", callback_data="nav_shop"),
            InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main"),
        ]
    ])

    if hasattr(update_or_query, "message") and update_or_query.message:
        if update_or_query.message.photo:
            try: await update_or_query.message.delete()
            except: pass
        await update_or_query.message.reply_photo(
            photo=InputFile(banner_io, filename="market.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )
    else:
        if hasattr(update_or_query, "photo") and update_or_query.photo:
            try: await update_or_query.delete()
            except: pass
        await update_or_query.reply_photo(
            photo=InputFile(banner_io, filename="market.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb
        )

async def show_market_filter_price_menu(query):
    text = (
        "💰 <b>Фильтр маркета по стоимости:</b>\n"
        "Выберите интересующий ценовой диапазон:"
    )
    buttons = []
    for pkey, (ptitle, _, _) in MARKET_PRICE_TIERS.items():
        buttons.append([InlineKeyboardButton(ptitle, callback_data=f"market_view:price:{pkey}:1")])
    buttons.append([InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")])
    kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_market_filter_model_menu(query):
    text = (
        "🧸 <b>Фильтр маркета по моделям и редкости:</b>\n"
        "Выберите категорию для поиска лотов:"
    )
    buttons = [
        [InlineKeyboardButton("🌑 Редкие тёмные и золотые фоны (≤0.9%)", callback_data="market_view:model:rare_dark:1")]
    ]
    for mkey, mtitle in MODEL_GROUPS.items():
        buttons.append([InlineKeyboardButton(mtitle, callback_data=f"market_view:model:{mkey}:1")])
    buttons.append([InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")])
    kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_market_view_page(query, ftype: str, fkey: str, page: int = 1):
    rows, total_pages, total_cnt = get_market_listings_filtered(ftype, fkey, page, page_size=8)
    if ftype == "price":
        filter_name = MARKET_PRICE_TIERS.get(fkey, ("По цене", 0, 0))[0]
    elif ftype == "model":
        if fkey == "rare_dark":
            filter_name = "Редкие тёмные и золотые фоны"
        else:
            filter_name = MODEL_GROUPS.get(fkey, "По модели")
    else:
        filter_name = "Все лоты"

    lines = [
        f"📋 <b>Маркет: {filter_name}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"Найдено активных лотов: <b>{total_cnt}</b> (Стр. {page}/{total_pages})\n",
    ]
    buttons = []

    if not rows:
        lines.append("<i>Активных лотов по выбранному фильтру пока нет.</i>")
    else:
        lines.append("Нажмите на лот ниже, чтобы открыть картинку, редкости и купить:")
        for lot in rows:
            lines.append(
                f"• 🐸 <b>{clean_html(lot['model_name'])}</b> | "
                f"🎨 {clean_html(lot['bg_name'])} ({lot['bg_rarity']:.2f}%) — <b>{lot['price_stars']:,} ⭐</b>"
            )
            btn_lbl = f"🐸 {lot['model_name'][:14]} • {lot['bg_name'][:12]} ({lot['bg_rarity']:.2f}%) — {lot['price_stars']:,}⭐"
            buttons.append([InlineKeyboardButton(btn_lbl, callback_data=f"market_lot:{lot['id']}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"market_view:{ftype}:{fkey}:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"market_view:{ftype}:{fkey}:{page+1}"))
    if total_cnt > 0:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("➕ Выставить подарок", callback_data="market_create_offer")])
    buttons.append([
        InlineKeyboardButton("💰 По стоимости", callback_data="market_filter_price_menu"),
        InlineKeyboardButton("🧸 По моделям", callback_data="market_filter_model_menu"),
    ])
    buttons.append([InlineKeyboardButton("⬅️ В витрину маркета", callback_data="nav_market")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")])

    kb = InlineKeyboardMarkup(buttons)
    text = "\n".join(lines)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_market_lot_detail(query, listing_id: int, viewer_id: int):
    lot = get_market_listing(listing_id)
    if not lot or lot["status"] != "active":
        await query.answer("❌ Этот лот уже продан или снят с продажи.", show_alert=True)
        await show_market_view_page(query, "all", "all", 1)
        return

    seller = get_or_create_user(lot["seller_id"], "", "")
    seller_name = normalize_telegram_name(seller["first_name"] or seller["username"] or "Игрок")
    seller_sys_id = seller["id_num"] if seller["id_num"] else lot["seller_id"]

    fee_stars = int(round(lot["price_stars"] * MARKET_FEE_RATE))
    seller_payout = max(0, lot["price_stars"] - fee_stars)
    bg_obj = next((b for b in PLUSHPEPE_BACKDROPS if b.name == lot["bg_name"]), None)
    rarity_lbl = bg_obj.rarity_label if bg_obj else ("Ультра-редкий" if lot["bg_rarity"] <= 0.45 else "Редкий")

    caption = (
        f"✨ <b>Улучшенный Plush Pepe #{lot['collection_id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🧸 Модель: <b>{clean_html(lot['model_name'])}</b> (редкость: <b>{lot['model_rarity']:.1f}%</b>)\n"
        f"🎨 Фон: <b>{clean_html(lot['bg_name'])}</b> — {clean_html(lot['bg_palette'])}\n"
        f"💎 Шанс фона: <b>{lot['bg_rarity']:.2f}%</b> ({rarity_lbl})\n"
        f"📊 Оценочная стоимость: <b>{fmt_stars_rub(lot['estimated_stars'])}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Продавец: <b>{clean_html(seller_name)}</b> (ID #{seller_sys_id})\n"
        f"💰 <b>Цена покупки: {fmt_stars_rub(lot['price_stars'])}</b>\n"
        f"🏦 <i>Комиссия маркета 15% (-{fee_stars:,} ⭐) • Продавец получит {seller_payout:,} ⭐</i>"
    )

    buttons = []
    if lot["seller_id"] == viewer_id:
        buttons.append([InlineKeyboardButton("❌ Снять лот с продажи", callback_data=f"market_cancel:{lot['id']}")])
    else:
        buttons.append([InlineKeyboardButton(f"✅ Купить за {lot['price_stars']:,} ⭐", callback_data=f"market_buy:{lot['id']}")])
    buttons.append([InlineKeyboardButton("⬅️ К списку лотов", callback_data="market_view:all:all:1")])
    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")])
    kb = InlineKeyboardMarkup(buttons)

    try:
        card_io = await generate_upgraded_gift_image(
            lot["model_file"],
            lot["model_name"],
            lot["bg_name"],
            lot["bg_center_hex"],
            lot["bg_edge_hex"],
            lot["bg_rarity"],
            lot["collection_id"],
        )
        if query.message.photo:
            try: await query.message.delete()
            except: pass
        await query.message.reply_photo(
            photo=InputFile(card_io, filename=f"lot_{lot['id']}.png"),
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return
    except Exception as e:
        log.warning("Ошибка генерации фото лота: %s", e)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(caption, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_market_create_offer_list(query, user_id: int):
    items = [
        i for i in get_user_collection(user_id)
        if i["is_upgraded"] and not i["is_listed"]
    ]
    if not items:
        text = (
            "➕ <b>Выставление подарка на Маркет</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "У вас пока нет свободных <b>улучшенных подарков</b> для продажи.\n\n"
            "Чтобы выставить подарок на маркет, сначала выбейте <b>Plush Pepe</b> (в чате по слову <code>NFT</code> или в кейсах) "
            "и улучшите его за <b>150,000 ⭐</b> в разделе <b>«🛍 Улучшения»</b>!"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✨ Перейти в Улучшения", callback_data="nav_shop")],
            [InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")],
        ])
    else:
        text = (
            "➕ <b>Выберите улучшенный подарок для выставления на Маркет:</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "• Можно указать любую цену от <b>1,000 ⭐</b> до <b>100,000,000,000 ⭐</b>\n"
            "• При покупке взимается комиссия рынка <b>15%</b>."
        )
        buttons = []
        for item in items[:15]:
            buttons.append([
                InlineKeyboardButton(
                    f"✨ #{item['id']} {item['model_name']} | {item['bg_name']} ({item['estimated_stars']:,}⭐)",
                    callback_data=f"market_sell_start:{item['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")])
        kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def market_sell_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if query.message.chat.type != "private":
        await query.answer("⚠️ Откройте личные сообщения с ботом для торговли на маркете!", show_alert=True)
        return ConversationHandler.END

    item_id = int(query.data.split(":")[1])
    item = get_collection_item(item_id)
    if not item or item["user_id"] != user.id:
        await query.answer("❌ Подарок не найден.", show_alert=True)
        return ConversationHandler.END
    if not item["is_upgraded"]:
        await query.answer("❌ Выставлять можно только улучшенные подарки!", show_alert=True)
        return ConversationHandler.END
    if item["is_listed"]:
        await query.answer("⚠️ Этот подарок уже выставлен на маркете!", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    context.user_data["market_sell_item_id"] = item_id

    text = (
        f"💰 <b>Выставление лота на NFT Маркет</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• Подарок: <b>Plush Pepe #{item['id']}</b>\n"
        f"• Модель: <b>{clean_html(item['model_name'])}</b>\n"
        f"• Фон: <b>{clean_html(item['bg_name'])}</b> ({item['bg_rarity']:.2f}%)\n"
        f"• Примерная цена: <b>{item['estimated_stars']:,} ⭐</b>\n\n"
        f"Введите желаемую цену продажи в звёздах (от <b>1,000</b> до <b>100,000,000,000</b> ⭐):\n"
        f"<i>Напоминание: при покупке удерживается комиссия 15%.</i>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="market_offer_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_MARKET_OFFER_PRICE

async def market_offer_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    raw = re.sub(r"[\s,_]", "", update.message.text.strip())
    if not raw.isdigit():
        await update.message.reply_text(
            f"❌ Введите целое число звёзд от {MARKET_MIN_PRICE:,} до {MARKET_MAX_PRICE:,}:"
        )
        return WAIT_MARKET_OFFER_PRICE

    price = int(raw)
    if price < MARKET_MIN_PRICE or price > MARKET_MAX_PRICE:
        await update.message.reply_text(
            f"❌ Цена должна быть от <b>{MARKET_MIN_PRICE:,}</b> до <b>{MARKET_MAX_PRICE:,} ⭐</b>!",
            parse_mode=ParseMode.HTML,
        )
        return WAIT_MARKET_OFFER_PRICE

    item_id = context.user_data.get("market_sell_item_id")
    if not item_id:
        await update.message.reply_text("❌ Сессия истекла. Попробуйте снова.", reply_markup=quick_nav_keyboard())
        return ConversationHandler.END

    ok, listing_id, err = create_market_listing(item_id, user.id, price)
    if not ok:
        await update.message.reply_text(f"❌ {err}", reply_markup=quick_nav_keyboard())
        return ConversationHandler.END

    fee_stars = int(round(price * MARKET_FEE_RATE))
    payout = max(0, price - fee_stars)
    await update.message.reply_text(
        f"✅ <b>Подарок успешно выставлен на NFT Маркет!</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• Номер лота: <b>#{listing_id}</b>\n"
        f"• Цена: <b>{fmt_stars_rub(price)}</b>\n"
        f"• Комиссия 15%: <b>-{fee_stars:,} ⭐</b>\n"
        f"• Вы получите при продаже: <b>{payout:,} ⭐</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Открыть мой лот", callback_data=f"market_lot:{listing_id}")],
            [InlineKeyboardButton("🛒 В маркет", callback_data="nav_market")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
        ]),
    )
    return ConversationHandler.END

async def market_offer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Отменено.")
        await show_market_hub(query)
    else:
        await update.message.reply_text("Выставление лота отменено.", reply_markup=back_to_main_keyboard())
    return ConversationHandler.END

async def show_market_my_offers(query, user_id: int):
    lots = get_user_market_listings(user_id)
    if not lots:
        text = "🔍 <b>Мои лоты на маркете</b>\n\nУ вас пока нет активных лотов."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Выставить подарок", callback_data="market_create_offer")],
            [InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")],
        ])
    else:
        lines = [f"🔍 <b>Ваши активные лоты ({len(lots)}):</b>\n━━━━━━━━━━━━━━━━━━"]
        buttons = []
        for lot in lots:
            lines.append(
                f"• Лот #{lot['id']}: 🐸 <b>{clean_html(lot['model_name'])}</b> | "
                f"{clean_html(lot['bg_name'])} — <b>{lot['price_stars']:,} ⭐</b>"
            )
            buttons.append([
                InlineKeyboardButton(
                    f"Лот #{lot['id']} • {lot['model_name']} ({lot['price_stars']:,}⭐)",
                    callback_data=f"market_lot:{lot['id']}",
                )
            ])
        buttons.append([InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")])
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_market_history_page(query, user_id: int):
    rows = get_market_history_rows(user_id, limit=12)
    if not rows:
        text = "📊 <b>История сделок</b>\n\nУ вас пока нет завершённых покупок или продаж на маркете."
    else:
        lines = ["📊 <b>Ваши последние сделки на маркете:</b>\n━━━━━━━━━━━━━━━━━━"]
        for r in rows:
            dt = datetime.datetime.fromtimestamp(r["sold_ts"]).strftime("%d.%m %H:%M")
            if r["seller_id"] == user_id:
                lines.append(
                    f"🟢 <b>Продажа</b> ({dt}): {clean_html(r['model_name'])} [{clean_html(r['bg_name'])}]\n"
                    f"   Цена: {r['price_stars']:,} ⭐ | Комиссия 15%: -{r['fee_stars']:,} ⭐ | Итог: <b>+{r['seller_payout']:,} ⭐</b>"
                )
            else:
                lines.append(
                    f"🔵 <b>Покупка</b> ({dt}): {clean_html(r['model_name'])} [{clean_html(r['bg_name'])}]\n"
                    f"   Оплачено: <b>-{r['price_stars']:,} ⭐</b>"
                )
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад в маркет", callback_data="nav_market")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# АДМИН-ПАНЕЛЬ
# ---------------------------------------------------------------------------

async def show_admin_panel(query) -> None:
    conn = db_connect()
    try:
        total_users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        total_banned = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_banned=1").fetchone()["cnt"]
        total_collection_gifts = conn.execute("SELECT COUNT(*) as cnt FROM collection").fetchone()["cnt"]
        total_sold = conn.execute("SELECT SUM(total_sold) as s FROM users").fetchone()["s"] or 0
        total_drops = conn.execute("SELECT SUM(total_drops) as s FROM users").fetchone()["s"] or 0
        total_stars_capital = conn.execute("SELECT SUM(balance_stars) as s FROM users").fetchone()["s"] or 0
        total_clans = conn.execute("SELECT COUNT(*) as cnt FROM clans").fetchone()["cnt"]
    finally:
        conn.close()

    text = (
        "👑 <b>Панель управления администратора</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"👥 Зарегистрировано игроков: <b>{total_users:,}</b>\n"
        f"⛔️ Заблокировано игроков: <b>{total_banned:,}</b>\n"
        f"🛡 Создано кланов: <b>{total_clans:,}</b>\n"
        f"💰 Совокупный баланс игроков: <b>{total_stars_capital:,} ⭐</b>\n"
        f"🎁 Подарков в коллекциях: <b>{total_collection_gifts:,}</b>\n"
        f"🎰 Всего выбито подарков: <b>{total_drops:,}</b>\n"
        f"🛍 Продано предметов: <b>{total_sold:,}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Выберите действие:"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Выдать Звёзды игроку", callback_data="admin_give_stars_start")],
        [InlineKeyboardButton("🎁 Выдать NFT-подарок (фильтры)", callback_data="admin_give_nft_start")],
        [
            InlineKeyboardButton("🔨 Забанить игрока", callback_data="admin_ban_start"),
            InlineKeyboardButton("🔓 Разбанить игрока", callback_data="admin_unban_start"),
        ],
        [InlineKeyboardButton("☁️ Firebase Облако (base.db)", callback_data="admin_firebase_menu")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_admin_firebase_menu(query_or_msg) -> None:
    has_err = bool(firebase_manager.last_error) or ("Ошибка" in firebase_manager.last_sync_status)
    if not FIREBASE_ADMIN_AVAILABLE:
        status_icon = "⚠️"
        status_msg = "Библиотека firebase-admin не найдена (pip install firebase-admin)"
    elif has_err:
        status_icon = "🔴"
        status_msg = "Ошибка авторизации / ключа Firebase"
    elif firebase_manager.initialized:
        status_icon = "🟢"
        status_msg = "Подключено к Cloud Firestore (100% бесплатно)"
    else:
        status_icon = "🟡"
        status_msg = "SDK доступен (готов к синхронизации)"

    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0
    if firebase_manager.last_sync_ts > 0:
        diff = int(time.time() - firebase_manager.last_sync_ts)
        ago_str = f"{diff} сек. назад"
    else:
        ago_str = "еще не производилась"

    text = (
        "☁️ <b>Управление облачной базой Firebase Firestore</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"• Проект: <b>{clean_html(firebase_manager.project_id)}</b>\n"
        f"• Коллекция: <code>{clean_html(firebase_manager.collection_name)}</code>\n"
        f"• Документ: <code>{clean_html(firebase_manager.document_name)}</code>\n"
        f"• Статус: {status_icon} <b>{clean_html(status_msg)}</b>\n"
        f"• Локальная база: <b>{db_size:,} байт</b>\n"
        f"• Синхронизация: <b>{clean_html(firebase_manager.last_sync_status)}</b> ({ago_str})\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>Защита от очистки базы (Anti-Wipe):</b>\n"
        "Бот сначала скачивает сохраненную базу из Firestore при старте на bot host.ru. "
        "Пустая база никогда не затирает облачные данные игроков и кланов!\n"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Выгрузить в облако сейчас", callback_data="admin_firebase_sync")],
        [InlineKeyboardButton("📥 Восстановить из облака", callback_data="admin_firebase_restore")],
        [InlineKeyboardButton("🔑 Загрузить ключ Firebase (.json)", callback_data="admin_firebase_key_start")],
        [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")],
    ])

    if hasattr(query_or_msg, "message") and query_or_msg.message:
        if query_or_msg.message.photo:
            await query_or_msg.message.delete()
            await query_or_msg.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query_or_msg.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query_or_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def admin_firebase_key_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    text = (
        "🔑 <b>Обновление сервисного ключа Firebase (.json)</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Если возникает ошибка <code>Invalid JWT Signature</code>, значит старый ключ был отозван.\n\n"
        "1. Откройте Firebase Console → Настройки проекта → <b>Сервисные аккаунты</b>.\n"
        "2. Нажмите <b>Создать новый закрытый ключ</b> (скачается файл <code>.json</code>).\n"
        "3. Отправьте этот <b>.json файл</b> сюда (или вставьте его содержимое текстом)."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")]])
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_ADMIN_FIREBASE_KEY

async def admin_firebase_key_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END

    raw_json_str = ""
    if update.message.document:
        doc_file = await update.message.document.get_file()
        bio = io.BytesIO()
        await doc_file.download_to_memory(bio)
        raw_json_str = bio.getvalue().decode("utf-8", errors="replace")
    elif update.message.text:
        raw_json_str = update.message.text.strip()

    try:
        cred_dict = json.loads(raw_json_str)
        if not isinstance(cred_dict, dict) or "private_key" not in cred_dict or "client_email" not in cred_dict:
            raise ValueError("Нет полей private_key / client_email")
    except Exception as e:
        await update.message.reply_text(f"❌ Некорректный JSON-ключ ({clean_html(str(e))}). Отправьте правильный файл .json из Firebase Console:")
        return WAIT_ADMIN_FIREBASE_KEY

    key_path = BASE_DIR / "firebase-service-account.json"
    key_path.write_text(json.dumps(cred_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = firebase_manager.reinit()
    if ok:
        restored = firebase_manager.download_db_on_startup()
        if restored:
            db_init()
            msg = "✅ Ключ сохранён! Подключение к Cloud Firestore успешно, база восстановлена из облака без потерь."
        elif firebase_manager._cloud_doc_missing:
            msg = "✅ Ключ сохранён! Подключение к Cloud Firestore успешно (в облаке пока нет сохранённой базы)."
        else:
            msg = f"⚠️ Ключ сохранён, но при проверке облака возникла ошибка: {clean_html(firebase_manager.last_sync_status)}"
    else:
        msg = f"❌ Ключ сохранён, но подключиться не удалось: {clean_html(firebase_manager.last_sync_status)}"

    await update.message.reply_text(
        msg,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("☁️ Меню Firebase", callback_data="admin_firebase_menu")],
            [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")],
        ]),
    )
    return ConversationHandler.END

# --- БАН ИГРОКА (FSM) ---

async def admin_ban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    text = "🔨 <b>Блокировка игрока</b>\n\nВведите Telegram ID или @username нарушителя:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_ADMIN_BAN_USER

async def admin_ban_user_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден в базе данных. Попробуйте снова:")
        return WAIT_ADMIN_BAN_USER

    if target["user_id"] in ADMIN_IDS:
        await update.message.reply_text("❌ Нельзя заблокировать администратора!")
        return ConversationHandler.END

    context.user_data["ban_target_id"] = target["user_id"]
    tname = normalize_telegram_name(target["first_name"] or target["username"] or "Игрок")
    await update.message.reply_text(
        f"✅ Игрок найден: <b>{clean_html(tname)}</b> (ID: <code>{target['user_id']}</code>).\n\n"
        f"Введите срок блокировки в часах (например, <code>24</code>, <code>72</code>, <code>720</code>):",
        parse_mode=ParseMode.HTML
    )
    return WAIT_ADMIN_BAN_HOURS

async def admin_ban_hours_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hours_str = update.message.text.strip()
    if not hours_str.isdigit() or int(hours_str) <= 0:
        await update.message.reply_text("❌ Введите корректное положительное число часов:")
        return WAIT_ADMIN_BAN_HOURS

    context.user_data["ban_hours"] = int(hours_str)
    await update.message.reply_text("📝 Введите причину блокировки (кратко):")
    return WAIT_ADMIN_BAN_REASON

async def admin_ban_reason_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    target_id = context.user_data.get("ban_target_id")
    hours = context.user_data.get("ban_hours", 24)

    ban_user(target_id, hours, reason)

    try:
        until_ts = int(time.time()) + (hours * 3600)
        ban_text, ban_kb = format_ban_message(until_ts, reason, hours)
        await context.bot.send_message(
            chat_id=target_id,
            text=ban_text,
            parse_mode=ParseMode.HTML,
            reply_markup=ban_kb
        )
    except Exception as e:
        log.warning("Не удалось уведомить забаненного игрока %s: %s", target_id, e)

    await update.message.reply_text(
        f"⛔️ <b>Игрок (ID: <code>{target_id}</code>) успешно заблокирован!</b>\n"
        f"• Срок: <b>{hours} ч.</b>\n"
        f"• Причина: <b>{clean_html(reason)}</b>\n\n"
        f"При вводе любой команды нарушителю будет выводиться экран блокировки с поддержкой {SUPPORT_HANDLE}.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
        ])
    )
    return ConversationHandler.END

# --- РАЗБАН ИГРОКА (FSM) ---

async def admin_unban_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    text = "🔓 <b>Разблокировка игрока</b>\n\nВведите Telegram ID или @username игрока:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_ADMIN_UNBAN_USER

async def admin_unban_user_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден. Попробуйте снова:")
        return WAIT_ADMIN_UNBAN_USER

    target_id = target["user_id"]
    unban_user(target_id)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text="🎉 <b>Ваш аккаунт был разблокирован администрацией!</b>\nВы снова можете полноценно пользоваться ботом.",
            parse_mode=ParseMode.HTML,
            reply_markup=quick_nav_keyboard()
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ <b>Игрок (ID: <code>{target_id}</code>) успешно разблокирован!</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
        ])
    )
    return ConversationHandler.END

# --- ВЫДАЧА STARS ---

async def admin_give_stars_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    text = "⭐ <b>Выдача Звёзд игроку</b>\n\nВведите Telegram ID или @username игрока:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_ADMIN_GIVE_STARS_USER

async def admin_give_stars_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден. Попробуйте снова:")
        return WAIT_ADMIN_GIVE_STARS_USER

    context.user_data["admin_target_user_id"] = target["user_id"]
    target_name = normalize_telegram_name(target["first_name"] or target["username"] or "Игрок")
    await update.message.reply_text(
        f"✅ Пользователь найден: <b>{clean_html(target_name)}</b> (ID: <code>{target['user_id']}</code>).\n\n"
        f"Введите количество Stars (⭐) для начисления:",
        parse_mode=ParseMode.HTML
    )
    return WAIT_ADMIN_GIVE_STARS_AMOUNT

async def admin_give_stars_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt_str = update.message.text.strip()
    if not amt_str.isdigit() or int(amt_str) <= 0:
        await update.message.reply_text("❌ Введите положительное число звёзд:")
        return WAIT_ADMIN_GIVE_STARS_AMOUNT

    amount = int(amt_str)
    target_id = context.user_data.get("admin_target_user_id")
    add_user_stars(target_id, amount)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎉 <b>Уведомление от Администрации!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"Вам начислено: <b>+{amount:,} ⭐ (Stars)</b>!\n"
                f"Ваш игровой баланс пополнен."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=quick_nav_keyboard()
        )
    except Exception as e:
        log.warning("Не удалось доставить уведомление игроку %s: %s", target_id, e)

    await update.message.reply_text(
        f"✅ Успешно начислено <b>{amount:,} ⭐</b> пользователю (ID: <code>{target_id}</code>)!\n"
        f"Игроку отправлено личное уведомление.",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="nav_main")]
        ])
    )
    return ConversationHandler.END

# --- ВЫДАЧА NFT ПО ФИЛЬТРАМ (СТОИМОСТЬ И МОДЕЛИ) ---

async def admin_give_nft_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен!", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    text = "🎁 <b>Выдача NFT-подарка игроку</b>\n\nВведите Telegram ID или @username игрока:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_cancel")]])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_ADMIN_GIVE_NFT_USER

async def admin_give_nft_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден. Попробуйте еще раз:")
        return WAIT_ADMIN_GIVE_NFT_USER

    target_id = target["user_id"]
    context.user_data["admin_nft_target_user_id"] = target_id
    target_name = normalize_telegram_name(target["first_name"] or target["username"] or "Игрок")

    await show_admin_nft_filter_selector(update.message, target_id, target_name)
    return ConversationHandler.END

async def show_admin_nft_filter_selector(msg_or_query, target_id: int, target_name: str):
    text = (
        f"🎁 <b>Выдача подарка для игрока {clean_html(target_name)} (ID: {target_id})</b>\n\n"
        f"Выберите способ фильтрации подарков для выдачи по кнопкам:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Фильтр: По стоимости", callback_data=f"adm_filt_price:{target_id}")],
        [InlineKeyboardButton("🧸 Фильтр: По моделям", callback_data=f"adm_filt_model:{target_id}")],
        [InlineKeyboardButton("📋 Все модели подарков", callback_data=f"adm_items:all:all:{target_id}:1")],
        [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")]
    ])
    if hasattr(msg_or_query, "reply_text"):
        await msg_or_query.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await msg_or_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_admin_nft_price_tiers(query, target_id: int):
    text = f"💰 <b>Выбор по стоимости (ID получателя: {target_id}):</b>"
    buttons = []
    for pkey, (ptitle, _, _) in PRICE_TIERS.items():
        buttons.append([InlineKeyboardButton(ptitle, callback_data=f"adm_items:price:{pkey}:{target_id}:1")])
    buttons.append([InlineKeyboardButton("⬅️ К выбору фильтра", callback_data=f"adm_back_filters:{target_id}")])
    kb = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_admin_nft_model_groups(query, target_id: int):
    text = f"🧸 <b>Выбор по моделям Telegram (ID получателя: {target_id}):</b>"
    buttons = []
    for mkey, mtitle in MODEL_GROUPS.items():
        buttons.append([InlineKeyboardButton(mtitle, callback_data=f"adm_items:model:{mkey}:{target_id}:1")])
    buttons.append([InlineKeyboardButton("⬅️ К выбору фильтра", callback_data=f"adm_back_filters:{target_id}")])
    kb = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_admin_nft_items_page(query, ftype: str, fkey: str, target_id: int, page: int = 1):
    gifts_pool = get_gifts_filtered(ftype, fkey)
    page_size = 6
    total_pages = max(1, math.ceil(len(gifts_pool) / page_size))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * page_size
    items = gifts_pool[start_idx : start_idx + page_size]

    text = (
        f"🎁 <b>Выберите подарок для выдачи (Стр. {page}/{total_pages})</b>\n"
        f"Получатель ID: <code>{target_id}</code>\n"
        f"Нажмите на нужную кнопку для выдачи игроку:"
    )

    buttons = []
    for g in items:
        btn_text = f"🎁 {g.name[:25]} ({g.stars:,}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"adm_give_do:{g.key}:{target_id}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"adm_items:{ftype}:{fkey}:{target_id}:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"adm_items:{ftype}:{fkey}:{target_id}:{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("📂 Сменить фильтр", callback_data=f"adm_back_filters:{target_id}")])
    buttons.append([InlineKeyboardButton("👑 Админ-Панель", callback_data="admin_panel")])

    kb = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def execute_admin_give_nft(query, gift_key: str, target_id: int, context: ContextTypes.DEFAULT_TYPE):
    gift = GIFTS_BY_KEY.get(gift_key)
    if not gift:
        await query.answer("❌ Подарок не найден!", show_alert=True)
        return

    add_to_collection(target_id, gift_key)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎁 <b>Вам выдан NFT-подарок от Администрации!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"<b>{gift.name}</b>\n"
                f"• Модель: <b>{gift.model_name}</b>\n"
                f"• Ценность: <b>{fmt_stars_rub(gift.stars)}</b>\n"
                f"• Опыт: <b>+{gift.xp} XP</b>\n\n"
                f"Предмет уже добавлен в вашу коллекцию!"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=quick_nav_keyboard()
        )
    except Exception as e:
        log.warning("Не удалось доставить уведомление игроку %s: %s", target_id, e)

    await query.answer(f"✅ Выдан: {gift.name}!", show_alert=True)
    text = (
        f"✅ <b>Подарок успешно выдан!</b>\n\n"
        f"Предмет: <b>{gift.name}</b>\n"
        f"Модель: <b>{gift.model_name}</b>\n"
        f"Получатель: <code>{target_id}</code>\n"
        f"Игроку отправлено личное уведомление."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎁 Выдать еще один подарок", callback_data=f"adm_back_filters:{target_id}")],
        [InlineKeyboardButton("👑 В админ-панель", callback_data="admin_panel")],
        [InlineKeyboardButton("🏠 В главное меню", callback_data="nav_main")]
    ])
    await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Отменено.")
        await show_admin_panel(query)
    else:
        await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# КЛАНЫ - СОЗДАНИЕ И УПРАВЛЕНИЕ
# ---------------------------------------------------------------------------

CLAN_CREATE_LEVEL_REQ = 10
CLAN_CREATE_COST = 100_000

async def show_clans_hub(query_or_update, user_id: int, context: ContextTypes.DEFAULT_TYPE = None) -> None:
    user_clan = get_user_clan(user_id)
    if user_clan:
        await show_clan_profile_handler(query_or_update, user_clan["id"], context or query_or_update._bot)
        return

    db_user = get_or_create_user(user_id, "", "")
    lvl, _, _, _ = calculate_xp_level_info(db_user["xp"])

    text = (
        "🛡 <b>Система Кланов New NFT</b>\n\n"
        f"• Ваш уровень: <b>{lvl}</b> (требуется 10+)\n"
        f"• Стоимость основания: <b>100,000 ⭐</b>\n\n"
        "Клан даёт клановый тег, собственный герб, общую казну и мощный <b>бонус к шансу выигрыша подарков (+1%..+45%)</b>!\n\n"
        "Вы можете основать свой клан или вступить в существующий:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷 Основать клан", callback_data="clan_create_start")],
        [InlineKeyboardButton("📋 Просмотреть список кланов", callback_data="clan_list:1")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])

    if hasattr(query_or_update, "message") and query_or_update.message:
        if query_or_update.message.photo:
            try: await query_or_update.message.delete()
            except: pass
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
        total_treasury, _, members = get_clan_treasury_and_members(c["id"])
        lvl, _, _, _, bonus = calculate_clan_level_info(c["xp"])
        ctype = "Публичный" if c["type"] == "public" else ("За звёзды" if c["type"] == "stars" else "Закрытый")

        text += (
            f"🛡 <b>[{c['tag']}] {clean_html(c['name'])}</b>\n"
            f"• Ур. {lvl} (+{bonus}% бонус) | {len(members)}/{c['max_members']} чел.\n"
            f"• Казна: {total_treasury:,} ⭐ ({ctype})\n\n"
        )
        buttons.append([InlineKeyboardButton(f"[{c['tag']}] {c['name']} (Ур. {lvl})", callback_data=f"clan_info:{c['id']}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"clan_list:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"clan_list:{page+1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")])
    kb = InlineKeyboardMarkup(buttons)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def start_clan_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
        msg_obj = query.message
    else:
        user = update.effective_user
        msg_obj = update.message

    db_user = get_or_create_user(user.id, user.username or "", user.first_name or "")
    lvl, _, _, _ = calculate_xp_level_info(db_user["xp"])

    if lvl < CLAN_CREATE_LEVEL_REQ:
        text = f"❌ Для создания клана нужен {CLAN_CREATE_LEVEL_REQ} уровень!"
        if query: await query.answer(text, show_alert=True)
        else: await msg_obj.reply_text(text)
        return ConversationHandler.END

    if db_user["balance_stars"] < CLAN_CREATE_COST:
        text = f"❌ Создание клана стоит {CLAN_CREATE_COST:,} ⭐!"
        if query: await query.answer(text, show_alert=True)
        else: await msg_obj.reply_text(text)
        return ConversationHandler.END

    msg_text = (
        "🏷 <b>Шаг 1 из 4: Клантег</b>\n\n"
        "Введите заглавный английский клантег (от 3 до 6 символов, только A-Z и 0-9).\n"
        "<i>Пример: TOP1, GODS, ALPHA</i>"
    )
    if query and query.message.photo:
        await query.message.delete()
        await query.message.reply_text(msg_text, parse_mode=ParseMode.HTML)
    elif query:
        await query.edit_message_text(msg_text, parse_mode=ParseMode.HTML)
    else:
        await msg_obj.reply_text(msg_text, parse_mode=ParseMode.HTML)
    return WAIT_CLAN_TAG

async def clan_tag_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = update.message.text.strip().upper()
    if not re.match(r"^[A-Z0-9]{3,6}$", tag):
        await update.message.reply_text("❌ Некорректный клантег! Введите 3-6 заглавных английских букв или цифр:")
        return WAIT_CLAN_TAG

    context.user_data["clan_tag"] = tag
    await update.message.reply_text(
        "📝 <b>Шаг 2 из 4: Название клана</b>\n\n"
        "Введите название вашего клана (от 2 до 15 символов):",
        parse_mode=ParseMode.HTML
    )
    return WAIT_CLAN_NAME

async def clan_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) > 15 or len(name) < 2:
        await update.message.reply_text("❌ Название должно содержать от 2 до 15 символов! Попробуйте снова:")
        return WAIT_CLAN_NAME

    context.user_data["clan_name"] = name
    await update.message.reply_text(
        "ℹ️ <b>Шаг 3 из 4: Описание клана</b>\n\n"
        "Напишите краткое описание вашего клана (или точку):",
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
        "Выберите способ вступления в клан:",
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
        await update.message.reply_text("❌ Введите корректное число звёзд:")
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
        clan = get_clan_by_id(clan_id)
        clan_sys_id = clan["id_num"] if clan["id_num"] else clan["id"]
        text = (
            f"🎉 <b>Клан [{tag}] {clean_html(name)} успешно создан!</b>\n"
            f"Единый глобальный номер клана: <b>ID #{clan_sys_id}</b>\n\n"
            f"С вашего баланса списано {CLAN_CREATE_COST:,} ⭐."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛡 В профиль клана", callback_data=f"clan_info:{clan_id}")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
        ])
        if hasattr(msg_obj, "edit_text"):
            await msg_obj.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await msg_obj.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        add_user_stars(user_id, CLAN_CREATE_COST)
        await msg_obj.reply_text("❌ Ошибка при создании клана. Возможно, клантег уже занят.")

    return ConversationHandler.END

async def cancel_clan_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Создание клана отменено.", reply_markup=back_to_main_keyboard())
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# РАЗДЕЛ "УЛУЧШЕНИЯ" (PLUSH PEPE -> МОДЕЛЬ + ФОН, И СЛОТЫ ИНВЕНТАРЯ)
# ---------------------------------------------------------------------------

async def show_shop_page(query_or_msg, user_id: int, page: int = 1) -> None:
    db_user = get_or_create_user(user_id, "", "")
    all_items = get_user_collection(user_id)
    # Сначала показываем обычных Plush Pepe (доступных к улучшению), потом остальные
    sorted_items = sorted(
        all_items,
        key=lambda r: (
            0 if (r["gift_key"] == "pepe_heart" and not r["is_upgraded"]) else (1 if r["is_upgraded"] else 2),
            -r["id"],
        ),
    )

    pepe_ready = sum(1 for r in all_items if r["gift_key"] == "pepe_heart" and not r["is_upgraded"])
    pepe_upgraded = sum(1 for r in all_items if r["is_upgraded"])

    lines = [
        "✨ <b>Улучшения NFT-подарков</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"💰 Ваш баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>",
        f"💎 Стоимость улучшения Plush Pepe: <b>{UPGRADE_COST_STARS:,} ⭐</b>",
        f"🐸 Обычных Plush Pepe для улучшения: <b>{pepe_ready}</b> шт.",
        f"✨ Уже улучшено подарков: <b>{pepe_upgraded}</b> шт.\n",
    ]

    buttons = []
    if not sorted_items:
        lines.append("<i>У вас пока нет подарков в коллекции. Выбейте Plush Pepe в чате (слово NFT) или в кейсах!</i>")
    else:
        lines.append("Нажмите на подарок из списка ниже, чтобы перейти к улучшению:")
        page_size = 8
        total_pages = max(1, math.ceil(len(sorted_items) / page_size))
        page = max(1, min(page, total_pages))
        chunk = sorted_items[(page - 1) * page_size : page * page_size]

        for item in chunk:
            g = GIFTS_BY_KEY.get(item["gift_key"])
            if not g:
                continue
            if item["is_upgraded"]:
                badge = "✨ [Улучшен]"
                lbl = f"{badge} {item['model_name']} | {item['bg_name']} ({item['estimated_stars']:,}⭐)"
            elif item["gift_key"] == "pepe_heart":
                lbl = f"🐸 Plush Pepe #{item['id']} — Готов к улучшению!"
            else:
                lbl = f"🎁 {g.name.split('(')[0].strip()} ({g.stars:,}⭐)"
            buttons.append([InlineKeyboardButton(lbl[:60], callback_data=f"upgrade_item:{item['id']}")])

        if total_pages > 1:
            nav_row = []
            if page > 1:
                nav_row.append(InlineKeyboardButton("◀️", callback_data=f"upgrade_page:{page-1}"))
            nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav_row.append(InlineKeyboardButton("▶️", callback_data=f"upgrade_page:{page+1}"))
            buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("📦 Расширить слоты инвентаря", callback_data="shop_slots_menu")])
    buttons.append([
        InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main"),
    ])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(buttons)

    if hasattr(query_or_msg, "message") and query_or_msg.message:
        if query_or_msg.message.photo:
            await query_or_msg.message.delete()
            await query_or_msg.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query_or_msg.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query_or_msg.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_slots_shop_page(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    text = (
        "📦 <b>Расширение слотов инвентаря</b>\n\n"
        f"Текущие слоты коллекции: <b>{db_user['max_inventory']}</b>\n"
        f"Ваш баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
        "Доступные расширения слотов:\n"
        "• <b>+10 Слотов</b> — <b>300 ⭐</b>\n"
        "• <b>+25 Слотов</b> — <b>650 ⭐</b>\n"
        "• <b>+50 Слотов</b> — <b>1,200 ⭐</b>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📦 +10 Слотов (300⭐)", callback_data="buy_slots:10:300")],
        [InlineKeyboardButton("📦 +25 Слотов (650⭐)", callback_data="buy_slots:25:650")],
        [InlineKeyboardButton("📦 +50 Слотов (1200⭐)", callback_data="buy_slots:50:1200")],
        [InlineKeyboardButton("⬅️ Назад в Улучшения", callback_data="nav_shop")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def show_upgrade_item_preview(query, item_id: int, user_id: int) -> None:
    item = get_collection_item(item_id)
    if not item or item["user_id"] != user_id:
        await query.answer("❌ Подарок не найден.", show_alert=True)
        return

    g = GIFTS_BY_KEY.get(item["gift_key"])
    if not g:
        await query.answer("❌ Ошибка данных подарка.", show_alert=True)
        return

    if item["is_upgraded"]:
        bg_obj = next((b for b in PLUSHPEPE_BACKDROPS if b.name == item["bg_name"]), None)
        rarity_lbl = bg_obj.rarity_label if bg_obj else "Редкий"
        cap = (
            f"✨ <b>Улучшенный Plush Pepe #{item['id']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧸 Модель: <b>{clean_html(item['model_name'])}</b> ({item['model_rarity']:.1f}%)\n"
            f"🎨 Фон: <b>{clean_html(item['bg_name'])}</b> — {clean_html(item['bg_palette'])}\n"
            f"💎 Шанс фона: <b>{item['bg_rarity']:.2f}%</b> ({rarity_lbl})\n"
            f"💰 Оценка: <b>{fmt_stars_rub(item['estimated_stars'])}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Этот подарок уже улучшен! Вы можете передать его бесплатно или выставить на маркет."
        )
        buttons = []
        if not item["is_listed"]:
            buttons.append([InlineKeyboardButton("🛒 Выставить на маркет", callback_data=f"market_sell_start:{item['id']}")])
            buttons.append([InlineKeyboardButton("🎁 Передать бесплатно", callback_data=f"gift_transfer_start:{item['id']}")])
        else:
            buttons.append([InlineKeyboardButton("🔍 Лот на маркете", callback_data=f"market_lot_item:{item['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ Назад в Улучшения", callback_data="nav_shop")])
        kb = InlineKeyboardMarkup(buttons)

        try:
            card_io = await generate_upgraded_gift_image(
                item["model_file"], item["model_name"], item["bg_name"],
                item["bg_center_hex"], item["bg_edge_hex"], item["bg_rarity"], item["id"]
            )
            if query.message.photo:
                try: await query.message.delete()
                except: pass
            await query.message.reply_photo(photo=InputFile(card_io, filename=f"pepe_{item['id']}.png"), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception as e:
            log.warning("Ошибка фото улучшенного подарка: %s", e)
        await query.edit_message_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if item["gift_key"] != "pepe_heart":
        text = (
            f"🎁 <b>{g.name}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• Модель: <b>{g.model_name}</b>\n"
            f"• Стоимость: <b>{fmt_stars_rub(g.stars)}</b>\n\n"
            f"⚠️ <i>На данный момент улучшение до коллекционной модели и фона доступно только для <b>Plush Pepe</b>!</i>"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Назад в Улучшения", callback_data="nav_shop")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
        ])
        if query.message.photo:
            await query.message.delete()
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    db_user = get_or_create_user(user_id, "", "")
    cap = (
        f"🐸 <b>Улучшение Plush Pepe #{item['id']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"• Текущий подарок: <b>{g.name}</b>\n"
        f"• Базовая цена: <b>{fmt_stars_rub(g.stars)}</b>\n"
        f"• Ваш баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n"
        f"• Стоимость улучшения: <b>{UPGRADE_COST_STARS:,} ⭐</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎲 <b>Что произойдёт при улучшении:</b>\n"
        f"1. Выпадет случайная из <b>50 уникальных моделей</b> Plush Pepe.\n"
        f"2. Выпадет случайный <b>коллекционный фон</b> (чёрные/серые фоны — ультра-редкие, яркие — частые).\n"
        f"3. Стоимость подарка вырастет в разы (до 3–5+ млн ⭐ при редком фоне!), его можно <b>передавать бесплатно</b> и <b>продавать на маркете за свою цену</b>!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✨ Улучшить ({UPGRADE_COST_STARS:,} ⭐)", callback_data=f"upgrade_do:{item['id']}")],
        [InlineKeyboardButton("⬅️ Назад в Улучшения", callback_data="nav_shop")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])

    img_p = gift_image_path(g.key)
    if img_p:
        try:
            if query.message.photo:
                try: await query.message.delete()
                except: pass
            with open(img_p, "rb") as f:
                await query.message.reply_photo(photo=InputFile(f, filename=img_p.name), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
            return
        except Exception:
            pass
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)

async def execute_gift_upgrade(query, item_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Защита от двойного нажатия во время 5-секундной анимации
    upgrading_set = context.application.bot_data.setdefault("upgrading_items", set())
    if item_id in upgrading_set:
        await query.answer("⏳ Улучшение этого подарка уже идёт!", show_alert=True)
        return

    upgrading_set.add(item_id)
    try:
        model = roll_plush_model()
        backdrop = roll_backdrop()
        base_g = GIFTS_BY_KEY.get("pepe_heart")
        base_stars = base_g.stars if base_g else 350_000
        est_stars = calculate_upgraded_stars(base_stars, model, backdrop)

        ok, err = upgrade_collection_item(item_id, user_id, UPGRADE_COST_STARS, model, backdrop, est_stars)
        if not ok:
            await query.answer(f"❌ {err}", show_alert=True)
            return

        # 5-секундная анимация улучшения (сначала появляется модель, затем фон!)
        if query.message.photo:
            try: await query.message.delete()
            except: pass
            anim_msg = await context.bot.send_message(
                chat_id=user_id,
                text=(
                    "✨ <b>Запуск улучшения Plush Pepe...</b>\n"
                    "<code>[▓▓░░░░░░░░] 20%</code>\n\n"
                    "🔮 Инициализация матрицы коллекции..."
                ),
                parse_mode=ParseMode.HTML,
            )
        else:
            anim_msg = await query.edit_message_text(
                "✨ <b>Запуск улучшения Plush Pepe...</b>\n"
                "<code>[▓▓░░░░░░░░] 20%</code>\n\n"
                "🔮 Инициализация матрицы коллекции...",
                parse_mode=ParseMode.HTML,
            )

        await asyncio.sleep(1.2)
        try:
            await anim_msg.edit_text(
                "✨ <b>Подбор модели Plush Pepe...</b>\n"
                "<code>[▓▓▓▓▓░░░░░] 50%</code>\n\n"
                "🧸 Перебор 50 уникальных моделей...",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        await asyncio.sleep(1.3)
        try:
            await anim_msg.edit_text(
                "✨ <b>Модель определена!</b>\n"
                "<code>[▓▓▓▓▓▓▓░░░] 75%</code>\n\n"
                f"🧸 Выпала модель: <b>{clean_html(model.name)}</b>!\n"
                "🎨 Подбор цветовой палитры и редкости фона...",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        await asyncio.sleep(1.3)
        try:
            await anim_msg.edit_text(
                "✨ <b>Наложение коллекционного фона...</b>\n"
                "<code>[▓▓▓▓▓▓▓▓▓░] 95%</code>\n\n"
                f"🧸 Модель: <b>{clean_html(model.name)}</b>\n"
                f"🎨 Фон: <b>{clean_html(backdrop.name)}</b> ({backdrop.chance_pct:.2f}%)...",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            pass

        await asyncio.sleep(1.2)

        final_cap = (
            f"🎉 <b>УЛУЧШЕНИЕ ЗАВЕРШЕНО!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✨ <b>Plush Pepe #{item_id}</b>\n"
            f"🧸 Модель: <b>{clean_html(model.name)}</b> (редкость: <b>{model.rarity_pct:.1f}%</b>)\n"
            f"🎨 Фон: <b>{clean_html(backdrop.name)}</b> — {clean_html(backdrop.palette)}\n"
            f"💎 Шанс фона: <b>{backdrop.chance_pct:.2f}%</b> ({backdrop.rarity_label})\n"
            f"💰 Новая стоимость: <b>{fmt_stars_rub(est_stars)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• Бонус за улучшение: <b>+25,000 XP</b>\n"
            f"• Теперь подарок можно <b>передавать бесплатно</b> или <b>выставить на маркет</b> по своей цене!"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Выставить на маркет", callback_data=f"market_sell_start:{item_id}")],
            [InlineKeyboardButton("🎁 Передать бесплатно", callback_data=f"gift_transfer_start:{item_id}")],
            [
                InlineKeyboardButton("🗂 В коллекцию", callback_data="nav_collection_page:1"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main"),
            ],
        ])

        try:
            card_io = await generate_upgraded_gift_image(
                model.filename, model.name, backdrop.name,
                backdrop.center_hex, backdrop.edge_hex, backdrop.chance_pct, item_id
            )
            try: await anim_msg.delete()
            except Exception: pass
            await context.bot.send_photo(
                chat_id=user_id,
                photo=InputFile(card_io, filename=f"upgraded_pepe_{item_id}.png"),
                caption=final_cap,
                parse_mode=ParseMode.HTML,
                reply_markup=kb,
            )
        except Exception as e:
            log.warning("Не удалось отправить фото улучшенного Пепе: %s", e)
            await anim_msg.edit_text(final_cap, parse_mode=ParseMode.HTML, reply_markup=kb)
    finally:
        upgrading_set.discard(item_id)

# ---------------------------------------------------------------------------
# БЕСПЛАТНАЯ ПЕРЕДАЧА УЛУЧШЕННОГО ПОДАРКА (FSM)
# ---------------------------------------------------------------------------

async def gift_transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if query.message.chat.type != "private":
        await query.answer("⚠️ Откройте личные сообщения с ботом для передачи подарка!", show_alert=True)
        return ConversationHandler.END

    item_id = int(query.data.split(":")[1])
    item = get_collection_item(item_id)
    if not item or item["user_id"] != user.id:
        await query.answer("❌ Подарок не найден.", show_alert=True)
        return ConversationHandler.END
    if item["is_listed"]:
        await query.answer("❌ Сначала снимите подарок с маркета!", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    context.user_data["transfer_item_id"] = item_id
    label = f"✨ Plush Pepe #{item['id']} ({item['model_name']} | {item['bg_name']})" if item["is_upgraded"] else f"🎁 Подарок #{item['id']}"
    text = (
        f"🎁 <b>Бесплатная передача подарка</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Выбран предмет: <b>{clean_html(label)}</b>\n\n"
        f"Введите <b>Telegram ID</b>, внутренний <b>ID #</b> или <b>@username</b> игрока, которому хотите подарить этот NFT (передача абсолютно бесплатна — 0 ⭐):"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="gift_transfer_cancel")]])
    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    return WAIT_GIFT_TRANSFER_USER

async def gift_transfer_user_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender = update.effective_user
    target_str = update.message.text.strip()
    target = get_user_by_target(target_str)
    if not target:
        await update.message.reply_text("❌ Игрок не найден в боте. Попробуйте снова (ID или @username):")
        return WAIT_GIFT_TRANSFER_USER
    if target["user_id"] == sender.id:
        await update.message.reply_text("❌ Нельзя передать подарок самому себе! Укажите другого игрока:")
        return WAIT_GIFT_TRANSFER_USER

    item_id = context.user_data.get("transfer_item_id")
    item = get_collection_item(item_id) if item_id else None
    if not item or item["user_id"] != sender.id:
        await update.message.reply_text("❌ Подарок больше не найден в вашей коллекции.", reply_markup=quick_nav_keyboard())
        return ConversationHandler.END

    ok, err = transfer_collection_item(item_id, sender.id, target["user_id"])
    if not ok:
        await update.message.reply_text(f"❌ {err}", reply_markup=quick_nav_keyboard())
        return ConversationHandler.END

    rec_name = normalize_telegram_name(target["first_name"] or target["username"] or "Игрок")
    if item["is_upgraded"]:
        gift_desc = f"✨ Plush Pepe #{item['id']} ({item['model_name']} | Фон: {item['bg_name']} {item['bg_rarity']:.2f}%)"
    else:
        g = GIFTS_BY_KEY.get(item["gift_key"])
        gift_desc = g.name if g else item["gift_key"]

    try:
        await context.bot.send_message(
            chat_id=target["user_id"],
            text=(
                f"🎁 <b>Вам бесплатно подарили NFT-подарок!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"От игрока: <b>{clean_html(sender.first_name)}</b>\n"
                f"Предмет: <b>{clean_html(gift_desc)}</b>\n\n"
                f"Подарок уже добавлен в вашу коллекцию!"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=quick_nav_keyboard(),
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ <b>Подарок бесплатно передан!</b>\n"
        f"• Предмет: <b>{clean_html(gift_desc)}</b>\n"
        f"• Получатель: <b>{clean_html(rec_name)}</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=quick_nav_keyboard(),
    )
    return ConversationHandler.END

async def gift_transfer_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("Отменено.")
        await show_collection_page(query, query.from_user.id, 1)
    else:
        await update.message.reply_text("Передача подарка отменена.", reply_markup=back_to_main_keyboard())
    return ConversationHandler.END

# ---------------------------------------------------------------------------
# НАСТРОЙКИ
# ---------------------------------------------------------------------------

async def show_settings_page(query, user_id: int) -> None:
    db_user = get_or_create_user(user_id, "", "")
    hide_top = "✅ Да" if db_user["hide_top"] else "❌ Нет"
    hide_coll = "✅ Да" if db_user["hide_collection"] else "❌ Нет"
    auto_sell = "✅ Включена" if db_user["auto_sell"] else "❌ Выключена"
    has_bg = "✅ Установлен" if db_user["bg_image_path"] else "❌ Стандартный"

    text = (
        "⚙️ <b>Настройки аккаунта</b>\n\n"
        f"• Скрывать из ТОП-100: <b>{hide_top}</b>\n"
        f"• Скрывать коллекцию: <b>{hide_coll}</b>\n"
        f"• Авто-продажа кейсов: <b>{auto_sell}</b>\n"
        f"• Кастомный фон профиля: <b>{has_bg}</b>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Скрытие из ТОПа: {hide_top}", callback_data="toggle_set:hide_top")],
        [InlineKeyboardButton(f"Скрытие коллекции: {hide_coll}", callback_data="toggle_set:hide_collection")],
        [InlineKeyboardButton(f"Авто-продажа: {auto_sell}", callback_data="toggle_set:auto_sell")],
        [InlineKeyboardButton("🖼 Сменить фон профиля", callback_data="bg_change_start")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# КОЛЛЕКЦИЯ И ТОП 100
# ---------------------------------------------------------------------------

async def show_collection_page(query, user_id: int, page: int = 1) -> None:
    items = get_user_collection(user_id)
    db_user = get_or_create_user(user_id, "", "")
    max_inv = db_user["max_inventory"]

    if not items:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎰 Открыть кейсы", callback_data="nav_cases_hub")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
        ])
        msg_text = f"🗂 <b>Твоя коллекция пока пуста (0/{max_inv}).</b>\nВыбивай подарки по слову <code>NFT</code> в группах или открывай кейсы!"
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
        if item["is_upgraded"]:
            market_tag = "🛒 " if item["is_listed"] else "✨ "
            btn_text = f"{fav_star}{market_tag}Plush Pepe • {item['model_name']} [{item['bg_name']}] ({item['estimated_stars']:,}⭐)"
        else:
            btn_text = f"{fav_star}{g.name} ({g.stars:,}⭐)"
        buttons.append([InlineKeyboardButton(btn_text[:60], callback_data=f"view_item:{item['id']}:{page}")])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"nav_collection_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"nav_collection_page:{page+1}"))
    buttons.append(nav_row)

    buttons.append([InlineKeyboardButton("✨ Улучшения подарков", callback_data="nav_shop")])
    buttons.append([InlineKeyboardButton("🔥 Продать всё (кроме избранных)", callback_data="sell_all_confirm")])
    buttons.append([
        InlineKeyboardButton("👤 Профиль", callback_data="nav_profile"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
    ])

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

    lines = [f"🏆 <b>Глобальный ТОП-100 Игроков (Стр. {page}/{total_pages})</b>\n━━━━━━━━━━━━━━━━━━"]
    buttons = []

    start_rank = (page - 1) * page_size + 1
    for idx, u in enumerate(rows, start=start_rank):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"#{idx}"
        clan = get_user_clan(u['user_id'])
        tag_str = f"[{clan['tag']}] " if clan else ""
        name = normalize_telegram_name(u['first_name'] or u['username'] or 'Игрок')
        lvl, _, _, _ = calculate_xp_level_info(u['xp'])
        lines.append(f"{medal} <b>{tag_str}{clean_html(name)}</b> — <b>{u['balance_stars']:,} ⭐</b> (Ур. {lvl})")
        
        btn_text = f"👤 {medal} {tag_str}{name[:12]} ({u['balance_stars']:,}⭐)"
        buttons.append([InlineKeyboardButton(btn_text, callback_data=f"view_top_user:{u['user_id']}:{page}")])

    lines.append("━━━━━━━━━━━━━━━━━━\n<i>Нажмите на игрока выше, чтобы открыть его карточку профиля с фоном и статистикой!</i>")

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"nav_top_page:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"nav_top_page:{page+1}"))
    
    buttons.append(nav_row)
    buttons.append([
        InlineKeyboardButton("👤 Мой профиль", callback_data="nav_profile"),
        InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
    ])

    kb = InlineKeyboardMarkup(buttons)
    full_text = "\n".join(lines)

    if query.message.photo:
        await query.message.delete()
        await query.message.reply_text(full_text, parse_mode=ParseMode.HTML, reply_markup=kb)
    else:
        await query.edit_message_text(full_text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ---------------------------------------------------------------------------
# ОБРАБОТКА В ЧАТАХ (ДРОПЫ NFT С УЧЕТОМ БОНУСА КЛАНА)
# ---------------------------------------------------------------------------

async def on_group_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if msg is None or msg.text is None:
        return

    user = update.effective_user
    is_banned, until_ts, reason, hours = is_user_banned(user.id)
    if is_banned:
        return

    text_raw = msg.text.strip()
    text_lower = text_raw.lower()

    if text_lower in ("кто я", "я", "профиль", "profile"):
        await show_profile_handler(update, user.id, context)
        return

    allowed_words = {"nft", "нфт", "подарок"}
    if text_lower not in allowed_words:
        return

    row = get_or_create_user(user.id, user.username or "", user.first_name or "")

    now = int(time.time())
    if COOLDOWN_ENABLED:
        remaining = row["last_drop_ts"] + COOLDOWN_SECONDS - now
        if remaining > 0:
            await msg.reply_text(f"⏳ Рано! Команду NFT можно использовать 1 раз в час.\nПопробуйте через {seconds_to_hms(remaining)}.")
            return

    set_last_drop(user.id, now)

    if random.random() > CHAT_DROP_CHANCE:
        await msg.reply_text("💨 В этот раз ничего не выпало! Попробуйте снова через 1 час.")
        return

    # Клановый бонус к выигрышу (+1% .. +45%)
    clan = get_user_clan(user.id)
    clan_bonus_pct = 0.0
    clan_note = ""
    if clan:
        _, _, _, _, clan_bonus_pct = calculate_clan_level_info(clan["xp"])
        clan_note = f"\n🛡 Бонус клана [{clan['tag']}]: <b>+{clan_bonus_pct}%</b> к выигрышу!"

    gift = roll_gift_from_pool(GIFTS, bonus_pct=clan_bonus_pct)
    drop_id = create_pending_drop(user.id, update.effective_chat.id, gift.key)

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💾 Сохранить в коллекцию", callback_data=f"keep:{drop_id}"),
            InlineKeyboardButton("💰 Продать за Stars", callback_data=f"sell:{drop_id}"),
        ]
    ])

    caption = (
        f"🎉 <b>{clean_html(user.first_name)}</b>, вам выпал подарок!\n\n"
        f"<b>{gift.name}</b>\n"
        f"• Модель: <b>{gift.model_name}</b>\n"
        f"• Опыт: <b>+{gift.xp} XP</b>\n"
        f"• Ценность: {fmt_stars_rub(gift.stars)} / {fmt_ton(gift.ton)}"
        f"{clan_note}\n\n"
        f"Выберите действие ниже:"
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

    # Проверка блокировки пользователя
    is_banned, until_ts, reason, hours = is_user_banned(user.id)
    if is_banned and user.id not in ADMIN_IDS:
        ban_text, ban_kb = format_ban_message(until_ts, reason, hours)
        await query.answer("⛔️ Ваш аккаунт заблокирован!", show_alert=True)
        if query.message:
            await query.message.reply_text(ban_text, parse_mode=ParseMode.HTML, reply_markup=ban_kb)
        return

    # Защита приватных разделов в группах
    if query.message.chat.type != "private" and (
        data in ("nav_cases_hub", "nav_top_page:1", "nav_settings", "nav_shop", "shop_slots_menu", "nav_clans_hub", "admin_panel", "nav_market", "market_create_offer", "market_my_offers", "market_history")
        or data.startswith(("upgrade_", "market_"))
    ):
        await query.answer("⚠️ Откройте личные сообщения с ботом для этого меню!", show_alert=True)
        return

    if data == "admin_panel":
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
        await show_admin_panel(query)
        return

    if data == "admin_firebase_menu":
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
        await show_admin_firebase_menu(query)
        return

    if data == "admin_firebase_sync":
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
        ok = firebase_manager.upload_db_to_cloud(force=True)
        if ok:
            await query.answer("✅ База base.db успешно выгружена в Cloud Firestore!", show_alert=True)
        else:
            err_msg = f"❌ {firebase_manager.last_error or 'Ошибка синхронизации!'}"
            await query.answer(err_msg[:190], show_alert=True)
        await show_admin_firebase_menu(query)
        return

    if data == "admin_firebase_restore":
        if user.id not in ADMIN_IDS:
            await query.answer("❌ Доступ запрещен!", show_alert=True)
            return
        ok = firebase_manager.download_db_on_startup()
        if ok:
            db_init()
            await query.answer("📥 База base.db успешно восстановлена из Cloud Firestore!", show_alert=True)
        else:
            err_msg = f"❌ {firebase_manager.last_error or 'Не удалось восстановить базу из Firestore.'}"
            await query.answer(err_msg[:190], show_alert=True)
        await show_admin_firebase_menu(query)
        return

    # Клановые профили и действия
    if data == "nav_clans_hub":
        await show_clans_hub(query, user.id, context)
        return

    if data.startswith("clan_info:"):
        clan_id = int(data.split(":")[1])
        await show_clan_profile_handler(query, clan_id, context)
        return

    if data.startswith("clan_members_detail:"):
        clan_id = int(data.split(":")[1])
        await show_clan_members_detail(query, clan_id)
        return

    if data.startswith("clan_fav_menu:"):
        clan_id = int(data.split(":")[1])
        await show_clan_favorites_menu(query, clan_id)
        return

    if data.startswith("clan_toggle_fav:"):
        _, clan_id_str, gkey = data.split(":")
        clan_id = int(clan_id_str)
        if toggle_clan_favorite_gift(clan_id, gkey):
            await query.answer("Избранное клана обновлено!")
            await show_clan_favorites_menu(query, clan_id)
        else:
            await query.answer("Максимум 7 избранных подарков у клана!", show_alert=True)
        return

    if data.startswith("clan_donate_gift_menu:"):
        clan_id = int(data.split(":")[1])
        await show_clan_donate_gift_menu(query, clan_id, user.id)
        return

    if data.startswith("clan_donate_gift_do:"):
        _, clan_id_str, item_id_str = data.split(":")
        await execute_clan_donate_gift(query, int(clan_id_str), int(item_id_str), user.id)
        return

    # Админ-выдача подарков по фильтрам цены и моделей
    if data.startswith("adm_filt_price:"):
        target_id = int(data.split(":")[1])
        await show_admin_nft_price_tiers(query, target_id)
        return

    if data.startswith("adm_filt_model:"):
        target_id = int(data.split(":")[1])
        await show_admin_nft_model_groups(query, target_id)
        return

    if data.startswith("adm_back_filters:"):
        target_id = int(data.split(":")[1])
        target = get_user_by_target(str(target_id))
        tname = normalize_telegram_name(target["first_name"] if target else "Игрок")
        await show_admin_nft_filter_selector(query, target_id, tname)
        return

    if data.startswith("adm_items:"):
        _, ftype, fkey, target_id, page = data.split(":")
        await show_admin_nft_items_page(query, ftype, fkey, int(target_id), int(page))
        return

    if data.startswith("adm_give_do:"):
        _, gift_key, target_id = data.split(":")
        await execute_admin_give_nft(query, gift_key, int(target_id), context)
        return

    # Улучшения Plush Pepe и слоты
    if data == "shop_slots_menu":
        await show_slots_shop_page(query, user.id)
        return

    if data.startswith("upgrade_page:"):
        page = int(data.split(":")[1])
        await show_shop_page(query, user.id, page)
        return

    if data.startswith("upgrade_item:"):
        item_id = int(data.split(":")[1])
        await show_upgrade_item_preview(query, item_id, user.id)
        return

    if data.startswith("upgrade_do:"):
        item_id = int(data.split(":")[1])
        await execute_gift_upgrade(query, item_id, user.id, context)
        return

    # Маркет фильтры и торговля
    if data == "market_filter_price_menu":
        await show_market_filter_price_menu(query)
        return

    if data == "market_filter_model_menu":
        await show_market_filter_model_menu(query)
        return

    if data.startswith("market_view:"):
        _, ftype, fkey, page = data.split(":")
        await show_market_view_page(query, ftype, fkey, int(page))
        return

    if data.startswith("market_lot:"):
        listing_id = int(data.split(":")[1])
        await show_market_lot_detail(query, listing_id, user.id)
        return

    if data.startswith("market_lot_item:"):
        item_id = int(data.split(":")[1])
        lot = get_market_listing_by_item(item_id)
        if not lot:
            await query.answer("❌ Активный лот не найден.", show_alert=True)
            return
        await show_market_lot_detail(query, lot["id"], user.id)
        return

    if data.startswith("market_buy:"):
        listing_id = int(data.split(":")[1])
        ok, deal, err = buy_market_listing(listing_id, user.id)
        if not ok:
            await query.answer(f"❌ {err}", show_alert=True)
            return
        lot = deal["lot"]
        price = deal["price"]
        fee = deal["fee"]
        payout = deal["payout"]
        try:
            await context.bot.send_message(
                chat_id=lot["seller_id"],
                text=(
                    f"🎉 <b>Ваш лот на NFT Маркете продан!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"• Подарок: <b>Plush Pepe #{lot['collection_id']}</b> ({clean_html(lot['model_name'])} | {clean_html(lot['bg_name'])})\n"
                    f"• Цена продажи: <b>{price:,} ⭐</b>\n"
                    f"• Комиссия рынка 15%: <b>-{fee:,} ⭐</b>\n"
                    f"• Зачислено на баланс: <b>+{payout:,} ⭐</b>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=quick_nav_keyboard(),
            )
        except Exception:
            pass

        msg_txt = (
            f"✅ <b>Поздравляем с покупкой!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Вы приобрели улучшенный <b>Plush Pepe #{lot['collection_id']}</b>!\n"
            f"• Модель: <b>{clean_html(lot['model_name'])}</b>\n"
            f"• Фон: <b>{clean_html(lot['bg_name'])}</b> ({lot['bg_rarity']:.2f}%)\n"
            f"• Списано с баланса: <b>{price:,} ⭐</b>\n\n"
            f"Подарок уже добавлен в вашу коллекцию!"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗂 Открыть коллекцию", callback_data="nav_collection_page:1")],
            [InlineKeyboardButton("🛒 Вернуться в маркет", callback_data="nav_market")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
        ])
        if query.message.photo:
            await query.edit_message_caption(caption=msg_txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(msg_txt, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("market_cancel:"):
        listing_id = int(data.split(":")[1])
        ok, err = cancel_market_listing(listing_id, user.id)
        if ok:
            await query.answer("✅ Лот снят с продажи и возвращён в коллекцию!", show_alert=True)
            await show_market_my_offers(query, user.id)
        else:
            await query.answer(f"❌ {err}", show_alert=True)
        return

    if data.startswith("market_cancel_item:"):
        item_id = int(data.split(":")[1])
        lot = get_market_listing_by_item(item_id)
        if not lot:
            await query.answer("❌ Активный лот не найден.", show_alert=True)
            return
        ok, err = cancel_market_listing(lot["id"], user.id)
        if ok:
            await query.answer("✅ Подарок снят с маркета!", show_alert=True)
            await show_collection_page(query, user.id, 1)
        else:
            await query.answer(f"❌ {err}", show_alert=True)
        return

    if data == "market_create_offer":
        await show_market_create_offer_list(query, user.id)
        return

    if data == "market_my_offers":
        await show_market_my_offers(query, user.id)
        return

    if data == "market_history":
        await show_market_history_page(query, user.id)
        return

    if data == "nav_main":
        banner_img = await generate_main_menu_banner()
        if query.message.photo:
            try: await query.message.delete()
            except: pass
        await query.message.reply_photo(
            photo=InputFile(banner_img, filename="menu.png"),
            caption="🏠 <b>Главное меню New NFT Bot:</b>\nВыберите нужный раздел кнопками ниже:",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(user.id)
        )
        return

    if data == "nav_profile":
        await show_profile_handler(query, user.id, context)
        return

    if data == "nav_info":
        await show_info_page(query, context)
        return

    if data == "info_group_guide":
        await show_group_guide(query, context)
        return

    if data == "info_privacy":
        await show_privacy_policy(query)
        return

    if data == "info_rules":
        await show_rules_page(query)
        return

    if data == "nav_market":
        await show_market_hub(query)
        return

    if data == "bg_reset":
        await bg_reset_handler(query, user.id, context)
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

    if data.startswith("clan_list:"):
        page = int(data.split(":")[1])
        await show_clans_list(query, page)
        return

    if data.startswith("clan_join:"):
        clan_id = int(data.split(":")[1])
        if get_user_clan(user.id):
            await query.answer("Вы уже состоите в клане!", show_alert=True)
            return
        if add_user_to_clan(user.id, clan_id):
            await query.answer("🎉 Вы успешно вступили в клан!", show_alert=True)
            await show_clan_profile_handler(query, clan_id, context)
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
        await show_clan_profile_handler(query, clan_id, context)
        return

    if data.startswith("clan_apply:"):
        clan_id = int(data.split(":")[1])
        if add_clan_request(clan_id, user.id):
            await query.answer("📩 Заявка отправлена лидеру клана!", show_alert=True)
        else:
            await query.answer("⚠️ Вы уже подавали заявку!", show_alert=True)
        return

    if data.startswith("clan_kick:"):
        target_id = int(data.split(":")[1])
        clan = get_user_clan(user.id)
        if clan and clan["owner_id"] == user.id:
            remove_user_from_clan(target_id)
            await query.answer("Игрок исключён из клана.")
            await show_clan_members_detail(query, clan["id"])
        return

    if data.startswith("clan_leave:"):
        remove_user_from_clan(user.id)
        await query.answer("Вы покинули клан.")
        await show_clans_hub(query, user.id, context)
        return

    if data.startswith("clan_delete_confirm:"):
        clan_id = int(data.split(":")[1])
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔥 Да, расформировать", callback_data=f"clan_delete_do:{clan_id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data=f"clan_info:{clan_id}")]
        ])
        await query.edit_message_text("⚠️ Вы действительно хотите <b>РАСФОРМИРОВАТЬ</b> клан?", parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("clan_delete_do:"):
        clan_id = int(data.split(":")[1])
        delete_clan(clan_id)
        await query.answer("Клан расформирован.")
        await show_clans_hub(query, user.id, context)
        return

    if data.startswith("clan_upgrade:"):
        clan_id = int(data.split(":")[1])
        clan = get_clan_by_id(clan_id)
        cost = get_clan_upgrade_cost(clan["max_members"])

        if upgrade_clan_slots(clan_id, cost):
            await query.answer(f"🎉 Места расширены до {clan['max_members']+15}!", show_alert=True)
            await show_clan_profile_handler(query, clan_id, context)
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
                InlineKeyboardButton("❌ Отклонить", callback_data=f"clan_req_decline:{clan_id}:{r['user_id']}")
            ])

        buttons.append([InlineKeyboardButton("⬅️ В профиль клана", callback_data=f"clan_info:{clan_id}")])
        kb = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data.startswith("clan_req_accept:"):
        _, clan_id, req_user_id = data.split(":")
        if add_user_to_clan(int(req_user_id), int(clan_id)):
            await query.answer("Игрок принят в клан!")
        else:
            await query.answer("Нет свободных мест!", show_alert=True)
        await show_clan_profile_handler(query, int(clan_id), context)
        return

    if data.startswith("clan_req_decline:"):
        _, clan_id, req_user_id = data.split(":")
        remove_clan_request(int(clan_id), int(req_user_id))
        await query.answer("Заявка отклонена.")
        await show_clan_profile_handler(query, int(clan_id), context)
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
            await show_slots_shop_page(query, user.id)
        else:
            await query.answer("❌ Недостаточно Stars!", show_alert=True)
        return

    if data == "sell_all_confirm":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Продать все", callback_data="sell_all_do"),
                InlineKeyboardButton("❌ Отмена", callback_data="nav_collection_page:1"),
            ]
        ])
        await query.edit_message_text(
            "⚠️ <b>Продать все обычные предметы из коллекции?</b>\n"
            "Избранные (⭐), улучшенные (✨) и выставленные на маркет предметы затронуты не будут.",
            parse_mode=ParseMode.HTML,
            reply_markup=kb,
        )
        return

    if data == "sell_all_do":
        count, stars = sell_all_non_favorites(user.id)
        await query.answer(f"💰 Продано {count} обычных предметов за {stars:,} Stars!", show_alert=True)
        await show_collection_page(query, user.id, 1)
        return

    if data == "nav_bonus":
        remaining = claim_daily_bonus(user.id)
        if remaining is None:
            text = "🎁 <b>Ежедневный бонус получен:</b> <b>+50 Stars ⭐</b> и <b>+250 XP ⚡️</b>!"
        else:
            text = f"⏳ Бонус уже был получен сегодня.\nПопробуйте снова через {seconds_to_hms(remaining)}."

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🗂 В коллекцию", callback_data="nav_collection_page:1")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")]
        ])
        if query.message.photo:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        else:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
        return

    if data == "nav_cases_hub":
        db_user = get_or_create_user(user.id, "", "")
        text = (
            f"🎰 <b>Mystery Cases Hub</b>\n\n"
            f"Ваш баланс: <b>{fmt_stars_rub(db_user['balance_stars'])}</b>\n\n"
            f"1. 📦 <b>Кейс 1</b> — 100 ⭐\n"
            f"2. 🔷 <b>Кейс 2</b> — 500 ⭐\n"
            f"3. 🟣 <b>Кейс 3</b> — 2,500 ⭐\n"
            f"4. 👑 <b>Кейс 4</b> — 10,000 ⭐\n"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Кейс 1 (100⭐)", callback_data="open_case:tier1")],
            [InlineKeyboardButton("🔷 Кейс 2 (500⭐)", callback_data="open_case:tier2")],
            [InlineKeyboardButton("🟣 Кейс 3 (2500⭐)", callback_data="open_case:tier3")],
            [InlineKeyboardButton("👑 Кейс 4 (10000⭐)", callback_data="open_case:tier4")],
            [
                InlineKeyboardButton("🗂 Коллекция", callback_data="nav_collection_page:1"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
            ],
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

        clan = get_user_clan(user.id)
        clan_bonus_pct = 0.0
        if clan:
            _, _, _, _, clan_bonus_pct = calculate_clan_level_info(clan["xp"])

        won_gift = roll_gift_from_pool(tier["pool"], bonus_pct=clan_bonus_pct)

        if db_user["auto_sell"]:
            add_user_stars(user.id, won_gift.stars)
            res_note = f"💰 <b>Авто-продажа:</b> +{fmt_stars_rub(won_gift.stars)}!"
        else:
            success = add_to_collection(user.id, won_gift.key)
            if not success:
                add_user_stars(user.id, won_gift.stars)
                res_note = f"⚠️ Инвентарь переполнен! Авто-продажа за {fmt_stars_rub(won_gift.stars)}."
            else:
                res_note = f"✅ Сохранено в коллекцию! (+{won_gift.xp} XP)"

        cap = (
            f"🎰 <b>Открытие {tier['name']}!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎉 Выпал: <b>{won_gift.name}</b>!\n"
            f"• Модель: <b>{won_gift.model_name}</b>\n"
            f"• Ценность: <b>{fmt_stars_rub(won_gift.stars)}</b>\n\n"
            f"{res_note}"
        )

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎰 Еще раз ({tier['price']}⭐)", callback_data=f"open_case:{tier_key}")],
            [InlineKeyboardButton("🎰 К кейсам", callback_data="nav_cases_hub")],
            [InlineKeyboardButton("🗂 В коллекцию", callback_data="nav_collection_page:1")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
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
                await query.answer("❌ Это не ваш подарок!", show_alert=True)
                return
            if drop["resolved"]:
                await query.answer("⚠️ Уже обработано!", show_alert=True)
                return

            gift = GIFTS_BY_KEY.get(drop["gift_key"])
            resolve_pending_drop(drop_id)

            if action == "keep":
                added = add_to_collection(user.id, gift.key)
                if added:
                    res = f"✅ <b>{gift.name}</b> сохранён в коллекцию! (+{gift.xp} XP)"
                else:
                    sell_from_pending(user.id, gift.key, gift.stars)
                    res = f"⚠️ Инвентарь переполнен! <b>{gift.name}</b> продан за {fmt_stars_rub(gift.stars)}!"
            else:
                sell_from_pending(user.id, gift.key, gift.stars)
                res = f"💰 Продано <b>{gift.name}</b> за {fmt_stars_rub(gift.stars)}! (+{gift.xp // 2} XP)"

            kb = quick_nav_keyboard()
            if query.message.photo:
                await query.edit_message_caption(caption=res, parse_mode=ParseMode.HTML, reply_markup=kb)
            else:
                await query.edit_message_text(res, parse_mode=ParseMode.HTML, reply_markup=kb)
            return

        if action == "view_top_user":
            target_id = int(rest[0])
            back_page = int(rest[1])
            target = get_or_create_user(target_id, "", "")

            if target["hide_top"] and user.id not in ADMIN_IDS:
                await query.answer("🔒 Профиль скрыт настройками приватности игрока.", show_alert=True)
                return

            await show_profile_handler(query, target_id, context, back_to_top_page=back_page)
            return

        if action == "view_item":
            item_id = int(rest[0])
            page = int(rest[1]) if len(rest) > 1 else 1
            item = get_collection_item(item_id)
            if not item or item["user_id"] != user.id:
                await query.answer("Предмет не найден.", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            if not g:
                await query.answer("Ошибка данных предмета.", show_alert=True)
                return

            if item["is_upgraded"]:
                bg_obj = next((b for b in PLUSHPEPE_BACKDROPS if b.name == item["bg_name"]), None)
                rarity_lbl = bg_obj.rarity_label if bg_obj else "Редкий"
                est_val = item["estimated_stars"] or g.stars

                btns = []
                if item["is_listed"]:
                    btns.append([InlineKeyboardButton("🔍 Открыть лот на маркете", callback_data=f"market_lot_item:{item_id}")])
                    btns.append([InlineKeyboardButton("❌ Снять с маркета", callback_data=f"market_cancel_item:{item_id}")])
                else:
                    fav_text = "❌ Убрать из Избранного" if item["is_favorite"] else "⭐ В избранное"
                    btns.append([InlineKeyboardButton(fav_text, callback_data=f"toggle_fav:{item_id}:{page}")])
                    btns.append([InlineKeyboardButton("🛒 Выставить на маркет", callback_data=f"market_sell_start:{item_id}")])
                    btns.append([InlineKeyboardButton("🎁 Передать бесплатно", callback_data=f"gift_transfer_start:{item_id}")])
                    btns.append([InlineKeyboardButton(f"💰 Быстрая продажа ({est_val:,} ⭐)", callback_data=f"sell_item:{item_id}:{page}")])
                btns.append([
                    InlineKeyboardButton("🗂 Назад в коллекцию", callback_data=f"nav_collection_page:{page}"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main"),
                ])
                kb = InlineKeyboardMarkup(btns)

                status_str = "🛒 Выставлен на маркете" if item["is_listed"] else "🎒 В коллекции"
                cap = (
                    f"✨ <b>Улучшенный Plush Pepe #{item_id}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🧸 Модель: <b>{clean_html(item['model_name'])}</b> (редкость: <b>{item['model_rarity']:.1f}%</b>)\n"
                    f"🎨 Фон: <b>{clean_html(item['bg_name'])}</b> — {clean_html(item['bg_palette'])}\n"
                    f"💎 Шанс фона: <b>{item['bg_rarity']:.2f}%</b> ({rarity_lbl})\n"
                    f"💰 Оценочная стоимость: <b>{fmt_stars_rub(est_val)}</b>\n"
                    f"⭐ В Избранном: <b>{'Да' if item['is_favorite'] else 'Нет'}</b>\n"
                    f"📌 Статус: <b>{status_str}</b>\n"
                    f"━━━━━━━━━━━━━━━━━━"
                )
                try:
                    card_io = await generate_upgraded_gift_image(
                        item["model_file"], item["model_name"], item["bg_name"],
                        item["bg_center_hex"], item["bg_edge_hex"], item["bg_rarity"], item_id
                    )
                    await query.message.reply_photo(photo=InputFile(card_io, filename=f"pepe_{item_id}.png"), caption=cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                    await query.message.delete()
                    return
                except Exception as e:
                    log.warning("Ошибка рендера улучшенного предмета: %s", e)

                await query.edit_message_text(cap, parse_mode=ParseMode.HTML, reply_markup=kb)
                return

            fav_text = "❌ Убрать из Избранного" if item["is_favorite"] else "⭐ В избранное"
            btns = [[InlineKeyboardButton(fav_text, callback_data=f"toggle_fav:{item_id}:{page}")]]
            if g.key == "pepe_heart":
                btns.append([InlineKeyboardButton(f"✨ Улучшить ({UPGRADE_COST_STARS:,} ⭐)", callback_data=f"upgrade_item:{item_id}")])
            btns.append([InlineKeyboardButton(f"💰 Продать за {g.stars:,} Stars", callback_data=f"sell_item:{item_id}:{page}")])
            btns.append([
                InlineKeyboardButton("🗂 Назад в коллекцию", callback_data=f"nav_collection_page:{page}"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")
            ])
            kb = InlineKeyboardMarkup(btns)

            cap = (
                f"<b>{g.name}</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"• Модель: <b>{g.model_name}</b>\n"
                f"• Бонус опыта: <b>+{g.xp} XP</b>\n"
                f"• Стоимость: {fmt_stars_rub(g.stars)}\n"
                f"• В Избранном: <b>{'Да ⭐' if item['is_favorite'] else 'Нет'}</b>\n"
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
            item = get_collection_item(item_id)
            if item and item["is_listed"]:
                await query.answer("❌ Нельзя добавить в избранное предмет, который на маркете!", show_alert=True)
                return
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
            if item["is_listed"]:
                await query.answer("❌ Сначала снимите предмет с маркета!", show_alert=True)
                return

            g = GIFTS_BY_KEY.get(item["gift_key"])
            sell_price = item["estimated_stars"] if (item["is_upgraded"] and item["estimated_stars"]) else g.stars
            remove_from_collection(item_id, user.id)
            add_user_stars(user.id, sell_price)

            await query.answer(f"💰 Продано за {sell_price:,} Stars!", show_alert=True)
            await show_collection_page(query, user.id, page)
            return

# ---------------------------------------------------------------------------
# КОМАНДЫ БОТА
# ---------------------------------------------------------------------------

async def ensure_not_banned(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return True
    is_banned, until_ts, reason, hours = is_user_banned(user.id)
    if is_banned and user.id not in ADMIN_IDS:
        ban_text, ban_kb = format_ban_message(until_ts, reason, hours)
        if update.message:
            await update.message.reply_text(ban_text, parse_mode=ParseMode.HTML, reply_markup=ban_kb)
        return False
    return True

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
    user = update.effective_user
    get_or_create_user(user.id, user.username, user.first_name)
    banner_img = await generate_main_menu_banner()
    await update.message.reply_photo(
        photo=InputFile(banner_img, filename="menu.png"),
        caption=(
            f"👋 <b>Привет, {clean_html(user.first_name)}! Добро пожаловать в New NFT Bot!</b>\n\n"
            "Пишите слово <code>NFT</code> в группах, чтобы выбивать редчайшие Telegram Gifts! 🎁\n\n"
            "• Вступайте в кланы, качайте уровень клана и гербы\n"
            "• Кастомизируйте профиль уникальными фонами\n"
            "• Исследуйте NFT Маркет и соревнуйтесь в ТОП-100\n"
            f"• Поддержка: {SUPPORT_HANDLE}\n\n"
            "Используйте кнопки меню для комфортного управления:"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(user.id)
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
    await show_info_page(update, context)

async def cmd_profile_alias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
    await show_profile_handler(update, update.effective_user.id, context)

async def cmd_clans(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
    await show_clans_hub(update, update.effective_user.id, context)

async def cmd_market(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
    await show_market_hub(update)

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return

    conn = db_connect()
    try:
        total_users = conn.execute("SELECT COUNT(*) as cnt FROM users").fetchone()["cnt"]
        total_banned = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_banned=1").fetchone()["cnt"]
        total_clans = conn.execute("SELECT COUNT(*) as cnt FROM clans").fetchone()["cnt"]
    finally:
        conn.close()

    text = (
        "👑 <b>Панель администратора</b>\n"
        f"• Пользователей: {total_users:,}\n"
        f"• Заблокировано: {total_banned:,}\n"
        f"• Кланов: {total_clans:,}\n\n"
        "Выберите действие:"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ Выдать Звёзды", callback_data="admin_give_stars_start")],
        [InlineKeyboardButton("🎁 Выдать NFT-подарок", callback_data="admin_give_nft_start")],
        [
            InlineKeyboardButton("🔨 Забанить игрока", callback_data="admin_ban_start"),
            InlineKeyboardButton("🔓 Разбанить игрока", callback_data="admin_unban_start"),
        ],
        [InlineKeyboardButton("☁️ Firebase Облако (base.db)", callback_data="admin_firebase_menu")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="nav_main")],
    ])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)

async def cmd_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
    sender = update.effective_user
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("⚠️ <b>Использование:</b> <code>/pay <ID или @username> <сумма></code>", parse_mode=ParseMode.HTML)
        return

    target_str, amount_str = args[0], args[1]
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await update.message.reply_text("❌ Введите корректное число.")
        return

    amount = int(amount_str)
    target_user = get_user_by_target(target_str)

    if not target_user:
        await update.message.reply_text("❌ Игрок не найден.")
        return

    if target_user["user_id"] == sender.id:
        await update.message.reply_text("❌ Перевод самому себе невозможен.")
        return

    if not deduct_user_stars(sender.id, amount):
        await update.message.reply_text("❌ Недостаточно Stars на балансе.")
        return

    add_user_stars(target_user["user_id"], amount)
    receiver_name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")

    try:
        await context.bot.send_message(
            chat_id=target_user["user_id"],
            text=(
                f"💸 <b>Вам поступил перевод!</b>\n\n"
                f"От игрока: <b>{clean_html(sender.first_name)}</b>\n"
                f"Сумма: <b>+{amount:,} ⭐</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=quick_nav_keyboard()
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"💸 <b>Перевод выполнен!</b>\nПереведено <b>{amount:,} ⭐</b> игроку <b>{clean_html(receiver_name)}</b>.",
        parse_mode=ParseMode.HTML,
        reply_markup=quick_nav_keyboard()
    )

async def cmd_send_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_not_banned(update):
        return
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
        await update.message.reply_text("❌ Предмет не найден в вашей коллекции.")
        return
    if item["is_listed"]:
        await update.message.reply_text("❌ Предмет выставлен на маркет. Сначала снимите его с продажи.")
        return

    target_user = get_user_by_target(target_str)
    if not target_user or target_user["user_id"] == sender.id:
        await update.message.reply_text("❌ Некорректный получатель.")
        return

    ok, err = transfer_collection_item(item_id, sender.id, target_user["user_id"])
    if not ok:
        await update.message.reply_text(f"❌ {err}")
        return

    g = GIFTS_BY_KEY.get(item["gift_key"])
    gift_label = (
        f"✨ Plush Pepe #{item['id']} ({item['model_name']} | {item['bg_name']})"
        if item["is_upgraded"]
        else (g.name if g else item["gift_key"])
    )
    receiver_name = normalize_telegram_name(target_user["first_name"] or target_user["username"] or "Игрок")

    try:
        await context.bot.send_message(
            chat_id=target_user["user_id"],
            text=(
                f"🎁 <b>Вам подарен NFT!</b>\n\n"
                f"От игрока: <b>{clean_html(sender.first_name)}</b>\n"
                f"Предмет: <b>{clean_html(gift_label)}</b>!\n"
                f"Предмет уже в вашей коллекции."
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=quick_nav_keyboard()
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"🎁 <b>Подарок бесплатно передан!</b>\nПредмет <b>{clean_html(gift_label)}</b> отправлен игроку <b>{clean_html(receiver_name)}</b>!",
        parse_mode=ParseMode.HTML,
        reply_markup=quick_nav_keyboard()
    )

# ---------------------------------------------------------------------------
# ТОЧКА ВХОДА (MAIN)
# ---------------------------------------------------------------------------

def main() -> None:
    # 1. Попытка восстановить сохраненную базу base.db из Cloud Firestore ПЕРЕД запуском
    # Защищает данные игроков и кланов от удаления при перезапуске на bot host.ru
    db_restored = False
    try:
        db_restored = firebase_manager.download_db_on_startup()
    except Exception as e:
        log.error(f"[Firestore] Ошибка скачивания базы при старте: {e}")

    # 2. Инициализация локальной базы SQLite и миграция таблиц (без затирания существующих данных)
    db_init()

    # 3. Выгружаем в Firestore при старте ТОЛЬКО если документа в облаке ещё не было (и не было ошибки загрузки!)
    if not db_restored and firebase_manager._cloud_doc_missing and not firebase_manager._startup_download_error:
        try:
            firebase_manager.upload_db_to_cloud(force=True)
        except Exception as e:
            log.error(f"[Firestore] Ошибка первой выгрузки базы в облако: {e}")

    # 4. Запускаем периодическую фоновую синхронизацию базы (каждые 60 сек)
    firebase_manager.start_periodic_sync(interval_seconds=60)

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )

    app = Application.builder().token(BOT_TOKEN).request(request).build()

    # 1. FSM Создания клана
    clan_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_clan_creation, pattern="^clan_create_start$"),
            CommandHandler("create_clan", start_clan_creation),
        ],
        states={
            WAIT_CLAN_TAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_tag_received)],
            WAIT_CLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_name_received)],
            WAIT_CLAN_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_desc_received)],
            WAIT_CLAN_TYPE: [CallbackQueryHandler(clan_type_selected, pattern="^ctype:")],
            WAIT_CLAN_FEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, clan_fee_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_clan_creation)],
        per_message=False,
        allow_reentry=True
    )

    # 2. FSM Выдачи Stars админом
    admin_give_stars_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_give_stars_start, pattern="^admin_give_stars_start$")],
        states={
            WAIT_ADMIN_GIVE_STARS_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_stars_user)],
            WAIT_ADMIN_GIVE_STARS_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_stars_amount)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        per_message=False,
        allow_reentry=True
    )

    # 3. FSM Выдачи NFT админом
    admin_give_nft_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_give_nft_start, pattern="^admin_give_nft_start$")],
        states={
            WAIT_ADMIN_GIVE_NFT_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_nft_user)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        per_message=False,
        allow_reentry=True
    )

    # 4. FSM Установки кастомного фона профиля игрока
    bg_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bg_change_start, pattern="^bg_change_start$")],
        states={
            WAIT_PROFILE_BG: [
                MessageHandler(filters.PHOTO, bg_photo_received),
                CallbackQueryHandler(bg_cancel, pattern="^bg_cancel$")
            ],
        },
        fallbacks=[CommandHandler("cancel", bg_cancel)],
        per_message=False,
        allow_reentry=True
    )

    # 5. FSM Бана пользователя
    admin_ban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_ban_start, pattern="^admin_ban_start$")],
        states={
            WAIT_ADMIN_BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_user_received)],
            WAIT_ADMIN_BAN_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_hours_received)],
            WAIT_ADMIN_BAN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ban_reason_received)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        per_message=False,
        allow_reentry=True
    )

    # 6. FSM Разбана пользователя
    admin_unban_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_unban_start, pattern="^admin_unban_start$")],
        states={
            WAIT_ADMIN_UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_unban_user_received)],
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$")
        ],
        per_message=False,
        allow_reentry=True
    )

    # 7. FSM Смены герба/аватарки клана
    clan_avatar_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(clan_avatar_start, pattern="^clan_avatar_start:")],
        states={
            WAIT_CLAN_AVATAR: [
                MessageHandler(filters.PHOTO, clan_avatar_photo_received),
                CallbackQueryHandler(clan_avatar_cancel, pattern="^clan_avatar_cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", clan_avatar_cancel)],
        per_message=False,
        allow_reentry=True
    )

    # 8. FSM Пополнения казны звездами
    clan_donate_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(clan_donate_stars_start, pattern="^clan_donate_stars_start:")],
        states={
            WAIT_CLAN_DONATE_STARS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, clan_donate_stars_amount),
                CallbackQueryHandler(clan_donate_cancel, pattern="^clan_donate_cancel$")
            ]
        },
        fallbacks=[CommandHandler("cancel", clan_donate_cancel)],
        per_message=False,
        allow_reentry=True
    )

    # 9. FSM Выставления лота на NFT Маркет
    market_offer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(market_sell_start, pattern="^market_sell_start:")],
        states={
            WAIT_MARKET_OFFER_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, market_offer_price_received),
                CallbackQueryHandler(market_offer_cancel, pattern="^market_offer_cancel$"),
            ]
        },
        fallbacks=[CommandHandler("cancel", market_offer_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # 10. FSM Бесплатной передачи подарка
    gift_transfer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(gift_transfer_start, pattern="^gift_transfer_start:")],
        states={
            WAIT_GIFT_TRANSFER_USER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, gift_transfer_user_received),
                CallbackQueryHandler(gift_transfer_cancel, pattern="^gift_transfer_cancel$"),
            ]
        },
        fallbacks=[CommandHandler("cancel", gift_transfer_cancel)],
        per_message=False,
        allow_reentry=True,
    )

    # 11. FSM Загрузки нового ключа Firebase (.json)
    admin_firebase_key_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_firebase_key_start, pattern="^admin_firebase_key_start$")],
        states={
            WAIT_ADMIN_FIREBASE_KEY: [
                MessageHandler(filters.Document.ALL | (filters.TEXT & ~filters.COMMAND), admin_firebase_key_received),
                CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$"),
            ]
        },
        fallbacks=[
            CommandHandler("cancel", admin_cancel),
            CallbackQueryHandler(admin_cancel, pattern="^admin_cancel$"),
        ],
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(clan_conv)
    app.add_handler(admin_give_stars_conv)
    app.add_handler(admin_give_nft_conv)
    app.add_handler(admin_ban_conv)
    app.add_handler(admin_unban_conv)
    app.add_handler(clan_avatar_conv)
    app.add_handler(clan_donate_conv)
    app.add_handler(bg_conv)
    app.add_handler(market_offer_conv)
    app.add_handler(gift_transfer_conv)
    app.add_handler(admin_firebase_key_conv)

    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("profile", cmd_profile_alias))
    app.add_handler(CommandHandler("pay", cmd_pay))
    app.add_handler(CommandHandler("send_gift", cmd_send_gift))
    app.add_handler(CommandHandler("clans", cmd_clans))
    app.add_handler(CommandHandler("market", cmd_market))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("info", lambda u, c: show_info_page(u, c)))

    app.add_handler(MessageHandler(filters.Regex(re.compile(r"^(кто я|я)$", re.IGNORECASE)), cmd_profile_alias))

    # Callback Queries и сообщения в группах
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_group_message))

    log.info("New NFT Gift Telegram Bot v12.0 запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
