import sqlite3

DATABASE = "./database.sqlite3"
_db = None


def get():
    global _db
    if _db is None:
        _db = sqlite3.connect(DATABASE)
        _db.row_factory = sqlite3.Row
    return _db


def close():
    global _db
    if _db is not None:
        _db.close()
        _db = None


def commit():
    get().commit()


def query(query, args=(), one=False, commit=False):
    db = get()
    cur = db.execute(query, args)
    rv = cur.fetchall()
    cur.close()
    if commit:
        db.commit()
    return (rv[0] if rv else None) if one else rv