import logging
import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from sheets import save_to_sheets, get_requests_by_date, update_request_status, get_all_pending_dates

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Стани розмови ---
NAME, AMOUNT, INSTALLMENTS, DATE, CONFIRM = range(5)

BOT_TOKEN = os.environ["BOT_TOKEN"]
RECEIVER_CHAT_ID = os.environ["RECEIVER_CHAT_ID"]

# ---------------------------------------------------------------------------
# Логіка дат
# ---------------------------------------------------------------------------

def get_next_payout_date(from_date: datetime) -> datetime:
    weekday = from_date.weekday()
    if weekday in (0, 1):
        days_ahead = 2 - weekday
    elif weekday in (2, 3):
        days_ahead = 4 - weekday
    else:
        days_ahead = 7 - weekday
    return from_date + timedelta(days=days_ahead)


def is_valid_payout_day(date: datetime) -> bool:
    return date.weekday() in (0, 2, 4)


def parse_date(text: str) -> datetime | None:
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def get_suggested_date(requested_date: datetime) -> tuple[datetime, bool]:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if requested_date < today:
        return get_next_payout_date(today), True
    if is_valid_payout_day(requested_date):
        payout_weekday = requested_date.weekday()
        request_weekday = today.weekday()
        valid_request_days = {0: (4, 5, 6), 2: (0, 1), 4: (2, 3)}
        if request_weekday in valid_request_days.get(payout_weekday, ()):
            return requested_date, False
        else:
            return get_next_payout_date(today), True
    else:
        return get_next_payout_date(requested_date), True


WEEKDAY_UA = {0: "понеділок", 1: "вівторок", 2: "середу",
              3: "четвер", 4: "п'ятницю", 5: "суботу", 6: "неділю"}

# ---------------------------------------------------------------------------
# Обробники розмови — подача заявки
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привіт! Це бот для запиту авансу.\n\nВведіть ваше *ім'я та прізвище*:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 3:
        await update.message.reply_text("❌ Введіть повне ім'я та прізвище:")
        return NAME
    context.user_data["name"] = name
    await update.message.reply_text(
        f"✅ *{name}*\n\nВкажіть *суму авансу* (тільки цифри, наприклад: 3000):",
        parse_mode="Markdown",
    )
    return AMOUNT


