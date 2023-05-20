import json
import logging
import os
import pickle
import threading
import time
import traceback

import telebot

import utils
from utils import sqlWorker, data, bot


class PoolEngine:
    vote_abuse = {}

    post_vote_list = {}

    def auto_restart_polls(self):
        time_now = int(time.time())
        records = sqlWorker.get_all_polls()
        for record in records:
            try:
                poll = open(data.path + record[0], 'rb')
                message_vote = pickle.load(poll)
                poll.close()
            except (IOError, pickle.UnpicklingError):
                logging.error(f"Failed to read a poll {record[0]}!")
                logging.error(traceback.format_exc())
                continue
            if record[5] > time_now:
                threading.Thread(target=self.vote_timer,
                                 args=(record[5] - time_now, record[0], message_vote)).start()
                logging.info("Restarted poll " + record[0])
            else:
                self.vote_result(record[0], message_vote)

    def vote_timer(self, current_timer, unique_id, message_vote):
        time.sleep(current_timer)
        self.vote_abuse.clear()
        self.vote_result(unique_id, message_vote)

    def vote_result(self, unique_id, message_vote):

        records = sqlWorker.msg_chk(unique_id=unique_id)
        if not records:
            return

        if records[0][1] != message_vote.id:
            return

        try:
            os.remove(data.path + unique_id)
        except IOError:
            logging.error("Failed to clear a poll file!")
            logging.error(traceback.format_exc())

        sqlWorker.rem_rec(message_vote.id, unique_id)

        try:
            self.post_vote_list[records[0][2]].post_vote(records, message_vote)
        except KeyError:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка применения результатов голосования. Итоговая функция не найдена!",
                                  message_vote.chat.id, message_vote.id)


pool_engine = PoolEngine()


class PreVote:
    args = {}  # Dictionary of possible command arguments
    vote_text = ""
    user_id = ""
    add_user = False
    silent = False
    unique_id = ""
    vote_type = ""
    vote_args = []
    help_text = "У этой команды нет справки!"
    reply_user_id = ""
    reply_username = ""
    reply_is_bot = False

    def __init__(self, message):
        if not utils.botname_checker(message):
            return
        self.message = message
        self.user_id = message.from_user.id
        if utils.extract_arg(message.text, 1) == "help":
            self.help()
            return
        self.current_timer, self.current_votes = self.timer_votes_init()
        if self.pre_return():
            return
        self.args = self.set_args()
        arg = utils.extract_arg(message.text, 1)
        if arg is None:
            self.direct_fn()
        else:
            self.arg_fn(arg)

    def set_args(self) -> dict:
        """return dictionary of class functions"""
        return {}

    def pre_return(self) -> bool:
        """Checking for conditions that will cause the command to be canceled prematurely"""
        return False

    @staticmethod
    def timer_votes_init():
        """timer, votes"""
        return data.global_timer, data.thresholds_get()

    def direct_fn(self):  # If the command was run without arguments
        bot.reply_to(self.message, "Эту команду нельзя запустить без аргументов!")

    def arg_fn(self, arg):  # If the command was run with arguments
        if self.args:
            try:
                self.args[arg]()  # Runs a function from a dictionary by default
            except KeyError:
                bot.reply_to(self.message, "Данного аргумента команды не существует!")
        else:
            bot.reply_to(self.message, "У этой команды нет аргументов!")

    def help(self):
        bot.reply_to(self.message, self.help_text, parse_mode="html")

    def is_voting_exist(self):
        records = sqlWorker.msg_chk(unique_id=self.unique_id)
        if utils.is_voting_exists(records, self.message, self.unique_id):
            return True
        return False

    def get_votes_text(self):
        return f"{self.vote_text}\nГолосование будет закрыто через {utils.formatted_timer(self.current_timer)}, " \
               f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}.\n" \
               f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."

    def poll_maker(self, vote_args: list = None, unique_id: str = "", vote_text: str = "", vote_type: str = "",
                   current_timer: int = None, current_votes: int = None,
                   user_id: int = None, add_user=False, silent=False):
        self.vote_args = self.vote_args or vote_args
        self.unique_id = self.unique_id or unique_id
        self.vote_text = self.vote_text or vote_text
        self.vote_type = self.vote_type or vote_type
        self.current_timer = self.current_timer or current_timer
        self.current_votes = self.current_votes or current_votes
        self.user_id = self.user_id or user_id
        self.add_user = add_user
        self.silent = silent
        self.__poll_constructor()

    def __poll_constructor(self):
        vote_text = self.get_votes_text()
        cancel = False if data.bot_id == self.user_id or self.user_id == data.ANONYMOUS_ID else True
        message_vote = utils.vote_make(vote_text, self.message, self.add_user, self.silent, cancel)
        sqlWorker.add_poll(self.unique_id, message_vote, self.vote_type, int(time.time()) + self.current_timer,
                           json.dumps(self.vote_args), self.current_votes, self.user_id)
        utils.poll_saver(self.unique_id, message_vote)
        threading.Thread(target=pool_engine.vote_timer, args=(self.current_timer, self.unique_id, message_vote)).start()

    def reply_msg_target(self):
        self.reply_user_id, self.reply_username, self.reply_is_bot = \
            utils.reply_msg_target(self.message.reply_to_message)


class PostVote:
    class SilentException(Exception):
        pass

    accept_text = ""
    decline_text = ""
    _description = ""  # Описание голосования
    votes_counter = ""
    is_accept = False
    records = []
    data_list = []
    message_vote = None

    def post_vote(self, records, message_vote):
        self.data_list = json.loads(records[0][6])
        self.message_vote = message_vote
        self.votes_counter = "\nЗа: " + str(records[0][3]) + "\n" + "Против: " + str(records[0][4])
        if records[0][3] > records[0][4] and records[0][3] + records[0][4] >= data.thresholds_get(minimum=True):
            self.is_accept = True
        elif records[0][3] + records[0][4] >= data.thresholds_get(minimum=True):
            self.is_accept = False
        else:
            self.is_accept = False
            self.votes_counter = f"\nНедостаточно голосов (требуется как минимум {data.thresholds_get(minimum=True)})"
        self.records = records
        self.post_vote_child()
        try:
            if self.is_accept:
                self.accept()
            else:
                self.decline()
        except Exception as e:
            logging.error(str(e) + "\n" + traceback.format_exc())
        self.final_hook()

    def post_vote_child(self):
        return

    def accept(self):
        return

    def decline(self):
        return

    def final_hook(self):
        try:
            bot.unpin_chat_message(self.message_vote.chat.id, self.message_vote.message_id)
        except telebot.apihelper.ApiTelegramException:
            pass
        try:
            bot.reply_to(self.message_vote, "Голосование завершено!")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

    @property
    def description(self):
        return self._description

    def change_rate(self, change):
        if all([not bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).user.is_bot,
                not bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).status == "restricted",
                data.rate]):
            sqlWorker.update_rate(self.data_list[0], change)
            return True
        return False
