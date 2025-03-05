import configparser
import hashlib
import json
import logging
import os
import pickle

from packaging import version
from telebot import types
import sys
import threading
import time
import traceback
from importlib import reload

import sql_worker

import telebot


class ConfigData:
    __ADMIN_RECOMMENDED = {"can_manage_chat": True,
                           "can_change_info": False,
                           # "can_post_messages": None,
                           # "can_edit_messages": None,
                           "can_delete_messages": False,
                           "can_invite_users": True,
                           "can_restrict_members": False,
                           "can_pin_messages": True,
                           "can_promote_members": False,
                           "is_anonymous": False,
                           "can_manage_video_chats": True,
                           # "can_manage_voice_chats": None,
                           "can_manage_topics": True,
                           "can_post_stories": True,
                           "can_edit_stories": False,
                           "can_delete_stories": False}

    __ADMIN_RUS = {"can_manage_chat": "Управление группой",
                   "can_change_info": "Изменения профиля группы",
                   # "can_post_messages": None,
                   # "can_edit_messages": None,
                   "can_delete_messages": "Удаление сообщений",
                   "can_invite_users": "Пригласительные ссылки",
                   "can_restrict_members": "Блокировка пользователей",
                   "can_pin_messages": "Закрепление сообщений",
                   "can_promote_members": "Добавление администраторов",
                   "is_anonymous": "Анонимность",
                   "can_manage_video_chats": "Управление видеочатами",
                   # "can_manage_voice_chats": None,
                   "can_manage_topics": "Управление темами",
                   "can_post_stories": "Публикация историй",
                   "can_edit_stories": "Изменение чужих историй",
                   "can_delete_stories": "Удаление чужих историй"}

    # Do not edit this section to change the parameters of the bot!
    # Equalazer is customizable via config file or chat voting!
    # It is possible to access sqlWorker.params directly for parameters that are stored in the database
    VERSION = "2.12.1"  # Current bot version
    CODENAME = "Primrose"
    MIN_VERSION = "2.10"  # The minimum version from which you can upgrade to this one without breaking the bot
    BUILD_DATE = "05.03.2025"  # Bot build date
    ANONYMOUS_ID = 1087968824  # ID value for anonymous user tg
    EASTER_LINK = "https://goo.su/wLZSEz1"  # Link for easter eggs
    global_timer = 3600  # Value in seconds of duration of votes
    global_timer_ban = 300  # Value in seconds of duration of ban-votes
    __votes_need = 0  # Required number of votes for early voting closure
    __votes_need_ban = 0  # Required number of votes for early ban-voting closure
    __votes_need_min = 2  # Minimum amount of votes for a vote to be accepted
    main_chat_id = ""  # Outside param/Bot Managed Chat ID
    debug = False  # Debug mode with special presets and lack of saving parameters in the database
    vote_mode = 3  # Sets the mode in which the voice cannot be canceled and transferred (1),
    # it cannot be canceled, but it can be transferred (2) and it can be canceled and transferred (3)
    vote_privacy = True  # When switching to False, the voting progress will be public for everyone
    wait_timer = 30  # Cooldown before being able to change or cancel voice
    kill_mode = 2  # Mode 0 - the /kill command is disabled, mode 1 - everyone can use it, mode 2 - only chat admins
    fixed_rules = False  # Outside param/If enabled, the presence and absence of rules is decided by the bot host
    rate = True  # Enables or disables the rating system
    admin_fixed = False  # Outside param/If enabled, chat participants
    # cannot change the admin rights allowed for issuance by voting
    admin_allowed = __ADMIN_RECOMMENDED  # Admin rights allowed for issuance in the chat
    path = ""  # Outside param/Path to the chat data folder
    token = ""  # Outside param/Bot token
    chat_mode = "mixed"  # Outside param
    # Private - the chat is protected with a whitelist
    # Mixed - the protection mode is changed by voting in the chat
    # Public - the chat is protected by rapid voting after the participant enters the chat
    # Captcha - chat is protected by a standard captcha
    binary_chat_mode = 0  # Chat protection mode in binary form
    bot_id = None  # Telegram bot account ID
    welcome_default = "Welcome to {1}!"  # Default chat greeting
    # Can be changed in the welcome.txt file, for example "{0}, welcome to {1}",
    # where {0} is the user's nickname, {1} is the name of the chat
    thread_id = None  # Default topic ID in Telegram chat
    SQL_INIT = {"version": VERSION,
                "votes": __votes_need,
                "votes_ban": __votes_need_ban,
                "timer": global_timer,
                "timer_ban": global_timer_ban,
                "min_vote": __votes_need_min,
                "vote_mode": vote_mode,  # Now taken from config.ini
                "wait_timer": wait_timer,  # Now taken from config.ini
                "kill_mode": kill_mode,  # Now taken from config.ini
                "rate": rate,  # It seems that this parameter is not used anywhere?
                "public_mode": binary_chat_mode,
                "allowed_admins": __ADMIN_RECOMMENDED,
                "vote_privacy": vote_privacy}
    __plugins = []

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
                self.kill_mode = int(config["Chat"]["kill-mode"])
                self.fixed_rules = self.bool_init(config["Chat"]["fixed-rules"])
                self.rate = self.bool_init(config["Chat"]["rate"])
                self.admin_fixed = self.bool_init(config["Chat"]["admin-fixed"])
                self.chat_mode = config["Chat"]["chat-mode"]
                if self.admin_fixed:
                    admin_allowed = {}
                    for name in self.__ADMIN_RECOMMENDED.keys():
                        admin_allowed.update({name: self.bool_init(config["Admin-rules"][name.replace("_", "-")])})
                    self.admin_allowed = admin_allowed
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
            self.thread_id = int(config["Chat"]["thread-id"])
        except (KeyError, TypeError, ValueError):
            pass

        if self.debug:
            self.wait_timer = 0

    def sql_worker_get(self):
        self.__votes_need = sqlWorker.params("votes")  # Обращение к глобальной переменной((((
        self.__votes_need_ban = sqlWorker.params("votes_ban")
        self.__votes_need_min = sqlWorker.params("min_vote")
        self.global_timer = sqlWorker.params("timer")
        self.global_timer_ban = sqlWorker.params("timer_ban")
        self.vote_privacy = sqlWorker.params("vote_privacy")
        # Start of backwards compatible code
        if isinstance(self.vote_privacy, str):
            if self.vote_privacy == "public":
                self.vote_privacy = False
            else:
                self.vote_privacy = True
            sqlWorker.params("vote_privacy", self.vote_privacy)
        # End of backwards compatible code
        if not self.admin_fixed:
            self.admin_allowed = sqlWorker.params("allowed_admins")
        if self.chat_mode == "mixed":
            self.binary_chat_mode = sqlWorker.params("public_mode")

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

        try:
            member_count = bot.get_chat_members_count(self.main_chat_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(e)
            member_count = 2

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
        config.set("Chat", "kill-mode", "2")
        config.set("Chat", "fixed-rules", "false")
        config.set("Chat", "rate", "true")
        config.set("Chat", "admin-fixed", "false")
        config.set("Chat", "chat-mode", "mixed")
        config.set("Chat", "thread-id", "none")
        config.add_section("Admin-rules")
        for name, value in self.__ADMIN_RECOMMENDED.items():
            config.set("Admin-rules", name.replace("_", "-"), str(value).lower())
        try:
            config.write(open(self.path + "config.ini", "w"))
            print("New config file was created successful")
        except IOError:
            print("ERR: Bot cannot write new config file and will close")
            logging.error(traceback.format_exc())
            sys.exit(1)

    @property
    def plugins(self):
        return self.__plugins

    @plugins.setter
    def plugins(self, value):
        if not isinstance(value, list):
            return
        self.__plugins = value

    @property
    def admin_rus(self):
        return self.__ADMIN_RUS


class Helper:

    __help_json: dict

    def __init__(self):
        try:
            with open("help.json", encoding='utf-8') as f:
                self.__help_json = json.load(f)
        except (IOError, json.decoder.JSONDecodeError):
            logging.error("Error reading JSON help file! Bot will be closed.")
            logging.error(traceback.format_exc())
            sys.exit(1)

    @property
    def help_json(self):
        return self.__help_json

    def get_main_list(self):
        output = "<b>Выберите категорию команд:</b>\n\n<blockquote expandable>"
        buttons_main_row = []
        buttons_main = []

        for index, category in enumerate(self.help_json['category']):
            buttons_main_row.append(types.InlineKeyboardButton(text=str(index + 1), callback_data=f"help!_cat_{index}"))
            if len(buttons_main_row) > 3:
                buttons_main.append(buttons_main_row)
                buttons_main_row = []
            output += f"<b>{index + 1} - {html_fix(category['name'])}</b>\n"
            commands_text = []
            for command in category['commands']:
                 commands_text.append(f"<code>{html_fix(command['name'])}</code>")
                 if command['aliases']:
                     commands_text.append(f"<code>{html_fix(', '.join(command['aliases']))}</code>")
            output += f'{", ".join(commands_text)}\n'
        if buttons_main_row:
            buttons_main.append(buttons_main_row)
        output += "</blockquote>"
        return output, types.InlineKeyboardMarkup(buttons_main)

    def get_category_list(self, index):
        output = ""
        try:
            category = self.help_json['category'][int(index)]
        except IndexError:
            raise IndexError("Category index not found")
        output += f"<b>{html_fix(category['name'])}</b>\n<blockquote>"
        commands_list = []
        for command in category['commands']:
            command_text = [html_fix(f"/{command['name']}")]
            if command['aliases']:
                command_text.append(f'/{html_fix("/".join(command["aliases"]))}')
            if command['args']:
                command_text.append("[" + html_fix("] [".join(command['args'])) + "]")
            if command['mark']:
                command_text.append(html_fix(f"({command['mark']})"))
            commands_list.append(f"{' '.join(command_text)} - {' '.join(command['short_desc'])}")
        output += "{}</blockquote>\n".format('\n'.join(commands_list))
        return output, types.InlineKeyboardMarkup([[types.InlineKeyboardButton(text="На главную",
                                                                               callback_data=f"help!_main")]])


data = ConfigData()
helper = Helper()
bot = telebot.TeleBot(data.token)
sqlWorker = sql_worker.SqlWorker(data.path + "database.db", data.SQL_INIT)


def init():
    data.sql_worker_get()
    try:
        data.bot_id = bot.get_me().id
    except Exception as e:
        logging.error(f"Bot was unable to get own ID and will close - {e}")
        logging.error(traceback.format_exc())
        sys.exit(1)

    threading.Thread(target=auto_clear, daemon=True).start()

    get_version = sqlWorker.params("version", default_return=data.VERSION)
    if version.parse(get_version) < version.parse(data.MIN_VERSION):
        logging.error(f"You cannot upgrade from version {get_version} because compatibility is lost! "
                      f"Minimum version to upgrade to version {data.VERSION} - {data.MIN_VERSION}")
        sys.exit(1)
    elif version.parse(get_version) < version.parse(data.VERSION):
        change_type = "повышение"
        logging.warning(f"Version {get_version} upgraded to version {data.VERSION}")
    elif version.parse(get_version) > version.parse(data.VERSION):
        logging.warning("Version downgrade detected! This can lead to unpredictable consequences for the bot!")
        logging.warning(f"Downgraded from {get_version} to {data.VERSION}")
        change_type = "понижение"
    else:
        change_type = ""
    update_text = "" if version.parse(get_version) == version.parse(data.VERSION) \
        else f"\nВнимание! Обнаружено {change_type} версии.\n" \
             f"Текущая версия: {data.VERSION}\n" \
             f"Предыдущая версия: {get_version}"

    sqlWorker.params("version", rewrite_value=data.VERSION)
    logging.info(f'###EQUALAZER {data.VERSION} "{data.CODENAME.upper()}" '
                 f'BUILD DATE {data.BUILD_DATE} LAUNCHED SUCCESSFULLY!###')

    if data.main_chat_id == -1:
        logging.warning("WARNING! BOT LAUNCHED IN INIT MODE!\n***\n"
                        "You need to add Equalazer to your chat and use the /getchat command.\n"
                        "The bot will automatically write information about the ID of this chat\n"
                        "(and topic, if necessary) to the configuration file.\n"
                        "Restart the bot and work with it as usual.\n***")
        return

    try:
        if data.debug:
            logging.warning("BOT LAUNCHED IN DEBUG MODE!\n***\n"
                            "The bot will ignore the configuration of some parameters "
                            "and will not record changes to them.\n***")
            bot.send_message(data.main_chat_id, f"Бот запущен в режиме отладки!" + update_text,
                             message_thread_id=data.thread_id)
        else:
            bot.send_message(data.main_chat_id, f"Бот перезапущен." + update_text, message_thread_id=data.thread_id)
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Bot was unable to send a launch message and will be closed! "
                      f"Possibly the wrong value for the main chat or topic?\n{e}")
        sys.exit(1)


