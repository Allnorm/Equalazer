import configparser
import logging
import os
import random
import sys
import threading
import time
import traceback
from importlib import reload

import telebot
from telebot import types

import utils
import sql_worker
import postvote

main_chat_id = ""
debug = False
minimum_vote = 1
vote_mode = 3
vote_abuse = {}
allies = []
abuse_random = 0
wait_timer = 30


def var_init(var):
    try:
        var = int(var)
        return var
    except ValueError:
        return 0


def config_init():
    global main_chat_id, minimum_vote, debug, vote_mode, abuse_random, wait_timer

    reload(logging)
    logging.basicConfig(
        handlers=[
            logging.FileHandler("ancap.log", 'w', 'utf-8'),
            logging.StreamHandler(sys.stdout)
        ],
        level=logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt="%d-%m-%Y %H:%M:%S")

    sql_worker.table_init()
    version = "0.5.5 beta"
    build = "2"
    logging.info("###ANK REMOTE CONTROL {} build {} HAS BEEN STARTED!###".format(version, build))

    try:
        if sys.argv[1] == "--debug":
            debug = True
    except IndexError:
        pass

    if not os.path.isfile("config.ini"):
        print("Config file isn't found! Trying to remake!")
        utils.remake_conf()

    config = configparser.ConfigParser()
    try:
        config.read("config.ini")
        token = config["Ancap"]["token"]
        utils.global_timer = config["Ancap"]["timer"]
        utils.global_timer_ban = config["Ancap"]["bantimer"]
        utils.votes_need = config["Ancap"]["votes"]
        utils.votes_need_ban = config["Ancap"]["banvotes"]
        vote_mode = int(config["Ancap"]["mode"])
        abuse_random = int(config["Ancap"]["abuse-random"])
        wait_timer = int(config["Ancap"]["wait-timer"])
        if config["Ancap"]["chatid"] != "init":
            main_chat_id = int(config["Ancap"]["chatid"])
        else:
            debug = True
            main_chat_id = "init"
    except Exception as e:
        logging.error((str(e)))
        logging.error(traceback.format_exc())
        time.sleep(1)
        print("\nInvalid config file! Trying to remake!")
        agreement = "-1"
        while agreement != "y" and agreement != "n" and agreement != "":
            agreement = input("Do you want to reset your broken config file on defaults? (y/n): ")
            agreement = agreement.lower()
        if agreement == "" or agreement == "y":
            utils.remake_conf()
            print("To apply the configuration you need to restart this bot")
            sys.exit(0)
        else:
            sys.exit(0)

    if debug:
        utils.global_timer = 20
        utils.global_timer_ban = 10
        utils.votes_need = 2
        utils.votes_need_ban = 2
        minimum_vote = 0
        wait_timer = 0
        return token

    utils.global_timer = var_init(utils.global_timer)
    utils.global_timer_ban = var_init(utils.global_timer_ban)
    utils.votes_need = var_init(utils.votes_need)
    utils.votes_need_ban = var_init(utils.votes_need_ban)

    if utils.global_timer < 5 or utils.global_timer > 86400:
        utils.global_timer = 3600
    if utils.global_timer_ban < 5 or utils.global_timer > 86400:
        utils.global_timer_ban = 300
    if utils.votes_need <= 1:
        utils.auto_thresholds = True
    if utils.votes_need_ban <= 1:
        utils.auto_thresholds_ban = True

    return token


def auto_clear():
    while True:
        sql_worker.deletion_of_overdue()
        time.sleep(3600)


def init():
    utils.auto_thresholds_init(main_chat_id)

    global allies

    try:
        file = open("allies.txt", 'r', encoding="utf-8")
        allies = file.readlines()
    except FileNotFoundError:
        logging.warning("file \"allies.txt\" not found.")
    except IOError:
        logging.error("file \"allies.txt\" isn't readable.")
    if not allies:
        logging.warning("allies is empty.")

    try:
        os.remove("tmp_img")
    except IOError:
        pass

    threading.Thread(target=auto_clear).start()

    if main_chat_id == "init":
        logging.info("WARNING! STARTED IN INIT MODE!")
        return

    if debug:
        logging.info("LAUNCH IN DEBUG MODE! IGNORE CONFIGURE!")
        utils.bot.send_message(main_chat_id, "Бот запущен в режиме отладки!")
    else:
        utils.bot.send_message(main_chat_id, "Бот перезапущен")


utils.bot_init(config_init())
init()


def vote_make(text, message, adduser=False, silent=False):
    buttons = [
        types.InlineKeyboardButton(text="Да - " + "0", callback_data="yes"),
        types.InlineKeyboardButton(text="Нет - " + "0", callback_data="no"),
        types.InlineKeyboardButton(text="Узнать мой голос", callback_data="vote")
    ]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    if adduser:
        vote_message = utils.bot.send_message(main_chat_id, text, reply_markup=keyboard, parse_mode='markdown')
    else:
        vote_message = utils.bot.reply_to(message, text, reply_markup=keyboard, parse_mode='html')
    if not silent:
        utils.bot.pin_chat_message(main_chat_id, vote_message.message_id, disable_notification=True)
    return vote_message


def vote_timer(unique_id, message_vote, time_to_sleep):
    time.sleep(time_to_sleep)
    vote_abuse.clear()
    vote_result(unique_id, message_vote)


