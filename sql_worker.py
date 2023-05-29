import json
import sqlite3
import time


def open_close_db(function):
    def wrapper(self, *args, **kwargs):
        sqlite_connection = sqlite3.connect(self.dbname)
        cursor = sqlite_connection.cursor()
        data = function(self, cursor, *args, **kwargs)
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()
        return data
    return wrapper


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
                                    votes_need INTEGER);""")
        cursor.execute("""CREATE TABLE if not exists abuse (
                                    user_id INTEGER PRIMARY KEY,
                                    start_time INTEGER,
                                    timer INTEGER);""")
        cursor.execute("""CREATE TABLE if not exists whitelist (
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
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()

    @open_close_db
    def get_all_polls(self, cursor):
        cursor.execute("""SELECT * FROM current_polls""")
        records = cursor.fetchall()
        return records

    @open_close_db
    def abuse_update(self, cursor, user_id, timer=1800, force=False):
        cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
        record = cursor.fetchall()
        if not record:
            cursor.execute("""INSERT INTO abuse VALUES (?,?,?);""", (user_id, int(time.time()), timer))
        elif not force:
            cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                           (int(time.time()), record[0][2] * 2, user_id))
        else:
            cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                           (int(time.time()), timer, user_id))

    @open_close_db
    def abuse_remove(self, cursor, user_id):
        cursor.execute("""DELETE FROM abuse WHERE user_id = ?""", (user_id,))

    @open_close_db
    def abuse_check(self, cursor, user_id, force=False):
        cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
        record = cursor.fetchall()
        if not record:
            return 0, 0
        if record[0][1] + record[0][2] < int(time.time()) and not force:
            return 0, 0
        else:
            return record[0][1], record[0][2]

    @open_close_db
    def whitelist(self, cursor, user_id, add=False, remove=False):
        cursor.execute("""SELECT * FROM whitelist WHERE user_id = ?""", (user_id,))
        fetchall = cursor.fetchall()
        is_white = False
        if fetchall:
            if remove:
                cursor.execute("""DELETE FROM whitelist WHERE user_id = ?""", (user_id,))
            else:
                is_white = True
        if add and not fetchall:
            cursor.execute("""INSERT INTO whitelist VALUES (?);""", (user_id,))
            is_white = True
        return is_white

    @open_close_db
    def whitelist_get_all(self, cursor):
        cursor.execute("""SELECT * FROM whitelist""")
        fetchall = cursor.fetchall()
        return fetchall

    @open_close_db
    def add_poll(self, cursor, unique_id, message_vote, poll_type, chat_id, buttons_scheme,
                 current_time, work_data, votes_need):
        cursor.execute("""INSERT INTO current_polls VALUES (?,?,?,?,?,?,?,?);""",
                       (unique_id, message_vote.id, poll_type, chat_id, buttons_scheme,
                        current_time, work_data, votes_need))

    @open_close_db
    def get_poll(self, cursor, message_id):
        cursor.execute("""SELECT * FROM current_polls WHERE message_id = ?""", (message_id,))
        records = cursor.fetchall()
        return records

    @open_close_db
    def get_message_id(self, cursor, unique_id):
        cursor.execute("""SELECT * FROM current_polls WHERE unique_id = ?""", (unique_id,))
        records = cursor.fetchall()
        if records:
            return records[0][1]
        return None

    @open_close_db
    def update_poll_votes(self, cursor, unique_id, buttons_scheme):
        cursor.execute("""UPDATE current_polls SET buttons = ? where unique_id = ?""", (buttons_scheme, unique_id))

    @open_close_db
    def rem_rec(self, cursor, unique_id):
        cursor.execute("""DELETE FROM current_polls WHERE unique_id = ?""", (unique_id,))

    @open_close_db
    def get_rate(self, cursor, user_id):
        cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
        record = cursor.fetchall()
        if not record:
            cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, 0))
            return 0
        return record[0][1]

    @open_close_db
    def get_all_rates(self, cursor):
        cursor.execute("""SELECT * FROM rating""")
        record = cursor.fetchall()
        if not record:
            return None
        return record

    @open_close_db
    def update_rate(self, cursor, user_id, change):
        cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
        record = cursor.fetchall()
        if not record:
            cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, change))
        else:
            cursor.execute("""UPDATE rating SET rate = ? where user_id = ?""", (record[0][1] + change, user_id))

    @open_close_db
    def clear_rate(self, cursor, user_id):
        cursor.execute("""DELETE FROM rating WHERE user_id = ?""", (user_id,))

    @open_close_db
    def get_ally(self, cursor, chat_id):
        cursor.execute("""SELECT * FROM allies WHERE chat_id = ?""", (chat_id,))
        record = cursor.fetchall()
        if not record:
            return None
        return record[0]

    @open_close_db
    def get_allies(self, cursor):
        cursor.execute("""SELECT * FROM allies""")
        record = cursor.fetchall()
        if not record:
            return None
        return record

    @open_close_db
    def add_ally(self, cursor, chat_id):
        cursor.execute("""INSERT INTO allies VALUES (?)""", (chat_id,))

    @open_close_db
    def remove_ally(self, cursor, chat_id):
        cursor.execute("""DELETE FROM allies WHERE chat_id = ?""", (chat_id,))

    @open_close_db
    def abuse_random(self, cursor, chat_id, change=None):
        cursor.execute("""SELECT * FROM abuse_random WHERE chat_id = ?""", (chat_id,))
        record = cursor.fetchall()
        if change is not None:
            if not record:
                cursor.execute("""INSERT INTO abuse_random VALUES (?,?)""", (chat_id, change))
            else:
                cursor.execute("""UPDATE abuse_random SET abuse_random = ? where chat_id = ?""", (change, chat_id))
        if not record:
            return 0
        return record[0][1]

    @open_close_db
    def params(self, cursor, key, rewrite_value=None, default_return=None):
        cursor.execute("""SELECT * FROM params""")
        record: dict = json.loads(cursor.fetchall()[0][0])
        return_value = record.get(key, default_return)
        if rewrite_value is not None:
            record.update({key: rewrite_value})
            cursor.execute("""UPDATE params SET params = ?""", (json.dumps(record),))
        return return_value

    @open_close_db
    def captcha(self, cursor, message_id, add=False, remove=False, user_id=None, max_value=None, username=None):
        if add:
            cursor.execute("""INSERT INTO captcha VALUES (?, ?, ?, ?)""", (message_id, user_id, max_value, username))
        elif remove:
            cursor.execute("""DELETE FROM captcha WHERE message_id = ?""", (message_id,))
        elif user_id:
            cursor.execute("""SELECT * FROM captcha WHERE user_id = ?""", (user_id,))
            return cursor.fetchall()
        else:
            cursor.execute("""SELECT * FROM captcha WHERE message_id = ?""", (message_id,))
            return cursor.fetchall()