def auto_clear():
    while True:
        records = sqlWorker.get_all_polls()
        for record in records:
            if record[5] + 600 < int(time.time()):
                sqlWorker.rem_rec(record[0])
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


def username_parser_chat_member(chat_member, html=False, need_username=True):
    if chat_member.user.username is None or need_username is False:
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
    elif message.left_chat_member is not None:
        user_id = message.left_chat_member.id
        is_bot = message.left_chat_member.is_bot
        message.from_user = message.left_chat_member  # Какие ж смешные костыли))0)))
        username = username_parser(message)
    else:
        user_id = message.from_user.id
        username = username_parser(message)
        is_bot = message.from_user.is_bot

    return user_id, username, is_bot


def time_parser(instr: str):
    if not isinstance(instr, str):
        return None
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


def make_keyboard(buttons_scheme):
    row_width = 2
    formatted_buttons = []
    for button in buttons_scheme:
        if "vote!" in button["button_type"]:
            text = f'{button["name"]} - {len(button["user_list"])}'
            formatted_buttons.append(types.InlineKeyboardButton(text=text, callback_data=button["button_type"]))
        elif button["button_type"] == "row_width":
            row_width = button["row_width"]  # Феерически убогий костыль, но мне нравится))))
        else:
            formatted_buttons.append(types.InlineKeyboardButton(
                text=button["name"], callback_data=button["button_type"]))
    keyboard = types.InlineKeyboardMarkup(row_width=row_width)
    keyboard.add(*formatted_buttons)
    return keyboard


