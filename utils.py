import configparser
import logging
import os
import pickle

from telebot import types
import sys
import threading
import time
import traceback
from importlib import reload

import sql_worker

import telebot

bot: telebot.TeleBot

global_timer = 3600
global_timer_ban = 300
votes_need = 0
votes_need_ban = 0
auto_thresholds = False
auto_thresholds_ban = False
main_chat_id = ""
debug = False
minimum_vote = 1
vote_mode = 3
vote_abuse = {}
wait_timer = 30
abuse_mode = 2
private_mode = True
rules = False
rate = True
PATH = ""
VERSION = "1.4.14"
BUILD_DATE = "29.12.2022"
welc_default = "Welcome to {1}!"


def config_init():

    def bool_init(var):
        if var.lower() in ("false", "0"):
            return False
        elif var.lower() in ("true", "1"):
            return True
        else:
            raise TypeError

    global PATH, global_timer, global_timer_ban, votes_need, votes_need_ban, vote_mode, wait_timer, abuse_mode
    global debug, main_chat_id, private_mode, rules, rate, minimum_vote, auto_thresholds, auto_thresholds_ban, bot

    config = configparser.ConfigParser()
    while True:
        try:
            config.read(PATH + "config.ini")
            token = config["Chat"]["token"]
            global_timer = int(config["Chat"]["timer"])
            global_timer_ban = int(config["Chat"]["bantimer"])
            votes_need = int(config["Chat"]["votes"])
            votes_need_ban = int(config["Chat"]["banvotes"])
            vote_mode = int(config["Chat"]["votes-mode"])
            wait_timer = int(config["Chat"]["wait-timer"])
            abuse_mode = int(config["Chat"]["abuse-mode"])
            private_mode = bool_init(config["Chat"]["private-mode"])
            rules = bool_init(config["Chat"]["rules"])
            rate = bool_init(config["Chat"]["rate"])
            break
        except Exception as e:
            logging.error((str(e)))
            logging.error(traceback.format_exc())
            time.sleep(1)
            print("\nInvalid config file! Trying to remake!")
            agreement = "-1"
            while agreement != "y" and agreement != "n" and agreement != "":
                agreement = input("Do you want to reset your broken config file on defaults? (Y/n): ")
                agreement = agreement.lower()
            if agreement == "" or agreement == "y":
                remake_conf()
            else:
                sys.exit(0)

    bot = telebot.TeleBot(token)

    if config["Chat"]["chatid"] != "init":
        main_chat_id = int(config["Chat"]["chatid"])
    else:
        debug = True
        main_chat_id = -1

    try:
        debug = bool_init(config["Chat"]["debug"])
    except (KeyError, TypeError):
        pass

    if debug:
        global_timer = 20
        global_timer_ban = 10
        votes_need = 2
        votes_need_ban = 2
        minimum_vote = 0
        wait_timer = 0
        return

    if global_timer < 5 or global_timer > 86400:
        global_timer = 3600
    if global_timer_ban < 5 or global_timer > 86400:
        global_timer_ban = 300
    if votes_need <= 1:
        auto_thresholds = True
    if votes_need_ban <= 1:
        auto_thresholds_ban = True

    return


def init():

    global PATH

    try:
        PATH = sys.argv[1] + "/"
        if not os.path.isdir(sys.argv[1]):
            print("WARNING: working path IS NOT EXIST. Remake.")
            os.mkdir(sys.argv[1])
    except IndexError:
        pass
    except IOError:
        traceback.print_exc()
        print("ERROR: Failed to create working directory! Bot will be closed!")
        sys.exit(1)

    sql_worker.dbname = PATH + "database.db"
    reload(logging)
    logging.basicConfig(
        handlers=[
            logging.FileHandler(PATH + "logging.log", 'w', 'utf-8'),
            logging.StreamHandler(sys.stdout)
        ],
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt="%d-%m-%Y %H:%M:%S")

    if not os.path.isfile(PATH + "config.ini"):
        print("Config file isn't found! Trying to remake!")
        remake_conf()

    config_init()
    sql_worker.table_init()
    auto_thresholds_init()

    try:
        os.remove(PATH + "tmp_img")
    except IOError:
        pass

    threading.Thread(target=auto_clear).start()

    if main_chat_id == -1:
        logging.info("WARNING! STARTED IN INIT MODE!")
        return

    get_version = sql_worker.params("version", VERSION)
    update_text = "" if get_version == VERSION else "\nВнимание! Обнаружено изменение версии.\n" \
                                                 f"Текущая версия: {VERSION}\n" \
                                                 f"Предыдущая версия: {get_version}"

    if debug:
        logging.info("LAUNCH IN DEBUG MODE! IGNORE CONFIGURE!")
        bot.send_message(main_chat_id, f"Бот запущен в режиме отладки!" + update_text)
    else:
        bot.send_message(main_chat_id, f"Бот перезапущен." + update_text)

    logging.info(f"###ANK REMOTE CONTROL {VERSION} BUILD DATE {BUILD_DATE} HAS BEEN STARTED!###")


