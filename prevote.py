import logging
import random
import threading
import time
import traceback
import zlib

import telebot
from telebot import types

import utils
from utils import data, bot, sqlWorker
from poll_engine import PreVote


class Invite(PreVote):

    def pre_return(self) -> bool:
        if not bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in \
               ("left", "kicked", "restricted"):
            bot.reply_to(self.message, "Вы уже есть в нужном вам чате.")
            return True
        self.user_id = data.bot_id

    def arg_fn(self, _):
        self.direct_fn()

    def direct_fn(self):

        if data.binary_chat_mode != 0 or sqlWorker.whitelist(self.message.from_user.id):  # 0 - mode with whitelist
            if sqlWorker.params("shield", default_return=0) > int(time.time()) and data.binary_chat_mode != 0:
                bot.reply_to(self.message, "В режиме защиты инвайт-ссылка на чат не выдаётся!")
                return

            try:
                invite_link = bot.get_chat(data.main_chat_id).invite_link
                if invite_link is None:
                    bot.reply_to(self.message, "Ошибка получения ссылки на чат. Недостаточно прав?")
                    return
                until_date = ""
                abuse_chk = sum(sqlWorker.abuse_check(self.message.from_user.id))
                if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "kicked":
                    if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).until_date == 0:
                        until_date = "Внимание! Вы бессрочно заблокированы в данном чате!\n"
                    else:
                        until_timer = utils.formatted_timer(bot.get_chat_member(data.main_chat_id,
                                                                                self.message.from_user.id).until_date
                                                            - int(time.time()))
                        until_date = "Внимание! Вы заблокированы в данном чате! " \
                                     f"До снятия ограничений осталось {until_timer}\n"
                elif abuse_chk > 0:
                    until_date = until_date + "Внимание! Вы находитесь под ограничением абуза инвайта! " \
                                              f"Вам следует подождать ещё " \
                                              f"{utils.formatted_timer(abuse_chk - int(time.time()))}, " \
                                              f"в противном случае при попытке входа в чат вы будете заблокированы."
                bot.reply_to(self.message, f"Ссылка на администрируемый мной чат:\n{invite_link}\n{until_date}")
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error when trying to issue a link to a new participant!\n{e}')
                bot.reply_to(self.message, "Ошибка получения ссылки на чат. Недостаточно прав?")
            return

        self.unique_id = str(self.message.from_user.id) + "_useradd"
        if self.is_voting_exist():
            return

        abuse_chk = sum(sqlWorker.abuse_check(self.message.from_user.id))
        if abuse_chk > 0:
            bot.reply_to(self.message, "Сработала защита от абуза инвайта! Вам следует подождать ещё "
                         + utils.formatted_timer(abuse_chk - int(time.time())))
            return

        try:
            msg_from_usr = self.message.text.split(None, 1)[1]
        except IndexError:
            msg_from_usr = "нет"

        self.vote_text = ("Тема голосования: заявка на вступление от пользователя <a href=\"tg://user?id="
                          + str(self.message.from_user.id) + "\">"
                          + utils.username_parser(self.message, True) + "</a>.\n"
                          + "Сообщение от пользователя: " + msg_from_usr + ".")
        self.vote_args = [self.message.chat.id, utils.username_parser(self.message), self.message.from_user.id]
        self.poll_maker(add_user=True, vote_type="invite")

        warn = ""
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "kicked":
            warn = "\nВнимание! Вы были заблокированы в чате ранее, поэтому вероятность инвайта минимальная!"
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "restricted":
            warn = "\nВнимание! Сейчас на вас распространяются ограничения прав в чате, выданные командой /mute!"
        bot.reply_to(self.message, "Голосование о вступлении отправлено в чат. Голосование завершится через "
                     + utils.formatted_timer(data.global_timer) + " или ранее." + warn)


class Ban(PreVote):
    vote_type = "ban"
    ban_reason = ""

    @staticmethod
    def timer_votes_init():
        return data.global_timer_ban, data.thresholds_get(True)

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение пользователя, которого требуется забанить.")
            return True

        self.reply_msg_target()

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу заблокировать анонимного администратора! "
                                       "Вы можете снять с него права командой /deop %индекс%.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True

    def arg_fn(self, arg):
        restrict_timer = utils.time_parser(utils.extract_arg(self.message.text, 1))
        if restrict_timer is None:
            self.direct_fn()
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(self.message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

        if utils.extract_arg(self.message.text, 2) is not None:
            self.ban_reason = self.message.text.split(maxsplit=2)[2]
        self.ban(restrict_timer, True, f"\nПредложенный срок блокировки: {utils.formatted_timer(restrict_timer)}", 1)

    def direct_fn(self):
        if utils.extract_arg(self.message.text, 1) is not None:
            self.ban_reason = self.message.text.split(maxsplit=1)[1]
        self.ban(0, False, "\nПредложенный срок блокировки: <b>перманентный</b>", 2)

    def ban(self, restrict_timer, kick_user, ban_timer_text, vote_type):

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "left" and kick_user:
            bot.reply_to(self.message, "Пользователя нет в чате, чтобы можно было кикнуть его.")
            return

        self.unique_id = str(self.reply_user_id) + "_userban"
        if self.is_voting_exist():
            return

        vote_theme = "блокировка пользователя"
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            vote_theme = "изменение срока блокировки пользователя"

        date_unban = ""
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            until_date = bot.get_chat_member(data.main_chat_id, self.reply_user_id).until_date
            if until_date == 0 or until_date is None:
                date_unban = "\nПользователь был ранее заблокирован перманентно"
            else:
                date_unban = "\nДо разблокировки пользователя оставалось " \
                             + utils.formatted_timer(until_date - int(time.time()))

        self.ban_reason = "" if not self.ban_reason else "\nПовод блокировки: " + self.ban_reason

        self.vote_text = f"Тема голосования: {vote_theme} {self.reply_username}" + \
                         date_unban + self.ban_reason + ban_timer_text + \
                         f"\nИнициатор голосования: {utils.username_parser(self.message, True)}."

        self.vote_args = [self.reply_user_id, self.reply_username, utils.username_parser(self.message),
                          vote_type, restrict_timer, self.ban_reason]

        self.poll_maker()


class Kick(Ban):

    def direct_fn(self):
        if utils.extract_arg(self.message.text, 1) is not None:
            self.ban_reason = self.message.text.split(maxsplit=1)[1]
        self.ban(3600, True, f"\nПредложенный срок блокировки: {utils.formatted_timer(3600)}", 1)


class Mute(PreVote):
    vote_type = "ban"
    ban_reason = ""

    @staticmethod
    def timer_votes_init():
        return data.global_timer_ban, data.thresholds_get(True)

    def pre_return(self) -> bool:

        if not utils.botname_checker(self.message) or utils.command_forbidden(self.message):
            return True

        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на имя пользователя, которого требуется замутить.")
            return True

        self.reply_msg_target()
        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу ограничить анонимного администратора! "
                                       "Вы можете снять с него права командой /deop %индекс%.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "kicked":
            bot.reply_to(self.message, "Данный пользователь уже забанен или кикнут.")
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True

    def direct_fn(self):
        if utils.extract_arg(self.message.text, 1) is not None:
            self.ban_reason = self.message.text.split(maxsplit=1)[1]
        self.mute(0, "\nПредложенный срок ограничений: перманентно")

    def arg_fn(self, arg):
        restrict_timer = utils.time_parser(utils.extract_arg(self.message.text, 1))
        if restrict_timer is None:
            self.direct_fn()
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(self.message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

        if utils.extract_arg(self.message.text, 2) is not None:
            self.ban_reason = self.message.text.split(maxsplit=2)[2]
        self.mute(restrict_timer, f"\nПредложенный срок ограничений: {utils.formatted_timer(restrict_timer)}")

    def mute(self, restrict_timer, ban_timer_text):

        self.unique_id = str(self.reply_user_id) + "_userban"
        if self.is_voting_exist():
            return

        vote_theme = "ограничение сообщений пользователя"
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            vote_theme = "изменение срока ограничения сообщений пользователя"

        date_unban = ""
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            until_date = bot.get_chat_member(data.main_chat_id, self.reply_user_id).until_date
            if until_date == 0 or until_date is None:
                date_unban = "\nПользователь был ранее заблокирован перманентно"
            else:
                date_unban = "\nДо разблокировки пользователя оставалось " \
                             + utils.formatted_timer(until_date - int(time.time()))

        self.ban_reason = "" if not self.ban_reason else "\nПовод блокировки: " + self.ban_reason

        self.vote_text = (f"Тема голосования: {vote_theme} {self.reply_username}" +
                          date_unban + self.ban_reason + ban_timer_text +
                          f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username,
                          utils.username_parser(self.message), 0, restrict_timer, self.ban_reason]
        self.poll_maker()


class Unban(PreVote):
    vote_type = "unban"

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на имя пользователя, которого требуется "
                                       "размутить, разбанить или обнулить значение абуза инвайта.")
            return True

        self.reply_msg_target()

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу разблокировать анонимного администратора!")
            return True

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return True

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status not in ("restricted", "kicked") and \
                sum(sqlWorker.abuse_check(self.reply_user_id)) == 0:
            bot.reply_to(self.message, "Данный пользователь не ограничен.")
            return True

    def direct_fn(self):
        self.unique_id = str(self.reply_user_id) + "_unban"
        if self.is_voting_exist():
            return

        self.vote_text = ("Тема голосования: снятие ограничений с пользователя " + self.reply_username +
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username, utils.username_parser(self.message)]
        self.poll_maker()


class Thresholds(PreVote):
    vote_type = "threshold"
    help_text = 'Используйте команду в формате "/threshold (число) [(пустое)|ban|min] "'

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def direct_fn(self):
        auto_thresholds_mode = "" if not data.is_thresholds_auto() else " (автоматический режим)"
        auto_thresholds_ban_mode = "" if not data.is_thresholds_auto(True) else " (автоматический режим)"
        auto_thresholds_min_mode = "" if not data.is_thresholds_auto(minimum=True) else " (автоматический режим)"
        bot.reply_to(self.message, "Текущие пороги:\nГолосов для обычного решения требуется: "
                     + str(data.thresholds_get()) + auto_thresholds_mode + "\n"
                     + "Голосов для бана требуется: " + str(data.thresholds_get(True)) + auto_thresholds_ban_mode
                     + "\n" + "Минимальный порог голосов для принятия решения: "
                     + str(data.thresholds_get(minimum=True)) + auto_thresholds_min_mode)

    def get_votes_text(self):
        if self.unique_id == "threshold_min":
            return f"{self.vote_text}\nГолосование будет закрыто через {utils.formatted_timer(self.current_timer)}, " \
                   f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}."

        return f"{self.vote_text}\nГолосование будет закрыто через {utils.formatted_timer(self.current_timer)}, " \
               f"для досрочного завершения требуется голосов за один из пунктов: {str(self.current_votes)}.\n" \
               f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."

    def arg_fn(self, arg):
        if arg != "auto":
            try:
                thr_value = int(arg)
            except (TypeError, ValueError):
                bot.reply_to(self.message, "Неверный аргумент (должно быть целое число от 2 до "
                             + str(bot.get_chat_members_count(data.main_chat_id)) + " или \"auto\").")
                return

            if thr_value > bot.get_chat_members_count(data.main_chat_id):
                bot.reply_to(self.message, "Количество голосов не может быть больше количества участников в чате.")
                return
            elif thr_value < 2 and not data.debug:
                bot.reply_to(self.message, "Минимальное количество голосов не может быть меньше 2")
                return
            elif thr_value < 1:
                bot.reply_to(self.message, "Минимальное количество голосов не может быть меньше 1")
                return
        else:
            thr_value = 0

        second_arg = utils.extract_arg(self.message.text, 2)
        if second_arg is None:
            self.main(thr_value)
        elif second_arg == "ban":
            self.ban(thr_value)
        elif second_arg == "min":
            self.min(thr_value)
        else:
            bot.reply_to(self.message, "Неизвестный второй аргумент, см. /threshold help")

    def main(self, thr_value):
        self.unique_id = "threshold"
        ban_text = " стандартных голосований "
        self.pre_vote(thr_value, False, False, ban_text=ban_text)

    def ban(self, thr_value):
        self.unique_id = "threshold_ban"
        ban_text = " бан-голосований "
        self.pre_vote(thr_value, True, False, ban_text=ban_text)

    def min(self, thr_value):
        self.unique_id = "threshold_min"
        min_text = " нижнего "
        warn = "\n<b>Внимание! Результаты голосования за минимальный порог " \
               "принимаются вне зависимости от минимального порога!" \
               "\nВремя завершения голосования за минимальный порог - 24 часа!</b>"
        if not data.debug:
            self.current_timer = 86400
        self.pre_vote(thr_value, False, True, min_text=min_text, warn=warn)

    def pre_vote(self, thr_value, _ban, _min, ban_text=" ", min_text=" ", warn=""):

        if self.is_voting_exist():
            return

        if thr_value < data.thresholds_get(minimum=True) and not _min:
            bot.reply_to(self.message, "Количество голосов не может быть меньше "
                         + str(data.thresholds_get(minimum=True)))
            return

        if thr_value == data.thresholds_get(_ban, _min):
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return

        if data.is_thresholds_auto(_ban, _min) and thr_value == 0:
            bot.reply_to(self.message, "Значения порога уже вычисляются автоматически!")
            return

        if thr_value != 0:
            self.vote_text = (f"Тема голосования: установка{min_text}порога голосов{ban_text}на значение {thr_value}"
                              f".\nИнициатор голосования: {utils.username_parser(self.message, True)}." + warn)
        else:
            self.vote_text = (f"Тема голосования: установка{min_text}порога голосов{ban_text}"
                              f"на автоматически выставляемое значение"
                              f".\nИнициатор голосования: {utils.username_parser(self.message, True)}." + warn)
        self.vote_args = [thr_value, self.unique_id]
        self.poll_maker()