def vote_make(text, message, buttons_scheme, add_user, direct):
    if add_user:
        vote_message = bot.send_message(data.main_chat_id, text, reply_markup=make_keyboard(
            buttons_scheme), parse_mode="html", message_thread_id=data.thread_id)
    elif direct:
        vote_message = bot.send_message(message.chat.id, text, reply_markup=make_keyboard(
            buttons_scheme), parse_mode="html", message_thread_id=message.message_thread_id)
    else:
        vote_message = bot.reply_to(message, text, reply_markup=make_keyboard(
            buttons_scheme), parse_mode="html")

    return vote_message


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


def poll_saver(unique_id, message_vote):
    try:
        poll = open(data.path + unique_id, 'wb')
        pickle.dump(message_vote, poll, protocol=4)
        poll.close()
    except (IOError, pickle.PicklingError):
        logging.error("Failed to picking a poll! You will not be able to resume the timer after restarting the bot!")
        logging.error(traceback.format_exc())


def allowed_list(locked=False):
    allowed_text = ""
    for name, value in data.admin_allowed.items():
        allowed_text += data.admin_rus[name]
        if value:
            allowed_text += " ✅\n"
        elif locked:
            allowed_text += " 🔒\n"
        else:
            allowed_text += " ❌\n"
    return allowed_text[:-1]


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
    if private_dialog and message.chat.id == message.from_user.id:
        text = text or "Данную команду невозможно запустить в личных сообщениях."
        bot.reply_to(message, text)
        return True
    elif private_dialog:
        return False
    elif message.chat.id != data.main_chat_id:
        text = text or "Данную команду можно запустить только в основном чате."
        bot.reply_to(message, text)
        return True


