import json
import logging
import os
import pickle
import random
import threading
import time
import traceback

import telebot

import utils
import prevote
from prevote import vote_abuse, post_vote_list

data = utils.data
bot = utils.bot


def auto_restart_polls():
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
            threading.Thread(target=prevote.vote_timer, args=(record[5] - time_now, record[0], message_vote)).start()
            logging.info("Restarted poll " + record[0])
        else:
            prevote.vote_result(record[0], message_vote)


sqlWorker = utils.sqlWorker
utils.init()
auto_restart_polls()


@bot.message_handler(commands=['invite'])
def add_usr(message):
    prevote.Invite(message)


@bot.message_handler(commands=['ban', 'kick'])
def ban_usr(message):
    prevote.Ban(message)


@bot.message_handler(commands=['mute'])
def mute_usr(message):
    prevote.Mute(message)


@bot.message_handler(commands=['unmute', 'unban'])
def unban_usr(message):
    prevote.Unban(message)


@bot.message_handler(commands=['threshold'])
def thresholds(message):
    prevote.Thresholds(message)


@bot.message_handler(commands=['timer'])
def timer(message):
    prevote.Timer(message)


@bot.message_handler(commands=['rate'])
def rate(message):
    prevote.Rating(message)


@bot.message_handler(commands=['whitelist'])
def whitelist(message):
    prevote.Whitelist(message)


@bot.message_handler(commands=['delete'])
def delete_msg(message):
    prevote.MessageRemover(message)


@bot.message_handler(commands=['clear'])
def clear_msg(message):
    prevote.MessageSilentRemover(message)


@bot.message_handler(commands=['private'])
def private_mode(message):
    prevote.PrivateMode(message)


@bot.message_handler(commands=['op'])
def op(message):
    prevote.Op(message)


@bot.message_handler(commands=['remtopic'])
def rem_topic(message):
    prevote.RemoveTopic(message)


@bot.message_handler(commands=['rank'])
def rank(message):
    prevote.Rank(message)


@bot.message_handler(commands=['deop'])
def deop(message):
    prevote.Deop(message)


@bot.message_handler(commands=['title'])
def title(message):
    prevote.Title(message)


@bot.message_handler(commands=['description'])
def description(message):
    prevote.Description(message)


@bot.message_handler(commands=['chatpic'])
def chat_pic(message):
    prevote.Avatar(message)


@bot.message_handler(content_types=['new_chat_members'])
def new_usr_checker(message):
    prevote.NewUserChecker(message)


@bot.message_handler(commands=['allies'])
def allies_list(message):
    prevote.AlliesList(message)


@bot.message_handler(commands=['rules'])
def rules_msg(message):
    prevote.Rules(message)


@bot.message_handler(commands=['poll'])
def custom_poll(message):
    prevote.CustomPoll(message)


