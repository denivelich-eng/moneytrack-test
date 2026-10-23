from pathlib import Path

p = Path("app_postgres.py")
s = p.read_text()

start = s.index("class CompatRow(dict):")
end = s.index("\ndef connect_db():", start)

replacement = '''class CompatRow(dict):
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
        if row is None:
            return None
        columns = [item[0] for item in self.cursor.description]
        return CompatRow(columns, row)

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
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
        return False

    def execute(self, sql, params=()):
        sql = sql.strip()
        lower_sql = sql.lower()

        if lower_sql.startswith("pragma table_info("):
            match = re.search(r"table_info\\\\((\\\\w+)\\\\)", sql, re.I)
            if not match:
                raise ValueError("Не удалось разобрать PRAGMA table_info")
            table = match.group(1)
            cur = self.connection.cursor()
            cur.execute(
                "SELECT ordinal_position AS cid, column_name AS name, "
                "data_type AS type, "
                "CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull, "
                "column_default AS dflt_value, "
                "CASE WHEN column_default LIKE 'nextval%%' THEN 1 ELSE 0 END AS pk "
                "FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = %s "
                "ORDER BY ordinal_position",
                (table,),
            )
            rows = cur.fetchall()
            columns = [item[0] for item in cur.description]
            return CompatCursor(columns=columns, rows=rows)

        if lower_sql.startswith("select last_insert_rowid()"):
            return CompatCursor(
                columns=["last_insert_rowid()"],
                rows=[(self.last_insert_id,)],
            )

        sql = sql.replace("?", "%s")
        is_insert = lower_sql.startswith("insert into ")
        added_returning = is_insert and " returning " not in lower_sql

        if added_returning:
            sql += " RETURNING id"

        cur = self.connection.cursor()
        cur.execute(sql, params)

        if added_returning:
            row = cur.fetchone()
            if row is not None:
                self.last_insert_id = row[0]
            return CompatCursor(columns=[], rows=[])

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

'''
p.write_text(s[:start] + replacement + s[end:])
print("Блок адаптера заменён.")
