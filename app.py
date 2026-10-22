import math
import os
import re
import sqlite3
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, request, redirect, url_for,
    session, render_template_string, flash
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))

DB = "moneytrack.db"

PLANS = {
    "month": ("1 месяц", 249, 30),
    "3months": ("3 месяца", 649, 90),
    "6months": ("6 месяцев", 1199, 180),
    "forever": ("Навсегда", 4990, None),
}

CATEGORIES = [
    "Продукты", "Транспорт", "Жильё",
    "Зарплата", "Развлечения", "Здоровье", "Другое"
]



def normalize_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    return digits


def connect_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE,
            email TEXT UNIQUE,
            password TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            expires TEXT,
            trial_started TEXT
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            note TEXT DEFAULT '',
            created TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            balance REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            UNIQUE(user_id, category)
        );

        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            direction TEXT NOT NULL,
            person TEXT NOT NULL,
            amount REAL NOT NULL,
            paid_amount REAL DEFAULT 0,
            note TEXT DEFAULT '',
            created TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS investments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            amount REAL NOT NULL,
            current_value REAL DEFAULT 0,
            note TEXT DEFAULT '',
            created TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS investment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            investment_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            current_value REAL NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recurring_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            frequency TEXT NOT NULL,
            next_date TEXT NOT NULL,
            note TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            created TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS financial_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            saved_amount REAL DEFAULT 0,
            target_date TEXT DEFAULT '',
            created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        """)
        columns = [
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(transactions)"
            ).fetchall()
        ]

        if "account_id" not in columns:
            db.execute(
                "ALTER TABLE transactions ADD COLUMN account_id INTEGER"
            )

        user_columns = [
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(users)"
            ).fetchall()
        ]

        if "trial_started" not in user_columns:
            db.execute(
                "ALTER TABLE users ADD COLUMN trial_started TEXT"
            )


init_db()


def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def current_user():
    with connect_db() as db:
        return db.execute(
            "SELECT * FROM users WHERE id=?",
            (session["user_id"],)
        ).fetchone()


def has_access(user):
    if user["plan"] == "forever":
        return True

    if user["expires"]:
        try:
            if datetime.fromisoformat(user["expires"]) > datetime.now():
                return True
        except ValueError:
            pass

    if user["trial_started"]:
        try:
            trial_end = (
                datetime.fromisoformat(user["trial_started"])
                + timedelta(days=3)
            )
            return trial_end > datetime.now()
        except ValueError:
            pass

    return False

STYLE = """
<style>
* {
    box-sizing: border-box;
}

:root {
    color-scheme: dark;
    --bg: #0b1120;
    --surface: #151f32;
    --surface-light: #1c2940;
    --border: #2a3850;
    --text: #f1f5f9;
    --muted: #94a3b8;
    --green: #34d399;
    --red: #fb7185;
    --blue: #818cf8;
}

body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Arial, sans-serif;
    font-size: 11px;
    line-height: 1.6;
}

header {
    background: var(--surface);
    color: var(--text);
    padding: 9px;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: -0.5px;
    border-bottom: 1px solid var(--border);
}

header::first-letter {
    color: var(--green);
}

main {
    width: 100%;
    max-width: 760px;
    margin: auto;
    padding: 12px 11px 27px;
}

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 15px;
    margin: 16px 0;
    box-shadow: 0 8px 24px #00000018;
    overflow-wrap: anywhere;
}

h2, h3 {
    color: var(--text);
    line-height: 1.3;
    letter-spacing: -0.3px;
}

h2 {
    font-size: 17px;
}

h3 {
    font-size: 9px;
    margin-top: 0;
}

p {
    margin: 12px 0;
}

a {
    color: var(--green);
    font-weight: 600;
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

.auth-submit {
    width: 50%;
    min-height: 40px;
    display: block;
    margin-left: auto;
    margin-right: auto;
    padding: 9px 10px;
    font: inherit;
    background: var(--green);
    color: #052e2b;
    border: 0;
    border-radius: 8px;
    font-weight: 750;
    cursor: pointer;
    transition: filter 0.2s, transform 0.2s;
}

button {
    width: 100%;
    min-height: 40px;
    padding: 9px 10px;
    margin: 8px 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    font: inherit;
}

input, select {
    background: #0f192b;
    color: var(--text);
}

/* Мобильная форма новой операции */
.operation-fields {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 8px;
}

.operation-fields label {
    display: block;
    width: 100%;
    margin: 8px 0 0;
    line-height: 1.4;
}

.operation-fields input,
.operation-fields select {
    display: block;
    box-sizing: border-box;
    width: 100%;
    max-width: 100%;
    min-width: 0;
    margin: 0;
}

.operation-fields button {
    width: 100%;
    max-width: 100%;
    margin: 12px 0 0;
}

.operation-fields #new-account-fields[hidden] {
    display: none;
}

input::placeholder {
    color: #718096;
}

input:focus, select:focus {
    outline: 2px solid var(--blue);
    outline-offset: 1px;
}

button {
    width: 50%;
    display: block;
    margin-left: auto;
    margin-right: auto;
    background: var(--green);
    color: #052e2b;
    border: 0;
    font-weight: 750;
    cursor: pointer;
    transition: filter 0.2s, transform 0.2s;
}

button:hover {
    filter: brightness(1.08);
}

button:active {
    transform: scale(0.99);
}

.small {
    color: var(--muted);
    font-size: 13px;
}

.amount {
    font-size: clamp(19px, 4.7vw, 25px);
    font-weight: 800;
    letter-spacing: -1px;
    overflow-wrap: anywhere;
}

.income {
    color: var(--green);
    font-weight: 650;
}

.expense {
    color: var(--red);
    font-weight: 650;
}

hr {
    border: 0;
    border-top: 1px solid var(--border);
}

.card a {
    display: inline-block;
    margin-top: 8px;
}

.card input, .card select, .card button {
    margin-top: 10px;
}

@media (max-width: 480px) {
    header {
        padding: 11px 12px;
        font-size: 15px;
    }

    main {
        padding: 8px 8px 19px;
    }

    .card {
        padding: 11px;
        border-radius: 11px;
        margin: 12px 0;
    }

    h2 {
        font-size: 22px;
    }

    .amount {
        font-size: 20px;
    }
.balance-card {
    padding: 16px;
    border-radius: 20px;
}

.balance-card .amount {
    font-size: clamp(15px, 4vw, 24px);
    font-weight: 800;
    margin: 14px 0 22px;
    overflow-wrap: anywhere;
}

.balance-details {
    display: flex;
    gap: 12px;
    margin-bottom: 22px;
}

.balance-item {
    flex: 1;
    min-width: 0;
    padding: 10px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.06);
    overflow-wrap: anywhere;
}

.balance-item .small {
    margin-bottom: 8px;
}

