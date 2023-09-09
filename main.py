import json
import logging
import multiprocessing
import os
import random
import time
import traceback

import telebot

import plugin_engine
import postvote
import utils
import prevote
from poll_engine import pool_engine
from utils import data, bot, sqlWorker


@bot.message_handler(commands=['invite'])
def add_usr(message):
    prevote.Invite(message)


@bot.message_handler(commands=['ban', 'banuser'])
def ban_usr(message):
    prevote.Ban(message)


@bot.message_handler(commands=['kick', 'kickuser'])
def kick_usr(message):
    prevote.Kick(message)


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


@bot.message_handler(commands=['shield'])
def shield(message):
    prevote.Shield(message)


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

    poll = sqlWorker.get_poll(message.reply_to_message.id)
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

    abuse_text = ""
    abuse_chk = sum(sqlWorker.abuse_check(user_id))
    if abuse_chk > 0:
        abuse_text = f"\nТаймаут абуза инвайта для пользователя: {utils.formatted_timer(abuse_chk - int(time.time()))}"

    bot.reply_to(message, f"Текущий статус пользователя {utils.html_fix(username)}: "
                          f"{statuses.get(bot.get_chat_member(data.main_chat_id, user_id).status)}\n"
                          f"ID пользователя: <code>{user_id}</code>\n"
                          f"Наличие в вайтлисте: {whitelist_status}{until_date}{abuse_text}", parse_mode='html')


@bot.message_handler(commands=['random', 'redrum'])
def random_msg(message):
    if not utils.botname_checker(message):
        return

    try:
        abuse_vote_timer = int(pool_engine.vote_abuse.get("random"))
    except TypeError:
        abuse_vote_timer = 0

    abuse_random = sqlWorker.abuse_random(message.chat.id)

    if abuse_vote_timer + abuse_random > int(time.time()) or abuse_random < 0:
        return

    pool_engine.vote_abuse.update({"random": int(time.time())})

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


@bot.message_handler(commands=['pardon'])
def pardon(message):
    if not utils.botname_checker(message):
        return

    if all([message.reply_to_message is not None,
            bot.get_chat_member(data.main_chat_id, message.from_user.id).status in ("administrator", "creator"),
            message.chat.id == data.main_chat_id]):
        user_id, username, _ = utils.reply_msg_target(message.reply_to_message)
        sqlWorker.abuse_remove(user_id)
        bot.reply_to(message, f"Абуз инвайта для {username} сброшен!")
        return

    if message.chat.id == data.main_chat_id:
        bot.reply_to(message, "Данная команда не может быть запущена в основном чате не администраторами!")
    elif data.debug:
        sqlWorker.abuse_remove(message.chat.id)
        user = "пользователя" if message.chat.id == message.from_user.id else "чата"
        bot.reply_to(message, f"Абуз инвайта и союзников сброшен для текущего {user}.")
    else:
        bot.reply_to(message, "Данная команда не может быть запущена в обычном режиме вне основного чата!")


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


@bot.message_handler(commands=['help'])
def help_msg(message):
    if not utils.botname_checker(message):
        return

    if message.from_user.id == message.chat.id:
        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status in ("left", "kicked"):
            bot.reply_to(message, "У вас нет прав для использования этой команды.")
            return
    elif utils.command_forbidden(message):
        return

    try:
        help_text = open("help.txt", encoding="utf-8").read()
    except FileNotFoundError:
        bot.reply_to(message, "Файл help.txt не найден")
        return
    except IOError:
        bot.reply_to(message, "Файл help.txt не читается")
        return

    datetime_help = "\nФормат времени (не зависит от регистра):\n" \
                    "без аргумента или s - секунды\n" \
                    "m - минуты\n" \
                    "h - часы\n" \
                    "d - дни\n" \
                    "w - недели\n" \
                    "Примеры использования: /abuse 12h30s, /timer 3600, /kickuser 30m12d12d"

    try:
        bot.send_message(message.from_user.id,
                         f"<b>Список всех доступных команд для ДейтерБота версии {data.VERSION}:</b>\n" +
                         "\n".join(sorted(help_text.split(sep="\n"))) + datetime_help, parse_mode="html")
        if not message.from_user.id == message.chat.id:
            bot.reply_to(message, "Текст помощи по командам отправлен в л/с.")
    except telebot.apihelper.ApiTelegramException:
        bot.reply_to(message, "Я не смог отправить сообщение вам в л/с. Недостаточно прав или нет личного диалога?")


