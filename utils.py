import configparser
import logging
import sys
import time
import traceback

import telebot

bot: telebot.TeleBot

global_timer = 3600
global_timer_ban = 300
votes_need = 0
votes_need_ban = 0
auto_thresholds = False
auto_thresholds_ban = False
PATH = ""


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
    config.set("Chat", "timer", "")
    config.set("Chat", "bantimer", "")
    config.set("Chat", "votes", "")
    config.set("Chat", "banvotes", "")
    config.set("Chat", "votes-mode", "3")
    config.set("Chat", "abuse-random", "0")
    config.set("Chat", "wait-timer", "30")
    config.set("Chat", "abuse-mode", "2")
    config.set("Chat", "private-mode", "true")
    config.set("Chat", "rules", "false")
    try:
        config.write(open(PATH + "config.ini", "w"))
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
        config.read(PATH + "config.ini")
        if auto_thresholds:
            config.set("Chat", "votes", "")
        else:
            config.set("Chat", "votes", str(votes_need))
        if auto_thresholds_ban:
            config.set("Chat", "banvotes", "")
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