class Timer(PreVote):
    help_text = "Использовать как /timer [время] [ban или без аргумента],\n" \
                "или как /timer [время|0 (без кулдауна)|off|disable] random.\n" \
                "Подробнее о парсинге времени - см. команду /help."

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message, private_dialog=True):
            return True

    def help(self):
        if self.message.chat.id != data.main_chat_id:
            bot.reply_to(self.message, "Использовать как  /timer [время|0 (без кулдауна)|off|disable] random.\n"
                                       "Подробнее о парсинге времени - см. команду /help.,", parse_mode="html")
        elif self.help_access_check():
            bot.reply_to(self.message, self.help_text, parse_mode="html")

    def direct_fn(self):
        timer_text = ""
        if self.message.chat.id == data.main_chat_id:
            timer_text = utils.formatted_timer(data.global_timer) + " для обычного голосования.\n" \
                         + utils.formatted_timer(data.global_timer_ban) + " для голосования за бан.\n"
        if sqlWorker.abuse_random(self.message.chat.id) == -1:
            timer_random_text = "Команда /random отключена."
        elif sqlWorker.abuse_random(self.message.chat.id) == 0:
            timer_random_text = "Кулдаун команды /random отключён."
        else:
            timer_random_text = utils.formatted_timer(sqlWorker.abuse_random(self.message.chat.id)) \
                                + " - кулдаун команды /random."
        bot.reply_to(self.message, "Текущие пороги таймера:\n" + timer_text + timer_random_text)

    def arg_fn(self, arg):
        if utils.extract_arg(self.message.text, 2) != "random":
            if utils.command_forbidden(self.message, text="Команду с данным аргументом невозможно "
                                                          "запустить не в основном чате."):
                return
        timer_arg = utils.time_parser(arg)
        second_arg = utils.extract_arg(self.message.text, 2)
        if second_arg is None or second_arg == "ban":
            self.main_and_ban(timer_arg, second_arg)
        elif second_arg == "random":
            self.random(timer_arg)
        else:
            bot.reply_to(self.message, "Неверный второй аргумент (должен быть ban, random или пустой).")
            return

    def main_and_ban(self, timer_arg, second_arg):
        if timer_arg is None:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 5 секунд до 1 суток).")
            return
        elif timer_arg < 5 or timer_arg > 86400:
            bot.reply_to(self.message, "Количество времени не может быть меньше 5 секунд и больше 1 суток.")
            return
        if second_arg is None:
            self.main(timer_arg)
        else:
            self.ban(timer_arg)

    def main(self, timer_arg):
        self.unique_id = "timer"
        ban_text = "таймера стандартных голосований"
        if timer_arg == data.global_timer:
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return
        self.pre_vote(timer_arg, ban_text)

    def ban(self, timer_arg):
        self.unique_id = "timer for ban votes"
        ban_text = "таймера бан-голосований"
        if timer_arg == data.global_timer_ban:
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return
        self.pre_vote(timer_arg, ban_text)

    def random(self, timer_arg):
        self.unique_id = "timer for random cooldown"
        ban_text = "кулдауна команды /random"
        if utils.extract_arg(self.message.text, 1) in ("off", "disable"):
            timer_arg = -1
        if timer_arg is None:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 0 секунд до 1 часа).")
            return
        elif timer_arg < -1 or timer_arg > 3600:
            bot.reply_to(self.message, "Количество времени не может быть меньше 0 секунд и больше 1 часа.")
            return
        elif timer_arg == sqlWorker.abuse_random(self.message.chat.id):
            bot.reply_to(self.message, "Это значение установлено сейчас!")
            return

        if self.message.chat.id != data.main_chat_id:
            user_status = bot.get_chat_member(self.message.chat.id, self.message.from_user.id).status
            if user_status not in ("creator", "administrator"):
                bot.reply_to(self.message, "Не-администратор не может использовать эту команду!")
                return
            sqlWorker.abuse_random(self.message.chat.id, timer_arg)
            if timer_arg == -1:
                bot.reply_to(self.message, "Команда /random отключена.")
            elif timer_arg == 0:
                bot.reply_to(self.message, "Кулдаун команды /random отключён.")
            else:
                bot.reply_to(self.message, "Установлен порог кулдауна команды "
                                           f"/random на значение {utils.formatted_timer(timer_arg)}")
            return

        if timer_arg == 0:
            vote_text = (f"Тема голосования: отключение кулдауна команды /random."
                         f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        elif timer_arg == -1:
            vote_text = (f"Тема голосования: отключение команды /random."
                         f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        else:
            vote_text = ""
        self.pre_vote(timer_arg, ban_text, vote_text)

    def pre_vote(self, timer_arg, ban_text, vote_text=""):
        if self.is_voting_exist():
            return
        self.vote_text = vote_text or (f"Тема голосования: смена {ban_text} на значение "
                                       + utils.formatted_timer(timer_arg) +
                                       f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_type = self.unique_id
        self.vote_args = [timer_arg, self.unique_id]
        self.poll_maker()


class Rating(PreVote):
    help_text = "Доступны аргументы top, up, down и команда без аргументов."
    vote_type = "change rate"

    def pre_return(self) -> bool:
        if not data.rate or utils.command_forbidden(self.message):
            return True

    def direct_fn(self):
        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            user_id, username, _ = utils.reply_msg_target(self.message)
            if user_id == data.ANONYMOUS_ID:
                bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
                return
        else:
            if self.message.reply_to_message.from_user.id in [data.bot_id, data.ANONYMOUS_ID]:
                bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
                return

            user_status = bot.get_chat_member(data.main_chat_id, self.message.reply_to_message.from_user.id).status

            if user_status == "kicked" or user_status == "left":
                sqlWorker.clear_rate(self.message.reply_to_message.from_user.id)
                bot.reply_to(self.message, "Этот пользователь не является участником чата.")
                return

            user_id, username, is_bot = utils.reply_msg_target(self.message.reply_to_message)
            if is_bot:
                bot.reply_to(self.message, "У ботов нет социального рейтинга!")
                return

        user_rate = sqlWorker.get_rate(user_id)
        bot.reply_to(self.message, f"Социальный рейтинг пользователя {username}: {user_rate}")
        return

    def set_args(self) -> dict:
        return {"top": self.top, "up": self.up, "down": self.down}

    def up(self):
        mode = "up"
        mode_text = "увеличение"
        self.pre_vote(mode, mode_text)

    def down(self):
        mode = "down"
        mode_text = "уменьшение"
        self.pre_vote(mode, mode_text)

    def pre_vote(self, mode, mode_text):
        if self.message.reply_to_message is None:
            bot.reply_to(self.message, "Пожалуйста, ответьте на сообщение пользователя, "
                                       "чей социальный рейтинг вы хотите изменить")
            return

        self.reply_msg_target()

        if self.reply_user_id == self.message.from_user.id:
            bot.reply_to(self.message, "Вы не можете менять свой собственный рейтинг!")
            return

        if self.reply_user_id in [data.bot_id, data.ANONYMOUS_ID]:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if self.reply_is_bot:
            bot.reply_to(self.message, "У ботов нет социального рейтинга!")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status in ("kicked", "left"):
            sqlWorker.clear_rate(self.reply_user_id)
            bot.reply_to(self.message, "Этот пользователь не является участником чата.")
            return

        self.unique_id = str(self.reply_user_id) + "_rating_" + mode
        if self.is_voting_exist():
            return

        self.vote_text = (f"Тема голосования: {mode_text} "
                          f"социального рейтинга пользователя {self.reply_username}"
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.reply_username, self.message.reply_to_message.from_user.id,
                          mode, utils.username_parser(self.message)]
        self.poll_maker()

    def top(self):
        threading.Thread(target=self.rate_top).start()

    def rate_top(self):
        rate_msg = bot.reply_to(self.message, "Сборка рейтинга, ожидайте...")
        rates = sqlWorker.get_all_rates()
        rates = sorted(rates, key=lambda rate: rate[1], reverse=True)
        rate_text = "Список пользователей по социальному рейтингу:"
        user_counter = 1

        for user_rate in rates:
            try:
                if bot.get_chat_member(data.main_chat_id, user_rate[0]).status in ["kicked", "left"]:
                    sqlWorker.clear_rate(user_rate[0])
                    continue
                username = utils.username_parser_chat_member(bot.get_chat_member(data.main_chat_id, user_rate[0]), True)
                rate_text = rate_text + f'\n{user_counter}. ' \
                                        f'<a href="tg://user?id={user_rate[0]}">{username}</a>: {str(user_rate[1])}'
                user_counter += 1
            except telebot.apihelper.ApiTelegramException:
                rates.remove(user_rate)

        if rates is None:
            bot.edit_message_text(self.message, "Ещё ни у одного пользователя нет социального рейтинга!",
                                  rate_msg.chat.id, rate_msg.id)
            return

        bot.edit_message_text(rate_text, chat_id=rate_msg.chat.id,
                              message_id=rate_msg.id, parse_mode='html')


class Whitelist(PreVote):
    vote_type = "whitelist"

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True
        if data.binary_chat_mode != 0:
            bot.reply_to(self.message, "Вайтлист в данном режиме отключён (см. команду /private).")
            return True
        if utils.extract_arg(self.message.text, 1) in ("add", "remove"):
            if utils.topic_reply_fix(self.message.reply_to_message) is not None:
                self.reply_user_id, self.reply_username, self.reply_is_bot = \
                    utils.reply_msg_target(self.message.reply_to_message)
            else:
                self.reply_user_id, self.reply_username, self.reply_is_bot = utils.reply_msg_target(self.message)

    def direct_fn(self):
        user_whitelist = sqlWorker.whitelist_get_all()
        if not user_whitelist:
            bot.reply_to(self.message, "Вайтлист данного чата пуст!")
            return

        threading.Thread(target=self.whitelist_building, args=(user_whitelist,)).start()

    def whitelist_building(self, user_whitelist):
        whitelist_msg = bot.reply_to(self.message, "Сборка вайтлиста, ожидайте...")
        user_list, counter = "Список пользователей, входящих в вайтлист:\n", 1
        for user in user_whitelist:
            try:
                username = utils.username_parser_chat_member(bot.get_chat_member(data.main_chat_id,
                                                                                 user[0]), html=True)
                if username == "":
                    sqlWorker.whitelist(user[0], remove=True)
                    continue
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error when assembling whitelist!\n{e}')
                sqlWorker.whitelist(user[0], remove=True)
                user_whitelist.remove(user)
                continue
            user_list = user_list + f'{counter}. <a href="tg://user?id={user[0]}">{username}</a>\n'
            counter = counter + 1

        if not user_whitelist:
            bot.edit_message_text("Вайтлист данного чата пуст!",
                                  chat_id=whitelist_msg.chat.id, message_id=whitelist_msg.id, parse_mode='html')
            return

        bot.edit_message_text(f"{user_list}Узнать подробную информацию о "
                              f"конкретном пользователе можно командой /status",
                              chat_id=whitelist_msg.chat.id, message_id=whitelist_msg.id, parse_mode='html')

    def set_args(self) -> dict:
        return {"add": self.add, "remove": self.remove}

    def add(self):
        is_whitelist = sqlWorker.whitelist(self.reply_user_id)
        if is_whitelist:
            bot.reply_to(self.message, f"Пользователь {self.reply_username} уже есть в вайтлисте!")
            return
        self.add_remove(f"добавление пользователя {self.reply_username} в вайтлист")

    def remove(self):
        if utils.extract_arg(self.message.text, 2) is not None:
            self.index_remove()
            return
        is_whitelist = sqlWorker.whitelist(self.reply_user_id)
        if not is_whitelist:
            bot.reply_to(self.message, f"Пользователя {self.reply_username} нет в вайтлисте!")
            return
        self.add_remove(f"удаление пользователя {self.reply_username} из вайтлиста")

    def add_remove(self, whitelist_text):
        if self.reply_user_id in [data.bot_id, data.ANONYMOUS_ID]:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return
        elif self.reply_is_bot:
            bot.reply_to(self.message, f"Вайтлист не работает для ботов!")
            return
        self.pre_vote(whitelist_text)

    def index_remove(self):
        user_whitelist = sqlWorker.whitelist_get_all()
        if not user_whitelist:
            bot.reply_to(self.message, "Вайтлист данного чата пуст!")
            return

        try:
            index = int(utils.extract_arg(self.message.text, 2)) - 1
            if index < 0:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Индекс должен быть больше нуля.")
            return

        try:
            self.reply_user_id = user_whitelist[index][0]
        except IndexError:
            bot.reply_to(self.message, "Пользователь с данным индексом не найден в вайтлисте!")
            return

        try:
            self.reply_username = utils.username_parser_chat_member(bot.get_chat_member(data.main_chat_id,
                                                                                        self.reply_user_id), html=True)
            if self.reply_username == "":
                sqlWorker.whitelist(self.reply_user_id, remove=True)
                bot.reply_to(self.message, "Удалена некорректная запись!")
                return
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error when deleting a member from the whitelist by index!\n{e}')
            sqlWorker.whitelist(self.reply_user_id, remove=True)
            bot.reply_to(self.message, "Удалена некорректная запись!")
            return

        self.pre_vote(f"удаление пользователя {self.reply_username} из вайтлиста")

    def pre_vote(self, whitelist_text):

        self.unique_id = str(self.reply_user_id) + "_whitelist"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: {whitelist_text}.\n"
                          f"Инициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username, utils.extract_arg(self.message.text, 1)]
        self.poll_maker()


class MessageRemover(PreVote):
    warn = ""
    clear = ""
    vote_type = "delete message"

    @staticmethod
    def timer_votes_init():
        return data.global_timer_ban, data.thresholds_get(True)

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение пользователя, которое требуется удалить.")
            return True

        if data.bot_id == self.message.reply_to_message.from_user.id \
                and sqlWorker.get_poll(self.message.reply_to_message.id):
            bot.reply_to(self.message, "Вы не можете удалить голосование до его завершения!")
            return True

    def direct_fn(self):
        self.unique_id = str(self.message.reply_to_message.message_id) + "_delmsg"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: удаление сообщения пользователя "
                          f"{utils.username_parser(self.message.reply_to_message, True)}"
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}." + self.warn)
        self.vote_args = [self.message.reply_to_message.message_id,
                          utils.username_parser(self.message.reply_to_message), self.silent]
        self.poll_maker(silent=self.silent)


class MessageSilentRemover(MessageRemover):
    warn = "\n\n<b>Внимание, голосования для бесследной очистки не закрепляются автоматически. Пожалуйста, " \
           "закрепите их самостоятельно при необходимости.</b>\n"
    silent = True
    clear = "бесследно "

    @staticmethod
    def timer_votes_init():
        return data.global_timer, data.thresholds_get()


class PrivateMode(PreVote):
    help_text = "Существуют три режима работы антиспам-фильтра ДейтерБота.\n" \
                "1. Использование вайтлиста и системы инвайтов. Участник, не найденный в вайтлисте или в " \
                "одном из союзных чатов, блокируется. Классическая схема, применяемая для приватных чатов.\n" \
                "2. Использование голосования при вступлении участника. При вступлении участника в чат " \
                "отправка от него сообщений ограничивается, выставляется голосование за возможность " \
                "его вступления в чат. По завершению голосования участник блокируется или ему позволяется " \
                "вступить в чат. Новая схема, созданная для публичных чатов.\n" \
                "3. Использование классической капчи при вступлении участника.\n" \
                "Если хостер бота выставил режим \"mixed\" в конфиге бота, можно сменить режим на другой " \
                "(команда /private 1/2/3), в противном случае хостер бота устанавливает режим работы " \
                "самостоятельно.\n<b>Текущие настройки чата:</b>" \
                "\nНастройки заблокированы хостером: {}" \
                "\nТекущий режим чата: {}{}"

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def direct_fn(self):
        self.help()

    def help(self):
        if not self.help_access_check():
            return
        if data.binary_chat_mode == 0:
            chat_mode = "приватный"
        elif data.binary_chat_mode == 1:
            chat_mode = "публичный (с голосованием)"
        else:
            chat_mode = "публичный (с капчёй)"

        chat_mode_locked = "да" if data.chat_mode != "mixed" else "нет"
        shield_info = ""
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            shield_info = "\n<b>Внимание! Включён режим защиты чата (подробнее - /shield)</b>\n" \
                          f"До отключения осталось {utils.formatted_timer(shield_timer - int(time.time()))}"
        bot.reply_to(self.message, self.help_text.format(chat_mode_locked, chat_mode, shield_info), parse_mode="html")

    def arg_fn(self, arg):
        if data.chat_mode != "mixed":
            bot.reply_to(self.message, "Хостер бота заблокировал возможность сменить режим работы бота.")
            return

        self.unique_id = "private mode"
        if self.is_voting_exist():
            return

        try:
            chosen_mode = int(arg)
            if not 1 <= chosen_mode <= 3:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Неверный аргумент (должно быть число от 1 до 3).")
            return

        if chosen_mode - 1 == data.binary_chat_mode:
            bot.reply_to(self.message, "Данный режим уже используется сейчас!")
            return

        chat_modes = ["", "приватный", "публичный (с голосованием)", "публичный (с капчёй)"]
        chat_mode = chat_modes[chosen_mode]

        self.vote_text = (f"Тема голосования: изменение режима приватности чата на {chat_mode}."
                          f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_type = self.unique_id
        self.vote_args = [chosen_mode - 1, utils.username_parser(self.message, True), chat_mode]
        self.poll_maker()


class Op(PreVote):
    vote_type = "op"
    help_text = "В ДейтерБоте используется система записи прав администратора в виде строки из единиц " \
                "и нулей. Для получения и выдачи нужных прав необходимо использовать запись вида " \
                "/op 001010010 и т. п. Если не использовать данную запись, будут выданы права по умолчанию " \
                "для чата.\nГлобальные права администраторов для чата можно изменить с помощью команды вида " \
                "/op global 001010010, если хостер бота не запретил это.\n<b>Попытка выдачи недоступных " \
                "боту или отключенных на уровне чата прав приведёт к ошибке!\nТекущие права для чата:</b>\n" \
                "Изменения заблокированы хостером - {}{}" \
                "\n<b>ВНИМАНИЕ: при переназначении прав пользователю его текущие права перезаписываются!</b>"

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def help(self):
        if self.help_access_check():
            bot.reply_to(self.message, self.help_text.format(data.admin_fixed, utils.allowed_list(data.admin_allowed)),
                         parse_mode="html")

    def arg_fn(self, arg):  # If the command was run with arguments
        try:
            self.args[arg]()  # Runs a function from a dictionary by default
        except KeyError:
            self.direct_fn()

    def set_args(self) -> dict:
        return {"list": self.list, "global": self.global_rules}

    def list(self):
        admin_list = bot.get_chat_administrators(data.main_chat_id)
        admin_msg = bot.reply_to(self.message, "Сборка списка администраторов, ожидайте...")
        admin_list_text = "Список текущих администраторов чата:" if admin_list else "В чате нет администраторов!"
        counter = 0
        for admin in admin_list:
            counter += 1
            admin_list_text += f"\n{counter}. "
            admin_title = f'"{admin.custom_title}"' if admin.custom_title else "отсутствует"
            if admin.is_anonymous and not admin.user.is_bot:
                admin_list_text += f'Анонимный администратор (звание {admin_title})'
            else:
                admin_list_text += utils.username_parser_chat_member(admin)
            if admin.status == "creator":
                admin_list_text += " - автор чата"
        bot.edit_message_text(admin_list_text, admin_msg.chat.id, admin_msg.id)
        return

    def global_rules(self):
        if data.admin_fixed:
            bot.reply_to(self.message, "Изменение глобальных прав администраторов для чата заблокировано хостером.")
            return

        self.unique_id = "global admin permissions"
        self.vote_type = self.unique_id
        if self.is_voting_exist():
            return

        if utils.extract_arg(self.message.text, 2) is None:
            bot.reply_to(self.message, "В сообщении не указан бинарный аргумент.")
            return

        try:
            binary_rules = int("1" + utils.extract_arg(self.message.text, 2)[::-1], 2)
            if not data.ADMIN_MIN <= binary_rules <= data.ADMIN_MAX:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Неверное значение бинарного аргумента!")
            return

        self.vote_text = (f"Тема голосования: изменение разрешённых прав для администраторов на следующие:"
                          f"{utils.allowed_list(binary_rules)}"
                          f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [binary_rules]
        self.poll_maker()

    def direct_fn(self):
        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            self.reply_user_id, self.reply_username, _ = utils.reply_msg_target(self.message)
        else:
            self.reply_user_id, self.reply_username, _ = utils.reply_msg_target(self.message.reply_to_message)

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу менять права анонимным администраторам!")
            return

        if self.reply_user_id == data.bot_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Пользователь является создателем чата.")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status in ("left", "kicked"):
            bot.reply_to(self.message, "Пользователь не состоит в чате.")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "restricted":
            bot.reply_to(self.message, "Ограниченный пользователь не может стать админом.")
            return

        if utils.extract_arg(self.message.text, 1) is not None:
            try:
                binary_rule = int("1" + utils.extract_arg(self.message.text, 1)[::-1], 2)
                if not data.ADMIN_MIN <= binary_rule <= data.ADMIN_MAX:
                    raise ValueError
            except ValueError:
                bot.reply_to(self.message, "Неверное значение бинарного аргумента!")
                return
            if not utils.is_current_perm_allowed(binary_rule, data.admin_allowed):
                bot.reply_to(self.message, "Есть правила, не разрешённые на уровне чата (см. /op help).")
                return
            chosen_rights = utils.allowed_list(binary_rule)
        else:
            binary_rule = data.admin_allowed
            chosen_rights = f" установленные в чате по умолчанию.{utils.allowed_list(binary_rule)}"

        self.unique_id = str(self.reply_user_id) + "_op"
        if self.is_voting_exist():
            return

        self.vote_text = (f"Тема голосования: выдача/изменение прав администратора пользователю "
                          f"{utils.html_fix(self.reply_username)}"
                          f"\nПрава, выбранные для выдачи пользователю:{chosen_rights}"
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}."
                          "\n<b>Звание можно будет установить ПОСЛЕ закрытия голосования.</b>")
        self.vote_args = [self.reply_user_id, self.reply_username, binary_rule]
        self.poll_maker()


class RemoveTopic(PreVote):
    vote_type = "remove topic"

    @staticmethod
    def timer_votes_init():
        return 86400, data.thresholds_get()

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

        if self.message.message_thread_id is None:
            bot.reply_to(self.message, "Данный чат НЕ является топиком или является основным топиком!")
            return True

    def direct_fn(self):
        self.unique_id = str(self.message.message_thread_id) + "_rem_topic"
        if self.is_voting_exist():
            return

        self.vote_text = ("Тема голосования: удаление данного топика"
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.message.message_thread_id, utils.username_parser(self.message),
                          self.message.reply_to_message.forum_topic_created.name]
        self.poll_maker()


class Rank(PreVote):
    vote_type = "rank"

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def direct_fn(self):
        bot.reply_to(self.message, "Звание не может быть пустым.")

    def arg_fn(self, arg):
        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            self.me()
            return
        elif self.message.reply_to_message.from_user.id == self.message.from_user.id:
            self.me()
            return

        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Ответьте на сообщение бота, звание которого вы хотите сменить.")
            return

        if self.message.reply_to_message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу менять звание анонимных администраторов!")
            return

        if not self.message.reply_to_message.from_user.is_bot:
            bot.reply_to(self.message, "Вы не можете менять звание других пользователей (кроме ботов).")
            return

        if bot.get_chat_member(data.main_chat_id, self.message.reply_to_message.from_user.id).status != "administrator":
            bot.reply_to(self.message, "Данный бот не является администратором.")
            return

        if data.bot_id == self.message.reply_to_message.from_user.id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        self.unique_id = str(self.message.reply_to_message.from_user.id) + "_rank"
        if self.is_voting_exist():
            return

        rank_text = self.message.text.split(maxsplit=1)[1]

        if len(rank_text) > 16:
            bot.reply_to(self.message, "Звание не может быть длиннее 16 символов.")
            return

        self.vote_text = ("Тема голосования: смена звания бота " +
                          utils.username_parser(self.message.reply_to_message, True) +
                          f" на \"{utils.html_fix(rank_text)}\""
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.message.reply_to_message.from_user.id,
                          utils.username_parser(self.message.reply_to_message),
                          rank_text, utils.username_parser(self.message)]

        self.poll_maker()

    def me(self):
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "administrator":

            rank_text = self.message.text.split(maxsplit=1)[1]

            if len(rank_text) > 16:
                bot.reply_to(self.message, "Звание не может быть длиннее 16 символов.")
                return

            try:
                bot.set_chat_administrator_custom_title(data.main_chat_id, self.message.from_user.id, rank_text)
                bot.reply_to(self.message, "Звание \"" + rank_text + "\" успешно установлено пользователю "
                             + utils.username_parser(self.message, True) + ".")
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    bot.reply_to(self.message, "В звании не поддерживаются эмодзи.")
                    return
                logging.error(f'Error when changing administrator title!\n{e}')
                bot.reply_to(self.message, "Не удалось сменить звание.")
            return
        elif bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "creator":
            bot.reply_to(self.message, "Я не могу изменить звание создателя чата.")
            return
        else:
            bot.reply_to(self.message, "Вы не являетесь администратором.")
            return


class Deop(PreVote):
    vote_type = "deop"

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def direct_fn(self):
        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message,
                         "Ответьте на сообщение, используйте аргумент \"me\" или номер админа из списка /op list")
            return

        if utils.topic_reply_fix(self.message.reply_to_message) is not None:
            if self.message.reply_to_message.from_user.id == self.message.from_user.id:
                self.me()
            else:
                self.reply_msg_target()
                self.pre_vote()

    def arg_fn(self, arg):
        if arg == "me":
            self.me()
        elif arg.isdigit():
            index = int(arg) - 1
            admin_list = bot.get_chat_administrators(data.main_chat_id)
            try:
                if index < 0:
                    raise IndexError
                admin = admin_list[index]
            except IndexError:
                bot.reply_to(self.message, "Админ с указанным индексом не найден")
                return
            if admin.is_anonymous and not admin.user.is_bot:
                admin_title = f'"{admin.custom_title}"' if admin.custom_title else "отсутствует"
                self.reply_username = f'ANONYMOUS (звание {admin_title})'
            else:
                self.reply_username = utils.username_parser_chat_member(admin)
            self.reply_user_id = admin.user.id
            self.pre_vote()
        else:
            bot.reply_to(self.message, "Неизвестный аргумент команды.")
            return

    def pre_vote(self):
        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, f"{self.reply_username} является создателем чата, я не могу снять его права.")
            return

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status != "administrator":
            bot.reply_to(self.message, f"{self.reply_username} не является администратором!")
            return

        if data.bot_id == self.reply_user_id:
            bot.reply_to(self.message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if self.reply_user_id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу снять права анонимного администратора таким образом! "
                                       "Для анонимов вы можете использовать команду вида /deop %индекс%. "
                                       "Список администраторов вы можете получить командой /op list.")
            return

        self.unique_id = str(self.reply_user_id) + "_deop"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: снятие прав администратора с {utils.html_fix(self.reply_username)}"
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [self.reply_user_id, self.reply_username]
        self.poll_maker()

    def me(self):
        if self.message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(self.message, "Я не могу снять права анонимного администратора таким образом! "
                                       "Для анонимов вы можете использовать команду вида /deop %индекс%. "
                                       "Список администраторов вы можете получить командой /op list.")
            return
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status == "creator":
            bot.reply_to(self.message, "Вы являетесь создателем чата, я не могу снять ваши права.")
            return
        if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status != "administrator":
            bot.reply_to(self.message, "Вы не являетесь администратором!")
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, self.message.from_user.id,
                                     None, can_send_messages=True)
            bot.restrict_chat_member(data.main_chat_id, self.message.from_user.id,
                                     None, True, True, True, True, True, True, True, True)
            bot.reply_to(self.message, "Пользователь " + utils.username_parser(self.message) +
                         " добровольно ушёл в отставку.\nСпасибо за верную службу!")
            return
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error when changing administrator rights!\n{e}')
            bot.reply_to(self.message, "Я не могу изменить ваши права!")
            return