.primary-link {
    display: block;
    text-align: center;
    padding: 9px 11px;
    margin-top: 10px;
    border-radius: 13px;
    background: linear-gradient(135deg, #4f6ef7, #6556e8);
    color: white;
    text-decoration: none;
    font-weight: 750;
    transition: filter 0.2s, transform 0.2s;
}

.primary-link:hover {
    filter: brightness(1.12);
    text-decoration: none;
}

.balance-item .income,
.balance-item .expense {
    font-size: 8px;
    font-weight: 700;
    line-height: 1.4;
    overflow-wrap: anywhere;
}

/* Обновлённый дизайн карточки баланса */
.balance-card {
    padding: 18px;
    border: 1px solid #344b70;
    border-radius: 15px;
    background:
        radial-gradient(ellipse at top right, #304b7c 0%, transparent 58%),
        linear-gradient(145deg, #1a2c4b, #111c30);
    box-shadow: 0 16px 38px rgba(0, 0, 0, 0.22);
}

.balance-card .amount {
    font-size: clamp(19px, 4.7vw, 28px);
    font-weight: 850;
    letter-spacing: -1px;
    margin: 14px 0 24px;
    overflow-wrap: anywhere;
}

.balance-details {
    display: flex;
    gap: 12px;
    margin-bottom: 22px;
}

.balance-item {
    flex: 1;
    min-width: 0;
    padding: 13px;
    border: 1px solid rgba(255, 255, 255, 0.07);
    border-radius: 15px;
    background: rgba(5, 12, 25, 0.35);
    overflow-wrap: anywhere;
}

.balance-item .small {
    margin-bottom: 7px;
}

.balance-item .income,
.balance-item .expense {
    font-size: 9px;
    line-height: 1.5;
    overflow-wrap: anywhere;
}

@media (max-width: 480px) {
    .balance-card {
        padding: 13px 11px;
    }

    .balance-details {
        gap: 8px;
    }

    .balance-item {
        padding: 10px 8px;
    }

    .balance-item .income,
    .balance-item .expense {
        font-size: 12px;
    }
}

/* Нижняя плавающая панель навигации */
.bottom-nav {
    position: fixed;
    bottom: calc(10px + env(safe-area-inset-bottom));
    left: 12px;
    right: 12px;
    z-index: 1000;
    display: flex;
    justify-content: space-around;
    align-items: center;
    gap: 3px;
    padding: 8px 7px;
    background: rgba(15, 23, 42, 0.58);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 22px;
    box-shadow: 0 6px 24px rgba(15, 23, 42, 0.14);
}

.bottom-nav a {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 9px 1px;
    color: #94a3b8;
    text-decoration: none;
    font-size: 11px;
    line-height: 1.2;
    border-radius: 15px;
    white-space: nowrap;
}

.bottom-nav a.active {
    color: #2563eb;
    font-weight: 700;
    background: rgba(219, 234, 254, 0.85);
}

.bottom-nav a.nav-main {
    flex: 1.2;
    margin-top: -9px;
    padding: 10px 2px 11px;
    color: #ffffff;
    font-size: 11px;
    font-weight: 800;
    background: linear-gradient(145deg, #3b82f6, #1d4ed8);
    border: 1px solid rgba(255, 255, 255, 0.28);
    border-radius: 18px;
    box-shadow: 0 5px 14px rgba(37, 99, 235, 0.38);
}

.bottom-nav a.nav-main .nav-icon {
    font-size: 27px;
}

.bottom-nav a.nav-main.active {
    color: #ffffff;
    background: linear-gradient(145deg, #2563eb, #1e40af);
    box-shadow: 0 5px 16px rgba(37, 99, 235, 0.48);
}

.bottom-nav .nav-icon {
    font-size: 22px;
    line-height: 1;
}

@media (max-width: 380px) {
    .bottom-nav {
        left: 7px;
        right: 7px;
        padding: 7px 4px;
        gap: 2px;
    }

    .bottom-nav a {
        font-size: 10px;
    }

    .bottom-nav a.nav-main {
        font-size: 10px;
    }
}

body {
    padding-bottom: 135px;
}

/* Единый компактный стиль интерфейса MoneyTrack */
body {
    font-size: 14px;
    line-height: 1.5;
}
h2 {
    font-size: 20px;
    line-height: 1.3;
    margin-bottom: 12px;
}
h3 {
    font-size: 15px;
    line-height: 1.35;
    margin-bottom: 10px;
}
p {
    font-size: 14px;
    line-height: 1.5;
}
.card {
    padding: 14px;
    margin: 13px 0;
    border-radius: 15px;
}
input, select {
    min-height: 42px;
    padding: 10px 12px;
    border-radius: 11px;
    font-size: 14px;
}
button {
    min-height: 42px;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 14px;
    line-height: 1.35;
}
.small {
    font-size: 12px;
    line-height: 1.45;
}
.primary-link {
    font-size: 14px;
    line-height: 1.4;
    border-radius: 12px;
}
@media (max-width: 480px) {
    h2 {
        font-size: 19px;
    }
    h3 {
        font-size: 14px;
    }
    .card {
        padding: 12px;
        margin: 11px 0;
        border-radius: 13px;
    }
    input, select, button {
        font-size: 13px;
        min-height: 40px;
    }
    .small {
        font-size: 11px;
    }
}


/* Единый стиль кнопок действий */
.action-edit,
.action-add,
.action-delete {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    box-sizing: border-box;
    min-width: 0;
    min-height: 42px;
    padding: 10px 12px;
    margin: 5px 0;
    border: 1px solid transparent;
    border-radius: 11px;
    font: inherit;
    font-size: 14px;
    font-weight: 750;
    line-height: 1.3;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    transition: filter 0.2s, transform 0.2s;
}

.action-edit {
    width: 100%;
    background: #203b3b;
    color: #45d6a1;
    border-color: #28554d;
}

.action-add {
    width: 100%;
    background: var(--green);
    color: #062b25;
}

.action-delete {
    width: 100%;
    background: #bd343b;
    color: #ffffff;
}

.action-edit:hover,
.action-add:hover,
.action-delete:hover {
    filter: brightness(1.1);
    text-decoration: none;
}

.action-edit:active,
.action-add:active,
.action-delete:active {
    transform: scale(0.99);
}


.reschedule-form {
    position: relative;
    display: flex;
    flex: 1 1 0;
    min-width: 0;
    margin: 0;
}
.reschedule-form .reschedule-date {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0;
    cursor: pointer;
}
.reschedule-form .action-add {
    width: 100%;
    min-width: 0;
    white-space: nowrap;
}
.recurring-actions > form {
    flex: 1 1 0;
    min-width: 0;
}
.recurring-actions button {
    width: 100%;
    min-width: 0;
    white-space: nowrap;
}
@media(max-width:380px) {
    .recurring-actions { gap: 6px; }
    .recurring-actions button { padding: 9px 4px; font-size: 12px; }
}

.action-row {
    display: flex;
    align-items: stretch;
    gap: 8px;
    width: 100%;
    margin: 8px 0;
}

.action-row > * {
    flex: 1 1 0;
    min-width: 0;
    width: auto;
    margin: 0;
}

.action-row form {
    display: flex;
    flex: 1 1 0;
    min-width: 0;
    margin: 0;
}

.action-row form button,
.action-row > button,
.action-row > a {
    width: 100%;
    min-width: 0;
}

@media (max-width: 380px) {
    .action-edit,
    .action-add,
    .action-delete {
        padding: 9px 6px;
        font-size: 12px;
    }
}

</style>
"""

def page(title, content, **context):
    template = """
    <!doctype html>
    <html lang="ru">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta charset="utf-8">
    <title>{{title}}</title>
    """ + STYLE + """
    <header>MoneyTrack</header>
    <main>
    {% with messages = get_flashed_messages() %}
      {% for msg in messages %}
        <div class="card">{{msg}}</div>
      {% endfor %}
    {% endwith %}
    """ + content + """

    </main>

    {% if request.endpoint not in ['login', 'register'] and session.get('user_id') %}
    <nav class="bottom-nav">
        <a href="/" class="{{ 'active' if request.endpoint == 'index' else '' }}">
            <span class="nav-icon">⌂</span>
            <span>Главная</span>
        </a>

        <a href="/analytics" class="{{ 'active' if request.endpoint == 'analytics' else '' }}">
            <span class="nav-icon">▥</span>
            <span>Аналитика</span>
        </a>

        <a href="/add" class="nav-main {{ 'active' if request.endpoint == 'add_transaction' else '' }}">
            <span class="nav-icon">⇄</span>
            <span>Операции</span>
        </a>

        <a href="/recurring" class="{{ 'active' if request.endpoint == 'recurring' else '' }}">
            <span class="nav-icon">▦</span>
            <span>Платежи</span>
        </a>

        <a href="/more" class="{{ 'active' if request.endpoint in ['more', 'about', 'contacts'] else '' }}">
            <span class="nav-icon">☰</span>
            <span>Ещё</span>
        </a>
    </nav>
    {% endif %}

    </html>

    """
    return render_template_string(
        template, title=title, **context
    )


@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user = current_user()

    selected_month = request.args.get(
        "month",
        datetime.now().strftime("%Y-%m")
    )

    try:
        datetime.strptime(selected_month, "%Y-%m")
    except ValueError:
        selected_month = datetime.now().strftime("%Y-%m")

    with connect_db() as db:
        rows = db.execute("""
            SELECT * FROM transactions
            WHERE user_id=?
            ORDER BY id DESC
            LIMIT 10
        """, (user["id"],)).fetchall()
        totals = db.execute("""
            SELECT
            SUM(CASE WHEN kind='income' THEN amount ELSE 0 END) income,
            SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END) expense
            FROM transactions WHERE user_id=?
        """, (user["id"],)).fetchone()

        month_totals = db.execute("""
            SELECT
                SUM(CASE WHEN kind='income'
                    THEN amount ELSE 0 END) AS income,
                SUM(CASE WHEN kind='expense'
                    THEN amount ELSE 0 END) AS expense
            FROM transactions
            WHERE user_id=?
              AND substr(created, 7, 4) || '-' ||
                  substr(created, 4, 2) = ?
        """, (user["id"], selected_month)).fetchone()

        accounts = db.execute("""
            SELECT * FROM accounts WHERE user_id=?
        """, (user["id"],)).fetchall()

        category_totals = db.execute("""
            SELECT category, SUM(amount) AS amount
            FROM transactions
            WHERE user_id=?
              AND kind='expense'
              AND substr(created, 7, 4) || '-' ||
                  substr(created, 4, 2) = ?
            GROUP BY category
            ORDER BY amount DESC
        """, (user["id"], selected_month)).fetchall()

    with connect_db() as db:
        upcoming_payments = db.execute("""
            SELECT id, name, amount, category, next_date, frequency
            FROM recurring_payments
            WHERE user_id = ? AND active = 1
            ORDER BY next_date ASC
            LIMIT 3
        """, (user["id"],)).fetchall()

    goal_list = []

    if has_access(user):
        with connect_db() as db:
            goal_rows = db.execute("""
                SELECT id, name, target_amount, saved_amount
                FROM financial_goals
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT 3
            """, (user["id"],)).fetchall()

        for goal in goal_rows:
            target = goal["target_amount"]
            saved = goal["saved_amount"] or 0

            goal_list.append({
                "name": goal["name"],
                "target_amount": target,
                "saved_amount": saved,
                "percent": round(saved / target * 100, 1)
                    if target > 0 else 0,
                "bar_percent": min(
                    round(saved / target * 100, 1), 100
                ) if target > 0 else 0
            })
    income = totals["income"] or 0
    expense = totals["expense"] or 0
    with connect_db() as db:
        accounts_total = db.execute("""
            SELECT COALESCE(SUM(balance), 0)
            FROM accounts
            WHERE user_id=?
        """, (user["id"],)).fetchone()[0]

    with connect_db() as db:
        unassigned_totals = db.execute("""
            SELECT
                COALESCE(SUM(CASE
                    WHEN kind='income' THEN amount ELSE 0
                END), 0) AS income,
                COALESCE(SUM(CASE
                    WHEN kind='expense' THEN amount ELSE 0
                END), 0) AS expense
            FROM transactions
            WHERE user_id=? AND account_id IS NULL
        """, (user["id"],)).fetchone()

    balance = (
        accounts_total
        + unassigned_totals["income"]
        - unassigned_totals["expense"]
    )
    colors = [
        "#6366f1", "#f59e0b", "#10b981",
        "#ef4444", "#06b6d4", "#ec4899",
        "#8b5cf6", "#84cc16", "#f97316",
        "#14b8a6"
    ]

    category_totals = [
        {
            "category": row["category"],
            "amount": row["amount"],
            "percent": round(row["amount"] / expense * 100, 1),
            "color": colors[i % len(colors)]
        }
        for i, row in enumerate(category_totals)
    ] if expense else []

    chart_gradient = ""
    if category_totals:
        start = 0
        segments = []

        for c in category_totals:
            end = start + c["percent"]
            segments.append(
                f'{c["color"]} {start}% {end}%'
            )
            start = end

        chart_gradient = ", ".join(segments)

    content = """
    <div class="card balance-card">
        <div class="small">Общий баланс</div>
        <div class="amount">{{balance|round(2)}} ₽</div>

        <div class="balance-details">
            <div class="balance-item">
                <div class="small">Доходы за месяц</div>
                <div class="income">+{{month_income|round(2)}} ₽</div>
            </div>
            <div class="balance-item">
                <div class="small">Расходы за месяц</div>
                <div class="expense">−{{month_expense|round(2)}} ₽</div>
            </div>
        </div>

        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:16px;">
            <a class="primary-link" href="/add?kind=income"
               style="background:#059669;flex:1;text-align:center;">
                + Доход
            </a>
            <a class="primary-link" href="/add?kind=expense"
               style="background:#dc2626;flex:1;text-align:center;">
                − Расход
            </a>
            <a class="primary-link" href="/accounts"
               style="flex:1;text-align:center;">
                Мои счета
            </a>
        </div>
    </div>

    <div class="card">
        <h3>Остаток за месяц</h3>
        <p class="small">Текущий месяц: {{selected_month}}</p>
        <div class="amount">{{month_balance|round(2)}} ₽</div>
        <p class="small">Доходы минус расходы за месяц</p>
        <a href="/analytics">Подробная аналитика →</a>
    </div>

       {% if goal_list %}
    <div class="card">
        <h3>Мои финансовые цели</h3>

        {% for g in goal_list %}
            <div style="margin-bottom:16px;">
                <div style="display:flex;justify-content:space-between;gap:8px;">
                    <strong>{{g.name}}</strong>
                    <span>{{g.percent}}%</span>
                </div>

                <div style="background:#e5e7eb;border-radius:8px;height:10px;margin:8px 0;overflow:hidden;">
                    <div style="width:{{g.bar_percent}}%;background:#10b981;height:10px;border-radius:8px;"></div>
                </div>

                <div class="small">
                    {{g.saved_amount|round(2)}} ₽ из {{g.target_amount|round(2)}} ₽
                </div>
            </div>
        {% endfor %}

        <a href="/goals">Все финансовые цели →</a>
    </div>
    {% endif %}
    {% if upcoming_payments %}
    <div class="card">
        <h3>Ближайшие платежи</h3>
        {% for payment in upcoming_payments %}
            <div style="padding:12px 0;border-bottom:1px solid #e5e7eb;">
                <div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;">
                    <strong>{{payment.name}}</strong>
                    <strong>{{payment.amount|round(2)}} ₽</strong>
                </div>
                <div class="small">{{payment.category}} · {{payment.next_date}}</div>
                {% if payment.next_date < today %}
                    <span class="expense">Просрочен</span>
                {% elif payment.next_date == today %}
                    <span class="expense">Сегодня</span>
                {% else %}
                    <span class="small">Предстоящий платёж</span>
                {% endif %}
            </div>
        {% endfor %}
        <a href="/recurring">Все регулярные платежи →</a>
    </div>
    {% endif %}

     <div class="card">
        <h3>Последние операции</h3>
        {% for t in rows %}
            <div class="transaction-row" style="padding:12px 0;border-bottom:1px solid #e5e7eb;">
                <p>
                    {% if t.kind == 'income' %}
                        <span class="income">+{{t.amount}} ₽</span>
                    {% else %}
                        <span class="expense">−{{t.amount}} ₽</span>
                    {% endif %}
                    — {{t.category}} {{t.note}}
                </p>
                <div class="small">{{t.created}}</div>
                <div class="action-row">
                    <a href="/edit/{{t.id}}" class="action-edit">✏️ Редактировать</a>
                    <form method="post" action="/delete/{{t.id}}"
                          onsubmit="return confirm('Удалить эту операцию?')">
                        <button type="submit" class="action-delete">🗑️ Удалить</button>
                    </form>
                </div>
            </div>
        {% else %}
            <p class="small">Операций пока нет.</p>
        {% endfor %}
    </div>

    <p><a href="/logout">Выйти</a></p>
    """
    month_income = month_totals["income"] or 0
    month_expense = month_totals["expense"] or 0
    month_balance = month_income - month_expense

    return page(
    "Главная", content,
    user=user, rows=rows, accounts=accounts,
    balance=balance, income=income, expense=expense,
    category_totals=category_totals,
    chart_gradient=chart_gradient,
     selected_month=selected_month,
     month_income=month_income,
     month_expense=month_expense,
     month_balance=month_balance,
     goal_list=goal_list,
     upcoming_payments=upcoming_payments,
     today=datetime.now().strftime("%Y-%m-%d"),
    )


@app.route("/analytics")
@login_required
def analytics():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    selected_month = request.args.get(
        "month", datetime.now().strftime("%Y-%m")
    )

    if not re.fullmatch(r"\d{4}-\d{2}", selected_month):
        selected_month = datetime.now().strftime("%Y-%m")

    with connect_db() as db:
        totals = db.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN kind='income'
                    THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN kind='expense'
                    THEN amount ELSE 0 END), 0) AS expense
            FROM transactions
            WHERE user_id=?
              AND substr(created, 7, 4) || '-' ||
                  substr(created, 4, 2) = ?
        """, (user["id"], selected_month)).fetchone()

        categories = db.execute("""
            SELECT category, SUM(amount) AS amount
            FROM transactions
            WHERE user_id=? AND kind='expense'
              AND substr(created, 7, 4) || '-' ||
                  substr(created, 4, 2) = ?
            GROUP BY category
            ORDER BY amount DESC
        """, (user["id"], selected_month)).fetchall()

    colors = [
        "#6366f1", "#f59e0b", "#10b981", "#ef4444",
        "#06b6d4", "#ec4899", "#8b5cf6", "#84cc16",
        "#f97316", "#14b8a6"
    ]

    category_total = sum(row["amount"] for row in categories)
    pie_categories = [
        {
            "category": row["category"],
            "amount": row["amount"],
            "percent": round(row["amount"] / category_total * 100, 1),
            "color": colors[i % len(colors)]
        }
        for i, row in enumerate(categories)
    ] if category_total > 0 else []

    pie_segments = []
    start_percent = 0
    for item in pie_categories:
        end_percent = start_percent + item["percent"]
        pie_segments.append(
            f'{item["color"]} {start_percent}% {end_percent}%'
        )
        start_percent = end_percent

    pie_gradient = ", ".join(pie_segments)

    month_income = totals["income"]
    month_expense = totals["expense"]
    month_balance = month_income - month_expense
    max_value = max(month_income, month_expense, 1)

    content = """
    <div class="card">
        <h3>Статистика за месяц</h3>
        <form method="get">
            <label>Выбери месяц</label>
            <input type="month" name="month"
                   value="{{selected_month}}" required>
            <button type="submit">Показать</button>
        </form>

        <p>Доходы:
            <span class="income">+{{month_income|round(2)}} ₽</span>
        </p>
        <p>Расходы:
            <span class="expense">−{{month_expense|round(2)}} ₽</span>
        </p>
        <p><strong>Итог: {{month_balance|round(2)}} ₽</strong></p>
    </div>

    <div class="card">
        <h3>Доходы и расходы</h3>
        {% for label, value, color in [
            ('Доходы', month_income, '#10b981'),
            ('Расходы', month_expense, '#ef4444')
        ] %}
            <p>{{label}} — {{value|round(2)}} ₽</p>
            <div style="height:18px;background:#e5e7eb;
                        border-radius:8px;margin-bottom:16px;">
                <div style="height:18px;border-radius:8px;
                    background:{{color}};
                    width:{{value / max_value * 100}}%;">
                </div>
            </div>
        {% endfor %}
    </div>

    <div class="card" style="padding:20px;">
        <h3>Структура расходов</h3>
        {% if pie_categories %}
        <div style="display:flex;justify-content:center;align-items:center;padding:16px 0;">
            <div style="position:relative;width:210px;height:210px;max-width:100%;aspect-ratio:1;border-radius:50%;background:conic-gradient({{pie_gradient}});flex-shrink:0;">
                <div style="position:absolute;inset:10%;border-radius:50%;background:var(--surface);border:1px solid var(--border);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:4px;">
                    <span class="small">Всего расходов</span>
                    <strong style="font-size:19px;line-height:1.3;">{{month_expense|round(0)|int}} ₽</strong>
                </div>
            </div>
        </div>
        <div style="margin-top:12px;">
            {% for c in pie_categories %}
            <div style="padding:12px 0;border-bottom:1px solid var(--border);">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    <span style="width:10px;height:10px;flex-shrink:0;border-radius:3px;background:{{c.color}};"></span>
                    <strong style="flex:1;">{{c.category}}</strong>
                    <strong style="color:var(--text-muted);">{{c.percent}}%</strong>
                </div>
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                    <span class="small">Доля расходов</span>
                    <strong>{{c.amount|round(2)}} ₽</strong>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <p class="small">За этот месяц расходов нет.</p>
        {% endif %}
    </div>
    """

    return page(
        "Аналитика", content,
        selected_month=selected_month,
        month_income=month_income,
        month_expense=month_expense,
        month_balance=month_balance,
        max_value=max_value,
        pie_categories=pie_categories,
        pie_gradient=pie_gradient,
        categories=categories
    )



@app.route("/register", methods=["GET", "POST"])
def register():
    content = """
    <div class="card">
    <h2>Регистрация</h2>
    <form method="post">
        <input name="phone" placeholder="Номер телефона (необязательно)">
        <input name="email" type="email" placeholder="Электронная почта (необязательно)">
        <input name="password" type="password"
               placeholder="Пароль от приложения" required>
        <button type="submit" class="auth-submit">Зарегистрироваться</button>
    </form>
    <a href="/login">Уже есть аккаунт? Войти</a>
    </div>
    """

    if request.method == "POST":
        phone = request.form.get("phone", "").strip() or None
        email = request.form.get("email", "").strip().lower() or None
        password = request.form.get("password", "")

        if bool(phone) == bool(email):
            flash("Укажи либо номер телефона, либо электронную почту.")
            return redirect(url_for("register"))

        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Укажи корректный адрес электронной почты.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Пароль должен содержать минимум 8 символов.")
            return redirect(url_for("register"))

        try:
            with connect_db() as db:
                db.execute(
                    """
                    INSERT INTO users(phone, email, password, trial_started)
                    VALUES(?,?,?,?)
                    """,
                    (
                        phone,
                        email,
                        generate_password_hash(password),
                        datetime.now().isoformat()
                    )
                )

            flash("Аккаунт создан! Бесплатный 3-дневный доступ активирован. Войди, чтобы начать пользоваться приложением.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Этот номер телефона или email уже зарегистрирован.")

    return page("Регистрация", content)


@app.route("/login", methods=["GET", "POST"])
def login():
    content = """
    <div class="card">
    <h2>Вход</h2>
    <form method="post">
        <input name="login" placeholder="Номер телефона или email" required style="width: 56%; display: block; margin-left: auto; margin-right: auto; box-sizing: border-box;">
        <input name="password" type="password"
               placeholder="Пароль" required style="width: 56%; display: block; margin-left: auto; margin-right: auto; box-sizing: border-box;">
        <button type="submit" class="auth-submit">Войти</button>
    </form>
    <a href="/register">Создать аккаунт</a>
    </div>
    """

    if request.method == "POST":
        login_value = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        normalized_login = normalize_phone(login_value)

        with connect_db() as db:
            users = db.execute("SELECT * FROM users").fetchall()

        user = None
        for candidate in users:
            saved_email = (candidate["email"] or "").lower()
            saved_phone = normalize_phone(candidate["phone"])
            if (
                saved_email == login_value.lower()
                or (
                    saved_phone
                    and saved_phone == normalized_login
                    and normalized_login.startswith("+")
                )
            ):
                user = candidate
                break

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("index"))

        flash("Неверный номер телефона, email или пароль.")

    return page("Вход", content)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    user = current_user()

    with connect_db() as db:
        accounts = db.execute("""
            SELECT id, name, balance
            FROM accounts
            WHERE user_id=?
            ORDER BY id
        """, (user["id"],)).fetchall()
        transactions = db.execute("""
            SELECT *
            FROM transactions
            WHERE user_id=?
            ORDER BY id DESC
        """, (user["id"],)).fetchall()

    content = """
    <div class="card operation-form">
        <h2>Новая операция</h2>
        <form method="post" class="operation-fields">
            <label>Тип операции</label>
            <select name="kind" required>
                <option value="expense"
                    {% if request.args.get('kind', 'expense') == 'expense' %}selected{% endif %}>
                    Расход
                </option>
                <option value="income"
                    {% if request.args.get('kind') == 'income' %}selected{% endif %}>
                    Доход
                </option>
            </select>

            <label>Счёт</label>
            <select name="account_id" id="account-select" required
                >
                <option value="" disabled
                    {% if not request.args.get('account_id') %}selected{% endif %}>
                    Выбери счёт
                </option>
                {% for a in accounts %}
                    <option value="{{a.id}}"
                        {% if request.args.get('account_id')|string == a.id|string %}selected{% endif %}>
                        {{a.name}} — {{a.balance|round(2)}} ₽
                    </option>
                {% endfor %}
                <option value="__add__">＋ Добавить счёт</option>
            </select>

            <div id="new-account-fields" hidden
                style="margin:10px 0; padding:12px; border:1px solid var(--border-color, #ccc); border-radius:12px;">
                <label>Название нового счёта</label>
                <input id="new_account_name" name="new_account_name" maxlength="60"
                    placeholder="Например, Основной">

                <label>Начальный баланс, ₽</label>
                <input name="new_account_balance" type="number"
                    step="0.01" value="0">

                <button type="submit" name="action" value="create_account" formnovalidate class="action-add">
                    ＋ Создать счёт
                </button>
            </div>

            <label>Сумма</label>
            <input name="amount" type="number" min="0.01"
                   step="0.01" placeholder="Сумма в рублях" required>

            <label>Категория</label>
            <select name="category" required>
                {% for c in categories %}
                    <option value="{{c}}">{{c}}</option>
                {% endfor %}
            </select>

            <label>Комментарий</label>
            <input name="note" maxlength="200"
                   placeholder="Комментарий">

            <button type="submit" class="action-add">💾 Сохранить операцию</button>
        </form>
        <a href="/">Назад</a>
    </div>
    <script>
    (() => {
        const accountSelect = document.getElementById('account-select');
        const fields = document.getElementById('new-account-fields');
        const nameInput = document.getElementById('new_account_name');
        const balanceInput = document.querySelector('[name="new_account_balance"]');

        function updateAccountFields() {
            const adding = accountSelect.value === '__add__';
            fields.hidden = !adding;
            nameInput.required = adding;
            balanceInput.required = adding;
            if (adding) nameInput.focus();
        }

        accountSelect.addEventListener('change', updateAccountFields);
        updateAccountFields();
    })();
    </script>

    <div class="card">
        <h2>Все операции</h2>
        {% for t in transactions %}
        <div class="transaction-row" style="padding:12px 0;border-bottom:1px solid var(--border-color, #e5e7eb);">
            <p>
                {% if t.kind == 'income' %}
                    <span class="income">+{{t.amount}} ₽</span>
                {% else %}
                    <span class="expense">−{{t.amount}} ₽</span>
                {% endif %}
                — {{t.category}}
                {% if t.note %} · {{t.note}}{% endif %}
            </p>
            <div class="small">{{t.created}}</div>
            <div class="action-row">
                <a href="/edit/{{t.id}}" class="action-edit">✏️ Редактировать</a>
                <form method="post" action="/delete/{{t.id}}" onsubmit="return confirm('Удалить эту операцию?')">
                    <button type="submit" class="action-delete">🗑️ Удалить</button>
                </form>
            </div>
        </div>
        {% else %}
        <p class="small">Операций пока нет.</p>
        {% endfor %}
    </div>
    """

    if request.method == "POST":
        if request.form.get("action") == "create_account":
            name = request.form.get("new_account_name", "").strip()
            try:
                balance = float(request.form.get("new_account_balance", "0"))
                if not name or len(name) > 60 or not math.isfinite(balance):
                    raise ValueError
            except (ValueError, TypeError):
                flash("Укажи название счёта и корректный начальный баланс.")
                return redirect(url_for(
                    "add_transaction",
                    kind=request.form.get("kind", "expense")
                ))

            with connect_db() as db:
                account_count = db.execute(
                    "SELECT COUNT(*) FROM accounts WHERE user_id=?",
                    (user["id"],)
                ).fetchone()[0]

                if account_count >= 2 and not has_access(user):
                    flash("На бесплатном тарифе можно иметь максимум 2 счёта. Удали один из счетов или подключи подписку.")
                    return redirect(url_for("accounts"))

                result = db.execute("""
                    INSERT INTO accounts (user_id, name, balance)
                    VALUES (?, ?, ?)
                """, (user["id"], name, balance))
                new_account_id = result.lastrowid

            return redirect(url_for(
                "add_transaction",
                kind=request.form.get("kind", "expense"),
                account_id=new_account_id
            ))

        if request.form.get("account_id") == "__add__":
            flash("Заполни данные нового счёта и нажми «Создать счёт».")
            return redirect(url_for(
                "add_transaction",
                kind=request.form.get("kind", "expense")
            ))

        try:
            amount = float(request.form.get("amount", "0"))
            kind = request.form.get("kind", "")
            category = request.form.get("category", "")
            note = request.form.get("note", "")[:200]
            account_id = int(request.form.get("account_id", "0"))

            if (
                amount <= 0
                or kind not in ("income", "expense")
                or category not in CATEGORIES
            ):
                raise ValueError

            with connect_db() as db:
                account = db.execute("""
                    SELECT id, balance FROM accounts
                    WHERE id=? AND user_id=?
                """, (account_id, user["id"])).fetchone()

                if account is None:
                    raise ValueError

                if kind == "expense" and amount > (account["balance"] or 0):
                    flash("Недостаточно средств на выбранном счёте.")
                    return redirect(url_for(
                        "add_transaction",
                        kind=kind,
                        account_id=account_id
                    ))

                db.execute("""
                    INSERT INTO transactions
                    (user_id, kind, amount, category, note,
                     created, account_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user["id"], kind, amount, category, note,
                    datetime.now().strftime("%d.%m.%Y %H:%M"),
                    account_id
                ))

                change = amount if kind == "income" else -amount

                db.execute("""
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE id=? AND user_id=?
                """, (change, account_id, user["id"]))

            return redirect(url_for("add_transaction"))

        except (ValueError, TypeError):
            flash("Проверь сумму, категорию и выбранный счёт.")

    return page(
        "Новая операция",
        content,
        categories=CATEGORIES,
        accounts=accounts,
        transactions=transactions
    )

@app.route("/delete/<int:transaction_id>", methods=["POST"])
@login_required
def delete_transaction(transaction_id):
    user = current_user()

    with connect_db() as db:
        transaction = db.execute("""
            SELECT id, kind, amount, account_id
            FROM transactions
            WHERE id=? AND user_id=?
        """, (transaction_id, user["id"])).fetchone()

        if transaction is not None:
            if transaction["account_id"] is not None:
                change = (
                    transaction["amount"]
                    if transaction["kind"] == "income"
                    else -transaction["amount"]
                )

                db.execute("""
                    UPDATE accounts
                    SET balance = balance - ?
                    WHERE id=? AND user_id=?
                """, (
                    change,
                    transaction["account_id"],
                    user["id"]
                ))

            db.execute("""
                DELETE FROM transactions
                WHERE id=? AND user_id=?
            """, (transaction_id, user["id"]))

    return redirect(url_for("index"))


@app.route("/edit/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    user = current_user()

    with connect_db() as db:
        transaction = db.execute("""
            SELECT * FROM transactions
            WHERE id=? AND user_id=?
        """, (transaction_id, user["id"])).fetchone()

    if transaction is None:
        flash("Операция не найдена.")
        return redirect(url_for("index"))

    if request.method == "POST":
        try:
            kind = request.form.get("kind", "")
            amount = float(request.form.get("amount", "0"))
            category = request.form.get("category", "").strip()
            note = request.form.get("note", "").strip()[:200]

            if (
                amount <= 0
                or kind not in ("income", "expense")
                or category not in CATEGORIES
            ):
                raise ValueError

            with connect_db() as db:
                if transaction["account_id"] is not None:
                    old_change = (
                        transaction["amount"]
                        if transaction["kind"] == "income"
                        else -transaction["amount"]
                    )
                    new_change = (
                        amount if kind == "income" else -amount
                    )

                    db.execute("""
                        UPDATE accounts
                        SET balance = balance + ?
                        WHERE id=? AND user_id=?
                    """, (
                        new_change - old_change,
                        transaction["account_id"],
                        user["id"]
                    ))

                db.execute("""
                    UPDATE transactions
                    SET kind=?, amount=?, category=?, note=?
                    WHERE id=? AND user_id=?
                """, (
                    kind, amount, category, note,
                    transaction_id, user["id"]
                ))

            flash("Операция успешно изменена.")
            return redirect(url_for("index"))

        except (ValueError, TypeError):
            flash("Проверь сумму и категорию.")

    content = """
    <div class="card">
        <h2>Редактировать операцию</h2>
        <form method="post">
            <label>Тип операции</label>
            <select name="kind" required>
                <option value="expense"
                    {% if transaction.kind == 'expense' %}selected{% endif %}>
                    Расход
                </option>
                <option value="income"
                    {% if transaction.kind == 'income' %}selected{% endif %}>
                    Доход
                </option>
            </select>

            <label>Сумма</label>
            <input name="amount" type="number" min="0.01" step="0.01"
                   value="{{ transaction.amount }}" required>

            <label>Категория</label>
            <select name="category" required>
                {% for c in categories %}
                    <option value="{{ c }}"
                        {% if c == transaction.category %}selected{% endif %}>
                        {{ c }}
                    </option>
                {% endfor %}
            </select>

            <label>Комментарий</label>
            <input name="note" maxlength="200"
                   value="{{ transaction.note or '' }}">

            <button type="submit" class="action-add">💾 Сохранить изменения</button>
        </form>
        <form method="post" action="/delete/{{ transaction.id }}" onsubmit="return confirm('Удалить эту операцию без возможности восстановления?');">
            <button type="submit" class="action-delete">🗑️ Удалить операцию</button>
        </form>
        <a href="/">Отмена</a>
    </div>
    """

    return page(
        "Редактировать операцию",
        content,
        transaction=transaction,
        categories=CATEGORIES
    )


@app.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    user = current_user()

    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "delete":
            try:
                account_id = int(request.form.get("account_id", "0"))
            except (ValueError, TypeError):
                flash("Счёт не найден.")
                return redirect(url_for("accounts"))
            with connect_db() as db:
                account = db.execute(
                    "SELECT id FROM accounts WHERE id=? AND user_id=?",
                    (account_id, user["id"])
                ).fetchone()
                if not account:
                    flash("Счёт не найден.")
                else:
                    linked = db.execute(
                        "SELECT COUNT(*) FROM transactions WHERE account_id=? AND user_id=?",
                        (account_id, user["id"])
                    ).fetchone()[0]
                    if linked:
                        flash("Нельзя удалить счёт: к нему привязаны операции. Сначала перенесите операции на другой счёт.")
                    else:
                        db.execute(
                            "DELETE FROM accounts WHERE id=? AND user_id=?",
                            (account_id, user["id"])
                        )
                        flash("Счёт удалён.")
            return redirect(url_for("accounts"))

        if action == "update_name":
            account_id = int(request.form.get("account_id", "0"))
            new_name = request.form.get("name", "").strip()
            if not new_name or len(new_name) > 60:
                flash("Название должно содержать от 1 до 60 символов.")
            else:
                with connect_db() as db:
                    result = db.execute(
                        "UPDATE accounts SET name=? WHERE id=? AND user_id=?",
                        (new_name, account_id, user["id"])
                    )
                    if result.rowcount:
                        flash("Название счёта обновлено.")
                    else:
                        flash("Счёт не найден.")
            return redirect(url_for("accounts"))

        if action == "update_balance":
            try:
                account_id = int(request.form.get("account_id", "0"))
                balance = float(request.form.get("balance", ""))
            except (ValueError, TypeError):
                flash("Укажи корректный баланс.")
                return redirect(url_for("accounts"))
            with connect_db() as db:
                account = db.execute(
                    "SELECT id FROM accounts WHERE id=? AND user_id=?",
                    (account_id, user["id"])
                ).fetchone()
                if account:
                    db.execute(
                        "UPDATE accounts SET balance=? WHERE id=? AND user_id=?",
                        (balance, account_id, user["id"])
                    )
                    flash("Баланс счёта обновлён.")
                else:
                    flash("Счёт не найден.")
            return redirect(url_for("accounts"))

        name = request.form.get("name", "").strip()
        try:
            balance = float(request.form.get("balance", "0"))
            if name and len(name) <= 60:
                with connect_db() as db:
                    db.execute("""
                        INSERT INTO accounts(user_id,name,balance)
                        VALUES(?,?,?)
                    """, (user["id"], name, balance))
                return redirect(url_for("index"))
        except ValueError:
            flash("Неверная сумма.")

    with connect_db() as db:
        user_accounts = db.execute(
            "SELECT id, name, balance FROM accounts WHERE user_id=? ORDER BY id",
            (user["id"],)
        ).fetchall()

    content = """
    <div class="card">
        <h2>Мои счета</h2>
        {% if accounts %}
            {% for account in accounts %}
                <div class="card">
                    <h3>{{ account["name"] }}</h3>
                    <form method="post">
                        <input type="hidden" name="action" value="update_name">
                        <input type="hidden" name="account_id" value="{{ account["id"] }}">
                        <label>Название счёта</label>
                        <input name="name" value="{{ account["name"] }}" maxlength="60" required>
                        <button type="submit" class="action-add">💾 Сохранить название</button>
                    </form>
                    <form method="post">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="account_id" value="{{ account["id"] }}">
                        <button type="submit" class="action-delete">🗑️ Удалить счёт</button>
                    </form>
                    <form method="post">
                        <input type="hidden" name="action" value="update_balance">
                        <input type="hidden" name="account_id" value="{{ account["id"] }}">
                        <label>Баланс</label>
                        <input name="balance" type="number" step="0.01" value="{{ account["balance"] }}" required>
                        <button type="submit" class="action-add">💾 Сохранить баланс</button>
                    </form>
                </div>
            {% endfor %}
        {% else %}
            <p>Пока нет счетов. Добавь первый ниже.</p>
        {% endif %}
    </div>
    <div class="card">
    <h2>Добавить новый счёт</h2>
    <form method="post">
        <input name="name" placeholder="Например, наличные" required>
        <input name="balance" type="number" step="0.01"
               placeholder="Начальный баланс" value="0">
        <button type="submit" class="action-add">＋ Добавить счёт</button>
    </form>
    <a href="/">Назад</a>
    </div>
    """

    return page("Мои счета", content, accounts=user_accounts)




@app.route("/debts", methods=["GET", "POST"])
@login_required
def debts():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    if request.method == "POST":
        action = request.form.get("action", "add")

        if action == "repay":
            try:
                debt_id = int(request.form.get("debt_id", "0"))
                payment = float(request.form.get("payment_amount", "0"))
                account_id = int(request.form.get("account_id", "0"))
            except (ValueError, TypeError):
                debt_id = 0
                payment = 0
                account_id = 0

            with connect_db() as db:
                debt = db.execute(
                    "SELECT * FROM debts WHERE id=? AND user_id=?",
                    (debt_id, user["id"])
                ).fetchone()

                account = db.execute(
                    "SELECT id FROM accounts WHERE id=? AND user_id=?",
                    (account_id, user["id"])
                ).fetchone()

                if not debt:
                    flash("Долг не найден.")
                elif not account:
                    flash("Выбери свой счёт.")
                else:
                    remaining = max(
                        0, float(debt["amount"]) -
                        float(debt["paid_amount"] or 0)
                    )

                    if payment <= 0 or payment > remaining:
                        flash("Укажи сумму в пределах оставшегося долга.")
                    else:
                        kind = (
                            "expense" if debt["direction"] == "i_owe"
                            else "income"
                        )
                        change = payment if kind == "income" else -payment
                        note = (
                            "Погашение долга: " + debt["person"]
                        )[:200]

                        db.execute("""
                            INSERT INTO transactions
                            (user_id, kind, amount, category, note,
                             created, account_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            user["id"], kind, payment, "Другое", note,
                            datetime.now().strftime("%d.%m.%Y %H:%M"),
                            account_id
                        ))

                        db.execute("""
                            UPDATE accounts
                            SET balance = balance + ?
                            WHERE id=? AND user_id=?
                        """, (change, account_id, user["id"]))

                        db.execute("""
                            UPDATE debts
                            SET paid_amount = COALESCE(paid_amount, 0) + ?
                            WHERE id=? AND user_id=?
                        """, (payment, debt_id, user["id"]))

                        flash("Погашение и финансовая операция записаны.")

            return redirect(url_for("debts"))

        direction = request.form.get("direction", "").strip()
        person = request.form.get("person", "").strip()
        note = request.form.get("note", "").strip()

        try:
            amount = float(request.form.get("amount", "0"))
        except ValueError:
            amount = 0

        if direction not in ("i_owe", "owed_to_me"):
            flash("Выбери тип долга.")
        elif not person or amount <= 0:
            flash("Укажи имя и положительную сумму.")
        else:
            with connect_db() as db:
                db.execute("""
                    INSERT INTO debts
                    (user_id, direction, person, amount, paid_amount, note, created)
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                """, (
                    user["id"], direction, person[:100], amount,
                    note[:200], datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
            return redirect(url_for("debts"))

    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM debts WHERE user_id=? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()
        accounts = db.execute(
            "SELECT id, name, balance FROM accounts "
            "WHERE user_id=? ORDER BY id",
            (user["id"],)
        ).fetchall()

    owe = sum(max(0, r["amount"] - r["paid_amount"])
              for r in rows if r["direction"] == "i_owe")
    owed_to_me = sum(max(0, r["amount"] - r["paid_amount"])
                     for r in rows if r["direction"] == "owed_to_me")
    paid = sum(r["paid_amount"] for r in rows
               if r["direction"] == "i_owe")

    content = """
    <div class="card">
        <h2>Долги</h2>
        <p>Осталось отдать: <strong class="expense">{{ owe|round(2) }} ₽</strong></p>
        <p>Должны мне: <strong class="income">{{ owed_to_me|round(2) }} ₽</strong></p>
        <p>Уже отдал: {{ paid|round(2) }} ₽</p>
    </div>

    <div class="card">
        <h3>Добавить долг</h3>
        <form method="post">
            <label>Тип долга</label>
            <select name="direction" required>
                <option value="i_owe">Я должен</option>
                <option value="owed_to_me">Должны мне</option>
            </select>
            <label>Кому или от кого</label>
            <input name="person" maxlength="100" required>
            <label>Сумма в рублях</label>
            <input name="amount" type="number" min="0.01" step="0.01" required>
            <label>Комментарий</label>
            <input name="note" maxlength="200">
            <button type="submit">Добавить долг</button>
        </form>
        <a href="/">На главную</a>
    </div>

    <div class="card">
        <h3>История</h3>
        {% for d in rows %}
            <hr>
            <p><strong>{{ d.person }}</strong></p>
            <p>{{ "Я должен" if d.direction == "i_owe" else "Должны мне" }}</p>
            <p>Сумма: {{ d.amount|round(2) }} ₽</p>
            <p>Уже погашено: {{ (d.paid_amount or 0)|round(2) }} ₽</p>
            <p>Остаток: {{ (d.amount - (d.paid_amount or 0))|round(2) }} ₽</p>
            {% if d.note %}<p class="small">{{ d.note }}</p>{% endif %}
            {% if d.amount - (d.paid_amount or 0) > 0 %}
                <form method="post">
                    <input type="hidden" name="action" value="repay">
                    <input type="hidden" name="debt_id" value="{{ d.id }}">
                    <label>Сумма погашения, ₽</label>
                    <input name="payment_amount" type="number"
                           min="0.01"
                           max="{{ d.amount - (d.paid_amount or 0) }}"
                           step="0.01" required>
                    <label>Счёт</label>
                    <select name="account_id" required>
                        <option value="" disabled selected>
                            Выбери счёт
                        </option>
                        {% for a in accounts %}
                            <option value="{{ a.id }}">
                                {{ a.name }} — {{ a.balance|round(2) }} ₽
                            </option>
                        {% endfor %}
                    </select>
                    <button type="submit" class="action-add">💸 Записать погашение</button>
                </form>
            {% else %}
                <p class="income">Долг полностью погашен!</p>
            {% endif %}
        {% else %}
            <p class="small">Долгов пока нет.</p>
        {% endfor %}
    </div>
    """

    return page(
        "Долги", content,
        rows=rows, owe=owe, owed_to_me=owed_to_me, paid=paid,
        accounts=accounts
    )



@app.route("/investments", methods=["GET", "POST"])
@login_required
def investments():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        asset_type = request.form.get("asset_type", "").strip()
        note = request.form.get("note", "").strip()

        try:
            amount = float(request.form.get("amount", "0"))
            current_value = float(
                request.form.get("current_value", "0")
            )
        except ValueError:
            amount = 0
            current_value = -1

        allowed_types = (
            "Криптовалюта", "Акции", "Фонды",
            "Бизнес", "Другое"
        )

        if not name or len(name) > 100:
            flash("Укажи название актива (до 100 символов).")
        elif asset_type not in allowed_types:
            flash("Выбери тип актива.")
        elif amount <= 0 or current_value < 0:
            flash("Проверь суммы инвестиций.")
        else:
            with connect_db() as db:
                db.execute("""
                    INSERT INTO investments
                    (user_id, name, asset_type, amount,
                     current_value, note, created)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    user["id"], name, asset_type, amount,
                    current_value, note[:200],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                investment_id = db.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]
                db.execute("""
                    INSERT INTO investment_history
                    (investment_id, user_id, amount, current_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    investment_id, user["id"], amount, current_value,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
            flash("Инвестиция добавлена.")
            return redirect(url_for("investments"))

    with connect_db() as db:
        rows = db.execute(
            "SELECT * FROM investments WHERE user_id=? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()

    invested = sum(float(r["amount"]) for r in rows)
    current_total = sum(float(r["current_value"] or 0) for r in rows)
    profit = current_total - invested
    profit_percent = profit / invested * 100 if invested else 0

    content = """
    <div class="card">
        <h2>Мои инвестиции</h2>
        <p>Всего вложено:
            <strong>{{ invested|round(2) }} ₽</strong>
        </p>
        <p>Текущая стоимость:
            <strong>{{ current_total|round(2) }} ₽</strong>
        </p>
        <p>Прибыль или убыток:
            <strong class="{{ 'income' if profit >= 0 else 'expense' }}">
                {{ '+' if profit > 0 else '' }}{{ profit|round(2) }} ₽
            </strong>
        </p>
        <p>Изменение: {{ profit_percent|round(2) }}%</p>
        <p class="small">
            Расчёт основан на указанных тобой суммах.
            Рыночные цены автоматически не обновляются.
        </p>
    </div>

    <div class="card">
        <h3>Добавить инвестицию</h3>
        <form method="post">
            <label>Название актива</label>
            <input name="name" maxlength="100"
                   placeholder="Например, Bitcoin" required>

            <label>Тип актива</label>
            <select name="asset_type" required>
                <option value="Криптовалюта">Криптовалюта</option>
                <option value="Акции">Акции</option>
                <option value="Фонды">Фонды</option>
                <option value="Бизнес">Бизнес</option>
                <option value="Другое">Другое</option>
            </select>

            <label>Вложенная сумма, ₽</label>
            <input name="amount" type="number" min="0.01"
                   step="0.01" required>

            <label>Текущая стоимость, ₽</label>
            <input name="current_value" type="number" min="0"
                   step="0.01" required>

            <label>Комментарий</label>
            <input name="note" maxlength="200">

            <button type="submit" class="action-add">＋ Добавить инвестицию</button>
        </form>
        <a href="/">На главную</a>
    </div>

    <div class="card">
        <h3>Мои активы</h3>
        {% for item in rows %}
            <hr>
            <p><strong>{{ item.name }}</strong></p>
            <p>Тип: {{ item.asset_type }}</p>
            <p>Вложено: {{ item.amount|round(2) }} ₽</p>
            <p>Текущая стоимость:
                {{ (item.current_value or 0)|round(2) }} ₽
            </p>
            <p>Результат:
                {% set result = (item.current_value or 0) - item.amount %}
                <strong class="{{ 'income' if result >= 0 else 'expense' }}">
                    {{ '+' if result > 0 else '' }}{{ result|round(2) }} ₽
                </strong>
            </p>
            {% if item.note %}
                <p class="small">{{ item.note }}</p>
            {% endif %}
            <div class="action-row">
<a class="action-edit"
               href="{{ url_for('edit_investment', investment_id=item.id) }}">
                Редактировать
            </a>
<form method="post"
                  action="{{ url_for('delete_investment', investment_id=item.id) }}"
                  onsubmit="return confirm('Удалить эту инвестицию?')">
                <button type="submit" class="action-delete">🗑️ Удалить</button>
            </form>
</div>
        {% else %}
            <p class="small">Инвестиции пока не добавлены.</p>
        {% endfor %}
    </div>
    """

    return page(
        "Инвестиции", content,
        rows=rows, invested=invested,
        current_total=current_total, profit=profit,
        profit_percent=profit_percent
    )



@app.route("/investments/edit/<int:investment_id>", methods=["GET", "POST"])
@login_required
def edit_investment(investment_id):
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    with connect_db() as db:
        item = db.execute(
            "SELECT * FROM investments WHERE id=? AND user_id=?",
            (investment_id, user["id"])
        ).fetchone()

    if not item:
        flash("Инвестиция не найдена.")
        return redirect(url_for("investments"))

    allowed_types = (
        "Криптовалюта", "Акции", "Фонды", "Бизнес", "Другое"
    )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        asset_type = request.form.get("asset_type", "").strip()
        note = request.form.get("note", "").strip()

        try:
            amount = float(request.form.get("amount", "0"))
            current_value = float(request.form.get("current_value", "-1"))
        except ValueError:
            amount = 0
            current_value = -1

        if not name or len(name) > 100:
            flash("Укажи название до 100 символов.")
        elif asset_type not in allowed_types:
            flash("Выбери тип актива.")
        elif amount <= 0 or current_value < 0:
            flash("Проверь суммы инвестиций.")
        else:
            with connect_db() as db:
                db.execute("""
                    UPDATE investments
                    SET name=?, asset_type=?, amount=?,
                        current_value=?, note=?
                    WHERE id=? AND user_id=?
                """, (
                    name, asset_type, amount, current_value,
                    note[:200], investment_id, user["id"]
                ))
                db.execute("""
                    INSERT INTO investment_history
                    (investment_id, user_id, amount, current_value, recorded_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    investment_id, user["id"], amount, current_value,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
            flash("Инвестиция обновлена.")
            return redirect(url_for("investments"))

    content = """
    <div class="card">
        <h2>Редактировать инвестицию</h2>
        <form method="post">
            <label>Название актива</label>
            <input name="name" maxlength="100"
                   value="{{ item.name }}" required>

            <label>Тип актива</label>
            <select name="asset_type" required>
                {% for t in ["Криптовалюта", "Акции", "Фонды", "Бизнес", "Другое"] %}
                    <option value="{{ t }}"
                        {% if item.asset_type == t %}selected{% endif %}>
                        {{ t }}
                    </option>
                {% endfor %}
            </select>

            <label>Вложенная сумма, ₽</label>
            <input name="amount" type="number" min="0.01"
                   step="0.01" value="{{ item.amount }}" required>

            <label>Текущая стоимость, ₽</label>
            <input name="current_value" type="number" min="0"
                   step="0.01" value="{{ item.current_value or 0 }}" required>

            <label>Комментарий</label>
            <input name="note" maxlength="200" value="{{ item.note or '' }}">

            <button type="submit">Сохранить изменения</button>
        </form>
        <a href="/investments">Назад к инвестициям</a>
    </div>
    """

    return page("Редактировать инвестицию", content, item=item)


@app.route("/investments/delete/<int:investment_id>", methods=["POST"])
@login_required
def delete_investment(investment_id):
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    with connect_db() as db:
        result = db.execute(
            "DELETE FROM investments WHERE id=? AND user_id=?",
            (investment_id, user["id"])
        )

    if result.rowcount:
        flash("Инвестиция удалена.")
    else:
        flash("Инвестиция не найдена.")

    return redirect(url_for("investments"))



@app.route("/investments/history/<int:investment_id>")
@login_required
def investment_history(investment_id):
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    with connect_db() as db:
        item = db.execute(
            "SELECT * FROM investments WHERE id=? AND user_id=?",
            (investment_id, user["id"])
        ).fetchone()

        if not item:
            flash("Инвестиция не найдена.")
            return redirect(url_for("investments"))

        history = db.execute("""
            SELECT * FROM investment_history
            WHERE investment_id=? AND user_id=?
            ORDER BY id DESC
        """, (investment_id, user["id"])).fetchall()

    content = """
    <div class="card">
        <h2>История стоимости</h2>
        <p><strong>{{ item.name }}</strong></p>
        <p>Текущая стоимость:
            {{ (item.current_value or 0)|round(2) }} ₽
        </p>
        <a href="{{ url_for('edit_investment', investment_id=item.id) }}">
            Редактировать актив
        </a>
        <a href="/investments">Ко всем инвестициям</a>
    </div>

    <div class="card">
        <h3>Изменения</h3>
        {% for h in history %}
            <hr>
            <p>{{ h.recorded_at }}</p>
            <p>Вложено: {{ h.amount|round(2) }} ₽</p>
            <p>Стоимость: {{ h.current_value|round(2) }} ₽</p>
            <p>Прибыль или убыток:
                {% set result = h.current_value - h.amount %}
                <strong class="{{ 'income' if result >= 0 else 'expense' }}">
                    {{ '+' if result > 0 else '' }}{{ result|round(2) }} ₽
                </strong>
            </p>
        {% else %}
            <p class="small">История пока пуста.</p>
        {% endfor %}
    </div>
    """

    return page("История стоимости", content, item=item, history=history)


@app.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    current_month = datetime.now().strftime("%Y-%m")

    if request.method == "POST":
        category = request.form.get("category", "").strip()

        try:
            amount = float(request.form.get("amount", "0"))

            if category not in CATEGORIES or amount <= 0:
                raise ValueError

            with connect_db() as db:
                db.execute("""
                    INSERT INTO budgets (user_id, category, amount)
                    VALUES (?, ?, ?)
                    ON CONFLICT(user_id, category)
                    DO UPDATE SET amount=excluded.amount
                """, (user["id"], category, amount))

            flash("Бюджет сохранён.")
            return redirect(url_for("budgets"))

        except (ValueError, TypeError):
            flash("Выбери категорию и укажи сумму больше нуля.")

    with connect_db() as db:
        budget_rows = db.execute("""
            SELECT
                b.category,
                b.amount AS budget,
                COALESCE(SUM(t.amount), 0) AS spent
            FROM budgets b
            LEFT JOIN transactions t
                ON t.user_id = b.user_id
                AND t.category = b.category
                AND t.kind = 'expense'
                AND substr(t.created, 7, 4) || '-' ||
                    substr(t.created, 4, 2) = ?
            WHERE b.user_id = ?
            GROUP BY b.id
            ORDER BY b.category
        """, (current_month, user["id"])).fetchall()

    budget_list = []

    for row in budget_rows:
        budget = row["budget"]
        spent = row["spent"]

        budget_list.append({
            "category": row["category"],
            "budget": budget,
            "spent": spent,
            "remaining": budget - spent,
            "percent": round(spent / budget * 100, 1),
            "status": (
                "Лимит превышен!" if spent >= budget
                else "Внимание! Использовано 80% бюджета"
                if spent >= budget * 0.8
                else "Всё в норме"
            )
        })

    content = """
    <div class="card">
        <h2>Месячные бюджеты</h2>
        <p class="small">Месяц: {{current_month}}</p>

        <form method="post">
            <label>Категория</label>
            <select name="category" required>
                {% for c in categories %}
                    <option value="{{c}}">{{c}}</option>
                {% endfor %}
            </select>

            <label>Лимит на месяц, ₽</label>
            <input name="amount" type="number"
                   min="0.01" step="0.01" required>

            <button type="submit" class="action-add">💾 Сохранить бюджет</button>
        </form>
    </div>

    {% for b in budget_list %}
        <div class="card">
            <h3>{{b.category}}</h3>

            <p>Лимит: {{b.budget|round(2)}} ₽</p>
            <p>Потрачено: {{b.spent|round(2)}} ₽</p>

            <p>
                Остаток:
                <strong>{{b.remaining|round(2)}} ₽</strong>
            </p>

            <p>Использовано: {{b.percent}}%</p>

            <p style="font-weight:bold;color:{{'#ef4444' if b.percent >= 100 else '#d97706' if b.percent >= 80 else '#10b981'}};">
                {{b.status}}
            </p>

            <div style="background:#e5e7eb;border-radius:8px;height:12px;overflow:hidden;">
                <div style="
                    background:{{'#ef4444' if b.percent >= 100 else '#10b981'}};
                    width:{{[b.percent, 100]|min}}%;
                    height:12px;
                "></div>
            </div>
        </div>
    {% else %}
        <div class="card">
            <p>Пока нет бюджетов. Добавь первый бюджет выше.</p>
        </div>
    {% endfor %}

    <div class="card">
        <a href="/">Вернуться на главную</a>
    </div>
    """

    return page(
        "Бюджеты",
        content,
        categories=CATEGORIES,
        budget_list=budget_list,
        current_month=current_month
    )

@app.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    if request.method == "POST":
        action = request.form.get("action", "create")

        try:
            if action == "create":
                name = request.form.get("name", "").strip()
                target = float(request.form.get("target_amount", "0"))
                date = request.form.get("target_date", "").strip()

                if not name or target <= 0:
                    raise ValueError

                with connect_db() as db:
                    db.execute(
                        "INSERT INTO financial_goals "
                        "(user_id, name, target_amount, saved_amount, target_date) "
                        "VALUES (?, ?, ?, 0, ?)",
                        (user["id"], name, target, date)
                    )
                flash("Финансовая цель создана.")

            elif action == "add":
                goal_id = int(request.form.get("goal_id", "0"))
                amount = float(request.form.get("amount", "0"))

                if amount <= 0:
                    raise ValueError

                with connect_db() as db:
                    result = db.execute(
                        "UPDATE financial_goals "
                        "SET saved_amount = saved_amount + ? "
                        "WHERE id = ? AND user_id = ?",
                        (amount, goal_id, user["id"])
                    )
                flash(
                    "Накопления обновлены."
                    if result.rowcount else "Цель не найдена."
                )

            elif action == "edit":
                goal_id = int(request.form.get("goal_id", "0"))
                name = request.form.get("name", "").strip()
                target = float(request.form.get("target_amount", "0"))
                date = request.form.get("target_date", "").strip()

                if not name or target <= 0:
                    raise ValueError

                with connect_db() as db:
                    result = db.execute(
                        "UPDATE financial_goals "
                        "SET name = ?, target_amount = ?, target_date = ? "
                        "WHERE id = ? AND user_id = ?",
                        (name, target, date, goal_id, user["id"])
                    )
                flash(
                    "Цель изменена."
                    if result.rowcount else "Цель не найдена."
                )

            elif action == "delete":
                goal_id = int(request.form.get("goal_id", "0"))

                with connect_db() as db:
                    result = db.execute(
                        "DELETE FROM financial_goals "
                        "WHERE id = ? AND user_id = ?",
                        (goal_id, user["id"])
                    )
                flash(
                    "Цель удалена."
                    if result.rowcount else "Цель не найдена."
                )

            else:
                flash("Неизвестное действие.")

        except (ValueError, TypeError):
            flash("Проверь название цели и введённые суммы.")

        return redirect(url_for("goals"))

    with connect_db() as db:
        rows = db.execute(
            "SELECT id, name, target_amount, saved_amount, target_date "
            "FROM financial_goals WHERE user_id = ? ORDER BY id DESC",
            (user["id"],)
        ).fetchall()

    goal_list = []

    for row in rows:
        target = row["target_amount"]
        saved = row["saved_amount"] or 0
        percent = round(saved / target * 100, 1) if target > 0 else 0

        goal_list.append({
            "id": row["id"],
            "name": row["name"],
            "target_amount": target,
            "saved_amount": saved,
            "target_date": row["target_date"],
            "percent": percent,
            "bar_percent": min(percent, 100),
            "remaining": max(target - saved, 0)
        })

    content = """
    <div class="card">
        <h2>Финансовые цели</h2>
        <p class="small">Создавай цели и отслеживай накопления.</p>
        <form method="post">
            <input type="hidden" name="action" value="create">
            <label>Название цели</label>
            <input name="name" maxlength="100"
                   placeholder="Например, финансовая подушка" required>
            <label>Сколько нужно накопить, ₽</label>
            <input name="target_amount" type="number"
                   min="0.01" step="0.01" required>
            <label>Желаемая дата (необязательно)</label>
            <input name="target_date" type="date">
            <button type="submit" class="action-add">🎯 Создать цель</button>
        </form>
    </div>

    {% for g in goal_list %}
    <div class="card">
        <h3>{{ g.name }}</h3>
        <p>Цель: {{ g.target_amount|round(2) }} ₽</p>
        <p>Накоплено: {{ g.saved_amount|round(2) }} ₽</p>
        <p>Осталось: {{ g.remaining|round(2) }} ₽</p>
        {% if g.target_date %}
        <p>Желаемая дата: {{ g.target_date }}</p>
        {% endif %}
        <p>Выполнено: {{ g.percent }}%</p>

        <div style="background:#e5e7eb;border-radius:8px;height:12px;overflow:hidden;">
            <div style="background:#10b981;width:{{ g.bar_percent }}%;height:12px;"></div>
        </div>

        {% if g.saved_amount >= g.target_amount %}
        <p style="color:#10b981;font-weight:bold;">Цель достигнута!</p>
        {% endif %}

        <details style="margin-top:12px;">
            <summary>Изменить цель</summary>
            <form method="post">
                <input type="hidden" name="action" value="edit">
                <input type="hidden" name="goal_id" value="{{ g.id }}">
                <label>Название</label>
                <input name="name" maxlength="100"
                       value="{{ g.name }}" required>
                <label>Целевая сумма, ₽</label>
                <input name="target_amount" type="number"
                       min="0.01" step="0.01"
                       value="{{ g.target_amount }}" required>
                <label>Желаемая дата</label>
                <input name="target_date" type="date"
                       value="{{ g.target_date }}">
                <button type="submit" class="action-add">💾 Сохранить изменения</button>
            </form>
        </details>

        <form method="post" style="margin-top:12px;">
            <input type="hidden" name="action" value="add">
            <input type="hidden" name="goal_id" value="{{ g.id }}">
            <label>Добавить к накоплениям, ₽</label>
            <input name="amount" type="number"
                   min="0.01" step="0.01" required>
            <button type="submit" class="action-add">＋ Добавить накопления</button>
        </form>

        <form method="post" style="margin-top:12px;"
              onsubmit="return confirm('Точно удалить эту цель?');">
            <input type="hidden" name="action" value="delete">
            <input type="hidden" name="goal_id" value="{{ g.id }}">
            <button type="submit" class="action-delete">🗑️ Удалить цель</button>
        </form>
    </div>
    {% else %}
    <div class="card"><p>Пока нет целей. Создай первую выше.</p></div>
    {% endfor %}

    <div class="card">
        <a href="/more">Вернуться в раздел «Ещё»</a>
    </div>
    """

    return page("Финансовые цели", content, goal_list=goal_list)

@app.route("/more")
@login_required
def more():
    content = """
    <div class="card" style="padding:12px;background:var(--surface);border:1px solid var(--border);border-radius:20px;">
        <h2 style="margin:8px 8px 16px;">Ещё</h2>

        {% for url, icon, bg, color, title, description in [
            ('/budgets', '◷', '#eef2ff', '#4f46e5', 'Бюджеты', 'Лимиты расходов и предупреждения'),
            ('/goals', '◎', '#dcfce7', '#15803d', 'Финансовые цели', 'Накопления и прогресс целей'),
            ('/plans', '♛', '#fef3c7', '#b45309', 'Моя подписка', 'Тариф и срок действия'),
            ('/about', 'ⓘ', '#dcfce7', '#15803d', 'О нас', 'Информация о MoneyTrack'),
            ('/contacts', '✉', '#fce7f3', '#be185d', 'Контакты', 'Связь с разработчиком'),
            ('/accounts', '▤', '#e0f2fe', '#0369a1', 'Мои счета', 'Управление счетами'),
            ('/debts', '⇄', '#f3e8ff', '#7e22ce', 'Долги', 'Учёт долгов и возвратов'),
            ('/investments', '↗', '#dcfce7', '#15803d', 'Инвестиции', 'Управление инвестициями'),
            ('/recurring', '▦', '#ffedd5', '#c2410c', 'Регулярные платежи', 'Плановые расходы'),
            ('/logout', '↪', '#f1f5f9', '#475569', 'Выйти', 'Завершить сеанс')
        ] %}
            <a href="{{url}}" style="
                display:flex;
                align-items:center;
                gap:12px;
                padding:14px 10px;
                background:var(--surface-light);
                border:1px solid var(--border);
                border-radius:14px;
                margin-bottom:8px;
                box-shadow:0 4px 12px #00000018;
                text-decoration:none;
                color:var(--text);
                border-bottom:1px solid var(--border);
            ">
                <span style="
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    flex-shrink:0;
                    width:44px;
                    height:44px;
                    border-radius:12px;
                    background:#243a55;
                    color:var(--green);
                    font-size:25px;
                ">{{icon}}</span>

                <span style="flex:1;min-width:0;">
                    <span style="display:block;font-weight:600;font-size:15px;">
                        {{title}}
                    </span>
                    <span style="display:block;color:var(--muted);font-size:12px;margin-top:4px;">
                        {{description}}
                    </span>
                </span>

                <span style="color:var(--muted);font-size:23px;">›</span>
            </a>
        {% endfor %}
    </div>
    """
    return page("Ещё", content)


@app.route("/about")
@login_required
def about():
    content = """
    <div class="card">
        <h2>О нас</h2>
        <p>MoneyTrack — приложение для учёта личных финансов.</p>
        <p>Следи за доходами, расходами, счетами и бюджетами в одном месте.</p>
        <a href="/more">Вернуться в раздел «Ещё»</a>
    </div>
    """
    return page("О нас", content)


@app.route("/contacts")
@login_required
def contacts():
    content = """
    <div class="card">
        <h2>Контакты</h2>
<div style="display:flex;align-items:center;gap:14px;padding:14px;margin:12px 0;background:#18212f;border-radius:14px;">
        <div style="width:42px;height:42px;display:flex;align-items:center;justify-content:center;background:#229ED9;border-radius:12px;color:white;font-size:23px;"><svg width="25" height="25" viewBox="0 0 24 24" fill="white" aria-label="Telegram"><path d="M22 2 2 10l7 3 3 7L22 2ZM9 13l8-7-5 9" stroke="white" stroke-width="1.2" stroke-linejoin="round"/></svg></div>
        <div style="flex:1;">
            <strong>Telegram</strong><br>
            <a href="https://t.me/veldenoff" target="_blank" rel="noopener noreferrer">@veldenoff</a>
        </div>
    </div>
    <div style="display:flex;align-items:center;gap:14px;padding:14px;margin:12px 0;background:#18212f;border-radius:14px;">
        <div style="width:42px;height:42px;display:flex;align-items:center;justify-content:center;background:#168DE2;border-radius:12px;color:white;font-size:22px;font-weight:bold;">M</div>
        <div style="flex:1;">
            <strong>MAX</strong><br>
            <a href="https://h1.nu/1AB0E" target="_blank" rel="noopener noreferrer">Написать в MAX</a>
        </div>
    </div>
    <div style="display:flex;align-items:center;gap:14px;padding:14px;margin:12px 0;background:#18212f;border-radius:14px;">
        <div style="width:42px;height:42px;display:flex;align-items:center;justify-content:center;background:linear-gradient(45deg,#FCAF45,#DD2A7B,#8134AF);border-radius:12px;color:white;font-size:22px;"><svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.2" aria-label="Instagram"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="white" stroke="none"/></svg></div>
        <div style="flex:1;">
            <strong>Instagram</strong><br>
            <a href="https://www.instagram.com/veldenoff/" target="_blank" rel="noopener noreferrer">@veldenoff</a>
        </div>
    </div>
    <div style="display:flex;align-items:center;gap:14px;padding:14px;margin:12px 0;background:#18212f;border-radius:14px;">
        <div style="width:42px;height:42px;display:flex;align-items:center;justify-content:center;background:#0077FF;border-radius:12px;color:white;font-size:18px;font-weight:bold;"><svg width="27" height="27" viewBox="0 0 24 24" fill="white" aria-label="VK"><path d="M3 7h4c.4 4 2.3 5.8 3.7 6.2V7h3.8v3.8c1.4-.2 3-2 3.5-3.8h3.8c-.4 2.5-2.2 4.5-3.7 5.5 1.5.8 3.5 2.6 4.4 5.5h-4.2c-.8-1.8-2.1-3.2-3.8-3.4V18h-.5C7.5 18 3.5 13.5 3 7Z"/></svg></div>
        <div style="flex:1;">
            <strong>ВКонтакте</strong><br>
            <a href="https://vk.com/denivelich" target="_blank" rel="noopener noreferrer">@denivelich</a>
        </div>
    </div>        <a href="/more">Вернуться в раздел «Ещё»</a>
    </div>
    """
    return page("Контакты", content)


@app.route("/recurring", methods=["GET", "POST"])
@login_required
def recurring():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        frequency = request.form.get("frequency", "").strip()
        next_date = request.form.get("next_date", "").strip()
        note = request.form.get("note", "").strip()

        try:
            amount = float(request.form.get("amount", "0"))

            datetime.strptime(next_date, "%Y-%m-%d")

            if (
                not name
                or amount <= 0
                or category not in CATEGORIES
                or frequency not in (
                    "monthly", "weekly", "yearly"
                )
            ):
                raise ValueError

            with connect_db() as db:
                db.execute("""
                    INSERT INTO recurring_payments
                    (user_id, name, amount, category, frequency,
                     next_date, note, created)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user["id"],
                    name,
                    amount,
                    category,
                    frequency,
                    next_date,
                    note,
                    datetime.now().strftime("%d.%m.%Y %H:%M")
                ))

            flash("Регулярный платеж добавлен.")
            return redirect(url_for("recurring"))

        except (ValueError, TypeError):
            flash("Проверь название, сумму, категорию и дату.")

    with connect_db() as db:
        payments = db.execute("""
            SELECT * FROM recurring_payments
            WHERE user_id=? AND active=1
            ORDER BY next_date
        """, (user["id"],)).fetchall()

    with connect_db() as db:
        accounts = db.execute("""
            SELECT id, name, balance
            FROM accounts
            WHERE user_id=?
            ORDER BY id
        """, (user["id"],)).fetchall()
    today = datetime.now().date()
    payment_list = []

    for p in payments:
        due_date = datetime.strptime(
            p["next_date"], "%Y-%m-%d"
        ).date()

        days_left = (due_date - today).days

        if days_left < 0:
            status = "Просрочен"
        elif days_left == 0:
            status = "Оплатить сегодня"
        elif days_left <= 3:
            status = "Скоро платеж"
        else:
            status = "Запланирован"

        payment_list.append({
            "id": p["id"],
            "name": p["name"],
            "amount": p["amount"],
            "category": p["category"],
            "frequency": p["frequency"],
            "next_date": p["next_date"],
            "note": p["note"],
            "status": status,
            "days_left": days_left
        })

    content = """
    <div class="card">
        <h2>Регулярные платежи</h2>
        <p class="small">
            Добавляй аренду, подписки и другие повторяющиеся платежи.
            Деньги автоматически не списываются.
        </p>

        <p>
            <a href="/calendar/export.ics">
                📅 Экспорт в Google Календарь (.ics)
            </a>
        </p>

        <form method="post">
            <label>Название платежа</label>
            <input name="name" placeholder="Например, аренда" required>

            <label>Сумма, ₽</label>
            <input name="amount" type="number"
                   min="0.01" step="0.01" required>

            <label>Категория</label>
            <select name="category" required>
                {% for c in categories %}
                    <option value="{{c}}">{{c}}</option>
                {% endfor %}
            </select>

            <label>Периодичность</label>
            <select name="frequency" required>
                <option value="monthly">Каждый месяц</option>
                <option value="weekly">Каждую неделю</option>
                <option value="yearly">Каждый год</option>
            </select>

            <label>Дата следующего платежа</label>
            <input name="next_date" type="date" required>

            <label>Примечание</label>
            <input name="note" placeholder="Необязательно">

            <button type="submit" class="action-add">＋ Добавить платёж</button>
        </form>
    </div>

        {% for p in payment_list %}
        <div class="card">
            <h3>{{p.name}}</h3>
            <p>Сумма: {{p.amount|round(2)}} ₽</p>
            <p>Категория: {{p.category}}</p>
            <p>Следующий платеж: {{p.next_date}}</p>
<p>
    <strong>Статус:</strong>
    {% if p.status == 'Просрочен' %}
        <span style="color: #ff4d4d; font-weight: bold;">
            {{p.status}}
        </span>
    {% elif p.status == 'Скоро платеж' or p.status == 'Оплатить сегодня' %}
        <span style="color: #ffd633; font-weight: bold;">
            {{p.status}}
        </span>
    {% else %}
        <span style="color: #4ade80; font-weight: bold;">
            {{p.status}}
        </span>
    {% endif %}
</p>
<form method="post" action="/pay-recurring/{{p.id}}" onsubmit="return confirm('Подтвердить оплату на сумму {{p.amount}} ₽ со счёта: ' + this.account_id.options[this.account_id.selectedIndex].text + '?');">
                <label>Списать со счёта</label>
                <select name="account_id" required>
                    <option value="" disabled selected>Выбери счёт</option>
                    {% for a in accounts %}
                        <option value="{{a.id}}">
                            {{a.name}} — {{a.balance|round(2)}} ₽
                        </option>
                    {% endfor %}
                </select>
                <button type="submit" class="action-add">💳 Оплатить</button>
            </form>
            <p>
                Периодичность:
                {% if p.frequency == 'monthly' %}
                    каждый месяц
                {% elif p.frequency == 'weekly' %}
                    каждую неделю
                {% else %}
                    каждый год
                {% endif %}
            </p>
            {% if p.note %}
                <p>{{p.note}}</p>
            {% endif %}

            <a href="/recurring/{{p.id}}/edit"
               class="action-edit">
                ✏️ Редактировать
            </a>

            <div class="action-row recurring-actions">
                <form method="post" action="/recurring/{{p.id}}/reschedule"
                      class="reschedule-form">
                    <input type="date" name="next_date"
                           value="{{p.next_date}}" required
                           aria-label="Выбрать новую дату"
                           class="reschedule-date"
                           onchange="this.form.requestSubmit()">
                    <button type="button" class="action-add"
                            onclick="this.form.querySelector('input[type=date]').showPicker()">
                        📅 Перенести
                    </button>
                </form>
                <form method="post"
                      action="/recurring/{{p.id}}/delete"
                      onsubmit="return confirm('Удалить регулярный платёж «{{p.name}}»?');">
                    <button type="submit" class="action-delete">
                        🗑️ Удалить
                    </button>
                </form>
            </div>
        </div>
    {% else %}
        <div class="card">
            <p>Пока нет регулярных платежей.</p>
        </div>
    {% endfor %}

    <div class="card">
        <a href="/">Вернуться на главную</a>
    </div>
    """

    return page(
        "Регулярные платежи",
        content,
        categories=CATEGORIES,
        payment_list=payment_list,
        accounts=accounts
    )


@app.route("/calendar/export.ics")
@login_required
def export_calendar():
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    with connect_db() as db:
        payments = db.execute("""
            SELECT id, name, amount, category, frequency,
                   next_date, note
            FROM recurring_payments
            WHERE user_id=? AND active=1
            ORDER BY next_date
        """, (user["id"],)).fetchall()

    def escape_ics(value):
        return (str(value or "")
                .replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\r\n", "\\n")
                .replace("\n", "\\n")
                .replace("\r", "\\n"))

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MoneyTrack//Calendar//RU",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:MoneyTrack - Платежи"
    ]

    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    frequencies = {
        "weekly": "WEEKLY",
        "monthly": "MONTHLY",
        "yearly": "YEARLY"
    }

    for payment in payments:
        try:
            start_date = datetime.strptime(
                payment["next_date"], "%Y-%m-%d"
            ).strftime("%Y%m%d")
        except (ValueError, TypeError):
            continue

        description = (
            "Сумма: " + str(round(payment["amount"], 2))
            + " руб.; Категория: " + str(payment["category"] or "")
            + "; Примечание: " + str(payment["note"] or "")
        )

        lines.extend([
            "BEGIN:VEVENT",
            "UID:moneytrack-" + str(user["id"]) + "-"
            + str(payment["id"]) + "@moneytrack.local",
            "DTSTAMP:" + stamp,
            "DTSTART;VALUE=DATE:" + start_date,
            "SUMMARY:" + escape_ics(payment["name"]),
            "DESCRIPTION:" + escape_ics(description),
            "RRULE:FREQ=" + frequencies.get(
                payment["frequency"], "MONTHLY"
            ),
            "END:VEVENT"
        ])

    lines.append("END:VCALENDAR")

    response = app.response_class(
        "\r\n".join(lines) + "\r\n",
        mimetype="text/calendar; charset=utf-8"
    )
    response.headers["Content-Disposition"] = (
        "attachment; filename=moneytrack.ics"
    )

    return response



@app.route("/recurring/<int:payment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_recurring(payment_id):
    user = current_user()
    if not has_access(user):
        return redirect(url_for("plans"))

    with connect_db() as db:
        payment = db.execute("""
            SELECT * FROM recurring_payments
            WHERE id=? AND user_id=? AND active=1
        """, (payment_id, user["id"])).fetchone()

        if payment is None:
            flash("Регулярный платёж не найден.")
            return redirect(url_for("recurring"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            frequency = request.form.get("frequency", "").strip()
            next_date = request.form.get("next_date", "").strip()
            note = request.form.get("note", "").strip()

            try:
                amount = float(request.form.get("amount", "0"))
                datetime.strptime(next_date, "%Y-%m-%d")
                if (not name or amount <= 0 or category not in CATEGORIES
                        or frequency not in ("monthly", "weekly", "yearly")):
                    raise ValueError

                db.execute("""
                    UPDATE recurring_payments
                    SET name=?, amount=?, category=?, frequency=?,
                        next_date=?, note=?
                    WHERE id=? AND user_id=? AND active=1
                """, (name, amount, category, frequency, next_date, note,
                      payment_id, user["id"]))
                flash("Регулярный платёж обновлён.")
                return redirect(url_for("recurring"))
            except (ValueError, TypeError):
                flash("Проверь название, сумму, категорию, периодичность и дату.")

    content = """
    <div class="card">
        <h2>Редактирование платежа</h2>
        <form method="post">
            <label>Название</label>
            <input name="name" value="{{ p.name }}" required>

            <label>Сумма, ₽</label>
            <input name="amount" type="number" min="0.01" step="0.01"
                   value="{{ p.amount }}" required>

            <label>Категория</label>
            <select name="category" required>
                {% for c in categories %}
                <option value="{{ c }}" {% if c == p.category %}selected{% endif %}>{{ c }}</option>
                {% endfor %}
            </select>

            <label>Периодичность</label>
            <select name="frequency" required>
                <option value="weekly" {% if p.frequency == 'weekly' %}selected{% endif %}>Каждую неделю</option>
                <option value="monthly" {% if p.frequency == 'monthly' %}selected{% endif %}>Каждый месяц</option>
                <option value="yearly" {% if p.frequency == 'yearly' %}selected{% endif %}>Каждый год</option>
            </select>

            <label>Следующий платеж</label>
            <input name="next_date" type="date" value="{{ p.next_date }}" required>

            <label>Примечание</label>
            <input name="note" value="{{ p.note or '' }}">

            <button type="submit">Сохранить изменения</button>
        </form>
        <p><a href="/recurring">Назад к платежам</a></p>
    </div>
    """
    return page("Редактирование платежа", content,
                p=payment, categories=CATEGORIES)


@app.route("/recurring/<int:payment_id>/reschedule", methods=["POST"])
@login_required
def reschedule_recurring(payment_id):
    user = current_user()
    if not has_access(user):
        return redirect(url_for("plans"))

    new_date = request.form.get("next_date", "").strip()
    try:
        datetime.strptime(new_date, "%Y-%m-%d")
        with connect_db() as db:
            result = db.execute("""
                UPDATE recurring_payments
                SET next_date=?
                WHERE id=? AND user_id=? AND active=1
            """, (new_date, payment_id, user["id"]))
            if result.rowcount == 0:
                flash("Регулярный платёж не найден.")
                return redirect(url_for("recurring"))
        flash("Дата следующего платежа перенесена.")
    except (ValueError, TypeError):
        flash("Укажи корректную дату переноса.")

    return redirect(url_for("recurring"))


@app.route("/recurring/<int:payment_id>/delete", methods=["POST"])
@login_required
def delete_recurring(payment_id):
    user = current_user()
    if not has_access(user):
        return redirect(url_for("plans"))

    with connect_db() as db:
        result = db.execute("""
            UPDATE recurring_payments
            SET active=0
            WHERE id=? AND user_id=? AND active=1
        """, (payment_id, user["id"]))
        if result.rowcount:
            flash("Регулярный платёж удалён.")
        else:
            flash("Регулярный платёж не найден.")

    return redirect(url_for("recurring"))

@app.route("/pay-recurring/<int:payment_id>", methods=["POST"])
@login_required
def pay_recurring(payment_id):
    user = current_user()

    if not has_access(user):
        return redirect(url_for("plans"))

    try:
        account_id = int(request.form.get("account_id", "0"))

        with connect_db() as db:
            payment = db.execute("""
                SELECT * FROM recurring_payments
                WHERE id=? AND user_id=? AND active=1
            """, (payment_id, user["id"])).fetchone()

            account = db.execute("""
                SELECT id, balance FROM accounts
                WHERE id=? AND user_id=?
            """, (account_id, user["id"])).fetchone()

            if payment is None or account is None:
                flash("Платёж или счёт не найден.")
                return redirect(url_for("recurring"))

            amount = float(payment["amount"])

            if amount <= 0:
                flash("Некорректная сумма платежа.")
                return redirect(url_for("recurring"))

            db.execute("""
                INSERT INTO transactions
                (user_id, kind, amount, category, note, created, account_id)
                VALUES (?, 'expense', ?, ?, ?, ?, ?)
            """, (
                user["id"],
                amount,
                payment["category"],
                f"Регулярный платеж: {payment['name']}"[:200],
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                account_id
            ))

            db.execute("""
                UPDATE accounts
                SET balance = balance - ?
                WHERE id=? AND user_id=?
            """, (amount, account_id, user["id"]))

            import calendar

            due_date = datetime.strptime(
                payment["next_date"], "%Y-%m-%d"
            ).date()

            if payment["frequency"] == "weekly":
                next_date = due_date + timedelta(days=7)

            elif payment["frequency"] == "monthly":
                month = due_date.month % 12 + 1
                year = due_date.year + (1 if due_date.month == 12 else 0)
                day = min(
                    due_date.day,
                    calendar.monthrange(year, month)[1]
                )
                next_date = due_date.replace(
                    year=year, month=month, day=day
                )

            else:
                year = due_date.year + 1
                day = due_date.day
                try:
                    next_date = due_date.replace(year=year)
                except ValueError:
                    next_date = due_date.replace(
                        year=year, day=28
                    )

            db.execute("""
                UPDATE recurring_payments
                SET next_date=?
                WHERE id=? AND user_id=?
            """, (
                next_date.strftime("%Y-%m-%d"),
                payment_id,
                user["id"]
            ))

        flash("Платёж оплачен, баланс и следующая дата обновлены.")

    except (ValueError, TypeError):
        flash("Не удалось выполнить оплату. Проверь выбранный счёт.")

    return redirect(url_for("recurring"))
@app.route("/plans")
@login_required
def plans():
    user = current_user()
    current_plan = None
    if user["plan"] == "forever":
        current_plan = "forever"
    elif user["plan"] in PLANS and user["expires"]:
        try:
            if datetime.fromisoformat(user["expires"]) > datetime.now():
                current_plan = user["plan"]
        except (ValueError, TypeError):
            pass
    content = """
    <div class="card">
    <h2>Тарифы</h2>

    <div class="card">
        <h3>Бесплатный 3-х дневный доступ</h3>
        <div class="amount">0 ₽</div>
    </div>

    <p class="small">
        Оплата платных тарифов пока не подключена.
    </p>

    {% for key, plan in plans.items() %}
        <div class="card">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                <h3 style="margin:0;">{{plan[0]}}</h3>
                {% if key == current_plan %}
                <span style="color:#4ade80;font-size:13px;font-weight:600;">Текущая подписка</span>
                {% endif %}
            </div>
            <div class="amount">{{plan[1]}} ₽</div>
            <p class="small">
                Оплата пока не подключена. Покупка тарифа временно недоступна.
            </p>
        </div>
    {% endfor %}
    <a href="/">Назад</a>
    </div>
    """
    return page("Тарифы", content, plans=PLANS, current_plan=current_plan)

@app.route("/demo-activate", methods=["POST"])
@login_required
def demo_activate():
    flash("Тестовая активация отключена. Реальная оплата пока не подключена.")
    return redirect(url_for("plans"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
