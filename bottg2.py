import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import aiohttp
import json
import random
import string
from datetime import datetime, timedelta
import aiofiles  # Добавляем aiofiles для асинхронной работы с файлами

# Настройка логирования (уровень DEBUG для детализации)
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

SOCKET_IO_URL = "https://gsocket.trump.tg/socket.io/"
subscribers = {}  # Изменяем на словарь для совместимости с предыдущими предложениями
user_filters = {}
user_error_counts = {}
gift_stats = {}
daily_stats = {}
stats_cache = {"total_notifications": 0, "total_users": 0}  # Добавляем кэш для статистики
application = None
sid = None

GIFT_NAMES = {
    "5983471780763796287": "Santa Hat", "5936085638515261992": "Signet Ring", "5933671725160989227": "Precious Peach",
    "5936013938331222567": "Plush Pepe", "5913442287462908725": "Spiced Wine", "5915502858152706668": "Jelly Bunny",
    "5915521180483191380": "Durov's Cap", "5913517067138499193": "Perfume Bottle", "5882125812596999035": "Eternal Rose",
    "5882252952218894938": "Berry Box", "5857140566201991735": "Vintage Cigar", "5846226946928673709": "Magic Potion",
    "5845776576658015084": "Kissed Frog", "5825801628657124140": "Hex Pot", "5825480571261813595": "Evil Eye",
    "5841689550203650524": "Sharp Tongue", "5841391256135008713": "Trapped Heart", "5839038009193792264": "Skull Flower",
    "5837059369300132790": "Scared Cat", "5821261908354794038": "Spy Agaric", "5783075783622787539": "Homemade Cake",
    "5933531623327795414": "Genie Lamp", "6028426950047957932": "Lunar Snake", "6003643167683903930": "Party Sparkler",
    "5933590374185435592": "Jester Hat", "5821384757304362229": "Witch Hat", "5915733223018594841": "Hanging Star",
    "5915550639663874519": "Love Candle", "6001538689543439169": "Cookie Heart", "5782988952268964995": "Desk Calendar",
    "6001473264306619020": "Jingle Bells", "5980789805615678057": "Snow Mittens", "5836780359634649414": "Voodoo Doll",
    "5841632504448025405": "Mad Pumpkin", "5825895989088617224": "Hypno Lollipop", "5782984811920491178": "B-Day Candle",
    "5935936766358847989": "Bunny Muffin", "5933629604416717361": "Astral Shard", "5837063436634161765": "Flying Broom",
    "5841336413697606412": "Crystal Ball", "5821205665758053411": "Eternal Candle", "5936043693864651359": "Swiss Watch",
    "5983484377902875708": "Ginger Cookie", "5879737836550226478": "Mini Oscar", "5170594532177215681": "Lol Pop",
    "5843762284240831056": "Ion Gem", "5936017773737018241": "Star Notepad", "5868659926187901653": "Loot Bag",
    "5868348541058942091": "Love Potion", "5868220813026526561": "Toy Bear", "5868503709637411929": "Diamond Ring",
    "5167939598143193218": "Sakura Flower", "5981026247860290310": "Sleigh Bell", "5897593557492957738": "Top Hat",
    "5856973938650776169": "Record Player", "5983259145522906006": "Winter Wreath", "5981132629905245483": "Snow Globe",
    "5846192273657692751": "Electric Skull", "6023752243218481939": "Tama Gadget", "6003373314888696650": "Candy Cane",
    "5933793770951673155": "Neko Helmet"
}

def generate_t():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))

# Функции для асинхронной работы с файлами
async def save_subscribers():
    async with aiofiles.open("subscribers.json", "w") as f:
        await f.write(json.dumps(list(subscribers.keys())))

async def load_subscribers():
    global subscribers
    try:
        async with aiofiles.open("subscribers.json", "r") as f:
            data = await f.read()
            subscribers = {int(user_id): True for user_id in json.loads(data)}
    except FileNotFoundError:
        subscribers = {}

async def save_user_filters():
    async with aiofiles.open("filters.json", "w") as f:
        await f.write(json.dumps({user_id: list(filters) for user_id, filters in user_filters.items()}))

async def load_user_filters():
    global user_filters
    try:
        async with aiofiles.open("filters.json", "r") as f:
            data = await f.read()
            user_filters = {int(user_id): set(filters) for user_id, filters in json.loads(data).items()}
    except FileNotFoundError:
        user_filters = {}

