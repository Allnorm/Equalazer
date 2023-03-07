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


class ConfigData:
    VERSION = "1.9.2"
    BUILD_DATE = "07.03.2023"
    ANONYMOUS_ID = 1087968824
    ADMIN_MAX = 0b1111111111
    ADMIN_MIN = 0b1000000000
    __ADMIN_RECOMMENDED = 0b1010010100
    EASTER_LINK = "https://goo.su/wLZSEz1"
    global_timer = 3600
    global_timer_ban = 300
    __votes_need = 0
    __votes_need_ban = 0
    __votes_need_min = 1
    main_chat_id = ""  # Outside param
    debug = False
    vote_mode = 3
    wait_timer = 30
    abuse_mode = 2
    secret_ballot = True  # Outside param
    rules = False
    rate = True
    admin_fixed = False  # Outside param
    admin_allowed = __ADMIN_RECOMMENDED  # Ведущий бит всегда 1, запись сделана задом наперёд
    path = ""  # Outside param
    token = ""  # Outside param
    chat_mode = "mixed"  # Outside param
    binary_chat_mode = 0
    bot_id = None
    welcome_default = "Welcome to {1}!"
    thread_id = None

    def __init__(self):

        try:
            self.path = sys.argv[1] + "/"
            if not os.path.isdir(sys.argv[1]):
                print("WARNING: working path IS NOT EXIST. Remake.")
                os.mkdir(sys.argv[1])
        except IndexError:
            pass
        except IOError:
            traceback.print_exc()
            print("ERROR: Failed to create working directory! Bot will be closed!")
            sys.exit(1)

        reload(logging)
        logging.basicConfig(
            handlers=[
                logging.FileHandler(self.path + "logging.log", 'w', 'utf-8'),
                logging.StreamHandler(sys.stdout)
            ],
            level=logging.INFO,
            format='%(asctime)s %(levelname)s: %(message)s',
            datefmt="%d-%m-%Y %H:%M:%S")

        if not os.path.isfile(self.path + "config.ini"):
            print("Config file isn't found! Trying to remake!")
            self.remake_conf()

        config = configparser.ConfigParser()
        while True:
            try:
                config.read(self.path + "config.ini")
                self.token = config["Chat"]["token"]
                self.vote_mode = int(config["Chat"]["votes-mode"])
                self.wait_timer = int(config["Chat"]["wait-timer"])
                self.abuse_mode = int(config["Chat"]["abuse-mode"])
                self.rules = self.bool_init(config["Chat"]["rules"])
                self.rate = self.bool_init(config["Chat"]["rate"])
                self.admin_fixed = self.bool_init(config["Chat"]["admin-fixed"])
                self.chat_mode = config["Chat"]["chat-mode"]
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
                    self.remake_conf()
                else:
                    sys.exit(0)

        if self.chat_mode not in ["private", "mixed", "public", "captcha"]:
            self.chat_mode = "mixed"
            logging.warning(f"Incorrect chat-mode value, reset to default (mixed)")

        if self.chat_mode == "private":
            self.binary_chat_mode = 0
        elif self.chat_mode == "public":
            self.binary_chat_mode = 1
        elif self.chat_mode == "captcha":
            self.binary_chat_mode = 2

        if config["Chat"]["chatid"] != "init":
            self.main_chat_id = int(config["Chat"]["chatid"])
        else:
            self.debug = True
            self.main_chat_id = -1

        try:
            self.debug = self.bool_init(config["Chat"]["debug"])
        except (KeyError, TypeError):
            pass

        try:
            self.secret_ballot = self.bool_init(config["Chat"]["secret-ballots"])
        except (KeyError, TypeError):
            pass

        try:
            self.thread_id = int(config["Chat"]["thread-id"])
        except (KeyError, TypeError, ValueError):
            pass

        try:
            if self.admin_fixed:
                self.admin_allowed = int("1" + config["Chat"]["admin-allowed"][::-1], 2)  # В конфиге прямая запись
            if not self.ADMIN_MIN <= self.admin_allowed <= self.ADMIN_MAX:
                raise ValueError
        except (KeyError, TypeError, ValueError):
            self.admin_allowed = self.__ADMIN_RECOMMENDED
            logging.warning(f"Incorrect admin-allowed value, reset to default ("
                            + f"{self.admin_allowed:b}"[:0:-1] + ")!")

        if self.debug:
            self.wait_timer = 0

    def sql_worker_get(self, sql_worker_):
        self.__votes_need = sql_worker_.params("votes")
        self.__votes_need_ban = sql_worker_.params("votes_ban")
        self.__votes_need_min = sql_worker_.params("min_vote")
        self.global_timer = sql_worker_.params("timer")
        self.global_timer_ban = sql_worker_.params("timer_ban")
        if not self.admin_fixed:
            self.admin_allowed = sql_worker_.params("allowed_admins")
            if not self.ADMIN_MIN <= self.admin_allowed <= self.ADMIN_MAX:
                self.admin_allowed = self.__ADMIN_RECOMMENDED
                sqlWorker.params("allowed_admins", self.admin_allowed)
                logging.warning(f"Incorrect admin-allowed value, reset to default ("
                                + f"{self.admin_allowed:b}"[:0:-1] + ")!")
        if self.chat_mode == "mixed":
            self.binary_chat_mode = sql_worker_.params("public_mode")

        if self.debug:
            self.global_timer = 20
            self.global_timer_ban = 10
            self.__votes_need = 2
            self.__votes_need_ban = 2
            self.__votes_need_min = 1

    @staticmethod
    def bool_init(var):
        if var.lower() in ("false", "0"):
            return False
        elif var.lower() in ("true", "1"):
            return True
        else:
            raise TypeError

    def auto_thresholds_get(self, ban=False, minimum=False):

        member_count = bot.get_chat_members_count(self.main_chat_id)

        if ban:
            if member_count > 15:
                return 5
            elif member_count > 5:
                return 3
            else:
                return 2
        elif minimum:
            if member_count > 30:
                min_value = 5
            elif member_count > 15:
                min_value = 3
            else:
                min_value = 2
            if self.__votes_need < min_value:
                self.__votes_need = min_value
            if self.__votes_need_ban < min_value:
                self.__votes_need_ban = min_value
            return min_value
        else:
            votes_need = member_count // 2
            if votes_need < self.__votes_need_min:
                return self.__votes_need_min
            if votes_need > 7:
                return 7
            if votes_need <= 1:
                return 2
            return votes_need

    def thresholds_get(self, ban=False, minimum=False):
        if ban:
            if self.__votes_need_ban != 0:
                return self.__votes_need_ban
            else:
                return self.auto_thresholds_get(ban)
        elif minimum:
            if self.__votes_need_min != 0:
                return self.__votes_need_min
            else:
                return self.auto_thresholds_get(False, minimum)
        else:
            if self.__votes_need != 0:
                return self.__votes_need
            else:
                return self.auto_thresholds_get()

    def is_thresholds_auto(self, ban=False, minimum=False):
        if ban:
            if not self.__votes_need_ban:
                return True
            return False
        elif minimum:
            if not self.__votes_need_min:
                return True
            return False
        else:
            if not self.__votes_need:
                return True
            return False

    def thresholds_set(self, value, ban=False, minimum=False):
        if ban:
            self.__votes_need_ban = value
            if not self.debug:
                sqlWorker.params("votes_ban", value)
        elif minimum:
            self.__votes_need_min = value
            if self.__votes_need_ban < self.thresholds_get(False, True) and self.__votes_need_ban:
                self.__votes_need_ban = value
            if self.__votes_need < self.thresholds_get(False, True) and self.__votes_need:
                self.__votes_need = value
            if not self.debug:
                sqlWorker.params("min_vote", value)
        else:
            self.__votes_need = value
            if not self.debug:
                sqlWorker.params("votes", value)

    def timer_set(self, value, ban=False):
        if ban:
            self.global_timer_ban = value
            if not self.debug:
                sqlWorker.params("timer_ban", value)
        else:
            self.global_timer = value
            if not self.debug:
                sqlWorker.params("timer", value)

    def remake_conf(self):
        token, chat_id = "", ""
        while token == "":
            token = input("Please, write your bot token: ")
        while chat_id == "":
            chat_id = input("Please, write your main chat ID: ")
        config = configparser.ConfigParser()
        config.add_section("Chat")
        config.set("Chat", "token", token)
        config.set("Chat", "chatid", chat_id)
        config.set("Chat", "votes-mode", "3")
        config.set("Chat", "wait-timer", "30")
        config.set("Chat", "abuse-mode", "2")
        config.set("Chat", "rules", "false")
        config.set("Chat", "rate", "true")
        config.set("Chat", "admin-fixed", "false")
        config.set("Chat", "chat-mode", "mixed")
        config.set("Chat", "admin-allowed", "001010010")
        config.set("Chat", "thread-id", "none")
        try:
            config.write(open(self.path + "config.ini", "w"))
            print("New config file was created successful")
        except IOError:
            print("ERR: Bot cannot write new config file and will close")
            logging.error(traceback.format_exc())
            sys.exit(1)