class Title(PreVote):
    unique_id = "title"
    vote_type = unique_id

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def direct_fn(self):
        bot.reply_to(self.message, "Название чата не может быть пустым.")

    def arg_fn(self, arg):
        if len(self.message.text.split(maxsplit=1)[1]) > 255:
            bot.reply_to(self.message, "Название не должно быть длиннее 255 символов!")
            return

        if bot.get_chat(data.main_chat_id).title == self.message.text.split(maxsplit=1)[1]:
            bot.reply_to(self.message, "Название чата не может совпадать с существующим названием!")
            return

        if self.is_voting_exist():
            return

        self.vote_text = ("От пользователя " + utils.username_parser(self.message, True)
                          + " поступило предложение сменить название чата на \""
                          + utils.html_fix(self.message.text.split(maxsplit=1)[1]) + "\".")
        self.vote_args = [self.message.text.split(maxsplit=1)[1], utils.username_parser(self.message)]
        self.poll_maker()


class Description(PreVote):
    unique_id = "description"
    vote_type = unique_id
    help_text = "Для установки описания чата следует реплейнуть командой " \
                "по сообщению с текстом описания или ввести его как аргумент команды."

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def arg_fn(self, _):
        description_text = self.message.text.split(maxsplit=1)[1]
        if len(description_text) > 255:
            bot.reply_to(self.message, "Описание не должно быть длиннее 255 символов!")
            return
        self.description(description_text)

    def direct_fn(self):
        if utils.topic_reply_fix(self.message.reply_to_message) is not None:
            if self.message.reply_to_message.text is not None:
                description_text = self.message.reply_to_message.text
                if len(description_text) > 255:
                    bot.reply_to(self.message, "Описание не должно быть длиннее 255 символов!")
                    return
            else:
                bot.reply_to(self.message, "В отвеченном сообщении не обнаружен текст!")
                return
        else:
            description_text = ""
        self.description(description_text)

    def description(self, description_text):
        if bot.get_chat(data.main_chat_id).description == description_text:
            bot.reply_to(self.message, "Описание чата не может совпадать с существующим описанием!")
            return

        formatted_desc = " пустое" if description_text == "" else f":\n<code>{utils.html_fix(description_text)}</code>"
        self.vote_text = (f"Тема голосования: смена описания чата на{formatted_desc}\n"
                          f"Инициатор голосования: {utils.username_parser(self.message, True)}.")
        if self.is_voting_exist():
            return
        self.vote_args = [description_text, utils.username_parser(self.message)]
        self.poll_maker()


