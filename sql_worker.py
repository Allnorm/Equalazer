import sqlite3
import time
import utils

dbname = ""


def table_init():

    global dbname

    dbname = utils.PATH + "database.db"
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
    cursor.execute("""CREATE TABLE if not exists version (
                                    version TEXT PRIMARY KEY);""")
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def get_all_pools():
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM current_pools""")
    records = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    return records


def abuse_update(user_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
    record = cursor.fetchall()
    if not record:
        cursor.execute("""INSERT INTO abuse VALUES (?,?,?);""", (user_id, int(time.time()), 1800))
    else:
        cursor.execute("""UPDATE abuse SET start_time = ?, timer = ? WHERE user_id = ?""",
                       (int(time.time()), record[0][2] * 2, user_id))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def abuse_remove(user_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""DELETE FROM abuse WHERE user_id = ?""", (user_id,))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def abuse_check(user_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM abuse WHERE user_id = ?""", (user_id,))
    record = cursor.fetchall()
    if not record:
        return 0
    if record[0][1] + record[0][2] < int(time.time()):
        return 0
    else:
        return record[0][1] + record[0][2]


def whitelist(user_id, add=False, remove=False):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
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
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()
    return is_white


def whitelist_get_all():
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM whitelist""")
    fetchall = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    return fetchall


def addpool(unique_id, message_vote, pool_type, current_time, work_data, votes_need, user_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""INSERT INTO current_pools VALUES (?,?,?,?,?,?,?,?,?);""",
                   (unique_id, message_vote.id, pool_type, 0, 0, current_time, work_data, votes_need, user_id))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def msg_chk(message_vote=None, unique_id=None):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    if message_vote is not None:
        cursor.execute("""SELECT * FROM current_pools WHERE message_id = ?""", (message_vote.message_id,))
    elif unique_id is not None:
        cursor.execute("""SELECT * FROM current_pools WHERE unique_id = ?""", (unique_id,))
    records = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    return records


def rem_rec(message_id, unique_id=None):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    if unique_id is not None:
        cursor.execute("""DELETE FROM current_pools WHERE unique_id = ?""", (unique_id,))
    cursor.execute("""DELETE FROM users_choise WHERE message_id = ?""", (message_id,))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def is_user_voted(user_id, message_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT choice FROM users_choise WHERE user_id = ? AND message_id = ?""", (user_id, message_id,))
    fetchall = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    if fetchall:
        return fetchall[0][0]
    return fetchall


def pool_update(counter_yes, counter_no, unique_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""UPDATE current_pools SET counter_yes = ?, counter_no = ? where unique_id = ?""",
                   (counter_yes, counter_no, unique_id))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def user_vote_update(call_msg, username):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM users_choise WHERE user_id = ? AND message_id = ?""",
                   (call_msg.from_user.id, call_msg.message.id,))
    record = cursor.fetchall()
    if not record:
        cursor.execute("""INSERT INTO users_choise VALUES (?,?,?,?)""",
                       (call_msg.message.id, call_msg.from_user.id, call_msg.data, username))
    else:
        cursor.execute("""UPDATE users_choise SET choice = ? where message_id = ? AND user_id = ?""",
                       (call_msg.data, call_msg.message.id, call_msg.from_user.id))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def user_vote_remove(call_msg):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""DELETE FROM users_choise WHERE message_id = ? AND user_id = ?""",
                   (call_msg.message.id, call_msg.from_user.id,))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def get_rate(user_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
    record = cursor.fetchall()
    if not record:
        cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, 0))
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()
        return 0
    cursor.close()
    sqlite_connection.close()
    return record[0][1]


def get_all_rates():
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM rating""")
    record = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    if not record:
        return None
    return record


def update_rate(user_id, change):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM rating WHERE user_id = ?""", (user_id,))
    record = cursor.fetchall()
    if not record:
        cursor.execute("""INSERT INTO rating VALUES (?,?)""", (user_id, change))
    else:
        cursor.execute("""UPDATE rating SET rate = ? where user_id = ?""", (record[0][1] + change, user_id))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def clear_rate(user_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""DELETE FROM rating WHERE user_id = ?""", (user_id,))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def get_ally(chat_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM allies WHERE chat_id = ?""", (chat_id,))
    record = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    if not record:
        return None
    return record[0]


def get_allies():
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM allies""")
    record = cursor.fetchall()
    cursor.close()
    sqlite_connection.close()
    if not record:
        return None
    return record


def add_ally(chat_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""INSERT INTO allies VALUES (?)""", (chat_id,))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def remove_ally(chat_id):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""DELETE FROM allies WHERE chat_id = ?""", (chat_id,))
    sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()


def abuse_random(chat_id, change=None):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM abuse_random WHERE chat_id = ?""", (chat_id,))
    record = cursor.fetchall()
    if change is not None:
        if not record:
            cursor.execute("""INSERT INTO abuse_random VALUES (?,?)""", (chat_id, change))
        else:
            cursor.execute("""UPDATE abuse_random SET abuse_random = ? where chat_id = ?""", (change, chat_id))
        sqlite_connection.commit()
    cursor.close()
    sqlite_connection.close()
    if not record:
        return 0
    return record[0][1]


def get_version(version):
    sqlite_connection = sqlite3.connect(dbname)
    cursor = sqlite_connection.cursor()
    cursor.execute("""SELECT * FROM version""")
    record = cursor.fetchall()
    if not record:
        cursor.execute("""INSERT INTO version VALUES (?)""", (version,))
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()
        return None
    if record[0][0] != version:
        cursor.execute("""UPDATE version SET version = ? where version = ?""", (version, record[0][0]))
        sqlite_connection.commit()
        cursor.close()
        sqlite_connection.close()
        return record[0][0]
    else:
        return None