def vote_result(unique_id, message_vote):
    utils.auto_thresholds_init(main_chat_id)
    records = sql_worker.msg_chk(unique_id=unique_id)
    sql_worker.rem_rec(message_vote.id, unique_id)
    if not records:
        return

    votes_counter = "За: " + str(records[0][3]) + "\n" + "Против: " + str(records[0][4])
    if records[0][3] > records[0][4] and records[0][3] > minimum_vote:
        accept = True
    elif records[0][3] + records[0][4] > minimum_vote:
        accept = False
    else:
        accept = False
        votes_counter = "Недостаточно голосов (требуется как минимум " + str(minimum_vote + 1) + ")"

    functions = {
        "adduser": postvote.vote_result_useradd,
        "banuser": postvote.vote_result_userkick,
        "unbanuser": postvote.vote_result_unban,
        "threshold": postvote.vote_result_treshold,
        "threshold_ban": postvote.vote_result_treshold_ban,
        "timer": postvote.vote_result_timer,
        "timer_ban": postvote.vote_result_timer,
        "delmsg": postvote.vote_result_delmsg,
        "op": postvote.vote_result_op,
        "deop": postvote.vote_result_deop,
        "title": postvote.vote_result_title,
        "chatpic": postvote.vote_result_chat_pic,
        "desc": postvote.vote_result_description
    }

    try:
        functions[records[0][2]](records, message_vote, votes_counter, accept)
    except KeyError:
        logging.error(traceback.format_exc())
        utils.bot.edit_message_text("Ошибка применения результатов голосования. Итоговая функция не найдена!",
                                    message_vote.chat.id, message_vote.id)

    try:
        utils.bot.unpin_chat_message(main_chat_id, message_vote.message_id)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())

    try:
        utils.bot.reply_to(message_vote, "Оповещение о закрытии голосования.")
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())

    utils.update_conf(debug)


def vote_update(counter_yes, counter_no, call):
    buttons = [
        types.InlineKeyboardButton(text="Да - " + str(counter_yes), callback_data="yes"),
        types.InlineKeyboardButton(text="Нет - " + str(counter_no), callback_data="no"),
        types.InlineKeyboardButton(text="Узнать мой голос", callback_data="vote")
    ]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    utils.bot.edit_message_reply_markup(call.chat.id, message_id=call.message_id, reply_markup=keyboard)


def botname_checker(message, getchat=False):  # Crutch to prevent the bot from responding to other bots commands

    cmd_text = message.text.split()[0]

    if main_chat_id != "init" and getchat:
        return False

    if main_chat_id == "init" and not getchat:
        return False

    if ("@" in cmd_text and "@" + utils.bot.get_me().username in cmd_text) or not ("@" in cmd_text):
        return True
    else:
        return False


def pool_constructor(unique_id: str, vote_text: str, message, vote_type: str,
                     current_timer: int, current_votes: int, vote_args: list, adduser=False, silent=False):
    vote_text = vote_text + "\nГолосование будет закрыто через " + utils.formatted_timer(current_timer) \
                + ", для досрочного завершения требуется голосов за один из пунктов: " + str(current_votes) + "\n" \
                + "Минимальный порог голосов для принятия решения: " + str(minimum_vote + 1)

    message_vote = vote_make(vote_text, message, adduser=adduser, silent=silent)
    sql_worker.addpool(unique_id, message_vote, vote_type,
                       int(time.time()) + current_timer, str(vote_args), current_votes)
    threading.Thread(target=vote_timer, args=(unique_id, message_vote, current_timer,)).start()


@utils.bot.message_handler(commands=['adduser'])
def add_usr(message):
    if not botname_checker(message):
        return

    unique_id = str(message.from_user.id) + "_useradd"
    try:
        msg_from_usr = message.text.split(None, 1)[1]
    except IndexError:
        msg_from_usr = "нет"

    if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status != "left" \
            and utils.bot.get_chat_member(main_chat_id, message.from_user.id).status != "kicked" \
            and utils.bot.get_chat_member(main_chat_id, message.from_user.id).status != "restricted" \
            or utils.bot.get_chat_member(main_chat_id, message.from_user.id).is_member:
        # Fuuuuuuuck my brain
        utils.bot.reply_to(message, "Вы уже есть в нужном вам чате.")
        return

    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    abuse_chk = sql_worker.abuse_check(message.from_user.id)
    if abuse_chk > 0:
        utils.bot.reply_to(message, "Сработала защита от абуза инвайта! Вам следует подождать ещё "
                           + time.strftime("%Hч., %Mм. и %Sс.", time.gmtime(abuse_chk - int(time.time()))))
        return

    vote_text = ("Пользователь " + "[" + utils.username_parser(message)
                 + "](tg://user?id=" + str(message.from_user.id) + ")" + " хочет в чат.\n"
                 + "Сообщение от пользователя: " + msg_from_usr + ".")

    pool_constructor(unique_id, vote_text, message, "adduser", utils.global_timer, utils.votes_need,
                     [message.chat.id, utils.username_parser(message), message.from_user.id], adduser=True)

    warn = ""
    if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status == "kicked":
        warn = "\nВнимание! Вы были заблокированы в чате ранее, поэтому вероятность инвайта минимальная!"
    if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status == "restricted":
        warn = "\nВнимание! Сейчас на вас распространяются ограничения прав в чате, выданные командой /mute!"
    utils.bot.reply_to(message, "Голосование о вступлении отправлено в чат. Голосование завершится через "
                       + utils.formatted_timer(utils.global_timer) + " или ранее." + warn)