data = ConfigData()
bot = telebot.TeleBot(data.token)
sqlWorker = sql_worker.SqlWorker(data.path + "database.db", data.VERSION)


def init():
    data.sql_worker_get(sqlWorker)
    data.bot_id = bot.get_me().id

    threading.Thread(target=auto_clear).start()

    if data.main_chat_id == -1:
        logging.info("WARNING! STARTED IN INIT MODE!")
        return

    get_version = sqlWorker.params("version", data.VERSION)
    update_text = "" if get_version == data.VERSION else "\nВнимание! Обнаружено изменение версии.\n" \
                                                         f"Текущая версия: {data.VERSION}\n" \
                                                         f"Предыдущая версия: {get_version}"
    try:
        if data.debug:
            logging.info("LAUNCH IN DEBUG MODE! IGNORE CONFIGURE!")
            bot.send_message(data.main_chat_id, f"Бот запущен в режиме отладки!" + update_text,
                             message_thread_id=data.thread_id)
        else:
            bot.send_message(data.main_chat_id, f"Бот перезапущен." + update_text, message_thread_id=data.thread_id)
    except telebot.apihelper.ApiTelegramException:
        logging.error("I was unable to send a launch message! Possibly the wrong value for the main chat or topic?")
        logging.error(traceback.format_exc())

    logging.info(f"###DEUTERBOT {data.VERSION} BUILD DATE {data.BUILD_DATE} HAS BEEN STARTED!###")