@bot.message_handler(commands=['votes'])
def votes_msg(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message, private_dialog=True):
        return

    records = sqlWorker.get_all_polls()
    poll_list = ""
    number = 1

    if bot.get_chat(message.chat.id).username is not None:
        format_chat_id = bot.get_chat(message.chat.id).username
    else:
        format_chat_id = "c/" + str(message.chat.id)[4:]

    for record in records:
        if record[3] != message.chat.id:
            continue
        try:
            vote_type = pool_engine.post_vote_list[record[2]].description
        except KeyError:
            vote_type = "INVALID (не загружен плагин?)"
        poll_list = poll_list + f"{number}. https://t.me/{format_chat_id}/{record[1]}, " \
                                f"тип - {vote_type}, " \
                                f"до завершения – {utils.formatted_timer(record[5] - int(time.time()))}\n"
        number = number + 1

    if poll_list == "":
        poll_list = "В этом чате нет активных голосований!"
    else:
        poll_list = "Список активных голосований:\n" + poll_list

    bot.reply_to(message, poll_list)


@bot.message_handler(commands=['kill'])
def mute_user(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if data.kill_mode == 0:
        bot.reply_to(message, "Команда /kill отключена в файле конфигурации бота.")
        return

    if utils.topic_reply_fix(message.reply_to_message) is None:

        if data.kill_mode == 2:
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

    if message.from_user.id != message.reply_to_message.from_user.id and data.kill_mode == 2:
        if bot.get_chat_member(data.main_chat_id, message.from_user.id).status not in ("administrator", "creator"):
            bot.reply_to(message, "В текущем режиме команду могут применять только администраторы чата.")
            return

    if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status == "restricted":
        bot.reply_to(message, "Он и так в муте, не увеличивайте его страдания.")
        return

    if bot.get_chat_member(data.main_chat_id, message.reply_to_message.from_user.id).status in ("kicked", "left"):
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
        abuse_vote_timer = int(pool_engine.vote_abuse.get("abuse" + str(message.from_user.id)))
    except TypeError:
        abuse_vote_timer = 0

    if abuse_vote_timer + 10 > int(time.time()):
        return

    pool_engine.vote_abuse.update({"abuse" + str(message.from_user.id): int(time.time())})

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
        logging.error(traceback.format_exc())
        bot.reply_to(message, "Ошибка сброса основной пригласительной ссылки! Подробная информация в логах бота.")


@bot.message_handler(commands=['cremate'])
def cremate(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    if message.reply_to_message is not None:
        user_id = message.reply_to_message.from_user.id
    elif utils.extract_arg(message.text, 1) is not None:
        user_id = utils.extract_arg(message.text, 1)
    else:
        bot.reply_to(message, "Требуется реплейнуть сообщение удалённого аккаунта "
                              "или ввести ID аккаунта аргументом команды.")
        return

    if user_id == data.bot_id:
        bot.reply_to(message, data.EASTER_LINK, disable_web_page_preview=True)
        return

    try:
        first_name = bot.get_chat_member(data.main_chat_id, user_id).user.first_name
    except telebot.apihelper.ApiTelegramException as e:
        if "invalid user_id specified" in str(e):
            bot.reply_to(message, "Указан неверный User ID.")
        else:
            logging.error(traceback.format_exc())
            bot.reply_to(message, "Неизвестная ошибка Telegram API. Информация сохранена в логи бота.")
        return

    if bot.get_chat_member(data.main_chat_id, user_id).status in ('left', 'kicked'):
        bot.reply_to(message, "Данный участник не находится в чате.")
    elif first_name == '':
        try:
            bot.ban_chat_member(data.main_chat_id, user_id, int(time.time()) + 60)
            bot.reply_to(message, "Удалённый аккаунт успешно кремирован.")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.reply_to(message, "Ошибка кремации удалённого аккаунта. Недостаточно прав?")
    else:
        bot.reply_to(message, "Данный участник не является удалённым аккаунтом.")


def calc_(calc_text, message):
    try:
        result = eval(calc_text.replace(',', '.').replace('^', '**'))
        if isinstance(result, float):
            result = round(result, 10)
            if result.is_integer():
                result = int(result)
        result = str(result)
    except SyntaxError:
        bot.reply_to(message, "Неверно введено выражение для вычисления.")
        return
    except ZeroDivisionError:
        bot.reply_to(message, f"{calc_text}\n=деление на 0")
        return
    except ValueError as e:
        if 'Exceeds the limit' in str(e):
            bot.reply_to(message, "Результат слишком большой для отправки.")
        else:
            logging.error(traceback.format_exc())
            bot.reply_to(message, "Неизвестная ошибка вычисления! Информация сохранена в логи бота.")
        return
    result = result.replace('.', ',') if calc_text.count(',') >= calc_text.count('.') else result
    try:
        bot.reply_to(message, f"{calc_text}\n=<code>{result}</code>", parse_mode='html')
    except telebot.apihelper.ApiTelegramException as e:
        if 'message is too long' in str(e):
            bot.reply_to(message, "Результат слишком большой для отправки.")


@bot.message_handler(commands=['calc'])
def calc(message):
    if not utils.botname_checker(message):
        return

    is_allies = False if sqlWorker.get_ally(message.chat.id) is None else True
    if not is_allies:
        if utils.command_forbidden(message, text="Данную команду можно запустить только "
                                                 "в основном чате или в союзных чатах."):
            return

    if utils.extract_arg(message.text, 1) is None:
        bot.reply_to(message, "Данная команда не может быть запущена без аргумента.")
        return

    calc_text = message.text.split(maxsplit=1)[1]
    if len(calc_text.replace(" ", "")) > 500:
        bot.reply_to(message, "В выражении должно быть не более 500 полезных символов.")
        return
    for i in calc_text:
        if i not in "1234567890 */+-().,^":
            bot.reply_to(message, "Неверно введено выражение для вычисления.")
            return

    process = multiprocessing.Process(target=calc_, args=(calc_text, message))
    process.start()
    process.join(timeout=5)
    if process.is_alive():
        process.terminate()
        bot.reply_to(message, "Время вычисления превысило таймаут. Отменено.")


@bot.message_handler(commands=['version'])
def revoke(message):
    if not utils.botname_checker(message):
        return

    bot.reply_to(message, f"DeuterBot, версия {data.VERSION}\nДата сборки: {data.BUILD_DATE}\n"
                          f"Created by Allnorm aka Peter Burzec")


@bot.message_handler(commands=['plugins'])
def revoke(message):
    if not utils.botname_checker(message) or utils.command_forbidden(message):
        return

    plugin_list = "Никакие плагины сейчас не загружены."
    if data.plugins:
        plugin_list = "Список загруженных плагинов: " + ", ".join(data.plugins)
    bot.reply_to(message, plugin_list)


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
    records = sqlWorker.get_poll(call_msg.message.id)
    if not records:
        bot.edit_message_text(utils.html_fix(call_msg.message.text)
                              + "\n\n<b>Голосование не найдено в БД и закрыто.</b>",
                              call_msg.message.chat.id, call_msg.message.id, parse_mode='html')
        try:
            bot.unpin_chat_message(call_msg.message.chat.id, call_msg.message.id)
        except telebot.apihelper.ApiTelegramException:
            pass

    return records


@bot.callback_query_handler(func=lambda call: "captcha" in call.data)
def captcha_buttons(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    data_list = sqlWorker.captcha(call_msg.message.message_id)
    if not data_list:
        bot.edit_message_text("Капча не найдена в БД и закрыта.", call_msg.message.chat.id, call_msg.message.message_id)
        return
    if data_list[0][1] != str(call_msg.from_user.id):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Вы не можете решать чужую капчу!', show_alert=True)
        return

    if int(call_msg.data.split("_")[1]) != data_list[0][2]:
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text='Неправильный ответ!', show_alert=True)
        return

    sqlWorker.captcha(call_msg.message.message_id, remove=True)
    sqlWorker.abuse_update(data_list[0][1], timer=3600, force=True)
    try:
        bot.restrict_chat_member(call_msg.message.chat.id, data_list[0][1],
                                 None, True, True, True, True, True, True, True, True)
    except telebot.apihelper.ApiTelegramException:
        bot.edit_message_text(f"Я не смог снять ограничения с пользователя {data_list[0][3]}! Недостаточно прав?",
                              call_msg.message.chat.id, call_msg.message.message_id)
        return

    try:
        bot.edit_message_text(utils.welcome_msg_get(data_list[0][3], call_msg.message), call_msg.message.chat.id,
                              call_msg.message.message_id)
    except telebot.apihelper.ApiTelegramException:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel_vote(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return

    button_data = json.loads(poll[0][4])
    for button in button_data:
        if button["button_type"] == "cancel":
            if button["user_id"] != call_msg.from_user.id:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text='Вы не можете отменить чужое голосование!', show_alert=True)
                return

    pool_engine.vote_abuse.clear()
    sqlWorker.rem_rec(poll[0][0])
    try:
        os.remove(data.path + poll[0][0])
    except IOError:
        pass
    bot.edit_message_text(utils.html_fix(call_msg.message.text)
                          + "\n\n<b>Голосование было отменено автором голосования.</b>",
                          call_msg.message.chat.id, call_msg.message.id, parse_mode="html")
    bot.reply_to(call_msg.message, "Голосование было отменено.")

    try:
        bot.unpin_chat_message(call_msg.message.chat.id, call_msg.message.id)
    except telebot.apihelper.ApiTelegramException:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "close")
def cancel_vote(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return

    button_data = json.loads(poll[0][4])
    for button in button_data:
        if button["button_type"] == "close":
            if button["user_id"] != call_msg.from_user.id:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text='Вы не можете закрыть чужой опрос!', show_alert=True)
                return

    pool_engine.vote_abuse.clear()
    pool_engine.vote_result(poll[0][0], call_msg.message)


@bot.callback_query_handler(func=lambda call: call.data == "my_vote")
def my_vote(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return

    button_data = json.loads(poll[0][4])
    for button in button_data:
        if button["button_type"] == "vote":
            if call_msg.from_user.id in button["user_list"]:
                bot.answer_callback_query(callback_query_id=call_msg.id,
                                          text=f'Вы голосовали за вариант "{button["name"]}".', show_alert=True)
                return
    bot.answer_callback_query(callback_query_id=call_msg.id, text='Вы не голосовали в данном опросе!', show_alert=True)


@bot.callback_query_handler(func=lambda call: "vote" in call.data)
def vote_button(call_msg):
    if data.main_chat_id == -1:  # Проверка на init mode
        return

    if bot.get_chat_member(call_msg.message.chat.id, call_msg.from_user.id).status in ("left", "kicked"):
        bot.answer_callback_query(callback_query_id=call_msg.id,
                                  text="Вы не являетесь участником данного чата!", show_alert=True)
        return

    poll = call_msg_chk(call_msg)
    if not poll:
        return

    if pool_engine.get_abuse_timer(call_msg):  # Voting click check
        return

    button_data = json.loads(poll[0][4])
    last_choice = None
    current_choice = call_msg.data.split("_")[1]
    for button in button_data:
        if button["button_type"] == "vote":
            if call_msg.from_user.id in button["user_list"]:
                last_choice = button["name"]
                break

    # Adding data to a button
    if data.vote_mode == 1:
        if last_choice is not None:
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Вы уже голосовали за вариант "{last_choice}". '
                                           f'Смена голоса запрещена.', show_alert=True)
            return
        else:
            for button in button_data:
                if button["button_type"] == "vote" and button["name"] == current_choice:
                    button["user_list"].append(call_msg.from_user.id)
                    break
    elif data.vote_mode == 2:
        if last_choice == current_choice:
            bot.answer_callback_query(callback_query_id=call_msg.id,
                                      text=f'Вы уже голосовали за вариант "{last_choice}". '
                                           f'Отмена голоса запрещена.', show_alert=True)
            return
        else:
            for button in button_data:
                if button["button_type"] == "vote" and button["name"] == current_choice:
                    button["user_list"].append(call_msg.from_user.id)
                if button["button_type"] == "vote" and button["name"] == last_choice:
                    button["user_list"].remove(call_msg.from_user.id)
    elif data.vote_mode == 3:
        if last_choice == current_choice:
            for button in button_data:
                if button["button_type"] == "vote" and button["name"] == current_choice:
                    button["user_list"].remove(call_msg.from_user.id)
                    break
        else:
            for button in button_data:
                if button["button_type"] == "vote" and button["name"] == current_choice:
                    button["user_list"].append(call_msg.from_user.id)
                if button["button_type"] == "vote" and button["name"] == last_choice:
                    button["user_list"].remove(call_msg.from_user.id)
    # Making changes to the database
    sqlWorker.update_poll_votes(poll[0][0], json.dumps(button_data))

    # Checking that there are enough votes to close the vote
    voting_completed = False
    for button in button_data:
        if button["button_type"] == "vote":
            if len(button["user_list"]) >= poll[0][7]:
                voting_completed = True
                break

    if voting_completed or poll[0][5] <= int(time.time()):
        pool_engine.vote_abuse.clear()
        pool_engine.vote_result(poll[0][0], call_msg.message)
        return

    # Making changes to the message
    bot.edit_message_reply_markup(call_msg.message.chat.id, message_id=call_msg.message.id,
                                  reply_markup=utils.make_keyboard(button_data))
    pool_engine.vote_abuse.update({str(call_msg.message.id) + "." + str(call_msg.from_user.id): int(time.time())})


if __name__ == "__main__":
    postvote.post_vote_list_init()
    plugin_engine.Plugins()
    utils.init()
    pool_engine.auto_restart_polls()
    bot.infinity_polling()