class Avatar(PreVote):
    unique_id = "chat picture"
    vote_type = unique_id

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

        if utils.topic_reply_fix(self.message.reply_to_message) is None:
            bot.reply_to(self.message, "Пожалуйста, используйте эту команду как ответ на фотографию, файл jpg или png.")
            return True

    def direct_fn(self):
        if self.is_voting_exist():
            return

        if self.message.reply_to_message.photo is not None:
            file_buffer = (bot.download_file
                           (bot.get_file(self.message.reply_to_message.photo[-1].file_id).file_path))
        elif self.message.reply_to_message.document is not None:
            if self.message.reply_to_message.document.mime_type not in ("image/png", "image/jpeg"):
                bot.reply_to(self.message, "Документ не является фотографией")
                return
            file_buffer = (bot.download_file(bot.get_file(self.message.reply_to_message.document.file_id).file_path))
        else:
            bot.reply_to(self.message, "В сообщении не обнаружена фотография")
            return

        try:
            tmp_img = open(data.path + 'tmp_img', 'wb')
            tmp_img.write(file_buffer)
        except Exception as e:
            logging.error((str(e)))
            logging.error(traceback.format_exc())
            bot.reply_to(self.message, "Ошибка записи изображения в файл!")
            return

        self.vote_text = ("Тема голосования: смена аватарки чата"
                          f".\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [utils.username_parser(self.message)]
        self.poll_maker()


class NewUserChecker(PreVote):
    vote_type = "captcha"
    abuse_time = [0, 0]

    def pre_return(self) -> bool:
        if data.main_chat_id == -1:  # Проверка на init mode
            return True

        if data.main_chat_id != self.message.chat.id:  # В чужих чатах не следим
            return True

        self.reply_username = utils.username_parser_invite(self.message)
        self.reply_user_id = self.message.json.get("new_chat_participant").get("id")
        self.reply_is_bot = self.message.json.get("new_chat_participant").get("is_bot")
        self.user_id = data.bot_id

        if bot.get_chat_member(data.main_chat_id, self.reply_user_id).status == "creator":
            bot.reply_to(self.message, "Приветствую вас, Владыка.")
            return True

        if sqlWorker.params("shield", default_return=0) > int(time.time()):
            if sqlWorker.whitelist(self.reply_user_id) and data.binary_chat_mode == 0:
                sqlWorker.abuse_update(self.message.from_user.id, timer=3600, force=True)
                bot.reply_to(self.message, "Данный участник есть в вайтлисте и не будет заблокирован в режиме защиты!")
            else:
                try:
                    bot.ban_chat_member(data.main_chat_id, self.reply_user_id, until_date=int(time.time() + 3600))
                    bot.delete_message(self.message.chat.id, self.message.id)
                    bot.delete_message(self.message.chat.id, self.message.id + 1)
                except telebot.apihelper.ApiTelegramException:
                    pass
            return True

        self.abuse_time = sqlWorker.abuse_check(self.reply_user_id, True)
        if sum(self.abuse_time) > int(time.time()):
            try:
                bot.ban_chat_member(data.main_chat_id, self.reply_user_id, until_date=sum(self.abuse_time))
                bot.reply_to(self.message, f"\u26a0\ufe0f <b>НЕ ХЛОПАТЬ ДВЕРЬЮ!</b> \u26a0\ufe0f\nСработала защита от "
                                           "абуза инвайта! Повторная попытка возможна через "
                                           f"{utils.formatted_timer(sum(self.abuse_time) - int(time.time()))}",
                             parse_mode="html")
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error blocking a new participant!\n{e}')
                bot.reply_to(self.message, "Ошибка блокировки вошедшего в режиме защиты пользователя!"
                                           "Информация сохранена в логах бота!")
            return True

        if self.reply_is_bot:
            if self.reply_user_id != data.bot_id:
                self.for_bots()
            return True
        if self.allies_whitelist_add():
            return True
        if data.binary_chat_mode == 0:
            self.whitelist_mode()
        elif data.binary_chat_mode == 1:
            self.vote_mode()
        else:
            self.captcha_mode()
        return True  # direct_fn() не выполняется

    def is_voting_exist(self):
        message_id = sqlWorker.get_message_id(self.unique_id)
        if message_id:
            poll = sqlWorker.get_poll(message_id)
            if poll[0][5] <= int(time.time()):
                sqlWorker.rem_rec(poll[0][0])
                return False
            else:
                bot.reply_to(self.message, "Голосование о добавлении участника уже существует.")
                return True
        return False

    def for_bots(self):
        self.unique_id = str(self.reply_user_id) + "_new_usr"
        if self.is_voting_exist():
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, self.reply_user_id, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False,
                                     until_date=int(time.time()) + 60)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new bot!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки нового бота. Недостаточно прав?")
            return

        until_time = self.abuse_time[1] * 2 if self.abuse_time[1] != 0 else 60
        self.vote_text = ("Требуется подтверждение вступления нового бота, добавленного пользователем " +
                          utils.username_parser(self.message, True) +
                          f", в противном случае он будет кикнут на {utils.formatted_timer(until_time)}")
        self.poll_maker(current_timer=60, vote_args=[self.reply_username, self.reply_user_id, "бота", until_time])

    def allies_whitelist_add(self):
        allies = sqlWorker.get_allies()
        if allies is not None:
            for i in allies:
                try:
                    usr_status = bot.get_chat_member(i[0], self.reply_user_id).status
                    if usr_status not in ["left", "kicked"]:
                        if data.binary_chat_mode == 0:
                            sqlWorker.whitelist(self.reply_user_id, add=True)
                        sqlWorker.abuse_update(self.reply_user_id, force=True, timer=3600)
                        bot.reply_to(self.message, utils.welcome_msg_get(self.reply_username, self.message))
                        return True
                except telebot.apihelper.ApiTelegramException:
                    sqlWorker.remove_ally(i[0])

    def whitelist_mode(self):
        until_date = int(time.time()) + 86400
        ban_text = "Пользователя нет в вайтлисте, он заблокирован на 1 сутки."
        if sqlWorker.whitelist(self.reply_user_id):
            sqlWorker.abuse_update(self.message.from_user.id, timer=3600, force=True)
            bot.reply_to(self.message, utils.welcome_msg_get(self.reply_username, self.message))
            return
        try:
            bot.ban_chat_member(data.main_chat_id, self.reply_user_id, until_date=until_date)
            bot.reply_to(self.message, ban_text)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки вошедшего пользователя. Недостаточно прав?")

    def vote_mode(self):
        self.unique_id = str(self.reply_user_id) + "_new_usr"
        if self.is_voting_exist():
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, self.reply_user_id, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки нового пользователя. Недостаточно прав?")
            return

        until_time = self.abuse_time[1] * 2 if self.abuse_time[1] != 0 else 300
        self.vote_text = (f"Требуется подтверждение вступления нового пользователя {self.reply_username}, "
                          f"в противном случае он будет кикнут на {utils.formatted_timer(until_time)}")
        self.poll_maker(current_timer=60,
                        vote_args=[self.reply_username, self.reply_user_id, "пользователя", until_time])

    def captcha_mode(self):
        try:
            bot.restrict_chat_member(data.main_chat_id, self.reply_user_id, can_send_messages=False,
                                     can_change_info=False, can_invite_users=False, can_pin_messages=False)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.reply_to(self.message, "Ошибка блокировки нового пользователя. Недостаточно прав?")
            return

        data_list = sqlWorker.captcha(self.message.message_id, user_id=self.message.from_user.id)
        if data_list:
            bot.reply_to(self.message, "Капча уже существует.")
            return

        button_values = [random.randint(1000, 9999) for _ in range(3)]
        max_value = max(button_values)
        buttons = [types.InlineKeyboardButton(text=str(i), callback_data=f"captcha_{i}") for i in button_values]
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(*buttons)
        until_time = self.abuse_time[1] * 2 if self.abuse_time[1] != 0 else 300
        bot_message = bot.reply_to(self.message, "\u26a0\ufe0f <b>СТОП!</b> \u26a0\ufe0f"  # Emoji
                                                 "\nВы были остановлены антиспам-системой ДейтерБота!\n"
                                                 "Для доступа в чат вам необходимо выбрать из списка МАКСИМАЛЬНОЕ "
                                                 "число в течении 60 секунд, иначе доступ в чат будет ограничен на "
                                                 f"срок {utils.formatted_timer(until_time)} Время пошло.",
                                   reply_markup=keyboard, parse_mode="html")

        sqlWorker.captcha(bot_message.id, add=True, user_id=self.reply_user_id,
                          max_value=max_value, username=self.reply_username)
        threading.Thread(target=self.captcha_mode_failed, daemon=True,
                         args=(bot_message, until_time)).start()

    @staticmethod
    def captcha_mode_failed(bot_message, until_time):
        time.sleep(60)
        data_list = sqlWorker.captcha(bot_message.message_id)
        if not data_list:
            return
        sqlWorker.captcha(bot_message.message_id, remove=True)
        sqlWorker.abuse_update(data_list[0][1], until_time)
        try:
            bot.ban_chat_member(bot_message.chat.id, data_list[0][1], until_date=int(time.time()) + until_time)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'Error blocking a new participant!\n{e}')
            bot.edit_message_text(f"Я не смог заблокировать пользователя {data_list[0][3]}! Недостаточно прав?",
                                  bot_message.chat.id, bot_message.message_id)
            return
        bot.edit_message_text(f"К сожалению, пользователь {data_list[0][3]} не смог пройти капчу и сможет войти в чат "
                              f"только через {utils.formatted_timer(until_time)}",
                              bot_message.chat.id, bot_message.message_id)


