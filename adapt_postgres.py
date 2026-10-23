from pathlib import Path
import re
import sys

path = Path("app_postgres.py")
source = path.read_text()

old_connect = '''def connect_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn
'''

if old_connect not in source:
    sys.exit("ОШИБКА: функция connect_db не совпала. Файл не изменён.")

if "import pg8000" in source:
    sys.exit("Адаптация уже начата. Файл не изменён повторно.")

adapter = r'''
import urllib.parse
import pg8000
import pg8000.dbapi


class CompatRow(dict):
    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class CompatCursor:
    def __init__(self, cursor=None, columns=None, rows=None):
        self.cursor = cursor
        self.columns = columns or []
        self.rows = rows
        self._used = False

    @property
    def rowcount(self):
        return self.cursor.rowcount if self.cursor else len(self.rows or [])

    def fetchone(self):
        if self.rows is not None:
            if self._used or not self.rows:
                return None
            self._used = True
            return CompatRow(self.columns, self.rows[0])
        row = self.cursor.fetchone()
        return CompatRow(
            [item[0] for item in self.cursor.description], row
        ) if row is not None else None

    def fetchall(self):
        if self.rows is not None:
            if self._used:
                return []
            self._used = True
            return [CompatRow(self.columns, row) for row in self.rows]
        rows = self.cursor.fetchall()
        columns = [item[0] for item in self.cursor.description]
        return [CompatRow(columns, row) for row in rows]

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row


class CompatConnection:
    def __init__(self, connection):
        self.connection = connection
        self.last_insert_id = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False

    def execute(self, sql, params=()):
        sql = sql.strip()

        if sql.lower().startswith("pragma table_info("):
            match = re.search(r"table_info\((\w+)\)", sql, re.I)
            if not match:
                raise ValueError("Не удалось разобрать PRAGMA table_info")
            cur = self.connection.cursor()
            cur.execute(
                "SELECT column_name AS name "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = %s ORDER BY ordinal_position",
                (match.group(1),),
            )
            return CompatCursor(cur)

        if sql.lower().startswith("select last_insert_rowid()"):
            return CompatCursor(
                columns=["last_insert_rowid()"],
                rows=[(self.last_insert_id,)],
            )

        sql = sql.replace("?", "%s")

        is_insert = sql.lower().startswith("insert into ")
        if is_insert and " returning " not in sql.lower():
            sql += " RETURNING id"

        cur = self.connection.cursor()
        cur.execute(sql, params)

        if is_insert:
            row = cur.fetchone()
            if row is not None:
                self.last_insert_id = row[0]
            return CompatCursor(
                columns=[item[0] for item in cur.description]
                if cur.description else [],
                rows=[],
            )

        return CompatCursor(cur)

    def executescript(self, script):
        script = script.replace(
            "INTEGER PRIMARY KEY AUTOINCREMENT",
            "BIGSERIAL PRIMARY KEY",
        )
        script = script.replace(
            "created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
            "created TEXT NOT NULL DEFAULT (CURRENT_TIMESTAMP::text)",
        )
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def close(self):
        self.connection.close()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()


def connect_db():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL не задан. PostgreSQL не подключён."
        )

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("DATABASE_URL должен быть PostgreSQL URL.")

    connection = pg8000.connect(
        user=urllib.parse.unquote(parsed.username or ""),
        password=urllib.parse.unquote(parsed.password or ""),
        host=parsed.hostname,
        port=parsed.port or 5432,
        database=urllib.parse.unquote(parsed.path.lstrip("/")),
        ssl_context=True,
        timeout=15,
    )
    return CompatConnection(connection)
'''

source = source.replace(
    "import sqlite3\n",
    "import sqlite3\n" + adapter + "\n",
    1,
)
source = source.replace(old_connect, "", 1)
source = source.replace(
    "except sqlite3.IntegrityError:",
    "except (sqlite3.IntegrityError, pg8000.dbapi.IntegrityError):",
)

path.write_text(source)
print("Адаптер добавлен в app_postgres.py.")
print("Рабочий app.py и moneytrack.db не изменялись.")
