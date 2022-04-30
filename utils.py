import configparser
import logging
import sys
import time
import traceback

import telebot

import sql_worker

bot: telebot.TeleBot

global_timer = 3600
global_timer_ban = 300
votes_need = 0
votes_need_ban = 0
auto_thresholds = False
auto_thresholds_ban = False


def bot_init(token):
    global bot
    bot = telebot.TeleBot(token)


def auto_thresholds_init(main_chat_id):
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
        elif bot.get_chat_members_count(main_chat_id) > 1:
            votes_need_ban = bot.get_chat_members_count(main_chat_id)
        else:
            votes_need_ban = 2


def extract_arg(text, num):
    try:
        return text.split()[num]
    except IndexError:
        pass


def username_parser(message):
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

    return username


def remake_conf():
    token, chat_id = "", ""
    while token == "":
        token = input("Please, write your bot token: ")
    while chat_id == "":
        chat_id = input("Please, write your main chat ID: ")
    config = configparser.ConfigParser()
    config.add_section("Ancap")
    config.set("Ancap", "token", token)
    config.set("Ancap", "chatid", chat_id)
    config.set("Ancap", "timer", "")
    config.set("Ancap", "bantimer", "")
    config.set("Ancap", "votes", "")
    config.set("Ancap", "banvotes", "")
    config.set("Ancap", "mode", "3")
    config.set("Ancap", "abuse-random", "0")
    config.set("Ancap", "wait-timer", "30")
    try:
        config.write(open("config.ini", "w"))
        print("New config file was created successful")
    except IOError:
        print("ERR: Bot cannot write new config file and will close")
        logging.error(traceback.format_exc())
        sys.exit(1)


def update_conf(debug):
    if debug:
        return

    config = configparser.ConfigParser()
    try:
        config.read("config.ini")
        if auto_thresholds:
            config.set("Ancap", "votes", "")
        else:
            config.set("Ancap", "votes", str(votes_need))
        if auto_thresholds_ban:
            config.set("Ancap", "banvotes", "")
        else:
            config.set("Ancap", "banvotes", str(votes_need_ban))
        config.set("Ancap", "timer", str(global_timer))
        config.set("Ancap", "bantimer", str(global_timer_ban))
        config.write(open("config.ini", "w"))
    except Exception as e:
        print(e)
        logging.error(traceback.format_exc())
        return


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


def time_parser(instring: str):
    preparsedata = 0
    buf = ""
    for letter in instring:
        if letter.isnumeric():
            buf += letter
        else:
            if letter == "s":  # seconds
                preparsedata += int(buf)
            elif letter == "m":  # minutes
                preparsedata += int(buf) * 60
            elif letter == "h":  # hours
                preparsedata += int(buf) * 60 * 60
            elif letter == "d":  # days
                preparsedata += int(buf) * 60 * 60 * 24
            elif letter == "w":  # weeks
                preparsedata += int(buf) * 60 * 60 * 24 * 7
            elif letter == "M":  # months
                preparsedata += int(buf) * 60 * 60 * 24 * 30
            else:
                return None
            buf = ""

    if buf != "":
        preparsedata += int(buf)

    return preparsedata


def time_parser_legacy(str_time: str):
    get_seconds = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    try:
        if str_time[-1].lower() in get_seconds:
            return int(float(str_time[:-1]) * get_seconds.get(str_time[-1]))
        else:
            return int(str_time)
    except ValueError:
        return None


def formatted_timer(timer_in_second):
    if timer_in_second < 60:
        return time.strftime("%Sс.", time.gmtime(timer_in_second))
    elif timer_in_second < 3600:
        return time.strftime("%Mм. и %Sс.", time.gmtime(timer_in_second))
    elif timer_in_second < 86400:
        return time.strftime("%Hч., %Mм. и %Sс.", time.gmtime(timer_in_second))
    else:
        return time.strftime("%m мес., %d дн., %Hч., %Mм. и %Sс.", time.gmtime(timer_in_second))
    # return datetime.datetime.fromtimestamp(timer_in_second).strftime("%d.%m.%Y в %H:%M:%S")