@utils.bot.message_handler(commands=['answer'])
def add_answer(message):
    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данную команду можно запустить только в основном чате.")
        return

    if message.reply_to_message is None:
        utils.bot.reply_to(message, "Пожалуйста, используйте эту команду как ответ на заявку на вступление")
        return

    pool = sql_worker.msg_chk(message_vote=message.reply_to_message)
    if not pool:
        utils.bot.reply_to(message, "Заявка на вступление не найдена или закрыта")
        return

    try:
        msg_from_usr = message.text.split(None, 1)[1]
    except IndexError:
        utils.bot.reply_to(message, "Ответ не может быть пустым.")
        return

    datalist = eval(pool[0][6])

    try:
        utils.bot.send_message(datalist[0], "Сообщение на вашу заявку от участника чата - \"" + msg_from_usr + "\"")
        utils.bot.reply_to(message, "Сообщение пользователю отправлено успешно.")
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        utils.bot.reply_to(message, "Ошибка отправки сообщению пользователю.")


@utils.bot.message_handler(commands=['kickuser', 'banuser', 'mute'])
def ban_usr(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if message.reply_to_message is None:
        utils.bot.reply_to(message, "Ответьте на имя пользователя, которого требуется забанить/кикнуть/замутить.")
        return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "kicked":
        utils.bot.reply_to(message, "Данный пользователь уже забанен или кикнут.")
        return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "left" \
            and utils.extract_arg(message.text, 0) == "/kickuser":
        utils.bot.reply_to(message, "Пользователя нет в чате, чтобы можно было кикнуть его.")
        return

    perm_ban = False
    if utils.extract_arg(message.text, 0) == "/banuser":
        perm_ban = True

    mute = False
    if utils.extract_arg(message.text, 0) == "/mute":
        if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "restricted":
            until_date = utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).until_date
            if until_date == 0 or until_date is None:
                utils.bot.reply_to(message, "Данный пользователь уже ограничен.")
                return
        mute = True

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "creator":
        utils.bot.reply_to(message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
        return

    if utils.bot.get_me().id == message.reply_to_message.from_user.id:
        utils.bot.reply_to(message, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    if perm_ban and message.reply_to_message.from_user.is_bot:
        utils.bot.reply_to(message, "Запрещено перманентно банить ботов.")
        return

    restrict_timer = 0
    if utils.extract_arg(message.text, 0) == "/kickuser" or utils.extract_arg(message.text, 0) == "/mute":
        if utils.extract_arg(message.text, 1) is not None:
            restrict_timer = utils.time_parser(utils.extract_arg(message.text, 1))
            if restrict_timer is None:
                utils.bot.reply_to(message, "Некорректный аргумент времени.")
                return
            if not 30 < restrict_timer < 31536000:
                utils.bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше/равно 365 суток.")
                return

    if utils.extract_arg(message.text, 0) == "/kickuser" and restrict_timer == 0:
        restrict_timer = 3600

    unique_id = str(message.reply_to_message.from_user.id) + "_userban"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    ban_timer_text = "."
    if restrict_timer != 0:
        ban_timer_text = " на срок {}".format(utils.formatted_timer(restrict_timer))

    if message.from_user.id == message.reply_to_message.from_user.id:
        ban_text = "самовыпилиться"
        if perm_ban:
            ban_text = "самовыпилиться из чата <b>навсегда</b>"
        if mute:
            ban_text = "сыграть в молчанку с самим собой"
        vote_text = ("От пользователя " + utils.username_parser(message) + " поступило предложение "
                     + ban_text + ban_timer_text)
    else:
        ban_text = "кикнуть"
        if perm_ban:
            ban_text = "<b>забанить перманентно</b>"
        if mute:
            ban_text = "отправить в мут"

        vote_text = ("От пользователя " + utils.username_parser(message) + " поступило предложение " + ban_text
                     + " пользователя " + utils.username_parser(message.reply_to_message) + ban_timer_text)
    vote_type = 1
    if mute:
        vote_type = 0
    if perm_ban:
        vote_type = 2

    pool_constructor(unique_id, vote_text, message, "banuser", utils.global_timer_ban, utils.votes_need_ban,
                     [message.reply_to_message.from_user.id, utils.username_parser(message.reply_to_message),
                      message.from_user.id, utils.username_parser(message), vote_type, restrict_timer])


@utils.bot.message_handler(commands=['unmute', 'unban'])
def unban_usr(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if message.reply_to_message is None:
        utils.bot.reply_to(message, "Ответьте на имя пользователя, которого требуется размутить или разбанить.")
        return

    if utils.bot.get_me().id == message.reply_to_message.from_user.id:
        utils.bot.reply_to(message, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status != "restricted" and \
            utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status != "kicked":
        utils.bot.reply_to(message, "Данный пользователь не ограничен.")
        return

    unique_id = str(message.reply_to_message.from_user.id) + "_unban"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("От пользователя " + utils.username_parser(message)
                 + " поступило предложение снять ограничения с пользователя "
                 + utils.username_parser(message.reply_to_message) + ".")

    pool_constructor(unique_id, vote_text, message, "unbanuser", utils.global_timer, utils.votes_need,
                     [message.reply_to_message.from_user.id, utils.username_parser(message.reply_to_message),
                      message.from_user.id, utils.username_parser(message)])


@utils.bot.message_handler(commands=['threshold'])
def thresholds(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данную команду можно запустить только в основном чате.")
        return

    mode = utils.extract_arg(message.text, 1)
    if mode is None:
        auto_thresholds_mode = ""
        auto_thresholds_ban_mode = ""
        if utils.auto_thresholds:
            auto_thresholds_mode = " (автоматический режим)"
        if utils.auto_thresholds_ban:
            auto_thresholds_ban_mode = " (автоматический режим)"
        utils.auto_thresholds_init(main_chat_id)
        utils.bot.reply_to(message, "Текущие пороги:\nГолосов для обычного решения требуется: " + str(utils.votes_need)
                           + auto_thresholds_mode + "\n"
                           + "Голосов для бана требуется: " + str(utils.votes_need_ban) + auto_thresholds_ban_mode
                           + "\n" + "Минимальный порог голосов для принятия решения: " + str(minimum_vote + 1))
        return
    unique_id = "threshold"
    bantext = ""
    if utils.extract_arg(message.text, 2) == "ban":
        unique_id = "threshold_ban"
        bantext = " для бана"

    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    if mode != "auto":
        try:
            mode = int(mode)
        except (TypeError, ValueError):
            utils.bot.reply_to(message, "Неверный аргумент (должно быть целое число от 2 до "
                               + str(utils.bot.get_chat_members_count(main_chat_id)) + " или \"auto\").")
            return

        if mode > utils.bot.get_chat_members_count(main_chat_id):
            utils.bot.reply_to(message,
                               "Количество необходимых голосов не может быть больше количества участников в чате.")
            return

        if mode <= minimum_vote:
            utils.bot.reply_to(message, "Количество необходимых голосов не может быть меньше " + str(minimum_vote + 1))
            return

        vote_text = ("От пользователя " + utils.username_parser(message)
                     + " поступило предложение изменить порог голосов" + bantext + " до " + str(mode) + ".")
    else:
        vote_text = ("От пользователя " + utils.username_parser(message)
                     + " поступило предложение включить автоматический порог голосов" + bantext + ".")

    pool_constructor(unique_id, vote_text, message, unique_id, utils.global_timer, utils.votes_need, [mode])


@utils.bot.message_handler(commands=['timer'])
def timer(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данную команду можно запустить только в основном чате.")
        return
    mode = utils.extract_arg(message.text, 1)
    if mode is None:
        utils.bot.reply_to(message, "Текущие пороги таймера:\n"
                           + time.strftime("%Hч., %Mм., %Sс.",
                                           time.gmtime(utils.global_timer)) + " для обычного голосования\n"
                           + time.strftime("%Hч., %Mм., %Sс.",
                                           time.gmtime(utils.global_timer_ban)) + " для голосования за бан\n"
                           + "При смене порога значение указывается в секундах.")
        return
    unique_id = "timer"
    bantext = ""
    if utils.extract_arg(message.text, 2) == "ban":
        unique_id = "timer_ban"
        bantext = " для бана"

    mode = utils.time_parser(mode)
    if mode is None:
        utils.bot.reply_to(message, "Неверный аргумент (должно быть число a от 5 секунд до 1 суток).")
        return

    if mode < 5 or mode > 86400:
        utils.bot.reply_to(message, "Количество времени не может быть меньше 5 секунд и больше 1 суток.")
        return

    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("От пользователя " + utils.username_parser(message)
                 + " поступило предложение изменить таймер на "
                 + time.strftime("%Hч., %Mм. и %Sс", time.gmtime(mode)) + bantext + ".")

    pool_constructor(unique_id, vote_text, message, unique_id, utils.global_timer, utils.votes_need, [mode, unique_id])


@utils.bot.message_handler(commands=['delmsg', 'clearmsg'])
def del_msg(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if message.reply_to_message is None:
        utils.bot.reply_to(message, "Ответьте на сообщение пользователя, которое требуется удалить.")
        return

    if utils.bot.get_me().id == message.reply_to_message.from_user.id and sql_worker.msg_chk(message.reply_to_message):
        utils.bot.reply_to(message, "Вы не можете удалить голосование до его завершения!")
        return

    unique_id = str(message.reply_to_message.message_id) + "_delmsg"

    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    silent_del = False
    votes = utils.votes_need_ban
    timer_del = utils.global_timer_ban
    clear = ""
    warn = ""
    if utils.extract_arg(message.text, 0) == "/clearmsg":
        silent_del = True
        votes = utils.votes_need
        timer_del = utils.global_timer
        clear = "бесследно "
        warn = "\nВнимание, голосования для бесследной очистки не закрепляются автоматически. Пожалуйста, " \
               "закрепите их самостоятельно при необходимости."

    vote_text = ("Пользователь " + utils.username_parser(message) + " хочет " + clear
                 + "удалить сообщение пользователя "
                 + utils.username_parser(message.reply_to_message) + "." + warn)

    pool_constructor(unique_id, vote_text, message, "delmsg", timer_del, votes,
                     [message.reply_to_message.message_id, utils.username_parser(message.reply_to_message), silent_del],
                     silent=silent_del)


def chname(message, rank):
    if len(rank) > 16:
        utils.bot.reply_to(message, "Звание не может быть длиннее 16 символов.")
        return
    try:
        utils.bot.set_chat_administrator_custom_title(main_chat_id, message.from_user.id, rank)
        utils.bot.reply_to(message, "Звание успешно изменено.")
    except telebot.apihelper.ApiTelegramException as e:
        if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
            utils.bot.reply_to(message, "В звании не поддерживаются эмодзи.")
            return
        logging.error(traceback.format_exc())
        utils.bot.reply_to(message, "Не удалось сменить звание.")


@utils.bot.message_handler(commands=['op'])
def op(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if message.reply_to_message is not None:
        if message.reply_to_message.from_user.is_bot \
                and utils.bot.get_chat_member(main_chat_id,
                                              message.reply_to_message.from_user.id).status == "administrator":
            if utils.bot.get_me().id == message.reply_to_message.from_user.id:
                utils.bot.reply_to(message, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
                return
            if utils.extract_arg(message.text, 1) is None:
                utils.bot.reply_to(message, "Звание не может быть пустым.")
                return
            chname(message.reply_to_message, message.text.split(maxsplit=1)[1])
            return

    if message.reply_to_message is None or message.reply_to_message.from_user.id == message.from_user.id:

        if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status == "administrator":
            if utils.extract_arg(message.text, 1) is None:
                utils.bot.reply_to(message, "Звание не может быть пустым.")
                return

            chname(message, message.text.split(maxsplit=1)[1])
            return

        who_id = message.from_user.id
        is_myself = True
        who_name = utils.username_parser(message)
    else:
        is_myself = False
        who_id = message.reply_to_message.from_user.id
        who_name = utils.username_parser(message.reply_to_message)

    if utils.bot.get_chat_member(main_chat_id, who_id).status == "administrator":
        utils.bot.reply_to(message, "Пользователь уже администратор.")
        return

    if utils.bot.get_chat_member(main_chat_id, who_id).status == "creator":
        utils.bot.reply_to(message, "Пользователь является создателем чата.")
        return

    if utils.bot.get_chat_member(main_chat_id, who_id).status == "left" or \
            utils.bot.get_chat_member(main_chat_id, who_id).status == "kicked":
        utils.bot.reply_to(message, "Пользователь не состоит в чате.")
        return

    if utils.bot.get_chat_member(main_chat_id, who_id).status == "restricted":
        utils.bot.reply_to(message, "Ограниченный пользователь не может стать админом.")
        return

    unique_id = str(who_id) + "_op"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    if is_myself:
        vote_text = ("От пользователя " + who_name
                     + " поступило предложение дать права администратора себе, великому.\n"
                     + "Звание можно будет установить после закрытия голосования.")
    else:
        vote_text = ("От пользователя " + utils.username_parser(message)
                     + " поступило предложение дать права администратора пользователю "
                     + who_name + ".\n"
                     + "Звание можно будет установить после закрытия голосования.")

    pool_constructor(unique_id, vote_text, message, "op", utils.global_timer, utils.votes_need, [who_id, who_name])


@utils.bot.message_handler(commands=['deop'])
def deop(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if utils.extract_arg(message.text, 1) != "me" and message.reply_to_message is None:
        utils.bot.reply_to(message, "Ответьте на сообщение или используйте аргумент \"me\"")
        return

    me = False
    if utils.extract_arg(message.text, 1) == "me":
        me = True
    if message.reply_to_message is not None:
        if message.reply_to_message.from_user.id == message.from_user.id:
            me = True

    if me:
        if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status == "creator":
            utils.bot.reply_to(message, "Вы являетесь создателем чата, я не могу снять ваши права.")
            return
        if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status != "administrator":
            utils.bot.reply_to(message, "Вы не являетесь администратором!")
            return
        try:
            utils.bot.restrict_chat_member(main_chat_id, message.from_user.id,
                                           None, can_send_messages=True)
            utils.bot.restrict_chat_member(main_chat_id, message.from_user.id,
                                           None, True, True, True, True, True, True, True, True)
            utils.bot.reply_to(message,
                               "Пользователь " + utils.username_parser(message) + " добровольно ушёл в отставку."
                               + "\nСпасибо за верную службу!")
            return
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.reply_to(message, "Я не могу изменить ваши права!")
            return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "creator":
        utils.bot.reply_to(message, "Пользователь " + utils.username_parser(message.reply_to_message)
                           + " является создателем чата, я не могу снять его права.")
        return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status != "administrator":
        utils.bot.reply_to(message, "Пользователь " + utils.username_parser(message.reply_to_message)
                           + " не является администратором!")
        return

    if utils.bot.get_me().id == message.reply_to_message.from_user.id:
        utils.bot.reply_to(message, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    unique_id = str(message.reply_to_message.from_user.id) + "_deop"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("От пользователя " + utils.username_parser(message)
                 + " поступило предложение снять права администратора с пользователя "
                 + utils.username_parser(message.reply_to_message) + ".")

    pool_constructor(unique_id, vote_text, message, "deop", utils.global_timer, utils.votes_need,
                     [message.reply_to_message.from_user.id, utils.username_parser(message.reply_to_message)])


@utils.bot.message_handler(commands=['title'])
def deop(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if utils.extract_arg(message.text, 1) is None:
        utils.bot.reply_to(message, "Название чата не может быть пустым.")
        return

    if len(message.text.split(maxsplit=1)[1]) > 255:
        utils.bot.reply_to(message, "Название не должно быть длиннее 255 символов!")
        return

    if utils.bot.get_chat(main_chat_id).title == message.text.split(maxsplit=1)[1]:
        utils.bot.reply_to(message, "Название чата не может совпадать с существующим названием!")
        return

    unique_id = "title"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("От пользователя " + utils.username_parser(message)
                 + " поступило предложение сменить название чата на \""
                 + message.text.split(maxsplit=1)[1] + "\".")

    pool_constructor(unique_id, vote_text, message, unique_id, utils.global_timer, utils.votes_need,
                     [message.text.split(maxsplit=1)[1], utils.username_parser(message)])


@utils.bot.message_handler(commands=['description'])
def description(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if message.reply_to_message is not None:
        if message.reply_to_message.text is not None:
            inputtext = message.reply_to_message.text
            if len(inputtext) > 255:
                utils.bot.reply_to(message, "Описание не должно быть длиннее 255 символов!")
                return

        else:
            utils.bot.reply_to(message, "В отвеченном сообщении не обнаружен текст!")
            return
    else:
        inputtext = None

    if utils.bot.get_chat(main_chat_id).description == inputtext:
        utils.bot.reply_to(message, "Описание чата не может совпадать с существующим описанием!")
        return

    if inputtext is None:
        vote_text = ("От пользователя " + utils.username_parser(message)
                     + " поступило предложение сменить описание чата на пустое.")
    else:
        vote_text = ("От пользователя " + utils.username_parser(message)
                     + " поступило предложение сменить описание чата на \""
                     + inputtext + "\".")

    unique_id = "desc"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    if inputtext is None:
        inputtext = ""

    pool_constructor(unique_id, vote_text, message, unique_id, utils.global_timer, utils.votes_need,
                     [inputtext, utils.username_parser(message)])


@utils.bot.message_handler(commands=['chatpic'])
def chat_pic(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данное голосование можно запустить только в основном чате.")
        return

    if message.reply_to_message is None:
        utils.bot.reply_to(message, "Пожалуйста, используйте эту команду как ответ на фотографию, файл jpg или png.")
        return

    if message.reply_to_message.photo is not None:
        file_buffer = (utils.bot.download_file
                       (utils.bot.get_file(message.reply_to_message.photo[-1].file_id).file_path))
    elif message.reply_to_message.document is not None:
        if not message.reply_to_message.document.mime_type == "image/png" and \
                not message.reply_to_message.document.mime_type == "image/jpeg":
            utils.bot.reply_to(message, "Документ не является фотографией")
            return
        file_buffer = (utils.bot.download_file(utils.bot.get_file(message.reply_to_message.document.file_id).file_path))
    else:
        utils.bot.reply_to(message, "В сообщении не обнаружена фотография")
        return

    try:
        tmp_img = open('tmp_img', 'wb')
        tmp_img.write(file_buffer)
    except Exception as e:
        logging.error((str(e)))
        logging.error(traceback.format_exc())
        utils.bot.reply_to(message, "Ошибка записи изображения в файл!")
        return

    unique_id = "chatpic"
    records = sql_worker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("От пользователя " + utils.username_parser(message)
                 + " поступило предложение сменить аватарку чата.")

    pool_constructor(unique_id, vote_text, message, unique_id, utils.global_timer,
                     utils.votes_need, [utils.username_parser(message)])


@utils.bot.message_handler(commands=['random', 'redrum'])
def random_msg(message):
    global abuse_random

    if not botname_checker(message):
        return

    try:
        abuse_vote_timer = int(vote_abuse.get("random"))
    except TypeError:
        abuse_vote_timer = 0

    if abuse_vote_timer + abuse_random > int(time.time()) or abuse_random < 0:
        return

    vote_abuse.update({"random": int(time.time())})

    msg_id = ""
    for i in range(5):
        try:
            msg_id = random.randint(1, message.id)
            utils.bot.forward_message(message.chat.id, message.chat.id, msg_id)
            return
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

    utils.bot.reply_to(message, "Ошибка взятия рандомного сообщения с номером {}!".format(msg_id))


@utils.bot.message_handler(commands=['reinvite'])
def reinvite(message):
    if not botname_checker(message):
        return

    if debug:
        sql_worker.abuse_remove(message.from_user.id)
        utils.bot.reply_to(message, "Абуз инвайта сброшен.")


@utils.bot.message_handler(commands=['getid'])
def get_id(message):
    if not botname_checker(message, getchat=True):
        return

    if debug:
        print(message.chat.id)
        utils.bot.reply_to(message, "ID чата сохранён")


@utils.bot.message_handler(commands=['getuser'])
def get_usr(message):
    if not botname_checker(message):
        return

    if debug and message.reply_to_message is not None:
        print("c")
        utils.bot.reply_to(message, "ID пользователя " + utils.username_parser(message.reply_to_message)
                           + " - " + str(message.reply_to_message.from_user.id))


@utils.bot.message_handler(commands=['help'])
def help_msg(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данную команду можно запустить только в основном чате.")
        return

    try:
        help_text = open("help.txt", encoding="utf-8").read()
    except FileNotFoundError:
        utils.bot.reply_to(message, "Файл help.txt не найден.")
        return
    except IOError:
        utils.bot.reply_to(message, "Файл help.txt не читается.")
        return

    utils.bot.reply_to(message, help_text, parse_mode="html")


@utils.bot.message_handler(commands=['abuse'])
def mute_user(message):
    if not botname_checker(message):
        return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данную команду можно запустить только в основном чате.")
        return

    if message.reply_to_message is None:
        utils.bot.reply_to(message, "Ответьте на сообщение пользователя, которого необходимо отправить в мут.\n"
                           + "ВНИМАНИЕ: использовать только в крайних случаях - во избежание злоупотреблений "
                           + "вы так же будете лишены прав на тот же срок.\n"
                           + "Даже если у вас есть права админа, вы будете их автоматически лишены, "
                           + "если они были выданы с помощью бота.")
        return

    if utils.bot.get_me().id == message.reply_to_message.from_user.id:
        utils.bot.reply_to(message, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "restricted":
        utils.bot.reply_to(message, "Он и так в муте, не увеличивайте его страдания.")
        return

    if utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "kicked" \
            or utils.bot.get_chat_member(main_chat_id, message.reply_to_message.from_user.id).status == "left":
        utils.bot.reply_to(message, "Данный пользователь не состоит в чате.")
        return

    timer_mute = 3600
    if utils.extract_arg(message.text, 1) is not None:
        timer_mute = utils.time_parser(utils.extract_arg(message.text, 1))
        if timer_mute is None:
            utils.bot.reply_to(message, "Неправильный аргумент, укажите время мута от 30 секунд до 12 часов.")
            return

    if not 30 < timer_mute < 43200:
        utils.bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше 12 часов.")
        return

    try:
        abuse_vote_timer = int(vote_abuse.get("abuse" + str(message.from_user.id)))
    except TypeError:
        abuse_vote_timer = 0

    if abuse_vote_timer + 10 > int(time.time()):
        return

    vote_abuse.update({"abuse" + str(message.from_user.id): int(time.time())})

    try:
        utils.bot.restrict_chat_member(main_chat_id, message.reply_to_message.from_user.id,
                                       until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                       can_change_info=False, can_invite_users=False, can_pin_messages=False)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        utils.bot.reply_to(message, "Я не смог снять права данного пользователя. Не имею права.")
        return
    try:
        utils.bot.restrict_chat_member(main_chat_id, message.from_user.id,
                                       until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                       can_change_info=False, can_invite_users=False, can_pin_messages=False)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        utils.bot.reply_to(message, "Я смог снять права данного пользователя на время "
                           + utils.formatted_timer(timer_mute) + ", но не смог снять права автора заявки.")
        return
    if message.from_user.id == message.reply_to_message.from_user.id:
        utils.bot.reply_to(message, "Пользователь " + utils.username_parser(message)
                           + " решил отдохнуть от чата на время " + utils.formatted_timer(timer_mute))
        return
    utils.bot.reply_to(message, "Обоюдоострый Меч сработал. Теперь " + utils.username_parser(message) + " и "
                       + utils.username_parser(message.reply_to_message) + " будут дружно молчать в течении "
                       + utils.formatted_timer(timer_mute))


@utils.bot.message_handler(content_types=['new_chat_members'])
def whitelist_checker(message):

    if utils.bot.get_chat_member(main_chat_id,
                                 message.json.get("new_chat_participant").get("id")).status == "creator":
        utils.bot.reply_to(message, "Приветствую вас, Владыка.")
        return

    if not (sql_worker.whitelist(message.json.get("new_chat_participant").get("id"))
            or message.json.get("new_chat_participant").get("is_bot")):
        # Fuck you Durov
        for chat in allies:
            if chat.rstrip("\n") == str(message.chat.id):
                if utils.bot.get_chat_member(main_chat_id, message.from_user.id).status == "kicked":
                    utils.bot.reply_to(message, utils.username_parser(message)
                                       + " ранее был заблокирован и не может быть добавлен в вайтлист "
                                       + "по упрощённой схеме входа.")
                    return
                sql_worker.whitelist(message.from_user.id, add=True)
                utils.bot.reply_to(message, utils.username_parser(message) + " добавлен в вайтлист в союзном чате "
                                   + utils.bot.get_chat(main_chat_id).title + "!")
                utils.bot.send_message(main_chat_id, utils.username_parser(message)
                                       + " добавлен в вайтлист в союзном чате " + message.chat.title + "!")
                return
        if message.chat.id != main_chat_id:
            return
        try:
            utils.bot.ban_chat_member(main_chat_id, message.json.get("new_chat_participant").get("id"),
                                      until_date=int(time.time()) + 86400)
            utils.bot.reply_to(message, "Пользователя нет в вайтлисте, он заблокирован на 1 сутки.")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.reply_to(message, "Ошибка блокировки вошедшего пользователя. Недостаточно прав?")
    elif not message.json.get("new_chat_participant").get("is_bot") and message.chat.id == main_chat_id:
        utils.bot.reply_to(message, utils.username_parser(message) + ", добро пожаловать в " + message.chat.title
                           + ", экспериментальный уголок демократии в Telegram! Разрешено всё, "
                             "что не запрещено другими людьми - ведь здесь всё решает народ!")


@utils.bot.message_handler(commands=['allies'])
def allies_list(message):
    for chat in allies:
        if chat.rstrip("\n") == str(message.chat.id):
            utils.bot.reply_to(message, "Данный чат является союзным чатом для "
                               + utils.bot.get_chat(main_chat_id).title
                               + ", ссылка для инвайта - " + utils.bot.get_chat(main_chat_id).invite_link)
            return

    if message.chat.id != main_chat_id:
        utils.bot.reply_to(message, "Данную команду можно запустить только в основном чате или в союзных чатах.")
        return

    allies_text = ""
    for i in allies:
        try:
            invite = utils.bot.get_chat(i).invite_link
            if invite is None:
                invite = "инвайт-ссылка отсутствует"
            allies_text = allies_text + utils.bot.get_chat(i).title + " - " + invite + "\n"
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
    utils.bot.reply_to(message, "Список союзных чатов: \n" + allies_text)


@utils.bot.message_handler(commands=['whitelist'])
def whitelist(message):
    if not botname_checker(message):
        return

    who_msg = message
    if message.reply_to_message is not None:
        if message.reply_to_message.from_user.is_bot:
            utils.bot.reply_to(message, "Вайтлист не работает для ботов.")
            return
        who_msg = message.reply_to_message
    if sql_worker.whitelist(who_msg.from_user.id):
        utils.bot.reply_to(message, "Пользователь " + utils.username_parser(who_msg)
                           + " есть в вайтлисте и может спокойно входить и выходить из чата, "
                           + "если ему не выдадут перманентный бан.")
        return
    else:
        utils.bot.reply_to(message, "Пользователя " + utils.username_parser(who_msg)
                           + " нет в вайтлисте. При перезаходе в чат он будет заблокирован. "
                           + "Попасть в чат он сможет по команде /adduser.")
        return


@utils.bot.message_handler(commands=['niko'])
def niko(message):
    if not botname_checker(message):
        return

    try:
        utils.bot.send_sticker(message.chat.id,
                               random.choice(utils.bot.get_sticker_set("OneShotSolstice").stickers).file_id)
        # utils.bot.send_sticker(message.chat.id, open(os.path.join("ee", random.choice(os.listdir("ee"))), 'rb'))
        # Random file
    except (FileNotFoundError, telebot.apihelper.ApiTelegramException, IndexError):
        pass


@utils.bot.callback_query_handler(func=lambda call: call.data == "vote")
def my_vote(call_msg):
    records = sql_worker.msg_chk(message_vote=call_msg.message)
    if not records:
        sql_worker.rem_rec(call_msg.message.id)
        utils.bot.edit_message_text(call_msg.message.text + "\n\nГолосование не найдено в БД и закрыто.",
                                    main_chat_id, call_msg.message.id, parse_mode='html')
        try:
            utils.bot.unpin_chat_message(main_chat_id, call_msg.message.id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
        return

    user_ch = sql_worker.is_user_voted(call_msg.from_user.id, call_msg.message.id)
    if user_ch:
        if user_ch == "yes":
            utils.bot.answer_callback_query(callback_query_id=call_msg.id,
                                            text='Вы голосовали за вариант "да".', show_alert=True)
        elif user_ch == "no":
            utils.bot.answer_callback_query(callback_query_id=call_msg.id,
                                            text='Вы голосовали за вариант "нет".', show_alert=True)
    else:
        utils.bot.answer_callback_query(callback_query_id=call_msg.id,
                                        text='Вы не голосовали в данном опросе!', show_alert=True)


@utils.bot.callback_query_handler(func=lambda call: True)
def callback_inline(call_msg):
    global vote_abuse, wait_timer
    if call_msg.data != "yes" and call_msg.data != "no":
        return

    try:
        abuse_vote_timer = int(vote_abuse.get(str(call_msg.message.id) + "." + str(call_msg.from_user.id)))
    except TypeError:
        abuse_vote_timer = None

    if abuse_vote_timer is not None:
        if abuse_vote_timer + wait_timer > int(time.time()):
            please_wait = wait_timer - int(time.time()) + abuse_vote_timer
            utils.bot.answer_callback_query(callback_query_id=call_msg.id,
                                            text="Вы слишком часто нажимаете кнопку. Пожалуйста, подождите ещё "
                                                 + str(please_wait) + " секунд", show_alert=True)
            return
        else:
            vote_abuse.pop(str(call_msg.message.id) + "." + str(call_msg.from_user.id), None)

    records = sql_worker.msg_chk(message_vote=call_msg.message)
    if not records:
        sql_worker.rem_rec(call_msg.message.id)
        utils.bot.edit_message_text(call_msg.message.text + "\n\nГолосование не найдено в БД и закрыто.",
                                    main_chat_id, call_msg.message.id, parse_mode='html')
        try:
            utils.bot.unpin_chat_message(main_chat_id, call_msg.message.id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
        return

    if records[0][5] <= int(time.time()):
        vote_abuse.clear()
        vote_result(records[0][0], call_msg.message)
        return

    unique_id = records[0][0]
    counter_yes = records[0][3]
    counter_no = records[0][4]
    votes_need_current = records[0][7]

    user_ch = sql_worker.is_user_voted(call_msg.from_user.id, call_msg.message.id)
    if user_ch:
        if vote_mode == 1:
            if user_ch == "yes":
                option = "да"
            elif user_ch == "no":
                option = "нет"
            else:
                option = "None"
            utils.bot.answer_callback_query(callback_query_id=call_msg.id,
                                            text="Вы уже голосовали за вариант \"" + option
                                                 + "\". Смена голоса запрещена.", show_alert=True)
        elif vote_mode == 2:
            if call_msg.data != user_ch:
                if call_msg.data == "yes":
                    counter_yes = counter_yes + 1
                    counter_no = counter_no - 1
                if call_msg.data == "no":
                    counter_no = counter_no + 1
                    counter_yes = counter_yes - 1
                sql_worker.pool_update(counter_yes, counter_no, unique_id)
                sql_worker.user_vote_update(call_msg)
                vote_update(counter_yes, counter_no, call_msg.message)
            else:
                utils.bot.answer_callback_query(callback_query_id=call_msg.id,
                                                text="Вы уже голосовали за этот вариант. " +
                                                     "Отмена голоса запрещена.", show_alert=True)
        else:
            if call_msg.data != user_ch:
                if call_msg.data == "yes":
                    counter_yes = counter_yes + 1
                    counter_no = counter_no - 1
                if call_msg.data == "no":
                    counter_no = counter_no + 1
                    counter_yes = counter_yes - 1
                sql_worker.user_vote_update(call_msg)
            else:
                if call_msg.data == "yes":
                    counter_yes = counter_yes - 1
                else:
                    counter_no = counter_no - 1
                sql_worker.user_vote_remove(call_msg)
            sql_worker.pool_update(counter_yes, counter_no, unique_id)
            vote_update(counter_yes, counter_no, call_msg.message)
    else:
        if call_msg.data == "yes":
            counter_yes = counter_yes + 1
        if call_msg.data == "no":
            counter_no = counter_no + 1

        sql_worker.pool_update(counter_yes, counter_no, unique_id)
        sql_worker.user_vote_update(call_msg)
        vote_update(counter_yes, counter_no, call_msg.message)

    if counter_yes >= votes_need_current or counter_no >= votes_need_current:
        vote_abuse.clear()
        vote_result(unique_id, call_msg.message)
        return

    vote_abuse.update({str(call_msg.message.id) + "." + str(call_msg.from_user.id): int(time.time())})


utils.bot.infinity_polling()
