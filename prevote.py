import json
import logging
import os
import random
import threading
import time
import traceback

import telebot
from telebot import types

import postvote
import utils

post_vote_list = {
    "invite": postvote.UserAdd(),
    "ban": postvote.Ban(),
    "unban": postvote.UnBan(),
    "threshold": postvote.Threshold(),
    "timer": postvote.Timer(),
    "timer for ban votes": postvote.TimerBan(),
    "delete message": postvote.DelMessage(),
    "op": postvote.Op(),
    "deop": postvote.Deop(),
    "title": postvote.Title(),
    "chat picture": postvote.ChatPic(),
    "description": postvote.Description(),
    "rank": postvote.Rank(),
    "captcha": postvote.Captcha(),
    "change rate": postvote.ChangeRate(),
    "add allies": postvote.AddAllies(),
    "remove allies": postvote.RemoveAllies(),
    "timer for random cooldown": postvote.RandomCooldown(),
    "whitelist": postvote.Whitelist(),
    "global admin permissons": postvote.GlobalOp(),
    "private mode": postvote.PrivateMode(),
    "remove topic": postvote.Topic()
}

sqlWorker = utils.sqlWorker
data = utils.data
bot = utils.bot

vote_abuse = {}


def pool_constructor(unique_id: str, vote_text: str, message, vote_type: str, current_timer: int, current_votes: int,
                     vote_args: list, user_id: int, adduser=False, silent=False):
    vote_text = f"{vote_text}\nГолосование будет закрыто через {utils.formatted_timer(current_timer)}, " \
                f"для досрочного завершения требуется голосов за один из пунктов: {str(current_votes)}.\n" \
                f"Минимальный порог голосов для принятия решения: {data.thresholds_get(minimum=True)}."
    cancel = False if data.bot_id == user_id or user_id == data.ANONYMOUS_ID else True
    message_vote = utils.vote_make(vote_text, message, adduser, silent, cancel)
    sqlWorker.add_pool(unique_id, message_vote, vote_type, int(time.time()) + current_timer,
                       json.dumps(vote_args), current_votes, user_id)
    utils.pool_saver(unique_id, message_vote)
    threading.Thread(target=vote_timer, args=(current_timer, unique_id, message_vote)).start()


def vote_timer(current_timer, unique_id, message_vote):
    time.sleep(current_timer)
    vote_abuse.clear()
    vote_result(unique_id, message_vote)


def vote_result(unique_id, message_vote):
    global post_vote_list
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if not records:
        return

    if records[0][1] != message_vote.id:
        return

    try:
        os.remove(data.path + unique_id)
    except IOError:
        logging.error("Failed to clear a pool file!")
        logging.error(traceback.format_exc())

    sqlWorker.rem_rec(message_vote.id, unique_id)

    try:
        post_vote_list[records[0][2]].post_vote(records, message_vote)
    except KeyError:
        logging.error(traceback.format_exc())
        bot.edit_message_text("Ошибка применения результатов голосования. Итоговая функция не найдена!",
                              message_vote.chat.id, message_vote.id)


def invite(message):
    if not utils.botname_checker(message):
        return

    if not bot.get_chat_member(data.main_chat_id, message.from_user.id).status in ("left", "kicked", "restricted"):
        bot.reply_to(message, "Вы уже есть в нужном вам чате.")
        return

    if data.binary_chat_mode != 0:
        try:
            invite_link = bot.get_chat(data.main_chat_id).invite_link
            if invite_link is None:
                raise telebot.apihelper.ApiTelegramException
            bot.reply_to(message, f"Ссылка на администрируемый мной чат:\n" + invite_link)
        except telebot.apihelper.ApiTelegramException:
            bot.reply_to(message, "Ошибка получения ссылки на чат. Недостаточно прав?")
        return

    unique_id = str(message.from_user.id) + "_useradd"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    abuse_chk = sqlWorker.abuse_check(message.from_user.id)
    if abuse_chk > 0:
        bot.reply_to(message, "Сработала защита от абуза инвайта! Вам следует подождать ещё "
                     + utils.formatted_timer(abuse_chk - int(time.time())))
        return

    if sqlWorker.whitelist(message.from_user.id):
        sqlWorker.abuse_remove(message.from_user.id)
        sqlWorker.abuse_update(message.from_user.id)
        invite_link = bot.create_chat_invite_link(data.main_chat_id, expire_date=int(time.time()) + 86400)
        bot.reply_to(message, f"Вы получили личную ссылку для вступления в чат, так как находитесь в вайтлисте.\n"
                              "Ссылка истечёт через 1 сутки.\n" + invite_link.invite_link)
        return

    try:
        msg_from_usr = message.text.split(None, 1)[1]
    except IndexError:
        msg_from_usr = "нет"

    vote_text = ("Тема голосования: заявка на вступление от пользователя <a href=\"tg://user?id="
                 + str(message.from_user.id) + "\">" + utils.username_parser(message, True) + "</a>.\n"
                 + "Сообщение от пользователя: " + msg_from_usr + ".")

    # vote_text = ("Пользователь " + "[" + utils.username_parser(message)
    # + "](tg://user?id=" + str(message.from_user.id) + ")" + " хочет в чат.\n"
    # + "Сообщение от пользователя: " + msg_from_usr + ".")

    pool_constructor(unique_id, vote_text, message, "invite", data.global_timer, data.thresholds_get(),
                     [message.chat.id, utils.username_parser(message), message.from_user.id], data.bot_id, adduser=True)

    warn = ""
    if bot.get_chat_member(data.main_chat_id, message.from_user.id).status == "kicked":
        warn = "\nВнимание! Вы были заблокированы в чате ранее, поэтому вероятность инвайта минимальная!"
    if bot.get_chat_member(data.main_chat_id, message.from_user.id).status == "restricted":
        warn = "\nВнимание! Сейчас на вас распространяются ограничения прав в чате, выданные командой /mute!"
    bot.reply_to(message, "Голосование о вступлении отправлено в чат. Голосование завершится через "
                 + utils.formatted_timer(data.global_timer) + " или ранее." + warn)