class AlliesList(PreVote):
    help_text = "Поддерживаются аргументы add, remove и запуск без аргументов."

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message, True):
            return True

        arg = utils.extract_arg(self.message.text, 1)
        if arg in ("add", "remove") and self.message.chat.id == data.main_chat_id:
            if arg == "add":
                bot.reply_to(self.message, "Команду с таким аргументом нельзя запустить в основном чате!")
                return True
            elif arg == "remove" and utils.extract_arg(self.message.text, 2) is None:
                bot.reply_to(self.message, "Команду с аргументом remove без указания "
                                           "индекса нельзя запустить в основном чате!")
                return True
        else:
            self.user_id = data.bot_id

    def set_args(self) -> dict:
        return {"add": self.add, "remove": self.remove}

    def add(self):
        if sqlWorker.get_ally(self.message.chat.id) is not None:
            bot.reply_to(self.message, "Данный чат уже входит в список союзников!")
            return

        abuse_chk = sum(sqlWorker.abuse_check(self.message.chat.id))
        if abuse_chk > 0:
            bot.reply_to(self.message, "Сработала защита от абуза добавления в союзники! Вам следует подождать ещё "
                         + utils.formatted_timer(abuse_chk - int(time.time())))
            return

        invite_link = bot.get_chat(self.message.chat.id).invite_link
        if invite_link is None:
            invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
        else:
            invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        self.vote_type = "add allies"
        self.pre_vote("установка", invite_link, "создании")

    def remove(self):
        if utils.extract_arg(self.message.text, 2) is not None and self.message.chat.id == data.main_chat_id:
            self.index_remove()
            return
        elif sqlWorker.get_ally(self.message.chat.id) is None:
            bot.reply_to(self.message, "Данный чат не входит в список союзников!")
            return
        invite_link = bot.get_chat(self.message.chat.id).invite_link
        if invite_link is None:
            invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
        else:
            invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        self.vote_type = "remove allies"
        self.pre_vote("разрыв", invite_link, "разрыве")

    def index_remove(self):
        allies = sqlWorker.get_allies()
        if not allies:
            bot.reply_to(self.message, "Список союзников данного чата пуст!")
            return

        try:
            index = int(utils.extract_arg(self.message.text, 2)) - 1
            if index < 0:
                raise ValueError
        except ValueError:
            bot.reply_to(self.message, "Индекс должен быть больше нуля.")
            return

        try:
            ally_id = allies[index]
        except IndexError:
            bot.reply_to(self.message, "Чат с данным индексом не найден в списке союзников!")
            return

        self.unique_id = f"{ally_id}_allies"
        if self.is_voting_exist():
            return
        invite_link = bot.get_chat(ally_id).invite_link
        if invite_link is None:
            invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
        else:
            invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        self.vote_text = (f"Тема голосования: разрыв союзных отношений с чатом " +
                          f"<b>{utils.html_fix(bot.get_chat(ally_id).title)}</b>{invite_link}\n" +
                          f"Инициатор голосования: {utils.username_parser(self.message, True)}.")
        self.poll_maker(vote_type="remove allies", vote_args=[ally_id, None, False])

    def pre_vote(self, vote_type_text, invite_link, mode_text):
        self.unique_id = str(self.message.chat.id) + "_allies"
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: {vote_type_text} союзных отношений с чатом " +
                          f"<b>{utils.html_fix(bot.get_chat(self.message.chat.id).title)}</b>{invite_link}\n" +
                          f"Инициатор голосования: {utils.username_parser(self.message, True)}.")
        self.poll_maker(add_user=True, vote_args=[self.message.chat.id, self.message.message_thread_id, True])

        bot.reply_to(self.message, f"Голосование о {mode_text} союза отправлено в чат "
                                   f"<b>{utils.html_fix(bot.get_chat(data.main_chat_id).title)}</b>.\nОно завершится "
                                   f"через {utils.formatted_timer(self.current_timer)} "
                                   f"или ранее в зависимости от количества голосов.",
                     parse_mode="html")
        return

    def direct_fn(self):
        if sqlWorker.get_ally(self.message.chat.id) is not None:
            if sqlWorker.params("shield", default_return=0) > int(time.time()):
                bot.reply_to(self.message, "В режиме защиты инвайт-ссылка на основной чат не выдаётся!")
            else:
                invite_link = bot.get_chat(data.main_chat_id).invite_link
                if invite_link is None:
                    invite_link = "отсутствует (недостаточно прав для выдачи?)"
                else:
                    invite_link = f"- {invite_link}"
                bot.reply_to(self.message, "Данный чат является союзным чатом для " +
                             f"{bot.get_chat(data.main_chat_id).title}.\nСсылка для вступления {invite_link}")
            return

        if utils.command_forbidden(self.message, text="Данную команду без аргументов можно "
                                                      "запустить только в основном чате или в союзных чатах."):
            return

        allies = sqlWorker.get_allies()
        if allies is None:
            bot.reply_to(self.message, "В настоящее время у вас нет союзников.")
            return
        threading.Thread(target=self.allies_building, args=(allies,)).start()

    def allies_building(self, allies):
        allies_msg = bot.reply_to(self.message, "Сборка списка союзных чатов, ожидайте...")
        allies_text = "Список союзных чатов: \n"
        ally_counter = 0
        for i in allies:
            try:
                bot.get_chat_member(i[0], data.bot_id).status
            except telebot.apihelper.ApiTelegramException:
                sqlWorker.remove_ally(i[0])
                allies.remove(i)
                continue
            try:
                invite_link = bot.get_chat(i[0]).invite_link
                ally_counter += 1
                if invite_link is not None:
                    allies_text = allies_text + \
                                  f'{ally_counter}. <a href="{invite_link}">' \
                                  f'{utils.html_fix(bot.get_chat(i[0]).title)}</a>\n'
                else:
                    allies_text = allies_text + \
                                  f"{ally_counter}. {utils.html_fix(bot.get_chat(i[0]).title)} " \
                                  f"(пригласительная ссылка отсутствует)\n"
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'Error while assembling the list of allies!\n{e}')

        if allies is None:  # Не исправлять!!!! Так надо на случай, если список полностью пуст после прохода!
            bot.edit_message_text("В настоящее время у вас нет союзников.",
                                  chat_id=allies_msg.chat.id, message_id=allies_msg.id, parse_mode='html')
        else:
            bot.edit_message_text(allies_text, disable_web_page_preview=True, parse_mode='html',
                                  chat_id=allies_msg.chat.id, message_id=allies_msg.id)

    def help_access_check(self):
        if self.message.chat.id != data.main_chat_id and self.message.chat.id == self.message.from_user.id:
            if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("left", "kicked"):
                bot.reply_to(self.message, "У вас нет прав на просмотр справки!")
                return False
        return True