def auto_clear():
    while True:
        records = sqlWorker.get_all_pools()
        for record in records:
            if record[5] + 600 < int(time.time()):
                sqlWorker.rem_rec(record[1], record[0])
                try:
                    os.remove(data.path + record[0])
                except IOError:
                    pass
                logging.info('Removed deprecated poll "' + record[0] + '"')
        time.sleep(3600)


def extract_arg(text, num):
    try:
        return text.split()[num]
    except (IndexError, AttributeError):
        pass


def html_fix(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def username_parser(message, html=False):
    if message.from_user.first_name == "":
        return "DELETED USER"

    if message.from_user.username == "GroupAnonymousBot":
        return "ANONYMOUS ADMIN"

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


def make_keyboard(counter_yes, counter_no, cancel=True):
    buttons = [
        types.InlineKeyboardButton(text="Да - " + str(counter_yes), callback_data="yes"),
        types.InlineKeyboardButton(text="Нет - " + str(counter_no), callback_data="no"),
        types.InlineKeyboardButton(text="Узнать мой голос", callback_data="vote")
    ]
    if cancel:
        buttons.append(types.InlineKeyboardButton(text="Отмена голосования", callback_data="cancel"))
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)
    return keyboard


def vote_make(text, message, adduser, silent, cancel=True):
    if adduser:
        vote_message = bot.send_message(data.main_chat_id, text, reply_markup=make_keyboard("0", "0", cancel=False),
                                        parse_mode="html", message_thread_id=data.thread_id)
    else:
        vote_message = bot.reply_to(message, text, reply_markup=make_keyboard("0", "0", cancel), parse_mode="html")
    if not silent:
        try:
            bot.pin_chat_message(data.main_chat_id, vote_message.message_id, disable_notification=True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

    return vote_message


def vote_update(counter_yes, counter_no, call, cancel=True):
    bot.edit_message_reply_markup(call.chat.id, message_id=call.message_id,
                                  reply_markup=make_keyboard(counter_yes, counter_no, cancel))


def is_voting_exists(records, message, unique_id):
    if not records:
        return False
    if records[0][5] <= int(time.time()):
        sqlWorker.rem_rec("", unique_id=unique_id)
        sqlWorker.rem_rec(records[0][1])
        return False
    else:
        bot.reply_to(message, "Голосование о данном вопросе уже идёт.")
        return True


def botname_checker(message, get_chat=False) -> bool:
    """Crutch to prevent the bot from responding to other bots commands"""

    if message.text is None:
        return True

    cmd_text = message.text.split()[0]

    if data.main_chat_id != -1 and get_chat:
        return False

    if data.main_chat_id == -1 and not get_chat:
        return False

    if ("@" in cmd_text and "@" + bot.get_me().username in cmd_text) or not ("@" in cmd_text):
        return True
    else:
        return False


def private_checker(message):  # Проверка на то, можно ли сохранять имя пользователя в БД SQLite в данных о голосовании
    if not data.secret_ballot:
        return username_parser(message)
    else:
        return "none"


def pool_saver(unique_id, message_vote):
    try:
        pool = open(data.path + unique_id, 'wb')
        pickle.dump(message_vote, pool, protocol=4)
        pool.close()
    except (IOError, pickle.PicklingError):
        logging.error("Failed to picking a pool! You will not be able to resume the timer after restarting the bot!")
        logging.error(traceback.format_exc())


def allowed_list(admin_int):
    rules = ["Изменение профиля группы", "Удаление сообщений", "Пригласительные ссылки", "Блокировка участников",
             "Закрепление сообщений", "Добавление администраторов", "Анонимность", "Управление видеочатами",
             "Управление темами"]
    admin_str = ""
    binary = "\nВ бинарном виде - " + f"{admin_int:b}"[:0:-1]
    for i in rules:
        allowed_rule = "разрешено" if admin_int % 2 == 1 else "запрещено"
        admin_str = admin_str + "\n" + i + " - " + allowed_rule
        admin_int = admin_int >> 1
    return admin_str + binary


def is_current_perm_allowed(local_list, global_list):
    def current_perm_counter():
        nonlocal local_list, global_list
        while local_list != 1 or global_list != 1:
            if local_list % 2 == 1 and global_list % 2 == 0:
                yield False
            else:
                yield True
            local_list, global_list = local_list >> 1, global_list >> 1

    for i in current_perm_counter():
        if not i:
            return False
    return True


def get_promote_args(promote_list):
    kwargs_list = {"can_change_info": False,
                   "can_delete_messages": False,
                   "can_invite_users": False,
                   "can_restrict_members": False,
                   "can_pin_messages": False,
                   "can_promote_members": False,
                   "is_anonymous": False,
                   "can_manage_video_chats": False,
                   "can_manage_topics": False}
    for key in kwargs_list:
        if promote_list % 2 == 1:
            kwargs_list[key] = True
        promote_list = promote_list >> 1
    return kwargs_list


def welcome_msg_get(username, message):
    try:
        file = open(data.path + "welcome.txt", 'r', encoding="utf-8")
        welcome_msg = file.read().format(username, message.chat.title)
        file.close()
    except FileNotFoundError:
        logging.warning("file \"welcome.txt\" isn't found. The standard welcome message will be used.")
        welcome_msg = data.welcome_default.format(username, message.chat.title)
    except (IOError, IndexError):
        logging.error("file \"welcome.txt\" isn't readable. The standard welcome message will be used.")
        logging.error(traceback.format_exc())
        welcome_msg = data.welcome_default.format(username, message.chat.title)
    if welcome_msg == "":
        logging.warning("file \"welcome.txt\" is empty. The standard welcome message will be used.")
        welcome_msg = data.welcome_default.format(username, message.chat.title)
    return welcome_msg


def write_init_chat(message):
    config = configparser.ConfigParser()
    try:
        config.read(data.path + "config.ini")
        config.set("Chat", "chatid", str(message.chat.id))
        if message.message_thread_id is not None:
            config.set("Chat", "thread-id", str(message.message_thread_id))
            thread_ = " и темы "
        else:
            thread_ = " "
            config.set("Chat", "thread-id", "none")
        config.write(open(data.path + "config.ini", "w"))
        bot.reply_to(message, f"ID чата{thread_}сохранён. "
                              "Теперь требуется перезапустить бота для перехода в нормальный режим.")
    except Exception as e:
        logging.error(str(e) + "\n" + traceback.format_exc())
        bot.reply_to(message, "Ошибка обновления конфига! Информация сохранена в логи бота!")


def topic_reply_fix(message):  # Опять эти конченые из тг мне насрали
    if not message:
        return
    if message.content_type == "forum_topic_created":
        return
    return message


def command_forbidden(message, private_dialog=False, text=None):
    if private_dialog:
        if message.chat.id == message.from_user.id:
            text = text or "Данную команду невозможно запустить в личных сообщениях."
            bot.reply_to(message, text)
            return True
    else:
        if message.chat.id != data.main_chat_id:
            text = text or "Данную команду можно запустить только в основном чате."
            bot.reply_to(message, text)
            return True
    return False