async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Введіть коректну суму (наприклад: 3000):")
        return AMOUNT

    context.user_data["amount"] = amount

    keyboard = ReplyKeyboardMarkup(
        [["1 місяць", "2 місяці", "3 місяці"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        f"✅ Сума: *{amount:,.0f} грн*\n\n"
        f"На скільки місяців розбити аванс?",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return INSTALLMENTS


async def get_installments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    mapping = {"1 місяць": 1, "2 місяці": 2, "3 місяці": 3}

    if text not in mapping:
        keyboard = ReplyKeyboardMarkup(
            [["1 місяць", "2 місяці", "3 місяці"]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await update.message.reply_text("❌ Оберіть варіант на клавіатурі:", reply_markup=keyboard)
        return INSTALLMENTS

    installments = mapping[text]
    context.user_data["installments"] = installments
    amount = context.user_data["amount"]
    per_month = amount / installments

    today = datetime.now()
    suggested = get_next_payout_date(today)
    suggested_str = suggested.strftime("%d.%m.%Y")
    weekday_str = WEEKDAY_UA[suggested.weekday()]

    if installments == 1:
        installment_info = f"💰 Повна сума: *{amount:,.0f} грн*"
    else:
        installment_info = f"💰 По *{per_month:,.0f} грн* × {installments} місяці"

    await update.message.reply_text(
        f"✅ {installment_info}\n\n"
        f"Введіть *бажану дату видачі* у форматі ДД.ММ.РРРР\n\n"
        f"💡 Найближча доступна: *{suggested_str}* ({weekday_str})",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    parsed = parse_date(text)

    if not parsed:
        await update.message.reply_text(
            "❌ Невірний формат. Введіть у форматі *ДД.ММ.РРРР*:",
            parse_mode="Markdown",
        )
        return DATE

    final_date, was_changed = get_suggested_date(parsed)
    final_str = final_date.strftime("%d.%m.%Y")
    weekday_str = WEEKDAY_UA[final_date.weekday()]
    context.user_data["date"] = final_str

    name = context.user_data["name"]
    amount = context.user_data["amount"]
    installments = context.user_data["installments"]
    per_month = amount / installments

    change_msg = ""
    if was_changed:
        change_msg = f"⚠️ Дату змінено на найближчу доступну: *{final_str}* ({weekday_str})\n\n"

    if installments == 1:
        installment_line = f"💰 Сума: *{amount:,.0f} грн* (без розбивки)"
    else:
        installment_line = f"💰 Сума: *{amount:,.0f} грн* → по *{per_month:,.0f} грн* × {installments} міс."

    keyboard = ReplyKeyboardMarkup([["✅ Підтвердити", "❌ Скасувати"]], resize_keyboard=True)
    await update.message.reply_text(
        f"{change_msg}"
        f"📋 *Перевірте дані заявки:*\n\n"
        f"👤 Ім'я: *{name}*\n"
        f"{installment_line}\n"
        f"📅 Дата видачі: *{final_str}* ({weekday_str})\n\n"
        f"Все вірно?",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if "Скасувати" in text:
        await update.message.reply_text("❌ Заявку скасовано. /start — нова заявка.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if "Підтвердити" not in text:
        await update.message.reply_text("Оберіть дію на клавіатурі 👇")
        return CONFIRM

    name = context.user_data["name"]
    amount = context.user_data["amount"]
    installments = context.user_data["installments"]
    date = context.user_data["date"]
    user = update.effective_user
    submitted_at = datetime.now().strftime("%d.%m.%Y %H:%M")
    per_month = amount / installments

    # Зберігаємо в Google Sheets
    try:
        row_index = save_to_sheets(name, amount, installments, date, user.id, user.username or "—", submitted_at)
        sheets_status = "✅ Збережено в таблиці"
        logger.info(f"Sheets OK: {name}, {amount}, {date}, row={row_index}")
    except Exception as e:
        logger.error(f"Sheets FAILED: {type(e).__name__}: {e}")
        sheets_status = f"⚠️ Помилка запису: {type(e).__name__}"
        row_index = None

    # Повідомлення користувачу
    if installments == 1:
        installment_line = f"💰 {amount:,.0f} грн (без розбивки)"
    else:
        installment_line = f"💰 {amount:,.0f} грн → по {per_month:,.0f} грн × {installments} міс."

    await update.message.reply_text(
        f"🎉 *Заявку подано!*\n\n"
        f"👤 {name}\n"
        f"{installment_line}\n"
        f"📅 Дата видачі: {date}\n"
        f"🕐 Дата звернення: {submitted_at}\n\n"
        f"{sheets_status}\n\nОчікуйте підтвердження від бухгалтера.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Повідомлення бухгалтеру з кнопками
    username_display = f"@{user.username}" if user.username else f"ID: {user.id}"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Прийняти", callback_data=f"approve:{user.id}:{row_index}:{date}"),
            InlineKeyboardButton("❌ Відхилити", callback_data=f"reject:{user.id}:{row_index}:{date}"),
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=RECEIVER_CHAT_ID,
            text=(
                f"💸 *Нова заявка на аванс*\n\n"
                f"👤 *{name}*\n"
                f"{installment_line}\n"
                f"📅 Дата видачі: *{date}*\n"
                f"🕐 Подано: {submitted_at}\n"
                f"📱 Telegram: {username_display}"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info(f"Notification sent to {RECEIVER_CHAT_ID}")
    except Exception as e:
        logger.error(f"Notification FAILED: {type(e).__name__}: {e}")

    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Обробник кнопок бухгалтера (Прийняти / Відхилити)
# ---------------------------------------------------------------------------

async def handle_accountant_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data.split(":")
    action = data[0]
    employee_chat_id = int(data[1])
    row_index = data[2]
    date = data[3]

    if action == "approve":
        status = "Схвалено"
        emoji = "✅"
        employee_msg = f"✅ Вашу заявку на аванс (*{date}*) *схвалено*! Очікуйте повідомлення коли можна отримати."
    else:
        status = "Відхилено"
        emoji = "❌"
        employee_msg = f"❌ На жаль, вашу заявку на аванс (*{date}*) *відхилено*. Зверніться до бухгалтера за деталями."

    # Оновлюємо статус в таблиці
    try:
        if row_index and row_index != "None":
            update_request_status(int(row_index), status)
        logger.info(f"Status updated: row={row_index}, status={status}")
    except Exception as e:
        logger.error(f"Status update FAILED: {e}")

    # Редагуємо повідомлення бухгалтера — прибираємо кнопки
    original_text = query.message.text
    await query.edit_message_text(
        text=f"{original_text}\n\n{emoji} *{status}*",
        parse_mode="Markdown",
        reply_markup=None,
    )

    # Повідомляємо співробітника
    try:
        await context.bot.send_message(
            chat_id=employee_chat_id,
            text=employee_msg,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Employee notification FAILED: {e}")


# ---------------------------------------------------------------------------
# Команда /ready — аванси готові
# ---------------------------------------------------------------------------

async def ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Перевіряємо чи це бухгалтер
    if str(update.effective_user.id) != str(RECEIVER_CHAT_ID):
        await update.message.reply_text("⛔ Ця команда тільки для бухгалтера.")
        return

    today = datetime.now().strftime("%d.%m.%Y")

    try:
        requests = get_requests_by_date(today)
    except Exception as e:
        logger.error(f"get_requests_by_date FAILED: {e}")
        await update.message.reply_text(f"⚠️ Помилка при отриманні заявок: {e}")
        return

    if not requests:
        await update.message.reply_text(f"📭 Немає схвалених заявок на сьогодні ({today}).")
        return

    sent = 0
    for req in requests:
        try:
            tg_id = int(req["tg_id"])
            await context.bot.send_message(
                chat_id=tg_id,
                text=f"💵 *Аванси готові!*\n\nМожна підійти до бухгалтерії за авансом.\n📅 Дата: *{today}*",
                parse_mode="Markdown",
            )
            sent += 1
        except Exception as e:
            logger.error(f"Ready notification FAILED for {req.get('tg_id')}: {e}")

    await update.message.reply_text(
        f"✅ Повідомлення надіслано *{sent}* співробітникам про готовність авансів на {today}.",
        parse_mode="Markdown",
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Скасовано. /start — нова заявка.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME:         [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AMOUNT:       [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            INSTALLMENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_installments)],
            DATE:         [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            CONFIRM:      [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_accountant_action, pattern="^(approve|reject):"))
    app.add_handler(CommandHandler("ready", ready))

    logger.info("Бот запущено ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