@bot.message_handler(commands=['answer'])
def add_answer(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:
        bot.reply_to(message, "Пожалуйста, используйте эту команду как ответ на заявку на вступление")
        return

    poll = sqlWorker.msg_chk(message_vote=message.reply_to_message)
    if poll:
        if poll[0][2] != "invite":
            bot.reply_to(message, "Данное голосование не является голосованием о вступлении.")
            return
    else:
        bot.reply_to(message, "Заявка на вступление не найдена или закрыта.")
        return

    try:
        msg_from_usr = message.text.split(None, 1)[1]
    except IndexError:
        bot.reply_to(message, "Ответ не может быть пустым.")
        return

    datalist = json.loads(poll[0][6])

    try:
        bot.send_message(datalist[0], "Сообщение на вашу заявку от участника чата - \"" + msg_from_usr + "\"")
        bot.reply_to(message, "Сообщение пользователю отправлено успешно.")
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        bot.reply_to(message, "Ошибка отправки сообщению пользователю.")


@bot.message_handler(commands=['status'])
def status(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    target_msg = message
    if utils.topic_reply_fix(message.reply_to_message) is not None:
        target_msg = message.reply_to_message

    statuses = {"left": "покинул группу",
                "kicked": "заблокирован",
                "restricted": "ограничен",
                "creator": "автор чата",
                "administrator": "администратор",
                "member": "участник"}

    user_id, username, is_bot = utils.reply_msg_target(target_msg)

    if user_id == data.ANONYMOUS_ID:
        bot.reply_to(message, "Данный пользователь является анонимным администратором. "
                              "Я не могу получить о нём информацию!")
        return

    if data.binary_chat_mode != 0:
        whitelist_status = "вайтлист отключён"
    elif is_bot:
        whitelist_status = "является ботом"
    elif sqlWorker.whitelist(target_msg.from_user.id):
        whitelist_status = "да"
    else:
        whitelist_status = "нет"

    until_date = ""
    if bot.get_chat_member(data.main_chat_id, user_id).status in ("kicked", "restricted"):
        if bot.get_chat_member(data.main_chat_id, user_id).until_date == 0:
            until_date = "\nОсталось до снятия ограничений: ограничен бессрочно"
        else:
            until_date = "\nОсталось до снятия ограничений: " + \
                         str(utils.formatted_timer(bot.get_chat_member(data.main_chat_id, user_id)
                                                   .until_date - int(time.time())))

    bot.reply_to(message, f"Текущий статус пользователя {username}"
                          f" - {statuses.get(bot.get_chat_member(data.main_chat_id, user_id).status)}"
                          f"\nНаличие в вайтлисте: {whitelist_status}{until_date}")


@bot.message_handler(commands=['random', 'redrum'])
def random_msg(message):
    if not utils.botname_checker(message):
        return

    try:
        abuse_vote_timer = int(vote_abuse.get("random"))
    except TypeError:
        abuse_vote_timer = 0

    abuse_random = sqlWorker.abuse_random(message.chat.id)

    if abuse_vote_timer + abuse_random > int(time.time()) or abuse_random < 0:
        return

    vote_abuse.update({"random": int(time.time())})

    msg_id = ""
    for i in range(5):
        try:
            msg_id = random.randint(1, message.id)
            bot.forward_message(message.chat.id, message.chat.id, msg_id)
            return
        except telebot.apihelper.ApiTelegramException:
            pass

    logging.error(traceback.format_exc())
    bot.reply_to(message, "Ошибка взятия рандомного сообщения с номером {}!".format(msg_id))


@bot.message_handler(commands=['reset'])
def reset(message):
    if not utils.botname_checker(message):
        return

    if data.debug:
        sqlWorker.abuse_remove(message.chat.id)
        bot.reply_to(message, "Абуз инвайта и союзников сброшен.")


@bot.message_handler(commands=['getchat'])
def get_id(message):
    if utils.extract_arg(message.text, 1) == "print" and data.debug:
        bot.reply_to(message, f"ID чата {message.chat.id}.\nID темы {message.message_thread_id}")
        return

    if not utils.botname_checker(message, get_chat=True):
        return

    if message.chat.id == message.from_user.id:
        bot.reply_to(message, "Данная команда не может быть запущена в личных сообщениях.")
        return

    utils.write_init_chat(message)


@bot.message_handler(commands=['getuser'])
def get_usr(message):
    if not utils.botname_checker(message):
        return

    if data.debug and utils.topic_reply_fix(message.reply_to_message) is not None:
        user_id, username, _ = utils.reply_msg_target(message.reply_to_message)
        bot.reply_to(message, f"ID пользователя {username} - {user_id}")


@bot.message_handler(commands=['help'])
def help_msg(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    try:
        help_text = open(data.path + "help.txt", encoding="utf-8").read()
    except FileNotFoundError:
        bot.reply_to(message, "Файл help.txt не найден")
        return
    except IOError:
        bot.reply_to(message, "Файл help.txt не читается")
        return

    bot.reply_to(message, help_text, parse_mode="html")


@bot.message_handler(commands=['votes'])
def votes_msg(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    records = sqlWorker.get_all_polls()
    poll_list = ""
    number = 1

    if bot.get_chat(data.main_chat_id).username is not None:
        format_chat_id = bot.get_chat(data.main_chat_id).username
    else:
        format_chat_id = "c/" + str(data.main_chat_id)[4:]

    for record in records:
        poll_list = poll_list + f"{number}. https://t.me/{format_chat_id}/{record[1]}, " \
                                f"тип - {post_vote_list[record[2]].description}, " + \
                    f"до завершения – {utils.formatted_timer(record[5] - int(time.time()))}\n"
        number = number + 1

    if poll_list == "":
        poll_list = "У вас нет активных голосований!"
    else:
        poll_list = "Список активных голосований:\n" + poll_list

    bot.reply_to(message, poll_list)


@bot.message_handler(commands=['abyss'])
def mute_user(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if data.abuse_mode == 0:
        bot.reply_to(message, "Команда /abyss отключена в файле конфигурации бота.")
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:

        if data.abuse_mode == 2:
            only_for_admins = "\nВ текущем режиме команду могут применять только администраторы чата."
        else:
            only_for_admins = ""

        bot.reply_to(message, "Ответьте на сообщение пользователя, которого необходимо отправить в мут.\n"
                     + "ВНИМАНИЕ: использовать только в крайних случаях - во избежание злоупотреблений "
                     + "вы так же будете лишены прав на тот же срок.\n"
                     + "Даже если у вас есть права админа, вы будете их автоматически лишены, "
                     + "если они были выданы с помощью бота." + only_for_admins)
        return

    if data.bot_id == message.reply_to_message.from_user.id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    if data.ANONYMOUS_ID in [message.reply_to_message.from_user.id, message.from_user.id]:
        bot.reply_to(message, "Я не могу ограничить анонимного пользователя!")
        return

    if message.from_user.id != message.reply_to_message.from_user.id and data.abuse_mode == 2:
        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status != "administrator" and \
                bot.get_chat_member(data.main_chat_id, message.from_user.id).status != "creator":
            bot.reply_to(message, "В текущем режиме команду могут применять только администраторы чата.")
            return

    if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status == "restricted":
        bot.reply_to(message, "Он и так в муте, не увеличивайте его страдания.")
        return

    if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status == "kicked" \
            or bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status == "left":
        bot.reply_to(message, "Данный пользователь не состоит в чате.")
        return

    timer_mute = 3600
    if utils.extract_arg(message.text, 1) is not None:
        timer_mute = utils.time_parser(utils.extract_arg(message.text, 1))
        if timer_mute is None:
            bot.reply_to(message, "Неправильный аргумент, укажите время мута от 31 секунды до 12 часов.")
            return

    if not 30 < timer_mute <= 43200:
        bot.reply_to(message, "Время не должно быть меньше 31 секунды и больше 12 часов.")
        return

    try:
        abuse_vote_timer = int(vote_abuse.get("abuse" + str(message.from_user.id)))
    except TypeError:
        abuse_vote_timer = 0

    if abuse_vote_timer + 10 > int(time.time()):
        return

    vote_abuse.update({"abuse" + str(message.from_user.id): int(time.time())})

    try:
        bot.restrict_chat_member(data.main_chat_id, message.reply_to_message.from_user.id,
                                 until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                 can_change_info=False, can_invite_users=False, can_pin_messages=False)
        if message.from_user.id == message.reply_to_message.from_user.id:
            if data.rate:
                sqlWorker.update_rate(message.from_user.id, -3)
                bot.reply_to(message, f"Пользователь {utils.username_parser(message)}"
                             + f" решил отдохнуть от чата на {utils.formatted_timer(timer_mute)}"
                             + " и снизить себе рейтинг на 3 пункта.")
            else:
                bot.reply_to(message, f"Пользователь {utils.username_parser(message)}"
                             + f" решил отдохнуть от чата на {utils.formatted_timer(timer_mute)}")
            return
        if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                and data.rate:
            sqlWorker.update_rate(message.reply_to_message.from_user.id, -5)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        bot.reply_to(message, "Я не смог снять права данного пользователя. Не имею права.")
        return

    try:
        bot.restrict_chat_member(data.main_chat_id, message.from_user.id,
                                 until_date=int(time.time()) + timer_mute, can_send_messages=False,
                                 can_change_info=False, can_invite_users=False, can_pin_messages=False)
        if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
                and data.rate:
            sqlWorker.update_rate(message.from_user.id, -5)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())
        bot.reply_to(message, "Я смог снять права данного пользователя на "
                     + utils.formatted_timer(timer_mute) + ", но не смог снять права автора заявки.")
        return

    user_rate = ""
    if not bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).user.is_bot \
            and data.rate:
        user_rate = "\nРейтинг обоих пользователей снижен на 5 пунктов."

    bot.reply_to(message, f"<b>Обоюдоострый Меч сработал</b>.\nТеперь {utils.username_parser(message, True)} "
                          f"и {utils.username_parser(message.reply_to_message, True)} "
                          f"будут дружно молчать в течении " + utils.formatted_timer(timer_mute) + user_rate,
                 parse_mode="html")


@bot.message_handler(commands=['revoke'])
def revoke(message):
    if not utils.botname_checker(message):
        return

    is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
    if not is_allies:
        if utils.command_forbidden(message, text="Данную команду можно запустить только "
                                                 "в основном чате или в союзных чатах."):
            return

    try:
        bot.revoke_chat_invite_link(data.main_chat_id, bot.get_chat(data.main_chat_id).invite_link)
        bot.reply_to(message, "Пригласительная ссылка на основной чат успешно сброшена.")
    except telebot.apihelper.ApiTelegramException:
        bot.reply_to(message, "Ошибка сброса основной пригласительной ссылки! Подробная информация в логах бота.")


@bot.message_handler(commands=['version'])
def revoke(message):
    if not utils.botname_checker(message):
        return

    bot.reply_to(message, f"DeuterBot, версия {data.VERSION}\nДата сборки: {data.BUILD_DATE}\n"
                          f"Created by Allnorm aka Peter Burzec")


@bot.message_handler(commands=['niko'])
def niko(message):
    if not utils.botname_checker(message):
        return

    try:
        bot.send_sticker(message.chat.id, random.choice(bot.get_sticker_set("OneShotSolstice").stickers).file_id,
                         message_thread_id=message.message_thread_id)
        # bot.send_sticker(message.chat.id, open(os.path.join("ee", random.choice(os.listdir("ee"))), 'rb'))
        # Random file
    except (FileNotFoundError, telebot.apihelper.ApiTelegramException, IndexError):
        pass


def call_msg_chk(call_msg):
    records = sqlWorker.msg_chk(message_vote=call_msg.message)
    if not records:
        sqlWorker.rem_rec(call_msg.message.id)
        bot.edit_message_text(utils.html_fix(call_msg.message.text)
                              + "\n\n<b>Голосование не найдено в БД и закрыто.</b>",
                              data.main_chat_id, call_msg.message.id, parse_mode='html')
        try:
            bot.unpin_chat_message(data.main_chat_id, call_msg.message.id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

    return records


@bot.callback_query_handler(func=lambda call: "captcha" in call.data)
def captcha_buttons(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    datalist = sqlWorker.captcha(call_msg.message.message_id)
    if not datalist:
        bot.edit_message_text("Капча не найдена в БД и закрыта.", call_msg.message.chat.id, call_msg.message.message_id)
        return
    if datalist[0][1] != str(call_msg.from_user.id):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Вы не можете решать чужую капчу!', show_alert=True)
        return

    if int(call_msg.data.split("_")[1]) != datalist[0][2]:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Неправильный ответ!', show_alert=True)
        return

    sqlWorker.captcha(call_msg.message.message_id, remove=True)
    try:
        bot.restrict_chat_member(call_msg.message.chat.id, datalist[0][1],
                                 None, True, True, True, True, True, True, True, True)
    except telebot.apihelper.ApiTelegramException:
        bot.edit_message_text(f"Я не смог снять ограничения с пользователя {datalist[0][3]}! Недостаточно прав?",
                              call_msg.message.chat.id, call_msg.message.message_id)
        return

    try:
        bot.edit_message_text(utils.welcome_msg_get(datalist[0][3], call_msg.message), call_msg.message.chat.id,
                              call_msg.message.message_id)
    except telebot.apihelper.ApiTelegramException:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel_vote(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return
    if poll[0][8] != call_msg.from_user.id:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Вы не можете отменить чужое голосование!', show_alert=True)
        return
    vote_abuse.clear()
    sqlWorker.rem_rec(call_msg.message.id, poll[0][0])
    try:
        os.remove(data.path + poll[0][0])
    except IOError:
        pass
    bot.edit_message_text(utils.html_fix(call_msg.message.text)
                          + "\n\n<b>Голосование было отменено автором голосования.</b>",
                          data.main_chat_id, call_msg.message.id, parse_mode="html")
    bot.reply_to(call_msg.message, "Голосование было отменено.")

    try:
        bot.unpin_chat_message(data.main_chat_id, call_msg.message.id)
    except telebot.apihelper.ApiTelegramException:
        logging.error(traceback.format_exc())


@bot.callback_query_handler(func=lambda call: call.data == "vote")
def my_vote(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if not call_msg_chk(call_msg):
        return

    user_ch = sqlWorker.is_user_voted(call_msg.from_user.id, call_msg.message.id)
    if user_ch:
        if user_ch == "yes":
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text='Вы голосовали за вариант "да".', show_alert=True)
        elif user_ch == "no":
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text='Вы голосовали за вариант "нет".', show_alert=True)
    else:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Вы не голосовали в данном опросе!', show_alert=True)


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if call_msg.data != "yes" and call_msg.data != "no":
        return

    def get_abuse_timer():
        try:
            abuse_vote_timer = int(vote_abuse.get(str(call_msg.message.id) + "." + str(call_msg.from_user.id)))
        except TypeError:
            abuse_vote_timer = None

        if abuse_vote_timer is not None:
            if abuse_vote_timer + data.wait_timer > int(time.time()):
                please_wait = data.wait_timer - int(time.time()) + abuse_vote_timer
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text="Вы слишком часто нажимаете кнопку. Пожалуйста, подождите ещё "
                                               + str(please_wait) + " секунд", show_alert=True)
                return True
            else:
                vote_abuse.pop(str(call_msg.message.id) + "." + str(call_msg.from_user.id), None)
                return False

    records = call_msg_chk(call_msg)
    if not records:
        return

    if records[0][5] <= int(time.time()):
        vote_abuse.clear()
        prevote.vote_result(records[0][0], call_msg.message)
        return

    unique_id = records[0][0]
    counter_yes = records[0][3]
    counter_no = records[0][4]
    votes_need_current = records[0][7]
    cancel = False if records[0][8] == data.bot_id or records[0][8] == data.ANONYMOUS_ID else True

    user_ch = sqlWorker.is_user_voted(call_msg.from_user.id, call_msg.message.id)
    if user_ch:
        if data.vote_mode == 1:
            option = {"yes": "да", "no": "нет"}
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Вы уже голосовали за вариант "{option[user_ch]}". '
                                           f'Смена голоса запрещена.', show_alert=True)
        elif data.vote_mode == 2:
            if call_msg.data != user_ch:
                if get_abuse_timer():
                    return
                if call_msg.data == "yes":
                    counter_yes = counter_yes + 1
                    counter_no = counter_no - 1
                if call_msg.data == "no":
                    counter_no = counter_no + 1
                    counter_yes = counter_yes - 1
                sqlWorker.poll_update(counter_yes, counter_no, unique_id)
                sqlWorker.user_vote_update(call_msg, utils.private_checker(call_msg))
                utils.vote_update(counter_yes, counter_no, call_msg.message, cancel)
            else:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text="Вы уже голосовали за этот вариант. " +
                                               "Отмена голоса запрещена.", show_alert=True)
        else:
            if get_abuse_timer():
                return
            if call_msg.data != user_ch:
                if call_msg.data == "yes":
                    counter_yes = counter_yes + 1
                    counter_no = counter_no - 1
                if call_msg.data == "no":
                    counter_no = counter_no + 1
                    counter_yes = counter_yes - 1
                sqlWorker.user_vote_update(call_msg, utils.private_checker(call_msg))
            else:
                if call_msg.data == "yes":
                    counter_yes = counter_yes - 1
                else:
                    counter_no = counter_no - 1
                sqlWorker.user_vote_remove(call_msg)
            sqlWorker.poll_update(counter_yes, counter_no, unique_id)
            utils.vote_update(counter_yes, counter_no, call_msg.message, cancel)
    else:
        if call_msg.data == "yes":
            counter_yes = counter_yes + 1
        if call_msg.data == "no":
            counter_no = counter_no + 1

        sqlWorker.poll_update(counter_yes, counter_no, unique_id)
        sqlWorker.user_vote_update(call_msg, utils.private_checker(call_msg))
        utils.vote_update(counter_yes, counter_no, call_msg.message, cancel)

    if counter_yes >= votes_need_current or counter_no >= votes_need_current:
        vote_abuse.clear()
        prevote.vote_result(unique_id, call_msg.message)
        return

    vote_abuse.update({str(call_msg.message.id) + "." + str(call_msg.from_user.id): int(time.time())})


bot.infinity_polling()