def auto_clear():
    while True:
        records = sql_worker.get_all_pools()
        for record in records:
            if record[5] + 600 < int(time.time()):
                sql_worker.rem_rec(record[1], record[0])
                try:
                    os.remove(PATH + record[0])
                except IOError:
                    pass
                logging.info('Removed deprecated poll "' + record[0] + '"')
        time.sleep(3600)


def auto_thresholds_init():
    global votes_need, votes_need_ban

    if auto_thresholds:
        votes_need = int(bot.get_chat_members_count(main_chat_id) / 2)
        if votes_need > 7:
            votes_need = 7
        if votes_need <= 1:
            votes_need = 2

    if auto_thresholds_ban:
        if bot.get_chat_members_count(main_chat_id) > 15:
            votes_need_ban = 5
        elif bot.get_chat_members_count(main_chat_id) > 5:
            votes_need_ban = 3
        else:
            votes_need_ban = 2


def extract_arg(text, num):
    try:
        return text.split()[num]
    except IndexError:
        pass


def html_fix(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def username_parser(message, html=False):
    if message.from_user.first_name == "":
        return "DELETED USER"

    if message.from_user.username is None:
        if message.from_user.last_name is None:
            username = str(message.from_user.first_name)
        else:
            username = str(message.from_user.first_name) + " " + str(message.from_user.last_name)
    else:
        if message.from_user.last_name is None:
            username = str(message.from_user.first_name) + " (@" + str(message.from_user.username) + ")"
        else:
            username = str(message.from_user.first_name) + " " + str(message.from_user.last_name) + \
                       " (@" + str(message.from_user.username) + ")"

    if not html:
        return username

    return html_fix(username)


def username_parser_invite(message, html=False):
    if message.json.get("new_chat_participant").get("username") is None:
        if message.json.get("new_chat_participant").get("last_name") is None:
            username = message.json.get("new_chat_participant").get("first_name")
        else:
            username = message.json.get("new_chat_participant").get("first_name") + " " \
                       + message.json.get("new_chat_participant").get("last_name")
    else:
        if message.json.get("new_chat_participant").get("last_name") is None:
            username = message.json.get("new_chat_participant").get("first_name") \
                       + " (@" + message.json.get("new_chat_participant").get("username") + ")"
        else:
            username = message.json.get("new_chat_participant").get("first_name") + " " \
                       + message.json.get("new_chat_participant").get("last_name") + \
                       " (@" + message.json.get("new_chat_participant").get("username") + ")"

    if not html:
        return username

    return html_fix(username)


def username_parser_chat_member(chat_member, html=False):
    if chat_member.user.username is None:
        if chat_member.user.last_name is None:
            username = chat_member.user.first_name
        else:
            username = chat_member.user.first_name + " " + chat_member.user.last_name
    else:
        if chat_member.user.last_name is None:
            username = chat_member.user.first_name + " (@" + chat_member.user.username + ")"
        else:
            username = chat_member.user.first_name + " " + chat_member.user.last_name + \
                   " (@" + chat_member.user.username + ")"

    if not html:
        return username

    return html_fix(username)


def reply_msg_target(message):
    if message.json.get("new_chat_participant") is not None:
        user_id = message.json.get("new_chat_participant").get("id")
        username = username_parser_invite(message)
        is_bot = message.json.get("new_chat_participant").get("is_bot")
    else:
        user_id = message.from_user.id
        username = username_parser(message)
        is_bot = message.from_user.is_bot

    return user_id, username, is_bot


def remake_conf():
    token, chat_id = "", ""
    while token == "":
        token = input("Please, write your bot token: ")
    while chat_id == "":
        chat_id = input("Please, write your main chat ID: ")
    config = configparser.ConfigParser()
    config.add_section("Chat")
    config.set("Chat", "token", token)
    config.set("Chat", "chatid", chat_id)
    config.set("Chat", "timer", "0")
    config.set("Chat", "bantimer", "0")
    config.set("Chat", "votes", "0")
    config.set("Chat", "banvotes", "0")
    config.set("Chat", "votes-mode", "3")
    config.set("Chat", "abuse-random", "0")
    config.set("Chat", "wait-timer", "30")
    config.set("Chat", "abuse-mode", "2")
    config.set("Chat", "private-mode", "true")
    config.set("Chat", "rules", "false")
    config.set("Chat", "rate", "true")
    try:
        config.write(open(PATH + "config.ini", "w"))
        print("New config file was created successful")
    except IOError:
        print("ERR: Bot cannot write new config file and will close")
        logging.error(traceback.format_exc())
        sys.exit(1)


def update_conf():
    if debug:
        return

    config = configparser.ConfigParser()
    try:
        config.read(PATH + "config.ini")
        if auto_thresholds:
            config.set("Chat", "votes", "0")
        else:
            config.set("Chat", "votes", str(votes_need))
        if auto_thresholds_ban:
            config.set("Chat", "banvotes", "0")
        else:
            config.set("Chat", "banvotes", str(votes_need_ban))
        config.set("Chat", "timer", str(global_timer))
        config.set("Chat", "bantimer", str(global_timer_ban))
        config.write(open(PATH + "config.ini", "w"))
    except Exception as e:
        print(e)
        logging.error(traceback.format_exc())
        return


def time_parser(instr: str):
    tf = {
        "s": lambda x: x,
        "m": lambda x: tf['s'](x) * 60,
        "h": lambda x: tf['m'](x) * 60,
        "d": lambda x: tf['h'](x) * 24,
        "w": lambda x: tf['d'](x) * 7,
    }
    buf = 0
    pdata = 0
    for label in instr:
        if label.isnumeric():
            buf = buf * 10 + int(label)
        else:
            label = label.lower()
            if label in tf:
                pdata += tf[label](buf)
            else:
                return None
            buf = 0
    return pdata + buf


def formatted_timer(timer_in_second):
    if timer_in_second <= 0:
        return "0c."
    elif timer_in_second < 60:
        return time.strftime("%Sс.", time.gmtime(timer_in_second))
    elif timer_in_second < 3600:
        return time.strftime("%Mм. и %Sс.", time.gmtime(timer_in_second))
    elif timer_in_second < 86400:
        return time.strftime("%Hч., %Mм. и %Sс.", time.gmtime(timer_in_second))
    else:
        days = timer_in_second // 86400
        timer_in_second = timer_in_second - days * 86400
        return str(days) + " дн., " + time.strftime("%Hч., %Mм. и %Sс.", time.gmtime(timer_in_second))
    # return datetime.datetime.fromtimestamp(timer_in_second).strftime("%d.%m.%Y в %H:%M:%S")


def make_keyboard(counter_yes, counter_no):
    buttons = [
        types.InlineKeyboardButton(text="Да - " + str(counter_yes), callback_data="yes"),
        types.InlineKeyboardButton(text="Нет - " + str(counter_no), callback_data="no"),
        types.InlineKeyboardButton(text="Узнать мой голос", callback_data="vote"),
        types.InlineKeyboardButton(text="Отмена голосования", callback_data="cancel")
    ]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    return keyboard


def vote_make(text, message, adduser, silent):
    if adduser:
        vote_message = bot.send_message(main_chat_id, text, reply_markup=make_keyboard("0", "0"), parse_mode="html")
    else:
        vote_message = bot.reply_to(message, text, reply_markup=make_keyboard("0", "0"), parse_mode="html")
    if not silent:
        try:
            bot.pin_chat_message(main_chat_id, vote_message.message_id, disable_notification=True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

    return vote_message


def vote_update(counter_yes, counter_no, call):
    bot.edit_message_reply_markup(call.chat.id, message_id=call.message_id,
                                  reply_markup=make_keyboard(counter_yes, counter_no))


def is_voting_exists(records, message, unique_id):
    if not records:
        return False
    if records[0][5] <= int(time.time()):
        sql_worker.rem_rec("", unique_id=unique_id)
        sql_worker.rem_rec(records[0][1])
        return False
    else:
        bot.reply_to(message, "Голосование о данном вопросе уже идёт.")
        return True


def botname_checker(message, getchat=False):  # Crutch to prevent the bot from responding to other bots commands

    cmd_text = message.text.split()[0]

    if main_chat_id != -1 and getchat:
        return False

    if main_chat_id == -1 and not getchat:
        return False

    if ("@" in cmd_text and "@" + bot.get_me().username in cmd_text) or not ("@" in cmd_text):
        return True
    else:
        return False


def private_checker(message):  # Проверка на то, можно ли сохранять имя пользователя в БД SQLite в данных о голосовании
    if not private_mode:
        return username_parser(message)
    else:
        return "none"


def pool_saver(unique_id, message_vote):
    try:
        pool = open(PATH + unique_id, 'wb')
        pickle.dump(message_vote, pool, protocol=4)
        pool.close()
    except (IOError, pickle.PicklingError):
        logging.error("Failed to picking a pool! You will not be able to resume the timer after restarting the bot!")
        logging.error(traceback.format_exc())
