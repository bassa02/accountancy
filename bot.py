import logging
import os
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from sheets import save_to_sheets

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Стани розмови ---
NAME, AMOUNT, DATE, CONFIRM = range(4)

# --- Токен бота та ID отримувача ---
BOT_TOKEN = os.environ["BOT_TOKEN"]
RECEIVER_CHAT_ID = os.environ["RECEIVER_CHAT_ID"]  # Telegram ID відповідальної людини


# ---------------------------------------------------------------------------
# Логіка дат
# ---------------------------------------------------------------------------

def get_next_payout_date(from_date: datetime) -> datetime:
    """
    Правила:
      Пн (0) → видача в середу (2)
      Вт (1) → видача в середу (2)
      Ср (2) → видача в п'ятницю (4)
      Чт (3) → видача в п'ятницю (4)
      Пт (4) → видача в понеділок (0) наступного тижня
      Сб (5) → видача в понеділок (0) наступного тижня
      Нд (6) → видача в понеділок (0) наступного тижня
    """
    weekday = from_date.weekday()  # 0=Пн, 6=Нд

    if weekday in (0, 1):       # Пн, Вт → Ср
        days_ahead = 2 - weekday
    elif weekday in (2, 3):     # Ср, Чт → Пт
        days_ahead = 4 - weekday
    else:                        # Пт, Сб, Нд → наступний Пн
        days_ahead = 7 - weekday  # до наступного Пн

    return from_date + timedelta(days=days_ahead)


def is_valid_payout_day(date: datetime) -> bool:
    """Перевіряє чи дата є допустимим днем видачі (Пн, Ср, Пт)."""
    return date.weekday() in (0, 2, 4)


def parse_date(text: str) -> datetime | None:
    """Парсить дату у форматах DD.MM.YYYY або DD/MM/YYYY."""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def get_suggested_date(requested_date: datetime) -> tuple[datetime, bool]:
    """
    Повертає (дата_видачі, чи_була_зміна).
    Якщо запитана дата не є допустимим днем — пропонує наступний.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Дата не може бути в минулому
    if requested_date < today:
        suggested = get_next_payout_date(today)
        return suggested, True

    if is_valid_payout_day(requested_date):
        # Перевіряємо чи запит подано вчасно для цієї дати
        # Пн → запит має бути Пт-Нд; Ср → Пн-Вт; Пт → Ср-Чт
        payout_weekday = requested_date.weekday()
        request_weekday = today.weekday()

        valid_request_days = {
            0: (4, 5, 6),   # Пн видача: Пт, Сб, Нд
            2: (0, 1),      # Ср видача: Пн, Вт
            4: (2, 3),      # Пт видача: Ср, Чт
        }

        if request_weekday in valid_request_days.get(payout_weekday, ()):
            return requested_date, False
        else:
            # Запит не вчасно — пропонуємо наступну доступну від сьогодні
            suggested = get_next_payout_date(today)
            return suggested, True
    else:
        # Не день видачі — знаходимо наступний від запитаної дати
        suggested = get_next_payout_date(requested_date)
        return suggested, True


WEEKDAY_UA = {0: "понеділок", 1: "вівторок", 2: "середу",
              3: "четвер", 4: "п'ятницю", 5: "суботу", 6: "неділю"}


# ---------------------------------------------------------------------------
# Обробники розмови
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Привіт! Це бот для запиту авансу.\n\n"
        "Будь ласка, введіть ваше *ім'я та прізвище*:",
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

    # Підказуємо найближчу доступну дату
    today = datetime.now()
    suggested = get_next_payout_date(today)
    suggested_str = suggested.strftime("%d.%m.%Y")
    weekday_str = WEEKDAY_UA[suggested.weekday()]

    await update.message.reply_text(
        f"✅ Сума: *{amount:,.0f} грн*\n\n"
        f"Введіть *бажану дату видачі* у форматі ДД.ММ.РРРР\n\n"
        f"💡 Найближча доступна дата: *{suggested_str}* ({weekday_str})\n\n"
        f"_Аванси видаються у понеділок, середу та п'ятницю._",
        parse_mode="Markdown",
    )
    return DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    parsed = parse_date(text)

    if not parsed:
        await update.message.reply_text(
            "❌ Невірний формат дати. Введіть у форматі *ДД.ММ.РРРР* (наприклад: 16.06.2025):",
            parse_mode="Markdown",
        )
        return DATE

    final_date, was_changed = get_suggested_date(parsed)
    final_str = final_date.strftime("%d.%m.%Y")
    weekday_str = WEEKDAY_UA[final_date.weekday()]

    context.user_data["date"] = final_str

    if was_changed:
        change_msg = (
            f"⚠️ Обрана дата не є днем видачі авансу.\n"
            f"Автоматично змінено на найближчу доступну: *{final_str}* ({weekday_str})\n\n"
        )
    else:
        change_msg = ""

    name = context.user_data["name"]
    amount = context.user_data["amount"]

    keyboard = ReplyKeyboardMarkup([["✅ Підтвердити", "❌ Скасувати"]], resize_keyboard=True)

    await update.message.reply_text(
        f"{change_msg}"
        f"📋 *Перевірте дані заявки:*\n\n"
        f"👤 Ім'я: *{name}*\n"
        f"💰 Сума: *{amount:,.0f} грн*\n"
        f"📅 Дата видачі: *{final_str}* ({weekday_str})\n\n"
        f"Все вірно?",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    if "Скасувати" in text:
        await update.message.reply_text(
            "❌ Заявку скасовано. Щоб подати нову — натисніть /start",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    if "Підтвердити" not in text:
        await update.message.reply_text("Оберіть дію на клавіатурі 👇")
        return CONFIRM

    name = context.user_data["name"]
    amount = context.user_data["amount"]
    date = context.user_data["date"]
    user = update.effective_user
    submitted_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Зберігаємо в Google Sheets
    try:
        save_to_sheets(name, amount, date, user.id, user.username or "—", submitted_at)
        sheets_status = "✅ Збережено в таблиці"
        logger.info(f"Sheets OK: {name}, {amount}, {date}")
    except Exception as e:
        logger.error(f"Sheets FAILED: {type(e).__name__}: {e}")
        sheets_status = f"⚠️ Помилка запису в таблицю: {type(e).__name__}"

    # Повідомлення для користувача
    await update.message.reply_text(
        f"🎉 *Заявку подано!*\n\n"
        f"👤 {name}\n"
        f"💰 {amount:,.0f} грн\n"
        f"📅 {date}\n"
        f"🕐 Дата звернення: {submitted_at}\n\n"
        f"{sheets_status}\n\n"
        f"Очікуйте підтвердження від відповідального.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Повідомлення відповідальній людині
    username_display = f"@{user.username}" if user.username else f"ID: {user.id}"
    try:
        await context.bot.send_message(
            chat_id=RECEIVER_CHAT_ID,
            text=(
                f"💸 *Нова заявка на аванс*\n\n"
                f"👤 *{name}*\n"
                f"💰 *{amount:,.0f} грн*\n"
                f"📅 Дата видачі: *{date}*\n"
                f"🕐 Дата звернення: {submitted_at}\n"
                f"📱 Telegram: {username_display}"
            ),
            parse_mode="Markdown",
        )
        logger.info(f"Notification sent to {RECEIVER_CHAT_ID}")
    except Exception as e:
        logger.error(f"Notification FAILED to {RECEIVER_CHAT_ID}: {type(e).__name__}: {e}")

    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ Скасовано. Для нової заявки — /start",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AMOUNT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            DATE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)

    logger.info("Бот запущено ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
