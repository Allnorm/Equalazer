import logging
import os
import time
import traceback

import telebot

import sql_worker
import utils


def vote_result_useradd(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    # mention = "[" + datalist[1] + "](tg://user?id=" + str(datalist[0]) + ")"
    mention = "<a href=\"tg://user?id=" + str(datalist[0]) + "\">" + utils.html_fix(datalist[1]) + "</a>"
    if accept:
        sql_worker.abuse_remove(records[0][8])
        sql_worker.abuse_update(records[0][8])
        sql_worker.whitelist(records[0][8], add=True)
        if utils.bot.get_chat_member(message_vote.chat.id, records[0][8]).status != "left" \
                and utils.bot.get_chat_member(message_vote.chat.id, records[0][8]).status != "kicked" \
                and utils.bot.get_chat_member(message_vote.chat.id, records[0][8]).status != "restricted" \
                or utils.bot.get_chat_member(message_vote.chat.id, records[0][8]).is_member:
            utils.bot.edit_message_text("Пользователь " + mention + " уже есть в этом чате. Инвайт отправлен не будет."
                                        + votes_counter,
                                        message_vote.chat.id, message_vote.message_id, parse_mode="html")
            utils.bot.send_message(datalist[0], "Вы уже есть в нужном вам чате. Повторный инвайт выдавать запрещено.")
            return

        try:
            invite = utils.bot.create_chat_invite_link(message_vote.chat.id, expire_date=int(time.time()) + 86400)
        except telebot.apihelper.ApiTelegramException:
            utils.bot.edit_message_text("Ошибка создания инвайт-ссылки для пользователя " + mention
                                        + "! Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id, parse_mode="html")
            utils.bot.send_message(datalist[0], "Ошибка создания инвайт-ссылки для вступления.")
            logging.error(traceback.format_exc())
            return

        try:
            utils.bot.unban_chat_member(message_vote.chat.id, records[0][8], only_if_banned=True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())

        utils.bot.edit_message_text("Создана инвайт-ссылка и отправлена запросившему кандидату "
                                    + mention + ".\n" + "Ссылка истечёт через 1 сутки." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id, parse_mode="html")
        utils.bot.send_message(datalist[0], f"Дано добро на вступление в чат {message_vote.chat.title}!\n"
                                            "Ссылка истечёт через 1 сутки.\n"
                               + invite.invite_link)
        sql_worker.update_rate(datalist[0], 0)
    else:
        sql_worker.abuse_update(datalist[0])
        utils.bot.edit_message_text("К сожалению, запрос вступления пользователя " + mention + " отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id, parse_mode="html")

        utils.bot.send_message(datalist[0], "Запрос на вступление был отклонён." + votes_counter)


def vote_result_userkick(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        until_date = int(time.time()) + datalist[4] if datalist[4] != 0 else None
        if datalist[4] != 0:
            until_text = " на время " + utils.formatted_timer(datalist[4])
        else:
            until_text = "."
        try:
            if utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "administrator":
                utils.bot.restrict_chat_member(message_vote.chat.id, datalist[0], None, can_send_messages=True)
            if datalist[3] == 2:
                sql_worker.whitelist(datalist[0], remove=True)
                utils.bot.ban_chat_member(message_vote.chat.id, datalist[0])
                utils.bot.edit_message_text("Пользователь " + datalist[1] + " перманентно забанен "
                                            + "по милости пользователя " + datalist[2]
                                            + " и не сможет войти в чат до разблокировки." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
                sql_worker.clear_rate(datalist[0])
            elif datalist[3] == 1:
                utils.bot.ban_chat_member(message_vote.chat.id, datalist[0], until_date=until_date)

                rate = ""
                if not utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot:
                    sql_worker.update_rate(datalist[0], -10)
                    rate = "\nРейтинг " + datalist[1] + " снижен на 10 пунктов."

                utils.bot.edit_message_text("Пользователь " + datalist[1] + " кикнут из чата "
                                            + "по милости пользователя " + datalist[2] + until_text + rate
                                            + votes_counter, message_vote.chat.id, message_vote.message_id)

            elif datalist[3] == 0:
                utils.bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                               can_send_messages=False, can_change_info=False,
                                               can_invite_users=False, can_pin_messages=False, until_date=until_date)
                rate = ""
                if not utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot:
                    sql_worker.update_rate(datalist[0], -5)
                    rate = "\nРейтинг " + datalist[1] + " снижен на 5 пунктов."

                utils.bot.edit_message_text("Пользователь " + datalist[1]
                                            + " лишён права переписки в чате по милости пользователя " + datalist[2]
                                            + until_text + rate + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)

        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Ошибка блокировки пользователя " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        solution = ("ограничения", "кика", "блокировки")
        utils.bot.edit_message_text("Вопрос " + solution[datalist[3]] + " " + datalist[1] + " отклонён"
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_unban(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            sql_worker.whitelist(datalist[0], add=True)
            utils.bot.unban_chat_member(message_vote.chat.id, datalist[0], True)
            utils.bot.restrict_chat_member(message_vote.chat.id, datalist[0], can_send_messages=True,
                                           can_change_info=True, can_invite_users=True, can_pin_messages=True,
                                           can_send_media_messages=True, can_send_polls=True,
                                           can_send_other_messages=True,
                                           can_add_web_page_previews=True)

            rate = ""
            if not utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot:
                sql_worker.update_rate(datalist[0], 2)
                rate = "\nРейтинг " + datalist[1] + " повышен на 2 пункта."

            utils.bot.edit_message_text("Пользователю " + datalist[1] + " восстановлено право переписки в чате "
                                        + "по милости пользователя " + datalist[2] + rate
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Я не смог вынести из мута пользователя " + datalist[1]
                                        + ".  Недостаточно прав?" + votes_counter, message_vote.chat.id,
                                        message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос снятия ограничений с пользователя " + datalist[1] + " отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_treshold(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[0] == "auto":
            utils.auto_thresholds = True
            utils.auto_thresholds_init(message_vote.chat.id)
            utils.bot.edit_message_text("Установлен автоматический порог голосования для стандартных вопросов.\n"
                                        + "Теперь требуется " + str(utils.votes_need)
                                        + " голосов для решения." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            utils.auto_thresholds = False
            utils.votes_need = datalist[0]
            utils.bot.edit_message_text("Установлен порог голосования для стандартных вопросов: "
                                        + str(datalist[0]) + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос смены порога голосования для стандартных вопросов отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_new_usr(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        utils.bot.restrict_chat_member(message_vote.chat.id, datalist[1],
                                       None, True, True, True, True, True, True, True, True)
        utils.bot.edit_message_text(f"Вступление {datalist[2]} {datalist[0]} одобрено!" + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)

    else:
        utils.bot.ban_chat_member(message_vote.chat.id, datalist[1], until_date=int(time.time()) + 60)
        utils.bot.edit_message_text(f"Вступление {datalist[2]} {datalist[0]} отклонено."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_treshold_ban(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[0] == "auto":
            utils.auto_thresholds_ban = True
            utils.auto_thresholds_init(message_vote.chat.id)
            utils.bot.edit_message_text("Установлен автоматический порог голосования для бана.\n"
                                        + "Теперь требуется " + str(utils.votes_need_ban)
                                        + " голосов для решения." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            utils.auto_thresholds_ban = False
            utils.votes_need_ban = datalist[0]
            utils.bot.edit_message_text("Установлен порог голосования для бана: " + str(datalist[0])
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос смены порога голосования для бана отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_timer(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[1] == "timer":
            utils.global_timer = datalist[0]
            utils.bot.edit_message_text("Установлен таймер основного голосования на "
                                        + utils.formatted_timer(datalist[0]) + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        elif datalist[1] == "timer for ban votes":
            utils.global_timer_ban = datalist[0]
            utils.bot.edit_message_text("Установлен таймер голосования за бан на " + utils.formatted_timer(datalist[0])
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        ban = "" if datalist[1] == "timer" else "для бана "
        utils.bot.edit_message_text("Вопрос смены таймера " + ban + "отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_delmsg(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            utils.bot.delete_message(message_vote.chat.id, datalist[0])
            if datalist[2]:
                utils.bot.delete_message(message_vote.chat.id, message_vote.message_id)
                raise Warning
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(traceback.format_exc())
            if datalist[2]:
                utils.bot.delete_message(message_vote.chat.id, message_vote.message_id)
                return
            if "message to delete not found" in str(e):
                utils.bot.edit_message_text("Сообщение, которое требуется удалить, не найдено." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            else:
                utils.bot.edit_message_text("Ошибка удаления сообщения по голосованию." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            return

        utils.bot.edit_message_text("Сообщение пользователя " + datalist[1] + " удалено успешно."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос удаления сообщения отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_op(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "administrator":
            utils.bot.edit_message_text("Пользователь " + datalist[1]
                                        + " уже является администратором." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return
        if utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).status != "member":
            utils.bot.edit_message_text("Пользователь " + datalist[1]
                                        + " имеет статус, не позволяющий назначить его администратором."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
        try:
            utils.bot.promote_chat_member(message_vote.chat.id, datalist[0], can_manage_chat=True,
                                          can_pin_messages=True, can_manage_voice_chats=True, can_invite_users=True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Ошибка назначения администратора " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return

        rate = ""
        if not utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot:
            sql_worker.update_rate(datalist[0], 3)
            rate = "\nРейтинг " + datalist[1] + " повышен на 3 пункта."

        utils.bot.edit_message_text("Пользователь " + datalist[1] + " назначен администратором в чате."
                                    + rate + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос назначения " + datalist[1] + " администратором отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_rank(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).status == "administrator":
            try:
                utils.bot.set_chat_administrator_custom_title(message_vote.chat.id, datalist[0], datalist[2])
                utils.bot.edit_message_text("Звание \"" + datalist[2] + "\" успешно установлено для бота "
                                            + datalist[1] + " пользователем " + datalist[3] + "." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    utils.bot.edit_message_text("Ошибка смены звания для бота " + datalist[1]
                                                + " - в звании не поддерживаются эмодзи." + votes_counter,
                                                message_vote.chat.id, message_vote.message_id)
                    return
                logging.error(traceback.format_exc())
                utils.bot.edit_message_text("Ошибка смены звания для бота " + datalist[1] + "." + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            return
        else:
            utils.bot.edit_message_text("Бот " + datalist[1] + " не является администратором. Смена звания невозможна."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
    else:
        utils.bot.edit_message_text("Вопрос смены звания бота " + datalist[1] + " отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_deop(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).status != "administrator":
            utils.bot.edit_message_text("Пользователь " + datalist[1] + " уже не является администратором."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return
        try:
            utils.bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                           None, can_send_messages=True)
            utils.bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                           None, True, True, True, True, True, True, True, True)
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Ошибка снятия администратора " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return

        rate = ""
        if not utils.bot.get_chat_member(message_vote.chat.id, datalist[0]).user.is_bot:
            sql_worker.update_rate(datalist[0], -3)
            rate = "\nРейтинг " + datalist[1] + " снижен на 3 пункта."

        utils.bot.edit_message_text("Пользователь " + datalist[1] + " разжалован из админов."
                                    + rate + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос снятия " + datalist[1] + " из администраторов отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_title(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            utils.bot.set_chat_title(message_vote.chat.id, datalist[0])
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Ошибка установки названия чата. Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return
        utils.bot.edit_message_text("Название чата успешно сменено на \"" + datalist[0]
                                    + "\" пользователем " + datalist[1] + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос смены названия чата отклонён." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)


def vote_result_description(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        description = datalist[0] if datalist[0] != "" else None
        try:
            utils.bot.set_chat_description(message_vote.chat.id, datalist[0])
        except telebot.apihelper.ApiTelegramException:
            utils.bot.edit_message_text("Ошибка установки описания чата. Недостаточно прав?" + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return
        if description is None:
            utils.bot.edit_message_text("Описание чата успешно сменено на пустое пользователем "
                                        + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            utils.bot.edit_message_text("Описание чата успешно сменено на\n<code>" + datalist[0]
                                        + "</code>\nпользователем " + datalist[1] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id, parse_mode="html")
    else:
        utils.bot.edit_message_text("Вопрос смены описания чата отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_chat_pic(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        try:
            utils.bot.set_chat_photo(message_vote.chat.id, open(utils.PATH + 'tmp_img', 'rb'))
            utils.bot.edit_message_text("Фотография чата успешно изменена пользователем " + datalist[0]
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        except Exception as e:
            logging.error((str(e)))
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Ошибка установки новой фотографии чата." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text("Вопрос смены фотографии чата отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    try:
        os.remove(utils.PATH + "tmp_img")
    except IOError:
        pass


def vote_result_change_rate(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        if datalist[2] == "up":
            chrate = "увеличил на " + str(records[0][3] - records[0][4])
            sql_worker.update_rate(datalist[1], records[0][3] - records[0][4])
        else:
            chrate = "уменьшил на " + str(records[0][3] - records[0][4])
            sql_worker.update_rate(datalist[1], records[0][4] - records[0][3])
        utils.bot.edit_message_text(f"Пользователь {datalist[3]} "
                                    f"{chrate} социальный рейтинг пользователя {datalist[0]}."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        utils.bot.edit_message_text(f"Вопрос изменения социального рейтинга пользователя {datalist[0]} отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_add_allies(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        sql_worker.abuse_remove(datalist[0])
        sql_worker.abuse_update(datalist[0])
        sql_worker.add_ally(datalist[0])
        try:
            ally_title = utils.bot.get_chat(datalist[0]).title
            invite = utils.bot.get_chat(datalist[0]).invite_link
            if invite is None:
                invite = "Инвайт-ссылка на данный чат отсутствует."
            else:
                invite = f"Инвайт ссылка на данный чат: {invite}."
            utils.bot.send_message(datalist[0], f"Установлены союзные отношения с чатом "
                                                f"<b>{utils.html_fix(message_vote.chat.title)}</b>!\n"
                                                f"Ссылка для упрощённого перехода: "
                                                f"{utils.bot.get_chat(message_vote.chat.id).invite_link}.",
                                   parse_mode="html")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())
            utils.bot.edit_message_text("Ошибка установки союзных отношений с чатом! Информация сохранена в логах бота."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            return

        utils.bot.edit_message_text(f"Установлены союзные отношения с чатом "
                                    f"<b>{utils.html_fix(ally_title)}!</b>\n{invite}"
                                    + votes_counter, message_vote.chat.id, message_vote.message_id, parse_mode="html")
    else:
        sql_worker.abuse_update(datalist[0])
        try:
            utils.bot.edit_message_text(f"Вопрос установки союзных отношения с чатом "
                                        f"{utils.bot.get_chat(datalist[0]).title} отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            utils.bot.send_message(datalist[0], f"Вопрос установки союзных отношения с чатом "
                                                f"{message_vote.chat.title} отклонён." + votes_counter)
        except telebot.apihelper.ApiTelegramException:
            utils.bot.edit_message_text(f"Вопрос установки союзных отношения с чатом отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_remove_allies(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        sql_worker.abuse_remove(datalist[0])
        sql_worker.remove_ally(datalist[0])
        try:
            ally_title = f" <b>{utils.html_fix(utils.bot.get_chat(datalist[0]).title)}</b> "
            utils.bot.send_message(datalist[0], f"Cоюз с чатом <b>{utils.html_fix(message_vote.chat.title)}</b> "
                                                f"разорван." + votes_counter, parse_mode="html")
        except telebot.apihelper.ApiTelegramException:
            ally_title = " "
        utils.bot.edit_message_text(f"Союзные отношения с чатом{ally_title}разорваны." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id, parse_mode="html")
    else:
        try:
            utils.bot.edit_message_text(f"Вопрос разрыва союзных отношений с чатом "
                                        f"{utils.bot.get_chat(datalist[0]).title} отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
            utils.bot.send_message(datalist[0], f"Вопрос разрыва союзных отношения с чатом "
                                                f"{message_vote.chat.title} отклонён." + votes_counter)
        except telebot.apihelper.ApiTelegramException:
            utils.bot.edit_message_text(f"Вопрос разрыва союзных отношения с чатом отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)


def vote_result_random_cooldown(records, message_vote, votes_counter, accept):
    datalist = eval(records[0][6])
    if accept:
        sql_worker.abuse_random(message_vote.chat.id, datalist[0])
        if datalist[0] == -1:
            utils.bot.edit_message_text("Команда /random отключена." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        elif datalist[0] == 0:
            utils.bot.edit_message_text("Кулдаун команды /random отключён." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
        else:
            utils.bot.edit_message_text("Установлен порог кулдауна команды /random на значение " +
                                        utils.formatted_timer(datalist[0]) + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
    else:
        if datalist[0] == 1:
            utils.bot.edit_message_text(f"Вопрос отключения команды /abuse отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        else:
            utils.bot.edit_message_text(f"Вопрос изменения таймера команды /abuse отклонён."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
