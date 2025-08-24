import json
import sqlite3
import time


class SQLWrapper:

    def __init__(self, dbname):
        self.dbname = dbname

    def __enter__(self):
        self.sqlite_connection = sqlite3.connect(self.dbname)
        self.cursor = self.sqlite_connection.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            self.sqlite_connection.commit()
        self.cursor.close()
        self.sqlite_connection.close()


class SqlWorker:
    dbname = ""

    def __init__(self, dbname, recommended):

        self.dbname = dbname

        sqlite_connection = sqlite3.connect(dbname)
        cursor = sqlite_connection.cursor()
        cursor.execute("""CREATE TABLE if not exists current_polls (
                                    unique_id TEXT NOT NULL PRIMARY KEY,
                                    message_id INTEGER UNIQUE,
                                    type TEXT NOT NULL,
                                    chat_id INTEGER,
                                    buttons TEXT,
                                    timer INTEGER,
                                    data TEXT NOT NULL,
                                    votes_need INTEGER,
                                    hidden INTEGER);""")
        cursor.execute("""CREATE TABLE if not exists abuse (
                                    user_id INTEGER PRIMARY KEY,
                                    start_time INTEGER,
                                    timer INTEGER);""")
        cursor.execute("""CREATE TABLE if not exists whitelist (
                                    user_id INTEGER PRIMARY KEY);""")
        cursor.execute("""CREATE TABLE if not exists mailing (
                                    user_id INTEGER PRIMARY KEY);""")
        cursor.execute("""CREATE TABLE if not exists rating (
                                    user_id INTEGER PRIMARY KEY,
                                    rate INTEGER);""")
        cursor.execute("""CREATE TABLE if not exists abuse_random (
                                    chat_id INTEGER PRIMARY KEY,
                                    abuse_random INTEGER);""")
        cursor.execute("""CREATE TABLE if not exists allies (
                                    chat_id INTEGER PRIMARY KEY);""")
        cursor.execute("""CREATE TABLE if not exists params (
                                    params TEXT PRIMARY KEY);""")
        cursor.execute("""CREATE TABLE if not exists captcha (
                                    message_id TEXT,
                                    user_id TEXT,
                                    max_value INTEGER,
                                    username TEXT);""")
        cursor.execute("""DELETE FROM captcha""")
        cursor.execute("""SELECT * FROM params""")
        records = cursor.fetchall()
        if not records:
            cursor.execute("""INSERT INTO params VALUES (?)""", (json.dumps(recommended),))
        # Start of backwards compatible code
        try:
            cursor.execute("ALTER TABLE current_polls ADD COLUMN hidden INTEGER")
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e):
                pass
        # End of backwards compatible code
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()

    def get_all_polls(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM current_polls""")
            records = sql_wrapper.cursor.fetchall()
            return records

    def abuse_update(self, user_id, timer=1800, force=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO abuse VALUES (?,?,?);""", (user_id, int(time.time()), timer))
            elif not force:
                sql_wrapper.cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                                           (int(time.time()), record[0][2] * 2, user_id))
            else:
                sql_wrapper.cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                                           (int(time.time()), timer, user_id))

    def abuse_remove(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM abuse WHERE user_id = ?""", (user_id,))

    def abuse_check(self, user_id, force=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return 0, 0
            if record[0][1] + record[0][2] < int(time.time()) and not force:
                return 0, 0
            else:
                return record[0][1], record[0][2]

    def whitelist(self, user_id, add=False, remove=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM whitelist WHERE user_id = ?""", (user_id,))
            fetchall = sql_wrapper.cursor.fetchall()
            is_white = False
            if fetchall:
                if remove:
                    sql_wrapper.cursor.execute("""DELETE FROM whitelist WHERE user_id = ?""", (user_id,))
                else:
                    is_white = True
            if add and not fetchall:
                sql_wrapper.cursor.execute("""INSERT INTO whitelist VALUES (?);""", (user_id,))
                is_white = True
            return is_white

    def whitelist_get_all(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM whitelist""")
            fetchall = sql_wrapper.cursor.fetchall()
            return fetchall

    def mailing(self, user_id, add=False, remove=False):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM mailing WHERE user_id = ?""", (user_id,))
            fetchall = sql_wrapper.cursor.fetchall()
            is_mailing = False
            if fetchall:
                if remove:
                    sql_wrapper.cursor.execute("""DELETE FROM mailing WHERE user_id = ?""", (user_id,))
                else:
                    is_mailing = True
            if add and not fetchall:
                sql_wrapper.cursor.execute("""INSERT INTO mailing VALUES (?);""", (user_id,))
                is_mailing = True
            return is_mailing

    def mailing_get_all(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM mailing""")
            fetchall = sql_wrapper.cursor.fetchall()
            return fetchall

    def add_poll(self, *args):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""INSERT INTO current_polls VALUES (?,?,?,?,?,?,?,?,?);""", args)

    def get_poll(self, message_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM current_polls WHERE message_id = ?""", (message_id,))
            records = sql_wrapper.cursor.fetchall()
            return records

    def get_message_id(self, unique_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM current_polls WHERE unique_id = ?""", (unique_id,))
            records = sql_wrapper.cursor.fetchall()
            if records:
                return records[0][1]
            return None

    def update_poll_votes(self, unique_id, buttons_scheme):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""UPDATE current_polls SET buttons = ? where unique_id = ?""",
                                       (buttons_scheme, unique_id))

    def rem_rec(self, unique_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM current_polls WHERE unique_id = ?""", (unique_id,))

    def get_rate(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, 0))
                return 0
            return record[0][1]

    def get_all_rates(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating""")
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record

    def update_rate(self, user_id, change):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                sql_wrapper.cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, change))
            else:
                sql_wrapper.cursor.execute("""UPDATE rating SET rate = ? where user_id = ?""",
                                           (record[0][1] + change, user_id))

    def clear_rate(self, user_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM rating WHERE user_id = ?""", (user_id,))

    def get_ally(self, chat_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM allies WHERE chat_id = ?""", (chat_id,))
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record[0]

    def get_allies(self):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM allies""")
            record = sql_wrapper.cursor.fetchall()
            if not record:
                return None
            return record

    def add_ally(self, chat_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""INSERT INTO allies VALUES (?)""", (chat_id,))

    def remove_ally(self, chat_id):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""DELETE FROM allies WHERE chat_id = ?""", (chat_id,))

    def abuse_random(self, chat_id, change=None):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM abuse_random WHERE chat_id = ?""", (chat_id,))
            record = sql_wrapper.cursor.fetchall()
            if change is not None:
                if not record:
                    sql_wrapper.cursor.execute("""INSERT INTO abuse_random VALUES (?,?)""", (chat_id, change))
                else:
                    sql_wrapper.cursor.execute("""UPDATE abuse_random SET abuse_random = ? where chat_id = ?""",
                                               (change, chat_id))
            if not record:
                return 0
            return record[0][1]

    def params(self, key, rewrite_value=None, default_return=None):
        with SQLWrapper(self.dbname) as sql_wrapper:
            sql_wrapper.cursor.execute("""SELECT * FROM params""")
            record: dict = json.loads(sql_wrapper.cursor.fetchall()[0][0])
            return_value = record.get(key, default_return)
            if rewrite_value is not None:
                record.update({key: rewrite_value})
                sql_wrapper.cursor.execute("""UPDATE params SET params = ?""", (json.dumps(record),))
            return return_value

    def captcha(self, message_id, add=False, remove=False, user_id=None, max_value=None, username=None):
        with SQLWrapper(self.dbname) as sql_wrapper:
            if add:
                sql_wrapper.cursor.execute("""INSERT INTO captcha VALUES (?, ?, ?, ?)""",
                                           (message_id, user_id, max_value, username))
                return None
            elif remove:
                sql_wrapper.cursor.execute("""DELETE FROM captcha WHERE message_id = ?""", (message_id,))
                return None
            elif user_id:
                sql_wrapper.cursor.execute("""SELECT * FROM captcha WHERE user_id = ?""", (user_id,))
                return sql_wrapper.cursor.fetchall()
            else:
                sql_wrapper.cursor.execute("""SELECT * FROM captcha WHERE message_id = ?""", (message_id,))
                return sql_wrapper.cursor.fetchall()
