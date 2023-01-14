import logging
import os
import time
import traceback

import telebot

import utils

sqlWorker = utils.sqlWorker
data = utils.data
bot = utils.bot


def vote_result_useradd(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    mention = "<a href=\"tg://user?id=" + str(datalist[0]) + "\">" + utils.html_fix(datalist[1]) + "</a>"
    if accept:
        sqlWorker.abuse_remove(records[0][8])
        sqlWorker.abuse_update(records[0][8])
        sqlWorker.whitelist(records[0][8], add=True)
        if bot.get_chat_member(message_vote.chat.id, records[0][8]).status != "left" \
                and bot.get_chat_member(message_vote.chat.id, records[0][8]).status != "kicked" \
                and bot.get_chat_member(message_vote.chat.id, records[0][8]).status != "restricted" \
                or bot.get_chat_member(message_vote.chat.id, records[0][8]).is_member:
            bot.edit_message_text("Пользователь " + mention + " уже есть в этом чате. Инвайт отправлен не будет."
                                        + votes_counter,
                                        message_vote.chat.id, message_vote.message_id, parse_mode="html")
            bot.send_message(datalist[0], "Вы уже есть в нужном вам чате. Повторный инвайт выдавать запрещено.")
            return

        try:
            invite = bot.create_chat_invite_link(message_vote.chat.id, expire_date=int(time.time()) + 86400)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text("Ошибка создания инвайт-ссылки для пользователя " + mention
                                        + "! Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id, parse_mode="html")
            bot.send_message(datalist[0], "Ошибка создания инвайт-ссылки для вступления.")
            logging.error(traceback.format_exc())
            return

        try:
            bot.unban_chat_member(message_vote.chat.id, records[0][8], only_if_banned=True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

        bot.edit_message_text("Создана инвайт-ссылка и отправлена запросившему кандидату "
                                    + mention + ".\n" + "Ссылка истечёт через 1 сутки." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id, parse_mode="html")
        bot.send_message(datalist[0], f"Дано добро на вступление в чат {message_vote.chat.title}!\n"
                                            "Ссылка истечёт через 1 сутки.\n"
                               + invite.invite_link)
        if data.rate:
            sqlWorker.update_rate(datalist[0], 0)
    else:
        sqlWorker.abuse_update(datalist[0])
        bot.edit_message_text("К сожалению, запрос вступления пользователя " + mention + " отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id, parse_mode="html")

        bot.send_message(datalist[0], "Запрос на вступление был отклонён." + votes_counter)


def vote_result_userkick(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        until_date = int(time.time()) + datalist[4] if datalist[4] != 0 else None
        if datalist[4] != 0:
            until_text = " на время " + utils.formatted_timer(datalist[4])
        else:
            until_text = "."
        try:
            if bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "administrator":
                bot.restrict_chat_member(message_vote.chat.id, datalist[0], None, can_send_messages=True)
            if datalist[3] == 2:
                if data.binary_chat_mode == 0:
                    sqlWorker.whitelist(datalist[0], remove=True)
                bot.ban_chat_member(message_vote.chat.id, datalist[0])
                bot.edit_message_text("Пользователь " + datalist[1] + " перманентно заблокирован "
                                            + "по милости пользователя " + datalist[2]
                                            + " и не сможет войти в чат до разблокировки." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
                sqlWorker.clear_rate(datalist[0])
            elif datalist[3] == 1:
                bot.ban_chat_member(message_vote.chat.id, datalist[0], until_date=until_date)
                rate = ""
                if not bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot \
                        and not bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "kicked" \
                        and data.rate:
                    sqlWorker.update_rate(datalist[0], -10)
                    rate = "\nРейтинг " + datalist[1] + " снижен на 10 пунктов."

                bot.edit_message_text("Пользователь " + datalist[1] + " заблокирован в чате "
                                            + "по милости пользователя " + datalist[2] + until_text + rate
                                            + votes_counter, message_vote.chat.id, message_vote.message_id)

            elif datalist[3] == 0:
                bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                               can_send_messages=False, can_change_info=False,
                                               can_invite_users=False, can_pin_messages=False, until_date=until_date)
                rate = ""
                if not bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot \
                        and not bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "restricted"\
                        and data.rate:
                    sqlWorker.update_rate(datalist[0], -5)
                    rate = "\nРейтинг " + datalist[1] + " снижен на 5 пунктов."

                bot.edit_message_text("Пользователь " + datalist[1]
                                            + " лишён права переписки в чате по милости пользователя " + datalist[2]
                                            + until_text + rate + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)

        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка блокировки пользователя " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        solution = ("ограничения", "кика", "блокировки")
        bot.edit_message_text("Вопрос " + solution[datalist[3]] + " " + datalist[1] + " отклонён"
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_unban(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            if data.binary_chat_mode == 0:
                sqlWorker.whitelist(datalist[0], add=True)
            bot.unban_chat_member(message_vote.chat.id, datalist[0], True)
            bot.restrict_chat_member(message_vote.chat.id, datalist[0], can_send_messages=True,
                                           can_change_info=True, can_invite_users=True, can_pin_messages=True,
                                           can_send_media_messages=True, can_send_polls=True,
                                           can_send_other_messages=True,
                                           can_add_web_page_previews=True)

            rate = ""
            if not bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot and data.rate:
                sqlWorker.update_rate(datalist[0], 2)
                rate = "\nРейтинг " + datalist[1] + " повышен на 2 пункта."

            bot.edit_message_text("Пользователю " + datalist[1] + " восстановлено право переписки в чате "
                                        + "по милости пользователя " + datalist[2] + rate
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Я не смог вынести из мута пользователя " + datalist[1]
                                        + ".  Недостаточно прав?" + votes_counter, message_vote.chat.id,
                                        message_vote.message_id)
    else:
        bot.edit_message_text("Вопрос снятия ограничений с пользователя " + datalist[1] + " отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_new_usr(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            bot.restrict_chat_member(message_vote.chat.id, datalist[1],
                                       None, True, True, True, True, True, True, True, True)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Я не смог снять ограничения с {datalist[2]} {datalist[0]}! Недостаточно прав?",
                                  message_vote.chat.id, message_vote.message_id)
            return
        bot.edit_message_text(f"Вступление {datalist[2]} {datalist[0]} одобрено!" + votes_counter,
                              message_vote.chat.id, message_vote.message_id)

    else:
        try:
            bot.ban_chat_member(message_vote.chat.id, datalist[1], until_date=int(time.time()) + 60)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Я не смог заблокировать {datalist[2]} {datalist[0]}! Недостаточно прав?",
                                  message_vote.chat.id, message_vote.message_id)
            return
        bot.edit_message_text(f"Вступление {datalist[2]} {datalist[0]} отклонено."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_treshold(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    ban = True if datalist[1] == "threshold_ban" else False
    minimum = True if datalist[1] == "threshold_min" else False
    if ban:
        ban_text = "голосований по вопросам бана"
    elif minimum:
        ban_text = "минимального количества голосов"
    else:
        ban_text = "голосований по стандартным вопросам"
    if datalist[1] == "threshold_min":
        votes_counter = "\nЗа: " + str(records[0][3]) + "\n" + "Против: " + str(records[0][4])
    if accept or records[0][3] > records[0][4] and datalist[1] == "threshold_min":
        if datalist[0] == 0:
            data.thresholds_set(0, ban, minimum)
            bot.edit_message_text(f"Установлен автоматический порог {ban_text}.\n"
                                        + "Теперь требуется " + str(data.thresholds_get(ban))
                                        + " голосов для решения." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            data.thresholds_set(datalist[0], ban, minimum)
            bot.edit_message_text(f"Установлен порог {ban_text}: "
                                        + str(datalist[0]) + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text(f"Вопрос смены порога {ban_text} отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_timer(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[1] == "timer":
            data.timer_set(datalist[0])
            bot.edit_message_text("Установлен таймер основного голосования на "
                                        + utils.formatted_timer(datalist[0]) + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        elif datalist[1] == "timer for ban votes":
            data.timer_set(datalist[0], True)
            bot.edit_message_text("Установлен таймер голосования за бан на " + utils.formatted_timer(datalist[0])
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        timer_text = "" if datalist[1] == "timer" else "для бана "
        bot.edit_message_text("Вопрос смены таймера " + timer_text + "отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_delmsg(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            bot.delete_message(message_vote.chat.id, datalist[0])
            if datalist[2]:
                bot.delete_message(message_vote.chat.id, message_vote.message_id)
                raise Warning
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(traceback.format_exc())
            if datalist[2]:
                bot.delete_message(message_vote.chat.id, message_vote.message_id)
                return
            if "message to delete not found" in str(e):
                bot.edit_message_text("Сообщение, которое требуется удалить, не найдено." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            else:
                bot.edit_message_text("Ошибка удаления сообщения по голосованию." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            return

        bot.edit_message_text("Сообщение пользователя " + datalist[1] + " удалено успешно."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text("Вопрос удаления сообщения отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_op_global(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if data.admin_fixed:
            bot.edit_message_text("Настройки выдачи прав администратора не могут быть перезаписаны "
                                  "(запрещено хостером бота!)"
                                  + votes_counter, message_vote.chat.id, message_vote.message_id)
            return

        data.admin_allowed = datalist[0]
        if not data.admin_fixed:
            sqlWorker.params("allowed_admins", datalist[0])
        bot.edit_message_text("Разрешённые для администраторов права успешно изменены на следующие:"
                              + utils.allowed_list(datalist[0]) + votes_counter,
                              message_vote.chat.id, message_vote.message_id)
        return
    else:
        bot.edit_message_text("Вопрос изменения разрешённых для администраторов прав отклонён" + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_op(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        status = bot.get_chat_member(message_vote.chat.id, datalist[0]).status
        if status != "member" and status != "administrator":
            bot.edit_message_text("Пользователь " + datalist[1]
                                        + " имеет статус, не позволяющий назначить его администратором."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
        try:
            bot.promote_chat_member(message_vote.chat.id, datalist[0],
                                    can_manage_chat=True, **utils.get_promote_args(datalist[2]))
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.edit_message_text(f"Ошибка назначения администратора {datalist[1]}. Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return

        rate = ""
        if all([not bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot,
                data.rate,
                not status == "administrator"]):
            sqlWorker.update_rate(datalist[0], 3)
            rate = "\nРейтинг " + datalist[1] + " повышен на 3 пункта."

        bot.edit_message_text("Пользователь " + datalist[1] + " назначен администратором в чате."
                                    + rate + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text("Вопрос назначения " + datalist[1] + " администратором отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_rank(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "administrator":
            try:
                bot.set_chat_administrator_custom_title(message_vote.chat.id, datalist[0], datalist[2])
                bot.edit_message_text("Звание \"" + datalist[2] + "\" успешно установлено для бота "
                                            + datalist[1] + " пользователем " + datalist[3] + "." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    bot.edit_message_text("Ошибка смены звания для бота " + datalist[1]
                                                + " - в звании не поддерживаются эмодзи." + votes_counter,
                                                message_vote.chat.id, message_vote.message_id)
                    return
                logging.error(traceback.format_exc())
                bot.edit_message_text("Ошибка смены звания для бота " + datalist[1] + "." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            return
        else:
            bot.edit_message_text("Бот " + datalist[1] + " не является администратором. Смена звания невозможна."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
    else:
        bot.edit_message_text("Вопрос смены звания бота " + datalist[1] + " отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_deop(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if bot.get_chat_member(message_vote.chat.id, datalist[0]).status != "administrator":
            bot.edit_message_text("Пользователь " + datalist[1] + " уже не является администратором."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
        try:
            bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                           None, can_send_messages=True)
            bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                           None, True, True, True, True, True, True, True, True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка снятия администратора " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return

        rate = ""
        if not bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot and data.rate:
            sqlWorker.update_rate(datalist[0], -3)
            rate = "\nРейтинг " + datalist[1] + " снижен на 3 пункта."

        bot.edit_message_text("Пользователь " + datalist[1] + " разжалован из админов."
                                    + rate + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text("Вопрос снятия " + datalist[1] + " из администраторов отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_title(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            bot.set_chat_title(message_vote.chat.id, datalist[0])
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка установки названия чата. Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return
        bot.edit_message_text("Название чата успешно сменено на \"" + datalist[0]
                                    + "\" пользователем " + datalist[1] + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text("Вопрос смены названия чата отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_description(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            bot.set_chat_description(message_vote.chat.id, datalist[0])
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text("Ошибка установки описания чата. Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return
        if datalist[0] == "":
            bot.edit_message_text("Описание чата успешно сменено на пустое пользователем "
                                        + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            bot.edit_message_text("Описание чата успешно сменено на\n<code>" + utils.html_fix(datalist[0])
                                        + "</code>\nпользователем " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id, parse_mode="html")
    else:
        bot.edit_message_text("Вопрос смены описания чата отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_chat_pic(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            bot.set_chat_photo(message_vote.chat.id, open(data.path + 'tmp_img', 'rb'))
            bot.edit_message_text("Фотография чата успешно изменена пользователем " + datalist[0]
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        except Exception as e:
            logging.error((str(e)))
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка установки новой фотографии чата." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text("Вопрос смены фотографии чата отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    try:
        os.remove(data.path + "tmp_img")
    except IOError:
        pass


def vote_result_change_rate(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[2] == "up":
            chrate = "увеличил на " + str(records[0][3] - records[0][4])
            sqlWorker.update_rate(datalist[1], records[0][3] - records[0][4])
        else:
            chrate = "уменьшил на " + str(records[0][3] - records[0][4])
            sqlWorker.update_rate(datalist[1], records[0][4] - records[0][3])
        bot.edit_message_text(f"Пользователь {datalist[3]} "
                                    f"{chrate} социальный рейтинг пользователя {datalist[0]}."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text(f"Вопрос изменения социального рейтинга пользователя {datalist[0]} отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_add_allies(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        sqlWorker.abuse_remove(datalist[0])
        sqlWorker.abuse_update(datalist[0])
        sqlWorker.add_ally(datalist[0])
        try:
            ally_title = bot.get_chat(datalist[0]).title
            invite = bot.get_chat(datalist[0]).invite_link
            if invite is None:
                invite = "Инвайт-ссылка на данный чат отсутствует."
            else:
                invite = f"Инвайт ссылка на данный чат: {invite}."
            bot.send_message(datalist[0], f"Установлены союзные отношения с чатом "
                                                f"<b>{utils.html_fix(message_vote.chat.title)}</b>!\n"
                                                f"Ссылка для упрощённого перехода: "
                                                f"{bot.get_chat(message_vote.chat.id).invite_link}.",
                                   parse_mode="html")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            bot.edit_message_text("Ошибка установки союзных отношений с чатом! Информация сохранена в логах бота."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return

        bot.edit_message_text(f"Установлены союзные отношения с чатом "
                                    f"<b>{utils.html_fix(ally_title)}!</b>\n{invite}"
                                    + votes_counter, message_vote.chat.id, message_vote.message_id, parse_mode="html")
    else:
        sqlWorker.abuse_update(datalist[0])
        try:
            bot.edit_message_text(f"Вопрос установки союзных отношения с чатом "
                                        f"{bot.get_chat(datalist[0]).title} отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            bot.send_message(datalist[0], f"Вопрос установки союзных отношения с чатом "
                                                f"{message_vote.chat.title} отклонён." + votes_counter)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Вопрос установки союзных отношения с чатом отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_remove_allies(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        sqlWorker.abuse_remove(datalist[0])
        sqlWorker.remove_ally(datalist[0])
        try:
            ally_title = f" <b>{utils.html_fix(bot.get_chat(datalist[0]).title)}</b> "
            bot.send_message(datalist[0], f"Cоюз с чатом <b>{utils.html_fix(message_vote.chat.title)}</b> "
                                                f"разорван." + votes_counter, parse_mode="html")
        except telebot.apihelper.ApiTelegramException:
            ally_title = " "
        bot.edit_message_text(f"Союзные отношения с чатом{ally_title}разорваны." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id, parse_mode="html")
    else:
        try:
            bot.edit_message_text(f"Вопрос разрыва союзных отношений с чатом "
                                        f"{bot.get_chat(datalist[0]).title} отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            bot.send_message(datalist[0], f"Вопрос разрыва союзных отношения с чатом "
                                                f"{message_vote.chat.title} отклонён." + votes_counter)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Вопрос разрыва союзных отношения с чатом отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_random_cooldown(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        sqlWorker.abuse_random(message_vote.chat.id, datalist[0])
        if datalist[0] == -1:
            bot.edit_message_text("Команда /random отключена." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        elif datalist[0] == 0:
            bot.edit_message_text("Кулдаун команды /random отключён." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            bot.edit_message_text("Установлен порог кулдауна команды /random на значение " +
                                        utils.formatted_timer(datalist[0]) + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        if datalist[0] == 1:
            bot.edit_message_text(f"Вопрос отключения команды /abuse отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        else:
            bot.edit_message_text(f"Вопрос изменения таймера команды /abuse отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_whitelist(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[2] == "add":
            sqlWorker.whitelist(datalist[0], add=True)
            bot.edit_message_text(f"Пользователь {datalist[1]} добавлен в вайтлист."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        else:
            sqlWorker.whitelist(datalist[0], remove=True)
            bot.edit_message_text(f"Пользователь {datalist[1]} удалён из вайтлиста."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        if datalist[2] == "add":
            bot.edit_message_text(f"Вопрос добавления пользователя {datalist[1]} в вайтлист отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        else:
            bot.edit_message_text(f"Вопрос удаления пользователя {datalist[1]} из вайтлиста отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_private_mode(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if data.chat_mode != "mixed":
            bot.edit_message_text("Настройки приватности не могут быть перезаписаны (запрещено хостером бота!)"
                                  + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
        data.binary_chat_mode = datalist[0]
        sqlWorker.params("public_mode", datalist[0])
        bot.edit_message_text(f"Пользователь {datalist[1]} изменил режим приватности чата на {datalist[2]}."
                              + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        bot.edit_message_text(f"Вопрос изменения настроек приватности чата отклонён."
                              + votes_counter, message_vote.chat.id, message_vote.message_id)