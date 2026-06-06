import os
import json
import logging
import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SHEET_NAME = os.environ.get("SHEET_NAME", "Аванси")

HEADERS = [
    "№",
    "ПІБ",
    "Сума (грн)",
    "Розбивка (міс.)",
    "Сума/міс. (грн)",
    "Дата видачі",
    "Telegram ID",
    "Username",
    "Дата подання",
    "Статус",
]


def get_sheet():
    creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)

    try:
        sheet = spreadsheet.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=12)
        sheet.append_row(HEADERS)
        sheet.format("A1:J1", {"textFormat": {"bold": True}})

    return sheet


def save_to_sheets(name: str, amount: float, installments: int, date: str,
                   tg_id: int, username: str, submitted_at: str) -> int:
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    next_num = len(all_values)
    per_month = round(amount / installments, 2)

    row = [
        next_num,
        name,
        amount,
        installments,
        per_month,
        date,
        tg_id,
        username,
        submitted_at,
        "Нова",
    ]

    sheet.append_row(row)
    logger.info(f"Row appended: {row}")

    # Повертаємо індекс рядка (для оновлення статусу)
    return len(all_values) + 1  # +1 бо append_row додав рядок


def update_request_status(row_index: int, status: str):
    sheet = get_sheet()
    # Колонка "Статус" — 10-та (J)
    sheet.update_cell(row_index, 10, status)
    logger.info(f"Status updated: row={row_index}, status={status}")


def get_requests_by_date(date: str) -> list[dict]:
    """Повертає всі схвалені заявки на конкретну дату."""
    sheet = get_sheet()
    all_values = sheet.get_all_values()

    results = []
    for i, row in enumerate(all_values[1:], start=2):  # пропускаємо заголовок
        if len(row) >= 10:
            row_date = row[5]    # колонка "Дата видачі"
            row_status = row[9]  # колонка "Статус"
            if row_date == date and row_status == "Схвалено":
                results.append({
                    "row": i,
                    "name": row[1],
                    "amount": row[2],
                    "tg_id": row[6],
                })

    return results


def get_all_pending_dates() -> list[str]:
    """Повертає унікальні дати де є нові заявки."""
    sheet = get_sheet()
    all_values = sheet.get_all_values()
    dates = set()
    for row in all_values[1:]:
        if len(row) >= 10 and row[9] == "Нова":
            dates.add(row[5])
    return sorted(list(dates))