def ban(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Ответьте на сообщение пользователя, которого требуется забанить.")
        return

    user_id, username, _ = utils.reply_msg_target(message.reply_to_message)

    if user_id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Я не могу заблокировать анонимного администратора! "
                              "Вы можете снять с него права командой /deop %индекс%.")
        return

    restrict_timer = 0
    if utils.extract_arg(message.text, 1) is not None:
        restrict_timer = utils.time_parser(utils.extract_arg(message.text, 1))
        if restrict_timer is None:
            bot.reply_to(message,
                         "Некорректный аргумент времени (не должно быть меньше 31 секунды и больше 365 суток).")
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

        if 31535991 <= restrict_timer <= 31536000:
            restrict_timer = 31535990

    kickuser = True if restrict_timer != 0 else False

    if bot.get_chat_member(data.main_chat_id, user_id).status == "left" and kickuser:
        bot.reply_to(message, "Пользователя нет в чате, чтобы можно было кикнуть его.")
        return

    if bot.get_chat_member(data.main_chat_id, user_id).status == "creator":
        bot.reply_to(message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
        return

    if data.bot_id == user_id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    unique_id = str(user_id) + "_userban"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    ban_timer_text = "\nПредложенный срок блокировки: <b>перманентный</b>" if restrict_timer == 0 else \
        f"\nПредложенный срок блокировки: {utils.formatted_timer(restrict_timer)}"
    vote_type = 1 if kickuser else 2

    vote_theme = "блокировка пользователя"
    if bot.get_chat_member(data.main_chat_id, user_id).status == "kicked":
        vote_theme = "изменение срока блокировки пользователя"

    date_unban = ""
    if bot.get_chat_member(data.main_chat_id, user_id).status == "kicked":
        until_date = bot.get_chat_member(data.main_chat_id, user_id).until_date
        if until_date == 0 or until_date is None:
            date_unban = "\nПользователь был ранее заблокирован перманентно"
        else:
            date_unban = "\nДо разблокировки пользователя оставалось " \
                         + utils.formatted_timer(until_date - int(time.time()))

    vote_text = (f"Тема голосования: {vote_theme} {username}" + date_unban + ban_timer_text +
                 f"\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, "ban", data.global_timer_ban, data.thresholds_get(True),
                     [user_id, username, utils.username_parser(message), vote_type, restrict_timer],
                     message.from_user.id)


def mute(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Ответьте на имя пользователя, которого требуется замутить.")
        return

    user_id, username, _ = utils.reply_msg_target(message.reply_to_message)

    if user_id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Я не могу ограничить анонимного администратора! "
                              "Вы можете снять с него права командой /deop %индекс%.")
        return

    if bot.get_chat_member(data.main_chat_id, user_id).status == "kicked":
        bot.reply_to(message, "Данный пользователь уже забанен или кикнут.")
        return

    if bot.get_chat_member(data.main_chat_id, user_id).status == "creator":
        bot.reply_to(message, "Я думаю, ты сам должен понимать тщетность своих попыток.")
        return

    if data.bot_id == user_id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    restrict_timer = 0
    if utils.extract_arg(message.text, 1) is not None:
        restrict_timer = utils.time_parser(utils.extract_arg(message.text, 1))
        if restrict_timer is None:
            bot.reply_to(message, "Некорректный аргумент времени "
                                  "(должно быть меньше 31 секунды и больше 365 суток).")
            return
        if not 30 < restrict_timer <= 31536000:
            bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше 365 суток.")
            return

    if 31535991 <= restrict_timer <= 31536000:
        restrict_timer = 31535990

    unique_id = str(user_id) + "_userban"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    ban_timer_text = "\nПредложенный срок ограничений: перманентно" if restrict_timer == 0 else \
        f"\nПредложенный срок ограничений: {utils.formatted_timer(restrict_timer)}"

    vote_theme = "ограничение сообщений пользователя"
    if bot.get_chat_member(data.main_chat_id, user_id).status == "restricted":
        vote_theme = "изменение срока ограничения сообщений пользователя"

    date_unban = ""
    if bot.get_chat_member(data.main_chat_id, user_id).status == "restricted":
        until_date = bot.get_chat_member(data.main_chat_id, user_id).until_date
        if until_date == 0 or until_date is None:
            date_unban = "\nПользователь был ранее заблокирован перманентно"
        else:
            date_unban = "\nДо разблокировки пользователя оставалось " \
                         + utils.formatted_timer(until_date - int(time.time()))

    vote_text = (f"Тема голосования: {vote_theme} {username}" + date_unban + ban_timer_text
                 + f"\nИнициатор голосования: {utils.username_parser(message, True)}.")

    vote_type = 0
    pool_constructor(unique_id, vote_text, message, "ban", data.global_timer_ban, data.thresholds_get(True),
                     [user_id, username, utils.username_parser(message), vote_type, restrict_timer],
                     message.from_user.id)


def unban(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Ответьте на имя пользователя, которого требуется размутить или разбанить.")
        return

    user_id, username, _ = utils.reply_msg_target(message.reply_to_message)

    if user_id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Я не могу разблокировать анонимного администратора!")
        return

    if data.bot_id == user_id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    if bot.get_chat_member(data.main_chat_id, user_id).status != "restricted" and \
            bot.get_chat_member(data.main_chat_id, user_id).status != "kicked":
        bot.reply_to(message, "Данный пользователь не ограничен.")
        return

    unique_id = str(user_id) + "_unban"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("Тема голосования: снятие ограничений с пользователя " + username
                 + f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, "unban", data.global_timer, data.thresholds_get(),
                     [user_id, username, utils.username_parser(message)], message.from_user.id)


def thresholds(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    mode = utils.extract_arg(message.text, 1)
    if mode is None:
        auto_thresholds_mode = "" if not data.is_thresholds_auto() else " (автоматический режим)"
        auto_thresholds_ban_mode = "" if not data.is_thresholds_auto(True) else " (автоматический режим)"
        auto_thresholds_min_mode = "" if not data.is_thresholds_auto(minimum=True) else " (автоматический режим)"
        bot.reply_to(message, "Текущие пороги:\nГолосов для обычного решения требуется: " + str(data.thresholds_get())
                     + auto_thresholds_mode + "\n"
                     + "Голосов для бана требуется: " + str(data.thresholds_get(True)) + auto_thresholds_ban_mode
                     + "\n" + "Минимальный порог голосов для принятия решения: "
                     + str(data.thresholds_get(minimum=True)) + auto_thresholds_min_mode)
        return
    unique_id = "threshold"
    bantext = " стандартных голосований "
    mintext = " "
    warn = ""
    _ban, minimum = False, False
    thr_timer = data.global_timer
    if utils.extract_arg(message.text, 2) == "ban":
        unique_id = "threshold_ban"
        bantext = " бан-голосований "
        _ban = True
    elif utils.extract_arg(message.text, 2) == "min":
        unique_id = "threshold_min"
        bantext = " "
        mintext = " нижнего "
        warn = "\n<b>Внимание! Результаты голосования за минимальный порог " \
               "принимаются вне зависимости от минимального порога!" \
               "\nВремя завершения голосования за минимальный порог - 24 часа!</b>"
        minimum = True
        if not data.debug:
            thr_timer = 86400

    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    thr_value = 0
    if data.is_thresholds_auto(_ban, minimum) and mode == "auto":
        bot.reply_to(message, "Значения порога уже вычисляются автоматически!")
        return

    if mode != "auto":
        try:
            thr_value = int(mode)
        except (TypeError, ValueError):
            bot.reply_to(message, "Неверный аргумент (должно быть целое число от 2 до "
                         + str(bot.get_chat_members_count(data.main_chat_id)) + " или \"auto\").")
            return

        if thr_value > bot.get_chat_members_count(data.main_chat_id):
            bot.reply_to(message, "Количество голосов не может быть больше количества участников в чате.")
            return

        if thr_value == data.thresholds_get(_ban, minimum):
            bot.reply_to(message, "Это значение установлено сейчас!")
            return

        if thr_value < data.thresholds_get(minimum=True) and unique_id != "threshold_min":
            bot.reply_to(message, "Количество голосов не может быть меньше " + str(data.thresholds_get(minimum=True)))
            return
        elif thr_value < 2 and not data.debug:
            bot.reply_to(message, "Минимальное количество голосов не может быть меньше 2")
            return
        elif thr_value < 1:
            bot.reply_to(message, "Минимальное количество голосов не может быть меньше 1")
            return

        vote_text = (f"Тема голосования: установка{mintext}порога голосов{bantext}на значение {thr_value}"
                     f".\nИнициатор голосования: {utils.username_parser(message, True)}." + warn)

    else:
        vote_text = (f"Тема голосования: установка{mintext}порога голосов{bantext}"
                     f"на автоматически выставляемое значение"
                     f".\nИнициатор голосования: {utils.username_parser(message, True)}." + warn)

    pool_constructor(unique_id, vote_text, message, "threshold", thr_timer, data.thresholds_get(),
                     [thr_value, unique_id], message.from_user.id)


def timer(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message, private_dialog=True):
        return

    timer_arg = utils.extract_arg(message.text, 1)
    if timer_arg is None:
        timer_text = ""
        if message.chat.id == data.main_chat_id:
            timer_text = utils.formatted_timer(data.global_timer) + " для обычного голосования.\n" \
                         + utils.formatted_timer(data.global_timer_ban) + " для голосования за бан.\n"
        if sqlWorker.abuse_random(message.chat.id) == -1:
            timer_random_text = "Команда /random отключена."
        elif sqlWorker.abuse_random(message.chat.id) == 0:
            timer_random_text = "Кулдаун команды /random отключён."
        else:
            timer_random_text = utils.formatted_timer(sqlWorker.abuse_random(message.chat.id)) \
                                + " - кулдаун команды /random."
        bot.reply_to(message, "Текущие пороги таймера:\n" + timer_text + timer_random_text)
        return

    if utils.extract_arg(message.text, 2) != "random":
        if utils.command_forbidden(message, text="Команду с данным аргументом невозможно "
                                                 "запустить не в основном чате."):
            return

    if utils.extract_arg(message.text, 2) is None:
        unique_id = "timer"
        bantext = "таймера стандартных голосований"
        timer_arg = utils.time_parser(timer_arg)
        if timer_arg is None:
            bot.reply_to(message, "Неверный аргумент (должно быть число от 5 секунд до 1 суток).")
            return
        elif timer_arg < 5 or timer_arg > 86400:
            bot.reply_to(message, "Количество времени не может быть меньше 5 секунд и больше 1 суток.")
            return
        elif timer_arg == data.global_timer:
            bot.reply_to(message, "Это значение установлено сейчас!")
            return
    elif utils.extract_arg(message.text, 2) == "ban":
        unique_id = "timer for ban votes"
        bantext = "таймера бан-голосований"
        timer_arg = utils.time_parser(timer_arg)
        if timer_arg is None:
            bot.reply_to(message, "Неверный аргумент (должно быть число от 5 секунд до 1 суток).")
            return
        elif timer_arg < 5 or timer_arg > 86400:
            bot.reply_to(message, "Количество времени не может быть меньше 5 секунд и больше 1 суток.")
            return
        elif timer_arg == data.global_timer_ban:
            bot.reply_to(message, "Это значение установлено сейчас!")
            return
    elif utils.extract_arg(message.text, 2) == "random":
        unique_id = "timer for random cooldown"
        bantext = "кулдауна команды /random"
        timer_arg = utils.time_parser(timer_arg)
        if utils.extract_arg(message.text, 1) == "off":
            timer_arg = -1
        if timer_arg is None:
            bot.reply_to(message, "Неверный аргумент (должно быть число от 0 секунд до 1 часа).")
            return
        elif timer_arg < -1 or timer_arg > 3600:
            bot.reply_to(message, "Количество времени не может быть меньше 0 секунд и больше 1 часа.")
            return
        elif timer_arg == sqlWorker.abuse_random(message.chat.id):
            bot.reply_to(message, "Это значение установлено сейчас!")
            return
    else:
        bot.reply_to(message, "Неверный второй аргумент (должен быть ban, random или пустой).")
        return

    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    if timer_arg == -1:
        vote_text = (f"Тема голосования: отключение команды /random."
                     f"\nИнициатор голосования: {utils.username_parser(message, True)}.")

    elif timer_arg == 0:
        vote_text = (f"Тема голосования: отключение кулдауна команды /random."
                     f"\nИнициатор голосования: {utils.username_parser(message, True)}.")
    else:
        vote_text = (f"Тема голосования: смена {bantext} на значение "
                     + utils.formatted_timer(timer_arg) +
                     f"\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, unique_id, data.global_timer, data.thresholds_get(),
                     [timer_arg, unique_id], message.from_user.id)


def rate_top(message):
    rate_msg = bot.reply_to(message, "Сборка рейтинга, ожидайте...")
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
        bot.edit_message_text(message, "Ещё ни у одного пользователя нет социального рейтинга!",
                              rate_msg.chat.id, rate_msg.id)
        return

    bot.edit_message_text(rate_text, chat_id=rate_msg.chat.id,
                          message_id=rate_msg.id, parse_mode='html')


def rating(message):
    if not utils.botname_checker(message) or not data.rate or utils.command_forbidden(message):
        return

    mode = utils.extract_arg(message.text, 1)

    if mode is None:
        if utils.topic_reply_fix(message.reply_to_message) is None:
            user_id, username, _ = utils.reply_msg_target(message)
            if user_id == data.ANONYMOUS_ID:
                bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
                return
        else:
            if message.reply_to_message.from_user.id in [data.bot_id, data.ANONYMOUS_ID]:
                bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
                return

            user_status = bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status

            if user_status == "kicked" or user_status == "left":
                sqlWorker.clear_rate(message.reply_to_message.from_user.id)
                bot.reply_to(message, "Этот пользователь не является участником чата.")
                return

            user_id, username, is_bot = utils.reply_msg_target(message.reply_to_message)
            if is_bot:
                bot.reply_to(message, "У ботов нет социального рейтинга!")
                return

        user_rate = sqlWorker.get_rate(user_id)
        bot.reply_to(message, f"Социальный рейтинг пользователя {username}: {user_rate}")
        return

    if mode == "top":
        threading.Thread(target=rate_top, args=(message,)).start()
        return

    if mode == "up" or mode == "down":

        if message.reply_to_message is None:
            bot.reply_to(message, "Пожалуйста, ответьте на сообщение пользователя, "
                                  "чей социальный рейтинг вы хотите изменить")
            return

        user_id, username, is_bot = utils.reply_msg_target(message.reply_to_message)

        if user_id == message.from_user.id:
            bot.reply_to(message, "Вы не можете менять свой собственный рейтинг!")
            return

        if user_id in [data.bot_id, data.ANONYMOUS_ID]:
            bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
            return

        if is_bot:
            bot.reply_to(message, "У ботов нет социального рейтинга!")
            return

        if bot.get_chat_member(data.main_chat_id, user_id).status == "kicked" \
                or bot.get_chat_member(data.main_chat_id, user_id).status == "left":
            sqlWorker.clear_rate(user_id)
            bot.reply_to(message, "Этот пользователь не является участником чата.")
            return

        unique_id = str(user_id) + "_rating_" + mode
        records = sqlWorker.msg_chk(unique_id=unique_id)
        if utils.is_voting_exists(records, message, unique_id):
            return

        mode_text = "увеличение" if mode == "up" else "уменьшение"

        vote_text = (f"Тема голосования: {mode_text} "
                     f"социального рейтинга пользователя {username}"
                     f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

        pool_constructor(unique_id, vote_text, message, "change rate", data.global_timer, data.thresholds_get(),
                         [username, message.reply_to_message.from_user.id,
                          mode, utils.username_parser(message)], message.from_user.id)
        return

    bot.reply_to(message, "Неправильные аргументы (доступны top, up, down и команда без аргументов).")


def whitelist_building(message, user_whitelist):
    whitelist_msg = bot.reply_to(message, "Сборка вайтлиста, ожидайте...")
    user_list, counter = "Список пользователей, входящих в вайтлист:\n", 1
    for user in user_whitelist:
        try:
            username = utils.username_parser_chat_member(bot.get_chat_member(data.main_chat_id,
                                                                             user[0]), html=True)
            if username == "":
                sqlWorker.whitelist(user[0], remove=True)
                continue
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            sqlWorker.whitelist(user[0], remove=True)
            user_whitelist.remove(user)
            continue
        user_list = user_list + f'{counter}. <a href="tg://user?id={user[0]}">{username}</a>\n'
        counter = counter + 1

    if not user_whitelist:
        bot.reply_to(message, "Вайтлист данного чата пуст!")
        return

    bot.edit_message_text(user_list + "Узнать подробную информацию о конкретном пользователе можно командой /status",
                          chat_id=whitelist_msg.chat.id, message_id=whitelist_msg.id, parse_mode='html')


def whitelist(message):
    if not utils.botname_checker(message) or data.binary_chat_mode != 0 or utils.command_forbidden(message):
        return

    if utils.extract_arg(message.text, 1) in ("add", "remove"):
        if utils.topic_reply_fix(message.reply_to_message) is not None:
            who_id, who_name, is_bot = utils.reply_msg_target(message.reply_to_message)
        else:
            who_id, who_name, is_bot = utils.reply_msg_target(message)

        if utils.extract_arg(message.text, 2) is not None and utils.extract_arg(message.text, 1) == "remove":
            user_whitelist = sqlWorker.whitelist_get_all()
            if not user_whitelist:
                bot.reply_to(message, "Вайтлист данного чата пуст!")
                return

            try:
                index = int(utils.extract_arg(message.text, 2)) - 1
                if index < 0:
                    raise ValueError
            except ValueError:
                bot.reply_to(message, "Индекс должен быть больше нуля.")
                return

            try:
                who_id = user_whitelist[index][0]
            except IndexError:
                bot.reply_to(message, "Пользователь с данным индексом не найден в вайтлисте!")
                return

            try:
                who_name = utils.username_parser_chat_member(bot.get_chat_member(data.main_chat_id, who_id),
                                                             html=True)
                if who_name == "":
                    sqlWorker.whitelist(who_id, remove=True)
                    bot.reply_to(message, "Удалена некорректная запись!")
                    return
            except telebot.apihelper.ApiTelegramException:
                logging.error(traceback.format_exc())
                sqlWorker.whitelist(who_id, remove=True)
                bot.reply_to(message, "Удалена некорректная запись!")
                return
        else:
            if who_id in [data.bot_id, data.ANONYMOUS_ID]:
                bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
                return
            elif is_bot:
                bot.reply_to(message, f"Вайтлист не работает для ботов!")
                return

        is_whitelist = sqlWorker.whitelist(who_id)
        unique_id = str(who_id) + "_whitelist"
        records = sqlWorker.msg_chk(unique_id=unique_id)

        if utils.is_voting_exists(records, message, unique_id):
            return

        if is_whitelist and utils.extract_arg(message.text, 1) == "add":
            bot.reply_to(message, f"Пользователь {who_name} уже есть в вайтлисте!")
            return

        if not is_whitelist and utils.extract_arg(message.text, 1) == "remove":
            bot.reply_to(message, f"Пользователя {who_name} нет в вайтлисте!")
            return

        if utils.extract_arg(message.text, 1) == "add":
            whitelist_text = f"добавление пользователя {who_name} в вайтлист"
        else:
            whitelist_text = f"удаление пользователя {who_name} из вайтлиста"

        vote_text = (f"Тема голосования: {whitelist_text}.\n"
                     f"Инициатор голосования: {utils.username_parser(message, True)}.")

        pool_constructor(unique_id, vote_text, message, "whitelist", data.global_timer, data.thresholds_get(),
                         [who_id, who_name, utils.extract_arg(message.text, 1)], message.from_user.id)

        return

    user_whitelist = sqlWorker.whitelist_get_all()
    if not user_whitelist:
        bot.reply_to(message, "Вайтлист данного чата пуст!")
        return

    threading.Thread(target=whitelist_building, args=(message, user_whitelist)).start()


def msg_remover(message, clearmsg):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Ответьте на сообщение пользователя, которое требуется удалить.")
        return

    if data.bot_id == message.reply_to_message.from_user.id and sqlWorker.msg_chk(message.reply_to_message):
        bot.reply_to(message, "Вы не можете удалить голосование до его завершения!")
        return

    unique_id = str(message.reply_to_message.message_id) + "_delmsg"

    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    silent_del, votes, timer_del, clear, warn = False, data.thresholds_get(True), data.global_timer_ban, "", ""
    if clearmsg:
        silent_del, votes, timer_del, clear = True, data.thresholds_get(), data.global_timer, "бесследно "
        warn = "\n\n<b>Внимание, голосования для бесследной очистки не закрепляются автоматически. Пожалуйста, " \
               "закрепите их самостоятельно при необходимости.</b>\n"

    vote_text = (f"Тема голосования: удаление сообщения пользователя "
                 f"{utils.username_parser(message.reply_to_message, True)}"
                 f".\nИнициатор голосования: {utils.username_parser(message, True)}." + warn)

    pool_constructor(unique_id, vote_text, message, "delete message", timer_del, votes,
                     [message.reply_to_message.message_id, utils.username_parser(message.reply_to_message), silent_del],
                     message.from_user.id, silent=silent_del)


def private_mode(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.extract_arg(message.text, 1) is not None:

        if data.chat_mode != "mixed":
            bot.reply_to(message, "Хостер бота заблокировал возможность сменить режим работы бота.")
            return

        unique_id = "private mode"
        records = sqlWorker.msg_chk(unique_id=unique_id)
        if utils.is_voting_exists(records, message, unique_id):
            return

        try:
            chosen_mode = int(utils.extract_arg(message.text, 1))
            if not 1 <= chosen_mode <= 3:
                raise ValueError
        except ValueError:
            bot.reply_to(message, "Неверный аргумент (должно быть число от 1 до 3).")
            return

        if chosen_mode - 1 == data.binary_chat_mode:
            bot.reply_to(message, "Данный режим уже используется сейчас!")
            return

        if chosen_mode == 1:
            chat_mode = "приватный"
        elif chosen_mode == 2:
            chat_mode = "публичный (с голосованием)"
        else:
            chat_mode = "публичный (с капчёй)"

        vote_text = (f"Тема голосования: изменение режима приватности чата на {chat_mode}."
                     f"\nИнициатор голосования: {utils.username_parser(message, True)}.")

        pool_constructor(unique_id, vote_text, message, unique_id, data.global_timer, data.thresholds_get(),
                         [chosen_mode - 1, utils.username_parser(message, True), chat_mode], message.from_user.id)
        return

    if data.binary_chat_mode == 0:
        chat_mode = "приватный"
    elif data.binary_chat_mode == 1:
        chat_mode = "публичный (с голосованием)"
    else:
        chat_mode = "публичный (с капчёй)"

    chat_mode_locked = "да" if data.chat_mode != "mixed" else "нет"

    bot.reply_to(message, "Существуют три режима работы антиспам-фильтра ДейтерБота.\n"
                          "1. Использование вайтлиста и системы инвайтов. Участник, не найденный в вайтлисте или в "
                          "одном из союзных чатов, блокируется. Классическая схема, применяемая для приватных чатов.\n"
                          "2. Использование голосования при вступлении участника. При вступлении участника в чат "
                          "отправка от него сообщений ограничивается, выставляется голосование за возможность "
                          "его вступления в чат. По завершению голосования участник блокируется или ему позволяется "
                          "вступить в чат. Новая схема, созданная для публичных чатов.\n"
                          "3. Использование классической капчи при вступлении участника.\n"
                          "Если хостер бота выставил режим \"mixed\" в конфиге бота, можно сменить режим на другой "
                          "(команда /private 1/2/3), в противном случае хостер бота устанавливает режим работы "
                          "самостоятельно.\n<b>Текущие настройки чата:</b>"
                          f"\nНастройки заблокированы хостером: {chat_mode_locked}"
                          f"\nТекущий режим чата: {chat_mode}", parse_mode="html")


def op(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.extract_arg(message.text, 1) == "help":
        help_txt = "В ДейтерБоте используется система записи прав администратора в виде строки из единиц и нулей. " \
                   "Для получения и выдачи нужных прав необходимо использовать запись вида /op 001010010 и т. п. " \
                   "Если не использовать данную запись, будут выданы права по умолчанию для чата.\n" \
                   "Глобальные права администраторов для чата можно изменить с помощью команды вида " \
                   "/op global 001010010, если хостер бота не запретил это.\n<b>Попытка выдачи недоступных боту или " \
                   "отключенных на уровне чата прав приведёт к ошибке!\nТекущие права для чата:</b>\n" \
                   f"Изменения заблокированы хостером - {data.admin_fixed}" \
                   f"{utils.allowed_list(data.admin_allowed)}" \
                   f"\n<b>ВНИМАНИЕ: при переназначении прав пользователю его текущие права перезаписываются!</b>"
        bot.reply_to(message, help_txt, parse_mode="html")
        return
    elif utils.extract_arg(message.text, 1) == "list":
        admin_list = bot.get_chat_administrators(data.main_chat_id)
        admin_msg = bot.reply_to(message, "Сборка списка администраторов, ожидайте...")
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
    elif utils.extract_arg(message.text, 1) == "global":
        if data.admin_fixed:
            bot.reply_to(message, "Изменение глобальных прав администраторов для чата заблокировано хостером.")
            return

        unique_id = "global admin permissons"
        records = sqlWorker.msg_chk(unique_id=unique_id)
        if utils.is_voting_exists(records, message, unique_id):
            return

        if utils.extract_arg(message.text, 2) is None:
            bot.reply_to(message, "В сообщении не указан бинарный аргумент.")
            return

        try:
            binary_rules = int("1" + utils.extract_arg(message.text, 2)[::-1], 2)
            if not data.ADMIN_MIN <= binary_rules <= data.ADMIN_MAX:
                raise ValueError
        except ValueError:
            bot.reply_to(message, "Неверное значение бинарного аргумента!")
            return

        vote_text = (f"Тема голосования: изменение разрешённых прав для администраторов на следующие:"
                     f"{utils.allowed_list(binary_rules)}"
                     f"\nИнициатор голосования: {utils.username_parser(message, True)}.")

        pool_constructor(unique_id, vote_text, message, unique_id, data.global_timer, data.thresholds_get(),
                         [binary_rules], message.from_user.id)
        return
    elif utils.extract_arg(message.text, 1) is not None:
        bot.reply_to(message, "Неизвестный аргумент команды!")
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        who_id, who_name, _ = utils.reply_msg_target(message)
    else:
        who_id, who_name, _ = utils.reply_msg_target(message.reply_to_message)

    if who_id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Я не могу менять права анонимным администраторам!")
        return

    if who_id == data.bot_id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    if bot.get_chat_member(data.main_chat_id, who_id).status == "creator":
        bot.reply_to(message, "Пользователь является создателем чата.")
        return

    if bot.get_chat_member(data.main_chat_id, who_id).status == "left" or \
            bot.get_chat_member(data.main_chat_id, who_id).status == "kicked":
        bot.reply_to(message, "Пользователь не состоит в чате.")
        return

    if bot.get_chat_member(data.main_chat_id, who_id).status == "restricted":
        bot.reply_to(message, "Ограниченный пользователь не может стать админом.")
        return

    if utils.extract_arg(message.text, 1) is not None:
        try:
            binary_rule = int("1" + utils.extract_arg(message.text, 1)[::-1], 2)
            if not data.ADMIN_MIN <= binary_rule <= data.ADMIN_MAX:
                raise ValueError
        except ValueError:
            bot.reply_to(message, "Неверное значение бинарного аргумента!")
            return
        if not utils.is_current_perm_allowed(binary_rule, data.admin_allowed):
            bot.reply_to(message, "Есть правила, не разрешённые на уровне чата (см. /op help).")
            return
        chosen_rights = utils.allowed_list(binary_rule)
    else:
        binary_rule = data.admin_allowed
        chosen_rights = " дефолтные (см. /op help)"

    unique_id = str(who_id) + "_op"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = (f"Тема голосования: выдача/изменение прав администратора пользователю {utils.html_fix(who_name)}"
                 f"\nПрава, выбранные пользователем для выдачи:{chosen_rights}"
                 f".\nИнициатор голосования: {utils.username_parser(message, True)}."
                 "\n<b>Звание можно будет установить ПОСЛЕ закрытия голосования.</b>")

    pool_constructor(unique_id, vote_text, message, "op", data.global_timer, data.thresholds_get(),
                     [who_id, who_name, binary_rule], message.from_user.id)


def rem_topic(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if message.message_thread_id is None:
        bot.reply_to(message, "Данный чат НЕ является топиком или является основным топиком!")
        return

    unique_id = str(message.message_thread_id) + "_rem_topic"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("Тема голосования: удаление данного топика" +
                 f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, "remove topic", 86400, data.thresholds_get(),
                     [message.message_thread_id, utils.username_parser(message),
                      message.reply_to_message.forum_topic_created.name], message.from_user.id)


def rank(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    me = False
    if utils.topic_reply_fix(message.reply_to_message) is None:
        me = True
    elif message.reply_to_message.from_user.id == message.from_user.id:
        me = True

    if me:
        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status == "administrator":

            if utils.extract_arg(message.text, 1) is None:
                bot.reply_to(message, "Звание не может быть пустым.")
                return

            rank_text = message.text.split(maxsplit=1)[1]

            if len(rank_text) > 16:
                bot.reply_to(message, "Звание не может быть длиннее 16 символов.")
                return

            try:
                bot.set_chat_administrator_custom_title(data.main_chat_id, message.from_user.id, rank_text)
                bot.reply_to(message, "Звание \"" + rank_text + "\" успешно установлено пользователю "
                             + utils.username_parser(message, True) + ".")
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    bot.reply_to(message, "В звании не поддерживаются эмодзи.")
                    return
                logging.error(traceback.format_exc())
                bot.reply_to(message, "Не удалось сменить звание.")
            return
        elif bot.get_chat_member(data.main_chat_id, message.from_user.id).status == "creator":
            bot.reply_to(message, "Я не могу изменить звание создателя чата.")
            return
        else:
            bot.reply_to(message, "Вы не являетесь администратором.")
            return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Ответьте на сообщение бота, звание которого вы хотите сменить.")
        return

    if message.reply_to_message.from_user.id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Я не могу менять звание анонимных администраторов!")
        return

    if not message.reply_to_message.from_user.is_bot:
        bot.reply_to(message, "Вы не можете менять звание других пользователей (кроме ботов).")
        return

    if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status != "administrator":
        bot.reply_to(message, "Данный бот не является администратором.")
        return

    if data.bot_id == message.reply_to_message.from_user.id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    unique_id = str(message.reply_to_message.from_user.id) + "_rank"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    if utils.extract_arg(message.text, 1) is None:
        bot.reply_to(message, "Звание не может быть пустым.")
        return

    rank_text = message.text.split(maxsplit=1)[1]

    if len(rank_text) > 16:
        bot.reply_to(message, "Звание не может быть длиннее 16 символов.")
        return

    vote_text = ("Тема голосования: смена звания бота " + utils.username_parser(message.reply_to_message, True)
                 + f"на \"{utils.html_fix(rank_text)}\""
                   f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, "rank", data.global_timer, data.thresholds_get(),
                     [message.reply_to_message.from_user.id, utils.username_parser(message.reply_to_message),
                      rank_text, utils.username_parser(message)], message.from_user.id)


def deop(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.extract_arg(message.text, 1) is None and utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Ответьте на сообщение, используйте аргумент \"me\" или номер админа из списка /op list")
        return

    me = True if utils.extract_arg(message.text, 1) == "me" else False
    if utils.topic_reply_fix(message.reply_to_message) is not None:
        if message.reply_to_message.from_user.id == message.from_user.id:
            me = True

    if me:
        if message.from_user.id == data.ANONYMOUS_ID:
            bot.reply_to(message, "Я не могу снять права анонимного администратора таким образом! "
                                  "Для анонимов вы можете использовать команду вида /deop %индекс%. "
                                  "Список администраторов вы можете получить командой /op list.")
            return
        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status == "creator":
            bot.reply_to(message, "Вы являетесь создателем чата, я не могу снять ваши права.")
            return
        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status != "administrator":
            bot.reply_to(message, "Вы не являетесь администратором!")
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, message.from_user.id,
                                     None, can_send_messages=True)
            bot.restrict_chat_member(data.main_chat_id, message.from_user.id,
                                     None, True, True, True, True, True, True, True, True)
            bot.reply_to(message,
                         "Пользователь " + utils.username_parser(message) + " добровольно ушёл в отставку."
                         + "\nСпасибо за верную службу!")
            return
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.reply_to(message, "Я не могу изменить ваши права!")
            return

    if str(utils.extract_arg(message.text, 1)).isdigit():
        index = int(utils.extract_arg(message.text, 1)) - 1
        admin_list = bot.get_chat_administrators(data.main_chat_id)
        try:
            if index < 0:
                raise IndexError
            admin = admin_list[index]
        except IndexError:
            bot.reply_to(message, "Админ с указанным индексом не найден")
            return
        if admin.is_anonymous and not admin.user.is_bot:
            admin_title = f'"{admin.custom_title}"' if admin.custom_title else "отсутствует"
            who_name = f'ANONYMOUS (звание {admin_title})'
        else:
            who_name = utils.username_parser_chat_member(admin)
        who_id = admin.user.id
    elif utils.topic_reply_fix(message.reply_to_message) is not None:
        who_id, who_name, _ = utils.reply_msg_target(message.reply_to_message)
    else:
        bot.reply_to(message, "Неизвестный аргумент команды")
        return

    if bot.get_chat_member(data.main_chat_id, who_id).status == "creator":
        bot.reply_to(message, f"{who_name} является создателем чата, я не могу снять его права.")
        return

    if bot.get_chat_member(data.main_chat_id, who_id).status != "administrator":
        bot.reply_to(message, f"{who_name} не является администратором!")
        return

    if data.bot_id == who_id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    if who_id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Я не могу снять права анонимного администратора таким образом! "
                              "Для анонимов вы можете использовать команду вида /deop %индекс%. "
                              "Список администраторов вы можете получить командой /op list.")
        return

    unique_id = str(who_id) + "_deop"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = (f"Тема голосования: снятие прав администратора с {utils.html_fix(who_name)}"
                 f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, "deop", data.global_timer, data.thresholds_get(),
                     [who_id, who_name],
                     message.from_user.id)


def title(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.extract_arg(message.text, 1) is None:
        bot.reply_to(message, "Название чата не может быть пустым.")
        return

    if len(message.text.split(maxsplit=1)[1]) > 255:
        bot.reply_to(message, "Название не должно быть длиннее 255 символов!")
        return

    if bot.get_chat(data.main_chat_id).title == message.text.split(maxsplit=1)[1]:
        bot.reply_to(message, "Название чата не может совпадать с существующим названием!")
        return

    unique_id = "title"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    vote_text = ("От пользователя " + utils.username_parser(message, True)
                 + " поступило предложение сменить название чата на \""
                 + utils.html_fix(message.text.split(maxsplit=1)[1]) + "\".")

    pool_constructor(unique_id, vote_text, message, unique_id, data.global_timer, data.thresholds_get(),
                     [message.text.split(maxsplit=1)[1], utils.username_parser(message)],
                     message.from_user.id)


def description(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is not None:
        if message.reply_to_message.text is not None:
            description_text = message.reply_to_message.text
            if len(description_text) > 255:
                bot.reply_to(message, "Описание не должно быть длиннее 255 символов!")
                return

        else:
            bot.reply_to(message, "В отвеченном сообщении не обнаружен текст!")
            return
    else:
        description_text = ""

    if bot.get_chat(data.main_chat_id).description == description_text:
        bot.reply_to(message, "Описание чата не может совпадать с существующим описанием!")
        return

    formatted_desc = " пустое" if description_text == "" else f":\n<code>{utils.html_fix(description_text)}</code>"

    vote_text = (f"Тема голосования: смена описания чата на{formatted_desc}\n"
                 f"Инициатор голосования: {utils.username_parser(message, True)}.")

    unique_id = "desc"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    pool_constructor(unique_id, vote_text, message, "description", data.global_timer, data.thresholds_get(),
                     [description_text, utils.username_parser(message)], message.from_user.id)


def chat_pic(message):

    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Пожалуйста, используйте эту команду как ответ на фотографию, файл jpg или png.")
        return

    unique_id = "chatpic"
    records = sqlWorker.msg_chk(unique_id=unique_id)
    if utils.is_voting_exists(records, message, unique_id):
        return

    if message.reply_to_message.photo is not None:
        file_buffer = (bot.download_file
                       (bot.get_file(message.reply_to_message.photo[-1].file_id).file_path))
    elif message.reply_to_message.document is not None:
        if not message.reply_to_message.document.mime_type == "image/png" and \
                not message.reply_to_message.document.mime_type == "image/jpeg":
            bot.reply_to(message, "Документ не является фотографией")
            return
        file_buffer = (bot.download_file(bot.get_file(message.reply_to_message.document.file_id).file_path))
    else:
        bot.reply_to(message, "В сообщении не обнаружена фотография")
        return

    try:
        tmp_img = open(data.path + 'tmp_img', 'wb')
        tmp_img.write(file_buffer)
    except Exception as e:
        logging.error((str(e)))
        logging.error(traceback.format_exc())
        bot.reply_to(message, "Ошибка записи изображения в файл!")
        return

    vote_text = ("Тема голосования: смена аватарки чата"
                 f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

    pool_constructor(unique_id, vote_text, message, "chat picture", data.global_timer,
                     data.thresholds_get(), [utils.username_parser(message)], message.from_user.id)


def captcha_failed(bot_message):
    time.sleep(60)
    datalist = sqlWorker.captcha(bot_message.message_id)
    if not datalist:
        return
    sqlWorker.captcha(bot_message.message_id, remove=True)
    try:
        bot.ban_chat_member(bot_message.chat.id, datalist[0][1], until_date=int(time.time()) + 60)
    except telebot.apihelper.ApiTelegramException:
        bot.edit_message_text(f"Я не смог заблокировать пользователя {datalist[0][3]}! Недостаточно прав?",
                              bot_message.chat.id, bot_message.message_id)
        return
    bot.edit_message_text(f"К сожалению, пользователь {datalist[0][3]} не смог пройти капчу и был кикнут на 60 секунд.",
                          bot_message.chat.id, bot_message.message_id)


def captcha(message, user_id, username):
    try:
        bot.restrict_chat_member(data.main_chat_id, user_id, can_send_messages=False, can_change_info=False,
                                 can_invite_users=False, can_pin_messages=False)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        bot.reply_to(message, "Ошибка блокировки нового пользователя. Недостаточно прав?")
        return

    button_values = [random.randint(1000, 9999) for _ in range(3)]
    max_value = max(button_values)
    buttons = [types.InlineKeyboardButton(text=str(i), callback_data=f"captcha_{i}") for i in button_values]
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(*buttons)

    bot_message = bot.reply_to(message, "\u26a0\ufe0f <b>СТОП!</b> \u26a0\ufe0f"
                                        "\nВы были остановлены антиспам-системой ДейтерБота!\n"
                                        "Для доступа в чат вам необходимо выбрать из списка МАКСИМАЛЬНОЕ число в "
                                        "течении 60 секунд, иначе вы будете кикнуты на 1 минуту. Время пошло.",
                               reply_markup=keyboard, parse_mode="html")

    sqlWorker.captcha(bot_message.id, add=True, user_id=user_id, max_value=max_value, username=username)
    threading.Thread(target=captcha_failed, args=(bot_message,)).start()


def new_usr_checker(message):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if data.main_chat_id != message.chat.id:  # В чужих чатах не следим
        return

    username = utils.username_parser_invite(message)
    user_id = message.json.get("new_chat_participant").get("id")
    is_bot = message.json.get("new_chat_participant").get("is_bot")

    if bot.get_chat_member(data.main_chat_id, user_id).status == "creator":
        bot.reply_to(message, "Приветствую вас, Владыка.")
        return

    if is_bot:
        unique_id = str(user_id) + "_new_usr"
        records = sqlWorker.msg_chk(unique_id=unique_id)
        if utils.is_voting_exists(records, message, unique_id):
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, user_id, can_send_messages=False, can_change_info=False,
                                     can_invite_users=False, can_pin_messages=False, until_date=int(time.time()) + 60)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.reply_to(message, "Ошибка блокировки нового бота. Недостаточно прав?")
            return

        vote_text = ("Требуется подтверждение вступления нового бота, добавленного пользователем "
                     + utils.username_parser(message, True) + ", в противном случае он будет кикнут.")

        pool_constructor(unique_id, vote_text, message, "captcha", 60, data.thresholds_get(),
                         [username, user_id, "бота"], data.bot_id)
        return

    allies = sqlWorker.get_allies()
    if allies is not None:
        for i in allies:
            try:
                usr_status = bot.get_chat_member(i[0], user_id).status
                if usr_status not in ["left", "kicked"]:
                    if data.binary_chat_mode == 0:
                        sqlWorker.whitelist(user_id, add=True)
                    bot.reply_to(message, utils.welcome_msg_get(username, message))
                    return
            except telebot.apihelper.ApiTelegramException:
                sqlWorker.remove_ally(i[0])

    if data.binary_chat_mode == 0:
        if sqlWorker.whitelist(user_id):
            bot.reply_to(message, utils.welcome_msg_get(username, message))
        else:
            try:
                bot.ban_chat_member(data.main_chat_id, user_id, until_date=int(time.time()) + 86400)
                bot.reply_to(message, "Пользователя нет в вайтлисте, он заблокирован на 1 сутки.")
            except telebot.apihelper.ApiTelegramException:
                logging.error(traceback.format_exc())
                bot.reply_to(message, "Ошибка блокировки вошедшего пользователя. Недостаточно прав?")
    elif data.binary_chat_mode == 1:
        unique_id = str(user_id) + "_new_usr"
        records = sqlWorker.msg_chk(unique_id=unique_id)
        if utils.is_voting_exists(records, message, unique_id):
            return
        try:
            bot.restrict_chat_member(data.main_chat_id, user_id, can_send_messages=False, can_change_info=False,
                                     can_invite_users=False, can_pin_messages=False)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.reply_to(message, "Ошибка блокировки нового пользователя. Недостаточно прав?")
            return

        vote_text = ("Требуется подтверждение вступления нового пользователя " + username
                     + ", в противном случае он будет кикнут.")

        pool_constructor(unique_id, vote_text, message, "captcha", data.global_timer, data.thresholds_get(),
                         [username, user_id, "пользователя"], data.bot_id)
    elif data.binary_chat_mode == 2:
        captcha(message, user_id, username)


def allies_list(message):
    if not utils.botname_checker(message):
        return

    if message.chat.id == message.from_user.id:
        bot.reply_to(message, "Данная команда не может быть запущена в личных сообщениях.")
        return

    mode = utils.extract_arg(message.text, 1)

    if mode == "add" or mode == "remove":

        if message.chat.id == data.main_chat_id:
            bot.reply_to(message, "Данную команду нельзя запустить в основном чате!")
            return

        if sqlWorker.get_ally(message.chat.id) is not None and mode == "add":
            bot.reply_to(message, "Данный чат уже входит в список союзников!")
            return

        if sqlWorker.get_ally(message.chat.id) is None and mode == "remove":
            bot.reply_to(message, "Данный чат не входит в список союзников!")
            return

        abuse_chk = sqlWorker.abuse_check(message.chat.id)
        if abuse_chk > 0 and mode == "add":
            bot.reply_to(message, "Сработала защита от абуза добавления в союзники! Вам следует подождать ещё "
                         + utils.formatted_timer(abuse_chk - int(time.time())))
            return

        unique_id = str(message.chat.id) + "_allies"
        records = sqlWorker.msg_chk(unique_id=unique_id)
        if utils.is_voting_exists(records, message, unique_id):
            return

        if mode == "add":
            vote_type_text, vote_type = "установка", "add allies"
            invite_link = bot.get_chat(message.chat.id).invite_link
            if invite_link is None:
                invite_link = "\nИнвайт-ссылка на данный чат отсутствует."
            else:
                invite_link = f"\nИнвайт-ссылка на данный чат: {invite_link}."
        else:
            vote_type_text, vote_type = "разрыв", "remove allies"
            invite_link = ""

        vote_text = (f"Тема голосования: {vote_type_text} союзных отношений с чатом "
                     f"<b>{utils.html_fix(bot.get_chat(message.chat.id).title)}</b>{invite_link}"
                     f".\nИнициатор голосования: {utils.username_parser(message, True)}.")

        pool_constructor(unique_id, vote_text, message, vote_type, 86400, data.thresholds_get(),
                         [message.chat.id, message.message_thread_id], message.from_user.id, adduser=True)

        mode_text = "создании" if mode == "add" else "разрыве"

        bot.reply_to(message, f"Голосование о {mode_text} союза отправлено в чат "
                              f"<b>{utils.html_fix(bot.get_chat(data.main_chat_id).title)}</b>.\n"
                              f"Оно завершится через 24 часа или ранее в зависимости от количества голосов.",
                     parse_mode="html")
        return

    elif mode is not None:
        bot.reply_to(message, "Неправильный аргумент (поддерживаются add и remove).")
        return

    if sqlWorker.get_ally(message.chat.id) is not None:
        bot.reply_to(message, "Данный чат является союзным чатом для "
                     + bot.get_chat(data.main_chat_id).title + ", ссылка для инвайта - "
                     + bot.get_chat(data.main_chat_id).invite_link)
        return

    if utils.command_forbidden(message, text="Данную команду без аргументов можно "
                                             "запустить только в основном чате или в союзных чатах."):
        return

    allies_text = "Список союзных чатов: \n"
    allies = sqlWorker.get_allies()
    if allies is not None:
        for i in allies:
            try:
                bot.get_chat_member(i[0], data.bot_id).status
            except telebot.apihelper.ApiTelegramException:
                sqlWorker.remove_ally(i[0])
                allies.remove(i)
                continue
            try:
                invite_link = bot.get_chat(i[0]).invite_link
                if invite_link is None:
                    invite_link = "инвайт-ссылка отсутствует"
                allies_text = allies_text + f"{bot.get_chat(i[0]).title} - {invite_link}\n"
            except telebot.apihelper.ApiTelegramException:
                logging.error(traceback.format_exc())

    if allies is None:
        bot.reply_to(message, "В настоящее время у вас нет союзников.")
        return

    bot.reply_to(message, allies_text)
