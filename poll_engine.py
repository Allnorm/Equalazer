import json
import logging
import os
import pickle
import threading
import time
import traceback
from typing import Optional

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
                threading.Thread(target=self.vote_timer, daemon=True,
                                 args=(record[5] - time_now, record[0], message_vote)).start()
                logging.info("Restarted poll " + record[0])
            else:
                self.vote_result(record[0], message_vote)

    def vote_timer(self, current_timer, unique_id, message_vote):
        time.sleep(current_timer)
        self.vote_abuse.clear()
        self.vote_result(unique_id, message_vote)

    def vote_result(self, unique_id, message_vote):

        records = sqlWorker.get_poll(message_vote.id)
        if not records:
            return

        if records[0][1] != message_vote.id:
            return

        try:
            os.remove(data.path + unique_id)
        except IOError:
            logging.error("Failed to clear a poll file!")
            logging.error(traceback.format_exc())

        sqlWorker.rem_rec(unique_id)

        try:
            self.post_vote_list[records[0][2]].post_vote(records, message_vote)
        except KeyError:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка применения результатов голосования. Итоговая функция не найдена!",
                                  message_vote.chat.id, message_vote.id)

    def get_abuse_timer(self, call_msg):
        try:
            abuse_vote_timer = int(self.vote_abuse.get(str(call_msg.message.id) + "." + str(call_msg.from_user.id)))
        except TypeError:
            abuse_vote_timer = None

        if abuse_vote_timer is not None:
            if abuse_vote_timer + data.wait_timer > int(time.time()):
                please_wait = data.wait_timer - int(time.time()) + abuse_vote_timer
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text="Вы слишком часто нажимаете кнопку. Пожалуйста, подождите ещё " +
                                               f"{please_wait}с.", show_alert=True)
                return True
            else:
                self.vote_abuse.pop(str(call_msg.message.id) + "." + str(call_msg.from_user.id), None)
                return False


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
    direct = False
    msg_txt = ""

    def __init__(self, message):
        if not utils.botname_checker(message):
            return
        self.message = message
        self.user_id = message.from_user.id
        self.msg_txt = message.text
        self.privacy = data.vote_privacy
        if utils.extract_arg(self.msg_txt, 1) == "help":
            self.help()
            return
        elif utils.extract_arg(self.msg_txt, 1) == "-pr":
            self.privacy = not self.privacy
            self.msg_txt = self.msg_txt.replace(" -pr", "", 1)
        self.current_timer, self.current_votes = self.timer_votes_init()
        if self.pre_return():
            return
        self.args = self.set_args()
        arg = utils.extract_arg(self.msg_txt, 1)
        if arg is None:
            self.direct_fn()
        else:
            self.arg_fn(arg)

    def set_args(self) -> dict:
        """return dictionary of class functions"""
        return {}

    def pre_return(self) -> Optional[bool]:
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
        if self.help_access_check():
            bot.reply_to(self.message, self.help_text, parse_mode="html")

    def help_access_check(self):
        if self.message.chat.id != data.main_chat_id:
            if self.message.chat.id == self.message.from_user.id:
                if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("left", "kicked"):
                    bot.reply_to(self.message, "У вас нет прав на просмотр справки!")
                    return False
            else:
                bot.reply_to(self.message, "У вас нет прав на просмотр справки!")
                return False
        return True

    def is_voting_exist(self):
        message_id = sqlWorker.get_message_id(self.unique_id)
        if message_id:
            poll = sqlWorker.get_poll(message_id)
            if poll[0][5] <= int(time.time()):
                sqlWorker.rem_rec(poll[0][0])
                return False
            else:
                bot.reply_to(self.message, "Голосование о данном вопросе уже идёт.")
                return True
        return False

    def get_votes_text(self):
        return f"{self.vote_text}\nГолосование будет закрыто через {utils.formatted_timer(self.current_timer)}, " \
               f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}.\n" \
               f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."

    def poll_maker(self, vote_args: list = None, unique_id: str = None, vote_text: str = None, vote_type: str = None,
                   current_timer: int = None, current_votes: int = None,
                   user_id: int = None, add_user=False, silent=False, direct=False):
        self.vote_args = vote_args or self.vote_args
        self.unique_id = unique_id or self.unique_id
        self.vote_text = vote_text or self.vote_text
        self.vote_type = vote_type or self.vote_type
        self.current_timer = current_timer or self.current_timer
        self.current_votes = current_votes or self.current_votes
        self.user_id = user_id or self.user_id
        self.add_user = add_user
        self.silent = silent
        self.direct = direct
        self.__poll_constructor()

    def __poll_constructor(self):
        vote_text = self.get_votes_text()
        buttons_scheme = self.get_buttons_scheme()
        message_vote = utils.vote_make(vote_text, self.message, buttons_scheme,
                                       self.add_user, self.direct)
        sqlWorker.add_poll(self.unique_id, message_vote.id, self.vote_type, self.message.chat.id,
                           json.dumps(buttons_scheme), int(time.time()) + self.current_timer,
                           json.dumps(self.vote_args), self.current_votes)
        utils.poll_saver(self.unique_id, message_vote)
        if not self.silent:
            threading.Thread(target=utils.make_mailing, daemon=True,
                             args=(pool_engine.post_vote_list[self.vote_type].description, message_vote.id,
                                   self.current_timer)).start()
            try:
                bot.pin_chat_message(message_vote.chat.id, message_vote.message_id, disable_notification=True)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f"I can't pin message in chat {message_vote.chat.id}!\n{e}")
        threading.Thread(target=pool_engine.vote_timer, daemon=True,
                         args=(self.current_timer, self.unique_id, message_vote)).start()

    def get_buttons_scheme(self):
        button_scheme = [{"button_type": f"vote!_{i}", "name": i, "user_list": []} for i in ("Да", "Нет")]
        if self.privacy:
            button_scheme.append({"button_type": "my_vote",
                                  "name": "Узнать мой голос"})
        else:
            button_scheme.append({"button_type": "user_votes",
                                  "name": "Список голосов"})
        if not (data.bot_id == self.user_id or self.user_id == data.ANONYMOUS_ID):
            button_scheme.append({"button_type": "cancel",
                                  "name": "Отмена голосования",
                                  "user_id": self.user_id})
        return button_scheme

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
        button_data = json.loads(records[0][4])
        counters_yes = 0
        counters_yes_text = counters_yes
        counters_no = 0
        counters_no_text = counters_no
        votes_private = True
        for button in button_data:
            if button["button_type"] == "user_votes":
                votes_private = False
        for button in button_data:
            if 'vote!' in button["button_type"]:
                if button["name"] == "Да":
                    counters_yes = len(button["user_list"])
                    if votes_private:
                        counters_yes_text = counters_yes
                    else:
                        counters_yes_text = self.get_voted_usernames(button["user_list"])
                elif button["name"] == "Нет":
                    counters_no = len(button["user_list"])
                    if votes_private:
                        counters_no_text = counters_no
                    else:
                        counters_no_text = self.get_voted_usernames(button["user_list"])
        self.votes_counter = f"\nЗа: {counters_yes_text}\nПротив: {counters_no_text}"
        if counters_yes > counters_no and counters_yes + counters_no >= data.thresholds_get(minimum=True):
            self.is_accept = True
        elif counters_yes + counters_no >= data.thresholds_get(minimum=True):
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
            self.final_hook(False)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error in poll {records[0][0]} with type "{records[0][2]}", '
                          f'chat ID {records[0][3]} and message ID {records[0][1]}\n{e}')
            self.final_hook(True)
        except Exception as e:
            logging.error(f'Unknown error in poll "{records[0][0]}" with type "{records[0][2]}", '
                          f'chat ID "{records[0][3]}" and message ID "{records[0][1]}"\n{e}')
            logging.error(traceback.format_exc())
            self.final_hook(True)

    def get_voted_usernames(self, user_list):
        usernames = ""
        for user_id in user_list:
            try:
                username = utils.username_parser_chat_member(
                    bot.get_chat_member(self.message_vote.chat.id, user_id), html=True)
                if username == "":
                    continue
                usernames += f"{username}, "
            except telebot.apihelper.ApiTelegramException:
                continue
        return "нет голосов" if usernames == "" else f'{usernames[:-2]}.'

    def post_vote_child(self):
        return

    def accept(self):
        return

    def decline(self):
        return

    def final_hook(self, error=False):
        try:
            bot.unpin_chat_message(self.message_vote.chat.id, self.message_vote.message_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"I can't unpin message in chat {self.message_vote.chat.id}!\n{e}")
        try:
            if error:
                bot.reply_to(self.message_vote, "Голосование завершено с ошибками. Информация сохранена в логи бота.")
            else:
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
