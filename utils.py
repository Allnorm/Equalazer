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
    config.set("Ancap", "votes-mode", "3")
    config.set("Ancap", "abuse-random", "0")
    config.set("Ancap", "wait-timer", "30")
    config.set("Ancap", "abuse-mode", "2")
    config.set("Ancap", "private-mode", "true")
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
    if timer_in_second < 60:
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
