import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
SHEET_NAME = os.environ.get("SHEET_NAME", "Аванси")

# Заголовки таблиці (створюються автоматично при першому запуску)
HEADERS = [
    "№",
    "ПІБ",
    "Сума (грн)",
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
        sheet = spreadsheet.add_worksheet(title=SHEET_NAME, rows=1000, cols=10)
        sheet.append_row(HEADERS)
        # Форматування заголовків
        sheet.format("A1:H1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
        })

    return sheet


def save_to_sheets(name: str, amount: float, date: str,
                   tg_id: int, username: str, submitted_at: str):
    sheet = get_sheet()

    # Визначаємо наступний номер
    all_values = sheet.get_all_values()
    next_num = len(all_values)  # рядок 1 = заголовки, тому len = наступний №

    row = [
        next_num,
        name,
        amount,
        date,
        tg_id,
        username,
        submitted_at,
        "Нова",          # Статус за замовчуванням
    ]

    sheet.append_row(row)
