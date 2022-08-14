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
        utils.bot.send_message(datalist[0], "Дано добро на вступление! Glory to 4\\<!\nСсылка истечёт через 1 сутки.\n"
                               + invite.invite_link)
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
            elif datalist[3] == 1:
                utils.bot.ban_chat_member(message_vote.chat.id, datalist[0], until_date=until_date)
                utils.bot.edit_message_text("Пользователь " + datalist[1] + " кикнут из чата "
                                            + "по милости пользователя " + datalist[2]
                                            + until_text + votes_counter,
                                            message_vote.chat.id, message_vote.message_id)
            elif datalist[3] == 0:
                utils.bot.restrict_chat_member(message_vote.chat.id, datalist[0],
                                               can_send_messages=False, can_change_info=False,
                                               can_invite_users=False, can_pin_messages=False, until_date=until_date)
                utils.bot.edit_message_text("Пользователь " + datalist[1]
                                            + " лишён права переписки в чате по милости пользователя " + datalist[2]
                                            + until_text + votes_counter,
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
            utils.bot.edit_message_text("Пользователю " + datalist[1] + " восстановлено право переписки в чате "
                                        + "по милости пользователя " + datalist[2] + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
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
            utils.bot.edit_message_text("Установлен таймер основного голосования на " + str(datalist[0]) + " секунд."
                                        + votes_counter, message_vote.chat.id, message_vote.message_id)
        elif datalist[1] == "timer_ban":
            utils.global_timer_ban = datalist[0]
            utils.bot.edit_message_text("Установлен таймер голосования за бан на " + str(datalist[0]) + " секунд."
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
                return
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
        utils.bot.edit_message_text("Пользователь " + datalist[1] + " назначен администратором в чате." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)
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
        utils.bot.edit_message_text("Пользователь " + datalist[1] + " разжалован из админов." + votes_counter,
                                    message_vote.chat.id, message_vote.message_id)
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
            utils.bot.set_chat_photo(message_vote.chat.id, open('tmp_img', 'rb'))
            os.remove("tmp_img")
        except Exception as e:
            logging.error((str(e)))
            logging.error(traceback.format_exc())
            try:
                os.remove("tmp_img")
            except IOError:
                pass
            utils.bot.edit_message_text("Ошибка установки новой фотографии чата." + votes_counter,
                                        message_vote.chat.id, message_vote.message_id)
            return
        utils.bot.edit_message_text("Фотография чата успешно изменена пользователем " + datalist[0]
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
    else:
        try:
            os.remove("tmp_img")
        except IOError:
            pass
        utils.bot.edit_message_text("Вопрос смены фотографии чата отклонён."
                                    + votes_counter, message_vote.chat.id, message_vote.message_id)
