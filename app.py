import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, url_for, session, render_template_string, flash
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

CATEGORIES = ["Продукты", "Транспорт", "Жильё", "Зарплата", "Развлечения", "Здоровье", "Другое"]

def connect_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            expires TEXT
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
        """)
        cols = [r[1] for r in db.execute("PRAGMA table_info(transactions)").fetchall()]
        if "account_id" not in cols:
            db.execute("ALTER TABLE transactions ADD COLUMN account_id INTEGER")
        if "client_change_id" not in cols:
            db.execute("ALTER TABLE transactions ADD COLUMN client_change_id TEXT")
            db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_client ON transactions(user_id, client_change_id)")

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
        return db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()

def has_access(user):
    if user["plan"] == "forever": return True
    if user["expires"]:
        try: return datetime.fromisoformat(user["expires"]) > datetime.now()
        except ValueError: pass
    return False

STYLE = """
<style>
* {box-sizing:border-box}
body { margin:0; background:#121212; color:#e0e0e0; font-family:Arial,sans-serif; }
header { background:#1a1a1a; color:#d4af37; padding:20px; font-size:23px; font-weight:bold; border-bottom: 2px solid #d4af37; }
main {max-width:650px; margin:auto; padding:16px}
.card { background:#1e1e1e; border-radius:16px; padding:18px; margin:14px 0; box-shadow:0 4px 15px rgba(0,0,0,0.5); border: 1px solid #333; }
input,select,button { width:100%; padding:13px; margin:7px 0; border:1px solid #444; border-radius:10px; font-size:16px; background:#2a2a2a; color:#fff; }
input:focus, select:focus { outline: none; border-color: #d4af37; }
button { background:#d4af37; color:#121212; border:0; font-weight:bold; cursor: pointer; transition: background 0.3s; }
button:hover { background:#e6c55c; }
a {color:#d4af37; text-decoration: none;}
a:hover {text-decoration: underline;}
.small {color:#888; font-size:13px}
.amount {font-size:30px; font-weight:bold; color:#d4af37;}
.expense {color:#ff6b6b}
.income {color:#d4af37}
</style>
"""

def page(title, content, **context):
    template = """
    <!doctype html>
    <html lang="ru">
    <head>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta charset="utf-8">
    <meta name="theme-color" content="#121212">
    <link rel="manifest" href="/static/manifest.json">
    <title>{{title}}</title>
    """ + STYLE + """
    </head>
    <body>
    <header>MoneyTrack</header>
    <main>
    {% with messages = get_flashed_messages() %}
      {% for msg in messages %} <div class="card">{{msg}}</div> {% endfor %}
    {% endwith %}
    """ + content + """
    </main>
    <script src="/static/offline-db.js"></script>
    <script src="/static/offline-sync.js"></script>
    <script>
    if ("serviceWorker" in navigator) { navigator.serviceWorker.register("/sw.js", {scope: "/"}); }
    </script>
    </body></html>
    """
    return render_template_string(template, title=title, **context)

@app.route("/")
def index():
    if "user_id" not in session: return redirect(url_for("login"))
    user = current_user()
    with connect_db() as db:
        rows = db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 30", (user["id"],)).fetchall()
        totals = db.execute("SELECT SUM(CASE WHEN kind='income' THEN amount ELSE 0 END) income, SUM(CASE WHEN kind='expense' THEN amount ELSE 0 END) expense FROM transactions WHERE user_id=?", (user["id"],)).fetchone()
        accounts = db.execute("SELECT * FROM accounts WHERE user_id=?", (user["id"],)).fetchall()
    income = totals["income"] or 0
    expense = totals["expense"] or 0
    balance = income - expense
    content = """
    <div class="card">
        <div class="small">Общий баланс по операциям</div>
        <div class="amount">{{balance|round(2)}} ₽</div>
        <p class="income">Доходы: +{{income|round(2)}} ₽</p>
        <p class="expense">Расходы: −{{expense|round(2)}} ₽</p>
        <a href="/add" style="display:block; text-align:center; background:#d4af37; color:#121212; padding:12px; border-radius:10px; font-weight:bold; margin-top:15px;">+ Добавить операцию</a>
    </div>
    <div class="card">
        <h3 style="color:#d4af37;">Мои счета</h3>
        {% for a in accounts %} <p>{{a.name}} — <span style="color:#d4af37; font-weight:bold;">{{a.balance|round(2)}} ₽</span></p> {% else %} <p class="small">Счетов пока нет.</p> {% endfor %}
        <a href="/accounts">Добавить счет</a>
    </div>
    <div class="card">
        <h3 style="color:#d4af37;">Последние операции</h3>
        {% for t in rows %}
            <p>{% if t.kind == 'income' %}<span class="income" style="font-weight:bold;">+{{t.amount}} ₽</span>{% else %}<span class="expense">−{{t.amount}} ₽</span>{% endif %} — {{t.category}} {{t.note}} <span class="small">{{t.created}}</span></p>
        {% else %} <p class="small">Операций пока нет.</p> {% endfor %}
    </div>
    <div class="card">
        <h3 style="color:#d4af37;">Подписка</h3>
        <p>Текущий тариф: <span style="color:#d4af37;">{{user.plan}}</span></p>
        <p>Доступ: {{user.expires or 'не ограничен / бесплатный'}}</p>
        <a href="/plans">Посмотреть тарифы</a>
    </div>
    <p><a href="/logout" style="color:#ff6b6b;">Выйти</a></p>
    """
    return page("Главная", content, user=user, rows=rows, accounts=accounts, balance=balance, income=income, expense=expense)

@app.route("/register", methods=["GET", "POST"])
def register():
    content = """
    <div class="card">
    <h2 style="color:#d4af37;">Регистрация</h2>
    <form method="post">
        <input name="phone" placeholder="+79991234567" required>
        <input name="password" type="password" placeholder="Пароль от приложения" required>
        <button>Зарегистрироваться</button>
    </form>
    <a href="/login">Уже есть аккаунт? Войти</a>
    </div>
    """
    if request.method == "POST":
        phone = request.form["phone"].strip()
        password = request.form["password"]
        if len(password) < 8:
            flash("Пароль должен содержать минимум 8 символов.")
            return redirect(url_for("register"))
        try:
            with connect_db() as db:
                db.execute("INSERT INTO users(phone,password) VALUES(?,?)", (phone, generate_password_hash(password)))
            flash("Аккаунт создан. Теперь войди.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Этот номер уже зарегистрирован.")
    return page("Регистрация", content)

@app.route("/login", methods=["GET", "POST"])
def login():
    content = """
    <div class="card">
    <h2 style="color:#d4af37;">Вход</h2>
    <form method="post">
        <input name="phone" placeholder="Номер телефона" required>
        <input name="password" type="password" placeholder="Пароль" required>
        <button>Войти</button>
    </form>
    <a href="/register">Создать аккаунт</a>
    </div>
    """
    if request.method == "POST":
        phone = request.form["phone"].strip()
        password = request.form["password"]
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("index"))
        flash("Неверный номер или пароль.")
    return page("Вход", content)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    user = current_user()
    if not has_access(user): return redirect(url_for("plans"))
    content = """
    <div class="card">
    <h2 style="color:#d4af37;">Новая операция</h2>
    <form method="post">
        <select name="kind">
            <option value="expense">Расход</option>
            <option value="income">Доход</option>
        </select>
        <input name="amount" type="number" min="0.01" step="0.01" placeholder="Сумма в рублях" required>
        <select name="category">
        {% for c in categories %} <option>{{c}}</option> {% endfor %}
        </select>
        <input name="note" placeholder="Комментарий">
        <button>Сохранить</button>
    </form>
    <a href="/">Назад</a>
    </div>
    """
    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            kind = request.form["kind"]
            category = request.form["category"]
            note = request.form.get("note", "")[:200]
            if amount <= 0 or kind not in ("income", "expense"): raise ValueError
            with connect_db() as db:
                db.execute("INSERT INTO transactions (user_id,kind,amount,category,note,created) VALUES(?,?,?,?,?,?)", (user["id"], kind, amount, category, note, datetime.now().strftime("%d.%m.%Y %H:%M")))
            return redirect(url_for("index"))
        except (ValueError, TypeError):
            flash("Проверь сумму операции.")
    return page("Новая операция", content, categories=CATEGORIES)

@app.route("/accounts", methods=["GET", "POST"])
@login_required
def accounts():
    user = current_user()
    if not has_access(user): return redirect(url_for("plans"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        try:
            balance = float(request.form.get("balance", "0"))
            if name and len(name) <= 60:
                with connect_db() as db:
                    db.execute("INSERT INTO accounts(user_id,name,balance) VALUES(?,?,?)", (user["id"], name, balance))
                return redirect(url_for("index"))
        except ValueError:
            flash("Неверная сумма.")
    content = """
    <div class="card">
    <h2 style="color:#d4af37;">Добавить счет</h2>
    <form method="post">
        <input name="name" placeholder="Например, наличные" required>
        <input name="balance" type="number" step="0.01" placeholder="Начальный баланс" value="0">
        <button>Добавить</button>
    </form>
    <a href="/">Назад</a>
    </div>
    """
    return page("Счета", content)

@app.route("/plans")
@login_required
def plans():
    content = """
    <div class="card">
    <h2 style="color:#d4af37;">Тарифы</h2>
    <p class="small">Демонстрационный режим: оплата не производится.</p>
    {% for key, plan in plans.items() %}
        <div class="card">
            <h3 style="color:#e0e0e0;">{{plan[0]}}</h3>
            <div class="amount">{{plan[1]}} ₽</div>
            <form method="post" action="/demo-activate">
                <input type="hidden" name="plan" value="{{key}}">
                <button>Активировать тестовый тариф</button>
            </form>
        </div>
    {% endfor %}
    <a href="/">Назад</a>
    </div>
    """
    return page("Тарифы", content, plans=PLANS)

@app.route("/demo-activate", methods=["POST"])
@login_required
def demo_activate():
    user = current_user()
    key = request.form.get("plan")
    if key not in PLANS:
        flash("Неизвестный тариф.")
        return redirect(url_for("plans"))
    name, price, days = PLANS[key]
    if days is None:
        expires = None
        plan = "forever"
    else:
        expires = (datetime.now() + timedelta(days=days)).isoformat()
        plan = key
    with connect_db() as db:
        db.execute("UPDATE users SET plan=?, expires=? WHERE id=?", (plan, expires, user["id"]))
    flash("Тестовый тариф активирован. Реальной оплаты не было.")
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/api/offline/snapshot")
@login_required
def offline_snapshot():
    user = current_user()
    with connect_db() as db:
        transactions = db.execute("SELECT id, kind, amount, category, note, created FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 200", (user["id"],)).fetchall()
        accounts = db.execute("SELECT id, name, balance FROM accounts WHERE user_id=?", (user["id"],)).fetchall()
    return {
        "ok": True,
        "user_id": user["id"],
        "data": {
            "transactions": [dict(t) for t in transactions],
            "accounts": [dict(a) for a in accounts],
            "user_categories": []
        }
    }

@app.route("/api/offline/sync", methods=["POST"])
@login_required
def offline_sync():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    changes = payload.get("changes", [])
    results = []
    for change in changes:
        client_id = change.get("client_change_id")
        try:
            tx = change.get("transaction", {})
            amount = float(tx.get("amount", 0))
            kind = tx.get("kind")
            category = (tx.get("category") or "").strip()[:60]
            note = (tx.get("note") or "").strip()[:200]
            if amount <= 0 or kind not in ("income", "expense") or not category:
                results.append({"client_change_id": client_id, "ok": False, "error": "bad-data"})
                continue
            with connect_db() as db:
                dup = db.execute("SELECT id FROM transactions WHERE user_id=? AND client_change_id=?", (user["id"], client_id)).fetchone()
                if dup:
                    results.append({"client_change_id": client_id, "ok": True})
                    continue
                db.execute("INSERT INTO transactions (user_id, kind, amount, category, note, created, client_change_id) VALUES (?,?,?,?,?,?,?)", (user["id"], kind, amount, category, note, tx.get("created") or datetime.now().strftime("%d.%m.%Y %H:%M"), client_id))
            results.append({"client_change_id": client_id, "ok": True})
        except Exception as e:
            results.append({"client_change_id": client_id, "ok": False, "error": str(e)})
    return {"ok": True, "results": results}

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
