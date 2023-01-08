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
    
    def table_init(self, dbname):

        sqlite_connection = sqlite3.connect(dbname)
        cursor = sqlite_connection.cursor()
        cursor.execute('''CREATE TABLE if not exists current_pools (
                                    unique_id TEXT NOT NULL PRIMARY KEY,
                                    message_id INTEGER UNIQUE,
                                    type TEXT NOT NULL,
                                    counter_yes INTEGER,
                                    counter_no INTEGER,
                                    timer INTEGER,
                                    data TEXT NOT NULL,
                                    votes_need INTEGER,
                                    user_id INTEGER);''')
        cursor.execute("""CREATE TABLE if not exists users_choise (
                                    message_id INTEGER,
                                    user_id INTEGER,
                                    choice TEXT,
                                    username TEXT);""")
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
                                    version TEXT,
                                    votes INTEGER,
                                    votes_ban INTEGER,
                                    timer INTEGER,
                                    timer_ban INTEGER);""")
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()

        self.dbname = dbname

    @open_close_db
    def get_all_pools(self, cursor):
        cursor.execute("""SELECT * FROM current_pools""")
        records = cursor.fetchall()
        return records

    @open_close_db
    def abuse_update(self, cursor, user_id):
        cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
        record = cursor.fetchall()
        if not record:
            cursor.execute("""INSERT INTO abuse VALUES (?,?,?);""", (user_id, int(time.time()), 1800))
        else:
            cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                           (int(time.time()), record[0][2] * 2, user_id))

    @open_close_db
    def abuse_remove(self, cursor, user_id):
        cursor.execute("""DELETE FROM abuse WHERE user_id = ?""", (user_id,))

    @open_close_db
    def abuse_check(self, cursor, user_id):
        cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
        record = cursor.fetchall()
        if not record:
            return 0
        if record[0][1] + record[0][2] < int(time.time()):
            return 0
        else:
            return record[0][1] + record[0][2]

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
    def addpool(self, cursor, unique_id, message_vote, pool_type, current_time, work_data, votes_need, user_id):
        cursor.execute("""INSERT INTO current_pools VALUES (?,?,?,?,?,?,?,?,?);""",
                       (unique_id, message_vote.id, pool_type, 0, 0, current_time, work_data, votes_need, user_id))

    @open_close_db
    def msg_chk(self, cursor, message_vote=None, unique_id=None):
        if message_vote is not None:
            cursor.execute("""SELECT * FROM current_pools WHERE message_id = ?""", (message_vote.message_id,))
        elif unique_id is not None:
            cursor.execute("""SELECT * FROM current_pools WHERE unique_id = ?""", (unique_id,))
        records = cursor.fetchall()
        return records

    @open_close_db
    def rem_rec(self, cursor, message_id, unique_id=None):
        if unique_id is not None:
            cursor.execute("""DELETE FROM current_pools WHERE unique_id = ?""", (unique_id,))
        cursor.execute("""DELETE FROM users_choise WHERE message_id = ?""", (message_id,))

    @open_close_db
    def is_user_voted(self, cursor, user_id, message_id):
        cursor.execute("""SELECT choice FROM users_choise WHERE user_id = ? AND message_id = ?""",
                       (user_id, message_id,))
        fetchall = cursor.fetchall()
        if fetchall:
            return fetchall[0][0]
        return fetchall

    @open_close_db
    def pool_update(self, cursor, counter_yes, counter_no, unique_id):
        cursor.execute("""UPDATE current_pools SET counter_yes = ?, counter_no = ? where unique_id = ?""",
                       (counter_yes, counter_no, unique_id))

    @open_close_db
    def user_vote_update(self, cursor, call_msg, username):
        cursor.execute("""SELECT * FROM users_choise WHERE user_id = ? AND message_id = ?""",
                       (call_msg.from_user.id, call_msg.message.id,))
        record = cursor.fetchall()
        if not record:
            cursor.execute("""INSERT INTO users_choise VALUES (?,?,?,?)""",
                           (call_msg.message.id, call_msg.from_user.id, call_msg.data, username))
        else:
            cursor.execute("""UPDATE users_choise SET choice = ? where message_id = ? AND user_id = ?""",
                           (call_msg.data, call_msg.message.id, call_msg.from_user.id))

    @open_close_db
    def user_vote_remove(self, cursor, call_msg):
        cursor.execute("""DELETE FROM users_choise WHERE message_id = ? AND user_id = ?""",
                       (call_msg.message.id, call_msg.from_user.id,))

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
    def params(self, cursor, key, value=None):
        cursor.execute(f"""SELECT {key} FROM params""")
        record = cursor.fetchall()
        if not record:
            cursor.execute("""INSERT INTO params VALUES (0, 0, 0, 0, 0)""")
        if value is not None:
            cursor.execute(f"""UPDATE params SET {key} = ?""", (value,))
        if not record:
            return value
        return record[0][0]