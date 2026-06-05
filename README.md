# 💸 Бот авансів BASSA

Telegram-бот для подачі заявок на аванс з автоматичною перевіркою дат та записом у Google Sheets.

---

## 📋 Як це працює

Співробітник пише `/start` → вводить ПІБ → суму → бажану дату.
Бот перевіряє дату і якщо вона некоректна — автоматично пропонує найближчу доступну.
Після підтвердження — запис у Google Sheets + повідомлення відповідальній людині.

**Дні видачі авансів:**
| День подання | День видачі |
|---|---|
| Пятниця – Неділя | Понеділок |
| Понеділок – Вівторок | Середа |
| Середа – Четвер | П'ятниця |

---

## 🚀 Розгортання: покрокова інструкція

### Крок 1 — Створити Telegram бота

1. Відкрити [@BotFather](https://t.me/BotFather) у Telegram
2. Написати `/newbot`
3. Задати ім'я та username бота
4. Скопіювати **токен** (виглядає як `123456789:ABCdef...`)

### Крок 2 — Дізнатися свій Telegram ID (для отримувача заявок)

1. Написати [@userinfobot](https://t.me/userinfobot)
2. Скопіювати числовий `Id` — це і є `RECEIVER_CHAT_ID`

### Крок 3 — Налаштувати Google Sheets

#### 3а. Створити таблицю
1. Відкрити [Google Sheets](https://sheets.google.com) → створити нову таблицю
2. Скопіювати **ID таблиці** з URL:
   `https://docs.google.com/spreadsheets/d/`**`ЦЕ_І_Є_ID`**`/edit`

#### 3б. Створити сервісний акаунт
1. Відкрити [Google Cloud Console](https://console.cloud.google.com)
2. Створити новий проєкт (або обрати існуючий)
3. Увімкнути **Google Sheets API** та **Google Drive API**:
   - Меню → APIs & Services → Library → шукати "Google Sheets API" → Enable
   - Те саме для "Google Drive API"
4. Меню → APIs & Services → Credentials → **Create Credentials** → **Service Account**
5. Задати ім'я → Create → Done
6. Натиснути на створений акаунт → вкладка **Keys** → Add Key → **JSON**
7. Завантажиться файл `.json` — він знадобиться далі

#### 3в. Дати доступ до таблиці
1. Відкрити завантажений JSON файл, знайти поле `"client_email"` (виглядає як `name@project.iam.gserviceaccount.com`)
2. Відкрити Google Таблицю → кнопка **Поділитися** → вставити цей email → роль **Редактор**

### Крок 4 — Завантажити код на GitHub

1. Відкрити [github.com](https://github.com) → **New repository**
2. Назвати `advance-bot` → Create
3. Завантажити всі файли цієї папки у репозиторій:
   - Через сайт: кнопка **Add file → Upload files**
   - Або через git:
     ```bash
     git init
     git add .
     git commit -m "init"
     git remote add origin https://github.com/YOUR_USERNAME/advance-bot.git
     git push -u origin main
     ```

> ⚠️ **ВАЖЛИВО:** НЕ завантажуйте `.env` файл з реальними даними. Тільки `.env.example`.

### Крок 5 — Розгорнути на Railway

1. Відкрити [railway.app](https://railway.app) → **New Project**
2. Обрати **Deploy from GitHub repo**
3. Підключити GitHub акаунт та обрати репозиторій `advance-bot`
4. Railway почне деплой — поки зупиниться, бо немає змінних середовища

#### Додати змінні середовища в Railway:
Меню проєкту → вкладка **Variables** → додати кожну:

| Змінна | Значення |
|---|---|
| `BOT_TOKEN` | Токен від BotFather |
| `RECEIVER_CHAT_ID` | Числовий Telegram ID отримувача |
| `SPREADSHEET_ID` | ID Google Таблиці |
| `SHEET_NAME` | `Аванси` |
| `GOOGLE_CREDENTIALS_JSON` | Вміст JSON файлу сервісного акаунту (весь текст в одному рядку) |

> 💡 Щоб вставити JSON в одному рядку: відкрийте файл, скопіюйте весь вміст і вставте як є — Railway обробить правильно.

5. Після додавання змінних — Railway автоматично перезапустить бота
6. У вкладці **Deployments** має з'явитися зелений статус ✅

---

## 🔄 Оновлення бота

Будь-який `git push` у GitHub автоматично оновить бота на Railway.

```bash
git add .
git commit -m "оновлення"
git push
```

---

## 📊 Структура Google Sheets

| № | ПІБ | Сума (грн) | Дата видачі | Telegram ID | Username | Дата подання | Статус |
|---|---|---|---|---|---|---|---|
| 1 | Іваненко Іван | 3000 | 16.06.2025 | 123456789 | @ivan | 13.06.2025 14:32 | Нова |

Статус можна змінювати вручну: **Нова / Схвалено / Відхилено / Видано**.