class Rules(PreVote):
    unique_id = "rules"
    help_text = "Используйте аргументы add (с реплеем по сообщению с текстом правил) для добавления правил, " \
                "remove - для их удаления."

    def pre_return(self) -> bool:
        if self.message.chat.id != data.main_chat_id and self.message.chat.id != self.message.from_user.id:
            bot.reply_to(self.message, "Данную команду можно запустить только в основном чате или в ЛС без аргументов.")
            return True

        if self.message.from_user.id == self.message.chat.id:
            if bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("left", "kicked"):
                bot.reply_to(self.message, "У вас нет прав использовать эту команду.")
                return True
            if utils.extract_arg(self.message.text, 1) is not None:
                bot.reply_to(self.message, "Данную команду в ЛС можно запустить только без аргументов.")
                return True

    def direct_fn(self):
        if data.fixed_rules:
            try:
                rules_text = open(data.path + "rules.txt", encoding="utf-8").read()
            except FileNotFoundError:  # No file = no rules!
                bot.reply_to(self.message, "В чате нет правил!")
                return
            except IOError:
                logging.error(traceback.format_exc())
                bot.reply_to(self.message, "Файл rules.txt не читается!")
                return
        else:
            rules_text = sqlWorker.params("rules", default_return="")
            if rules_text == "":
                bot.reply_to(self.message, "В чате нет правил!")
                return

        try:
            bot.send_message(self.message.from_user.id, f"<b>Правила чата:</b>\n{rules_text}", parse_mode="html")
            if self.message.from_user.id != self.message.chat.id:
                bot.reply_to(self.message, "Текст правил чата отправлен в л/с.")
        except telebot.apihelper.ApiTelegramException:
            bot.reply_to(self.message,
                         "Я не смог отправить сообщение вам в л/с. Недостаточно прав или нет личного диалога?")

    def set_args(self) -> dict:
        return {"add": self.add, "remove": self.remove}

    def help(self):
        if not self.help_access_check():
            return
        if data.fixed_rules:
            bot.reply_to(self.message, "Изменение правил запрещено хостером бота.")
            return
        bot.reply_to(self.message, self.help_text, parse_mode="html")

    def add(self):
        if data.fixed_rules:
            bot.reply_to(self.message, "Изменение правил запрещено хостером бота.")
            return
        if self.message.reply_to_message is None:
            bot.reply_to(self.message, "Пожалуйста, используйте эту команду как ответ на текстовое сообщение.")
            return

        if self.message.reply_to_message.text is None:
            bot.reply_to(self.message, "В отвеченном сообщении не обнаружен текст!")
            return
        self.vote_type = "add rules"
        self.pre_vote("добавление", self.message.reply_to_message.text)

    def remove(self):
        if data.fixed_rules:
            bot.reply_to(self.message, "Изменение правил запрещено хостером бота.")
            return
        rules_text = sqlWorker.params("rules", default_return="")
        if rules_text == "":
            bot.reply_to(self.message, "В чате нет правил!")
            return
        self.vote_type = "remove rules"
        self.pre_vote("удаление", rules_text)

    def pre_vote(self, vote_type_text, rules_text):
        if self.is_voting_exist():
            return
        self.vote_text = (f"Тема голосования: {vote_type_text} правил.\nТекст правил:\n"
                          f"<b>{utils.html_fix(rules_text)}</b>"
                          f"\nИнициатор голосования: {utils.username_parser(self.message, True)}.")
        self.vote_args = [rules_text, utils.username_parser(self.message)]
        self.poll_maker()