def get_hash(user_id, chat_instance, button_data) -> str:
    for button in button_data:
        if button["button_type"] == "user_votes":
            return user_id

    return hashlib.pbkdf2_hmac('sha256', str(user_id).encode('utf-8'),
                               chat_instance.encode('utf-8'), 100000, 16).hex()


def button_anonymous_checker(user_id, chat_id):
    try:
        for admin in bot.get_chat_administrators(chat_id):
            if admin.user.id == user_id:
                if admin.is_anonymous:
                    return True
        return False
    except telebot.apihelper.ApiTelegramException as e:
        logging.error(f"Error checking user with ID {user_id} for being an anonymous administrator.\n{e}")


def make_mailing(vote_type, message_vote_id, current_timer):
    mailing_list = sqlWorker.mailing_get_all()
    if not mailing_list:
        return
    if bot.get_chat(data.main_chat_id).username is not None:
        format_chat_id = bot.get_chat(data.main_chat_id).username
    else:
        format_chat_id = "c/" + str(data.main_chat_id)[4:]
    for subscriber_index in range(len(mailing_list)):
        subscriber = mailing_list[subscriber_index][0]
        if bot.get_chat_member(data.main_chat_id, subscriber).status in ("left", "kicked"):
            sqlWorker.mailing(subscriber, remove=True)
            logging.warning(f"The user with ID {subscriber} is no longer a member of "
                            f"the chat and has been excluded from mailing list.")
        try:
            bot.send_message(subscriber, f"<b>Было запущено новое голосование!</b>\n\nТип голосования: {vote_type}, "
                                         f"длительность: {formatted_timer(current_timer)}\n"
                                         f"Ссылка на голосование: https://t.me/{format_chat_id}/{message_vote_id}",
                             parse_mode='html')
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"Errors sending mailing to user with ID {subscriber}, "
                          f"he will be excluded from the mailing list.\n{e}")
            sqlWorker.mailing(subscriber, remove=True)
        if not subscriber_index % 10 and subscriber_index:
            time.sleep(10)  # Protection against too many requests
