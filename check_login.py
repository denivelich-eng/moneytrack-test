import getpass
import app_postgres
from werkzeug.security import check_password_hash

with app_postgres.connect_db() as db:
    rows = db.execute(
        "SELECT id, phone, email, password FROM users ORDER BY id"
    ).fetchall()

print("Аккаунты:")
for r in rows:
    print(f"ID {r['id']}: {r['phone'] or r['email']}")

account_id = input("Введи ID своего аккаунта: ").strip()
password = getpass.getpass("Введи пароль от этого аккаунта: ")

row = next((r for r in rows if str(r["id"]) == account_id), None)

if row is None:
    print("Такой ID не найден.")
elif check_password_hash(row["password"], password):
    print("РЕЗУЛЬТАТ: пароль совпадает с сохранённым хешем.")
else:
    print("РЕЗУЛЬТАТ: пароль не совпадает с сохранённым хешем.")