class Shield(PreVote):
    vote_type = "shield"
    unique_id = vote_type
    help_text = 'Эта команда включает режим защиты чата - Раскрытый Зонтик. В этом режиме бот блокирует входящих ' \
                'пользователей при попытке входа из союзного чата и напрямую, а так же ботов при попытке их ' \
                'добавить. В режиме чата "приватный" войти в чат всё ещё будет возможно по вайтлисту.\n' \
                'Аргумент "force", доступный только администраторам, позволит включить режим защиты чата на срок от ' \
                '1 до 24 часов, по умолчанию на 12 часов. Аргумент "enable" и "disable" позволит голосованием ' \
                'включить (обновить таймер) и отключить режим защиты чата на срок от 1 часа до 30 дней.\n' \
                'В режиме защиты бот удаляет сообщение о входе пользователя, не оставляя следов при флуд-атаке.\n'

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message):
            return True

    def help(self):
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer < int(time.time()):
            status = "<b>Текущий статус защиты</b>: отключена."
        else:
            status = f"<b>Текущий статус защиты</b>: включена.\n<b>До отключения осталось:</b> " \
                     f"{utils.formatted_timer(shield_timer - int(time.time()))}"
        bot.reply_to(self.message, self.help_text + status, parse_mode="html")

    def direct_fn(self):
        self.help()

    def set_args(self) -> dict:
        return {"force": self.force, "enable": self.enable, "disable": self.disable}

    def force(self):
        if not bot.get_chat_member(data.main_chat_id, self.message.from_user.id).status in ("creator", "administrator"):
            bot.reply_to(self.message, "Не-администратор не может использовать эту команду!")
            return
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer > int(time.time()):
            bot.reply_to(self.message, "Защита уже включена! До отключения осталось "
                                       f"{utils.formatted_timer(shield_timer - int(time.time()))}")
            return
        timer = utils.time_parser(utils.extract_arg(self.message.text, 2))
        if timer is None:
            timer = 43200
        if not 3600 <= timer <= 86400:
            bot.reply_to(self.message, "Значение таймера защиты может быть от 1 до 24 часов!")
            return
        sqlWorker.params("shield", rewrite_value=int(time.time()) + timer)
        bot.reply_to(self.message, f"Защита чата успешно включена на {utils.formatted_timer(timer)} "
                                   "Теперь добавление новых участников временно невозможно!")

    def enable(self):
        timer = utils.time_parser(utils.extract_arg(self.message.text, 2))
        if timer is None:
            timer = 43200
        if not 3600 <= timer <= 2592000:
            bot.reply_to(self.message, "Значение таймера защиты может быть от 1 часа до 30 дней!")
            return
        self.create_vote("включение/обновление таймера", timer)

    def disable(self):
        shield_timer = sqlWorker.params("shield", default_return=0)
        if shield_timer < int(time.time()):
            bot.reply_to(self.message, "Защита чата уже отключена!")
            return
        self.create_vote("отключение", 0)

    def create_vote(self, vote_type, timer):
        if self.is_voting_exist():
            return
        timer_text = "." if timer == 0 else f" на {utils.formatted_timer(timer)}"
        self.vote_text = (f"Тема голосования: {vote_type} режима защиты чата от атак{timer_text}\n"
                          f"Инициатор голосования: {utils.username_parser(self.message, True)}.")
        self.poll_maker(vote_args=[timer, utils.username_parser(self.message, True)])