# Функция для периодического логирования числа подписчиков
async def log_subscriber_count():
    while True:
        logger.info(f"Количество подписчиков: {len(subscribers)}")
        await asyncio.sleep(600)  # 600 секунд = 10 минут

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    user_id = update.message.from_user.id
    logger.debug(f"Start command received at {start_time} from user {user_id}")
    
    # Текст дисклеймера
    disclaimer = (
        "⚠️ <b>ВАЖНАЯ ИНФОРМАЦИЯ</b> ⚠️\n\n"
        "Этот бот предназначен только для информирования о новых подарках в Telegram.\n\n"
        "- Мы не несём ответственности за действия пользователей, включая возможное мошенничество или обман.\n"
        "- Будьте осторожны: некоторые пользователи могут использовать информацию из бота для обмана. Всегда проверяйте, с кем вы взаимодействуете.\n"
        "- Бот предоставляется \"как есть\". Мы не гарантируем его бесперебойную работу или точность информации.\n"
        "- Используя этот бот, вы соглашаетесь с тем, что делаете это на свой страх и риск.\n\n"
    )
    
    # Описание команд с исправленным <gift_name>
    commands_description = (
        "📋 <b>Доступные команды:</b>\n"
        "/enable — Включить уведомления о новых подарках 🔔\n"
        "/disable — Выключить уведомления 🚫\n"
        "/filter <i>gift_name</i> — Добавить фильтр для подарков 🎁\n"
        "/filter del <i>gift_name</i> — Удалить конкретный фильтр ❌\n"
        "/filter clear — Сбросить все фильтры 🗑️\n"
        "/filter list — Показать текущие фильтры 📜\n"
        "/stats — Посмотреть статистику подарков 📊\n"
        "/help — Показать список всех команд ℹ️\n\n"
        "Если вы согласны с условиями, выберите действие ниже:"
    )
    
    # Объединяем дисклеймер и описание команд
    full_message = disclaimer + commands_description
    
    keyboard = [
        [InlineKeyboardButton("Включить уведомления", callback_data='enable_notifications')],
        [InlineKeyboardButton("Выключить уведомления", callback_data='disable_notifications')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с обработкой ошибок
    try:
        if user_id not in subscribers:
            subscribers[user_id] = True
            await save_subscribers()
        await update.message.reply_text(
            full_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.debug(f"Start command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to send start message to user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Ведутся технические работы, новости в канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>",
            parse_mode='HTML'
        )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    query = update.callback_query
    user_id = query.from_user.id
    logger.debug(f"Button callback received at {start_time} from user {user_id}")
    await query.answer()
    try:
        if query.data == 'enable_notifications':
            subscribers[user_id] = True
            await save_subscribers()
            await query.edit_message_text(text="Уведомления включены")
            logger.info(f"User {user_id} enabled notifications. Current subscribers: {len(subscribers)}")
        elif query.data == 'disable_notifications':
            if user_id in subscribers:
                del subscribers[user_id]
                user_filters.pop(user_id, None)
                user_error_counts.pop(user_id, None)
                await save_subscribers()
                await save_user_filters()
            await query.edit_message_text(text="Уведомления выключены")
            logger.info(f"User {user_id} disabled notifications. Current subscribers: {len(subscribers)}")
        logger.debug(f"Button callback finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to handle button callback for user {user_id}: {str(e)}")

async def enable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    user_id = update.message.from_user.id
    logger.debug(f"Enable command received at {start_time} from user {user_id}")
    subscribers[user_id] = True
    user_error_counts[user_id] = 0
    try:
        await save_subscribers()
        await update.message.reply_text("Уведомления включены")
        logger.info(f"User {user_id} enabled notifications via /enable. Current subscribers: {len(subscribers)}")
        logger.debug(f"Enable command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to send enable message to user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Ведутся технические работы, новости в канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>",
            parse_mode='HTML'
        )

async def disable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    user_id = update.message.from_user.id
    logger.debug(f"Disable command received at {start_time} from user {user_id}")
    if user_id in subscribers:
        del subscribers[user_id]
        user_filters.pop(user_id, None)
        user_error_counts.pop(user_id, None)
        await save_subscribers()
        await save_user_filters()
    try:
        await update.message.reply_text("Уведомления выключены")
        logger.info(f"User {user_id} disabled notifications via /disable. Current subscribers: {len(subscribers)}")
        logger.debug(f"Disable command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to send disable message to user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Ведутся технические работы, новости в канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>",
            parse_mode='HTML'
        )

async def filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    user_id = update.message.from_user.id
    logger.debug(f"Filter command received at {start_time} from user {user_id}")
    args = context.args
    logger.debug(f"Filter args received: {args}")

    try:
        if not args:
            current_filters = user_filters.get(user_id, set())
            if current_filters:
                await update.message.reply_text(f"Ваши текущие фильтры: {', '.join(current_filters)}\nЧтобы добавить фильтр, используйте /filter <i>gift_name</i>\nЧтобы сбросить фильтр, используйте /filter clear\nПосмотреть список фильтров: /filter list\nУдалить один фильтр: /filter del <i>gift_name</i>")
            else:
                await update.message.reply_text("У вас нет активных фильтров. Используйте /filter <i>gift_name</i> для добавления фильтра.")
            logger.debug(f"Filter command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
            return

        if args[0].lower() == "clear":
            user_filters.pop(user_id, None)
            await save_user_filters()
            await update.message.reply_text("Фильтры сброшены. Теперь вы будете получать уведомления о всех подарках.")
            logger.debug(f"Filter command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
            return
        elif args[0].lower() == "list":
            current_filters = user_filters.get(user_id, set())
            if current_filters:
                await update.message.reply_text(f"Ваши текущие фильтры: {', '.join(current_filters)}")
            else:
                await update.message.reply_text("У вас нет активных фильтров.")
            logger.debug(f"Filter list command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
            return
        elif args[0].lower() == "del":
            if len(args) < 2:
                await update.message.reply_text("Укажите подарок для удаления: /filter del <i>gift_name</i>")
                logger.debug(f"Filter del command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
                return
            gift_to_remove = " ".join(args[1:])
            current_filters = user_filters.get(user_id, set())
            if not current_filters:
                await update.message.reply_text("У вас нет активных фильтров.")
                logger.debug(f"Filter del command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
                return
            valid_gifts = set(GIFT_NAMES.values())
            normalized_gifts = {gift.lower().replace(" ", "").replace("-", ""): gift for gift in valid_gifts}
            normalized_input = gift_to_remove.lower().replace(" ", "").replace("-", "")
            if normalized_input not in normalized_gifts:
                await update.message.reply_text(f"Подарок '{gift_to_remove}' не найден. Доступные подарки: {', '.join(valid_gifts)}")
                logger.debug(f"Filter del command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
                return
            gift_name = normalized_gifts[normalized_input]
            if gift_name in current_filters:
                current_filters.remove(gift_name)
                if current_filters:
                    user_filters[user_id] = current_filters
                    await update.message.reply_text(f"Подарок '{gift_name}' удалён из фильтров. Текущие фильтры: {', '.join(current_filters)}")
                else:
                    user_filters.pop(user_id, None)
                    await update.message.reply_text(f"Подарок '{gift_name}' удалён. Фильтры пусты.")
                await save_user_filters()
            else:
                await update.message.reply_text(f"Подарок '{gift_name}' не найден в ваших фильтрах.")
            logger.debug(f"Filter del command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
            return

        # Добавление нового фильтра
        gift_entry = " ".join(args)  # Собираем аргументы в строку (например, "Candy Cane")
        logger.debug(f"Processing gift entry: {gift_entry}")

        valid_gifts = set(GIFT_NAMES.values())
        normalized_gifts = {gift.lower().replace(" ", "").replace("-", ""): gift for gift in valid_gifts}
        logger.debug(f"Normalized gifts: {normalized_gifts}")

        normalized_input = gift_entry.lower().replace(" ", "").replace("-", "")
        logger.debug(f"Normalized gift entry: {normalized_input}")

        if normalized_input not in normalized_gifts:
            await update.message.reply_text(f"Подарок '{gift_entry}' не найден. Доступные подарки: {', '.join(valid_gifts)}")
            logger.debug(f"Gift not found: {gift_entry}")
            logger.debug(f"Filter command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
            return

        gift_name = normalized_gifts[normalized_input]
        logger.debug(f"Found gift: {gift_name}")

        # Получаем текущие фильтры или создаём новое множество
        current_filters = user_filters.get(user_id, set())
        current_filters.add(gift_name)  # Добавляем новый подарок
        user_filters[user_id] = current_filters  # Сохраняем обновлённое множество
        await save_user_filters()

        await update.message.reply_text(f"Фильтр добавлен: {gift_name}. Текущие фильтры: {', '.join(current_filters)}")
        logger.debug(f"Filter command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to process filter command for user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Ведутся технические работы, новости в канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>",
            parse_mode='HTML'
        )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    user_id = update.message.from_user.id
    logger.debug(f"Stats command received at {start_time} from user {user_id}")
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        today_stats = daily_stats.get(today, {})
        total_today = sum(today_stats.values())
        stats_message = (
            f"📊 Статистика:\n"
            f"Всего уведомлений: {stats_cache['total_notifications']}\n"
            f"Всего пользователей: {stats_cache['total_users']}\n\n"
            f"Статистика за сегодня ({today}):\nВсего подарков: {total_today}\n\n"
        )
        for gift_name, count in today_stats.items():
            stats_message += f"{gift_name}: {count}\n"
        stats_message += "\nОбщая статистика:\n"
        for gift_name, count in gift_stats.items():
            stats_message += f"{gift_name}: {count}\n"
        await update.message.reply_text(stats_message)
        logger.debug(f"Stats command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to send stats message to user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Ведутся технические работы, новости в канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>",
            parse_mode='HTML'
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    start_time = datetime.now()
    user_id = update.message.from_user.id
    logger.debug(f"Help command received at {start_time} from user {user_id}")
    help_text = (
        "📋 <b>Список команд:</b>\n"
        "/start — Запустить бота и получить приветственное сообщение 🚀\n"
        "/enable — Включить уведомления о новых NFT-подарках 🔔\n"
        "/disable — Выключить уведомления 🚫\n"
        "/filter <i>gift_name</i> — Добавить фильтр для подарков 🎁\n"
        "/filter del <i>gift_name</i> — Удалить конкретный фильтр ❌\n"
        "/filter clear — Сбросить все фильтры 🗑️\n"
        "/filter list — Показать текущие фильтры 📜\n"
        "/stats — Посмотреть статистику подарков 📊\n"
        "/help — Показать этот список команд ℹ️\n\n"
        "📢 Все новости в этом канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>"
    )
    try:
        await update.message.reply_text(help_text, parse_mode="HTML")
        logger.debug(f"Help command finished for user {user_id}, took {(datetime.now() - start_time).total_seconds()} seconds")
    except Exception as e:
        logger.error(f"Failed to send help message to user {user_id}: {str(e)}")
        await update.message.reply_text(
            "Ведутся технические работы, новости в канале: <a href=\"https://t.me/NewMintGift_channel\">@NewMintGift_channel</a>",
            parse_mode='HTML'
        )

async def send_notification(user_id, gift_data):
    try:
        gift_name = gift_data.get("gift_name", "Unknown Gift")
        gift_number = gift_data.get("number", "Unknown Number")
        description = gift_data.get("description", "No description available")
        image_preview = gift_data.get("image_preview", None)
        owner = gift_data.get("owner", "Unknown Owner")
        quantity = gift_data.get("quantity", "N/A")
        gift_url = gift_data.get("gift_url", "https://t.me/nft")

        # Фильтруем description, убираем всё, что связано с "Gifted by" или "Gifted to"
        description_lines = description.split('\n')
        filtered_lines = []
        for line in description_lines:
            line_lower = line.lower()
            if "gifted by" in line_lower or "gifted to" in line_lower:
                continue
            else:
                index = line_lower.find("gifted by")
                if index == -1:
                    index = line_lower.find("gifted to")
                if index != -1:
                    line = line[:index].rstrip()
                if line:
                    filtered_lines.append(line)
        filtered_description = '\n'.join(filtered_lines)

        # Формируем сообщение
        message = (
            f"🎁 <b>Новый подарок:</b> {gift_name} #{gift_number}\n"
            f"🖼️ {filtered_description}\n"
            f"👤 <b>Владелец:</b> {owner}\n"
            f"📊 <b>Количество:</b> {quantity}\n"
            f'<a href="{gift_url}">🔗 Посмотреть подарок</a>\n\n'
            f'<i>ℹ️ Если ссылка на подарок не открывается, подождите несколько секунд.</i>\n'
            f'<i>🗑️ Если чат стал тяжёлым из-за картинок, очистите историю: Настройки → Очистить историю.</i>'
        )

        if image_preview:
            await application.bot.send_photo(
                chat_id=user_id,
                photo=image_preview,
                caption=message,
                parse_mode='HTML'
            )
        else:
            await application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
        logger.info(f"Successfully sent message to {user_id}")
        user_error_counts[user_id] = 0
    except Exception as e:
        logger.error(f"Failed to send message to {user_id}: {str(e)}")
        user_error_counts[user_id] = user_error_counts.get(user_id, 0) + 1
        if user_error_counts[user_id] >= 3:
            logger.warning(f"User {user_id} has too many errors, removing from subscribers")
            if user_id in subscribers:
                del subscribers[user_id]
                user_filters.pop(user_id, None)
                user_error_counts.pop(user_id, None)
                await save_subscribers()
                await save_user_filters()

async def send_notification_to_all(gift_data):
    tasks = []
    for user_id in subscribers.copy():
        user_filter = user_filters.get(user_id, set())
        normalized_gift_name = gift_data.get("normalized_gift_name", "").lower().replace(" ", "").replace("-", "")
        normalized_user_filters = {filter_name.lower().replace(" ", "").replace("-", "") for filter_name in user_filter}
        logger.debug(f"User {user_id} filter: {user_filter}, normalized filters: {normalized_user_filters}, gift_name: {gift_data.get('gift_name')}, normalized for filter: {normalized_gift_name}")
        if not user_filter or normalized_gift_name in normalized_user_filters:
            logger.info(f"Sending notification to user {user_id} for gift {gift_data.get('gift_name')}")
            tasks.append(send_notification(user_id, gift_data))
    
    # Отправляем уведомления параллельно с учётом лимитов Telegram (30 сообщений в секунду)
    for i in range(0, len(tasks), 30):
        batch = tasks[i:i + 30]
        await asyncio.gather(*batch, return_exceptions=True)
        if i + 30 < len(tasks):
            await asyncio.sleep(1)  # Задержка 1 секунда между партиями

async def connect_socketio():
    global sid
    headers = {
        'Origin': 'https://see.tg',
        'Referer': 'https://see.tg/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 YaBrowser/25.2.0.0 Safari/537.36',
        'Content-Type': 'text/plain; charset=UTF-8',
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'ru,en;q=0.9',
        'Connection': 'keep-alive',
    }
    timeout = aiohttp.ClientTimeout(total=10)  # Увеличиваем таймаут до 10 секунд
    while True:
        try:
            async with aiohttp.ClientSession(cookies=None, connector=aiohttp.TCPConnector(ssl=True), timeout=timeout) as session:
                t_value = generate_t()
                params = {'EIO': '4', 'transport': 'polling', 't': t_value}
                async with session.get(SOCKET_IO_URL, params=params, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Failed to connect: {response.status}, Response: {await response.text()}")
                        await asyncio.sleep(10)
                        continue
                    text = await response.text()
                    json_start = text.find('{')
                    if json_start == -1:
                        logger.error("No JSON found in initial response")
                        await asyncio.sleep(10)
                        continue
                    json_data = text[json_start:]
                    data = json.loads(json_data)
                    sid = data['sid']
                    logger.info(f"Connected with SID: {sid}")

                t_value = generate_t()
                handshake_params = {'EIO': '4', 'transport': 'polling', 'sid': sid, 't': t_value}
                async with session.post(SOCKET_IO_URL, params=handshake_params, data='40', headers=headers) as response:
                    if response.status != 200:
                        text = await response.text()
                        logger.error(f"Handshake failed: {response.status}, Response: {text}")
                        await asyncio.sleep(10)
                        continue
                    text = await response.text()
                    logger.debug(f"Handshake response: {text}")

                while True:
                    try:
                        t_value = generate_t()
                        params = {'EIO': '4', 'transport': 'polling', 'sid': sid, 't': t_value}
                        async with session.get(SOCKET_IO_URL, params=params, headers=headers) as response:
                            if response.status != 200:
                                text = await response.text()
                                logger.error(f"Polling failed: {response.status}, Response: {text}")
                                break
                            text = await response.text()
                            logger.debug(f"Polling response: {text}")

                            messages = text.split('\x1e')
                            for message in messages:
                                if not message:
                                    continue
                                if message.startswith('42'):
                                    event_data = json.loads(message[2:])
                                    event_name, event_payload = event_data
                                    if event_name == 'message' and event_payload.get('type') == 'newMint':
                                        logger.info(f"Received newMint event: {event_payload}")
                                        gift_name_raw = event_payload.get('gift_name', 'Unknown Gift')
                                        gift_number = event_payload.get('number', 'Unknown Number')
                                        description = event_payload.get('description', 'No description available')
                                        image_preview = event_payload.get('image_preview', None)
                                        owner = event_payload.get('owner', {}).get('name', 'Unknown Owner')
                                        quantity = event_payload.get('Quantity', 'N/A')

                                        # Нормализация имени подарка
                                        normalized_gift_name = gift_name_raw.lower().replace(" ", "").replace("-", "")
                                        normalized_gifts = {gift.lower().replace(" ", "").replace("-", ""): gift for gift in GIFT_NAMES.values()}
                                        gift_name = normalized_gifts.get(normalized_gift_name, gift_name_raw)
                                        logger.debug(f"Raw gift name: {gift_name_raw}, Normalized: {normalized_gift_name}, Final gift name: {gift_name}")

                                        gift_slug = f"{gift_name.replace(' ', '')}-{gift_number}"
                                        gift_url = f"https://t.me/nft/{gift_slug}"

                                        gift_stats[gift_name] = gift_stats.get(gift_name, 0) + 1
                                        today = datetime.now().strftime('%Y-%m-%d')
                                        if today not in daily_stats:
                                            daily_stats[today] = {}
                                        daily_stats[today][gift_name] = daily_stats[today].get(gift_name, 0) + 1

                                        # Обновляем кэш статистики
                                        stats_cache["total_notifications"] += 1
                                        stats_cache["total_users"] = len(subscribers)

                                        gift_data = {
                                            "gift_name": gift_name,
                                            "normalized_gift_name": normalized_gift_name,
                                            "number": gift_number,
                                            "description": description,
                                            "image_preview": image_preview,
                                            "owner": owner,
                                            "quantity": quantity,
                                            "gift_url": gift_url
                                        }

                                        logger.info(f"Preparing to send notifications. Subscribers: {len(subscribers)}, User filters: {user_filters}")
                                        await send_notification_to_all(gift_data)
                                    elif event_name == 'message' and event_payload.get('type') == 'online':
                                        pass
                                elif message.startswith('0'):
                                    logger.debug("Received open message (already handled)")
                                elif message.startswith('1'):
                                    logger.debug("Received close message")
                                    break
                                elif message.startswith('2'):
                                    logger.debug("Received ping message")
                                    t_value = generate_t()
                                    async with session.post(SOCKET_IO_URL, params={'EIO': '4', 'transport': 'polling', 'sid': sid, 't': t_value}, data='3', headers=headers) as pong_response:
                                        pong_text = await pong_response.text()
                                        logger.debug(f"Pong response: {pong_text}")
                                elif message.startswith('3'):
                                    logger.debug("Received pong message")
                    except Exception as e:
                        logger.error(f"Error in polling loop: {str(e)}", exc_info=True)
                        break
                    await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error in connect_socketio: {str(e)}", exc_info=True)
            await asyncio.sleep(10)
            continue

async def main():
    global application
    telegram_token = '7807721394:AAEl0lCLsfBSK05XzD6LrWUe0i_ofcoQd7c'
    from telegram.request import HTTPXRequest
    http_client = HTTPXRequest(
        connect_timeout=60.0,
        read_timeout=60.0
    )
    application = Application.builder().token(telegram_token).request(http_client).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("enable", enable))
    application.add_handler(CommandHandler("disable", disable))
    application.add_handler(CommandHandler("filter", filter))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("help", help_command))
    await application.initialize()
    await load_subscribers()
    await load_user_filters()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")
    asyncio.create_task(connect_socketio())
    asyncio.create_task(log_subscriber_count())
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Stopping bot...")
    finally:
        await application.updater.stop()
        await application.stop()

if __name__ == '__main__':
    asyncio.run(main())