class CustomPoll(PreVote):
    vote_type = "custom poll"
    help_text = 'Используйте эту команду для создания опросов в стиле ДейтерБота.\n' \
                'Первым аргументом может быть парсимое время (подробнее см. /help).\n' \
                'Если аргумент времени не парсится, длительность опроса будет 1 сутки.\n' \
                'Если кроме аргумента времени текста больше нет, аргумент будет считаться текстом.\n' \
                'Если в конце текста идёт одна или несколько строк, начинающихся с символа "#" ' \
                'и пробела, то опрос считается кастомным, и каждая такая строка является пунктом ответа.\n' \
                'Опрос закрывается по завершении таймера или после набора голосов всех участников.'
    options_list: list

    def pre_return(self) -> bool:
        if utils.command_forbidden(self.message, True):
            return True
        self.options_list = []

    @staticmethod
    def timer_votes_init():
        """timer, votes"""
        return 86400, 0  # For custom poll, the upper threshold of votes is the sum of participants

    def direct_fn(self):
        self.help()

    def get_votes_text(self):
        return f"{self.vote_text}\nОпрос будет закрыт через {utils.formatted_timer(self.current_timer)}, " \
               f"после голосования всех участников чата или при закрытии вручную."

    def help_access_check(self):
        return True

    def arg_fn(self, arg):
        self.options_list = []
        poll_timer = utils.time_parser(arg)
        if poll_timer is None:
            poll_text = self.message.text.split(maxsplit=1)[1]
        else:
            if utils.extract_arg(self.message.text, 2) is None:
                poll_text = arg
            else:
                poll_text = self.message.text.split(maxsplit=2)[2]
                self.current_timer = poll_timer
        if not 300 <= self.current_timer <= 86400:
            bot.reply_to(self.message, "Время опроса не может быть меньше 5 минут и больше 1 суток.")
            return
        self.unique_id = f"custom_{zlib.crc32(poll_text.encode('utf-8'))}_{self.message.chat.id}"
        if self.is_voting_exist():
            return

        parsed_text = poll_text.split(sep="\n")
        poll_text = ""
        for poll_str in parsed_text:
            if not poll_str.split(maxsplit=1):
                continue
            elif poll_str.split(maxsplit=1)[0] == "#":
                try:
                    poll_point = poll_str.split(maxsplit=1)[1]
                except IndexError:
                    bot.reply_to(self.message, "Ошибка парсинга опроса! Пустой вариант в списке!")
                    return
                if poll_point in self.options_list:
                    bot.reply_to(self.message, "Ошибка парсинга опроса! Дублирующий вариант в списке!")
                    return
                elif len(poll_point) > 30:
                    bot.reply_to(self.message, "Ошибка парсинга опроса! Кнопка не вмещает более 30 символов!\n"
                                               f"(строка {poll_point})")
                    return
                self.options_list.append(poll_point)
            elif self.options_list:
                bot.reply_to(self.message, "Ошибка парсинга опроса! Варианты должны идти в конце текста!")
                return
            else:
                poll_text += poll_str + "\n"

        if len(self.options_list) > 15:
            bot.reply_to(self.message, "Ошибка парсинга опроса! Вариантов не может быть больше 15-ти!")
            return
        if poll_text == "":
            bot.reply_to(self.message, "Ошибка парсинга опроса! Отсутствует заголовок опроса!")
            return
        poll_text = poll_text[:-1]
        self.vote_text = (f"Текст опроса: <b>{utils.html_fix(poll_text)}</b>"
                          f"\nИнициатор опроса: {utils.username_parser(self.message, True)}.")
        custom_poll = True if self.options_list else False
        self.vote_args = [poll_text, int(time.time()), custom_poll]
        self.poll_maker()

    # noinspection PyTypeChecker
    # Совсем этот пучарм обурел
    # С++ хотя бы не пытается делать вид что он умнее прогера на нём (поскольку для кодинга на C++ нужны яйца)
    def get_buttons_scheme(self):
        if not self.options_list:
            button_scheme = [{"button_type": "vote", "name": i, "user_list": []} for i in ("Да", "Нет")]
        else:
            button_scheme = [{"button_type": "vote", "name": i, "user_list": []} for i in self.options_list]
            button_scheme.append({"button_type": "row_width", "row_width": 1})  # Меня вынудили.
        button_scheme.append({"button_type": "my_vote", "name": "Узнать мой голос"})
        if not self.user_id == data.ANONYMOUS_ID:
            button_scheme.append({"button_type": "close", "name": "Закрыть опрос", "user_id": self.user_id})
        return button_scheme
