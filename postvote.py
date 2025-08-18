import json
import logging
import os
import time
import traceback

import telebot

import utils
from utils import data, bot, sqlWorker
from poll_engine import PostVote, PoolEngine, SilentException, InternalBotException


class UserAdd(PostVote):
    _description = "инвайт пользователя"
    mention = ""

    def post_vote_child(self):
        self.mention = f'<a href="tg://user?id={self.data_list[0]}">{utils.html_fix(self.data_list[1])}</a>'

    def accept(self):
        sqlWorker.abuse_remove(self.data_list[2])
        sqlWorker.whitelist(self.data_list[2], add=True)
        status = bot.get_chat_member(self.message_vote.chat.id, self.data_list[2]).status
        if status not in ["left", "kicked", "restricted"] \
                or bot.get_chat_member(self.message_vote.chat.id, self.data_list[2]).is_member:
            bot.edit_message_text("Пользователь " + self.mention + " уже есть в этом чате. Инвайт отправлен не будет."
                                  + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id, parse_mode="html")
            bot.send_message(self.data_list[0], "Вы уже есть в нужном вам чате. Повторный инвайт выдавать запрещено.")
            return

        try:
            invite = bot.create_chat_invite_link(self.message_vote.chat.id, expire_date=int(time.time()) + 86400)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка создания инвайт-ссылки для пользователя " + self.mention
                                  + "! Недостаточно прав?" + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id, parse_mode="html")
            bot.send_message(self.data_list[0], "Ошибка создания инвайт-ссылки для вступления.")
            raise e

        try:
            bot.unban_chat_member(self.message_vote.chat.id, self.data_list[2], only_if_banned=True)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f'In func postvote.UserAdd.accept: {e}')

        bot.edit_message_text(f"Создана инвайт-ссылка и отправлена запросившему кандидату {self.mention}.\n"
                              f"Ссылка истечёт через 1 сутки." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id, parse_mode="html")
        bot.send_message(self.data_list[0], f"Дано добро на вступление в чат {self.message_vote.chat.title}!\n"
                                            "Ссылка истечёт через 1 сутки.\n" + invite.invite_link)
        if data.rate:
            sqlWorker.update_rate(self.data_list[0], 0)

    def decline(self):
        sqlWorker.abuse_update(self.data_list[0])
        bot.edit_message_text(f"Запрос вступления пользователя {self.mention} был отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id,
                              parse_mode="html")

        bot.send_message(self.data_list[0], "Запрос на вступление был отклонён." + self.votes_counter)


class Ban(PostVote):
    _description = "блокировка пользователя"

    def accept(self):
        until_date = int(time.time()) + self.data_list[4] if self.data_list[4] != 0 else None
        if self.data_list[4] != 0:
            until_text = " на время " + utils.formatted_timer(self.data_list[4])
        else:
            until_text = "."
        try:
            if bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).status == "administrator":
                bot.restrict_chat_member(self.message_vote.chat.id, self.data_list[0], None, can_send_messages=True)
            if self.data_list[3] == 2:
                if data.binary_chat_mode == 0:
                    sqlWorker.whitelist(self.data_list[0], remove=True)
                bot.ban_chat_member(self.message_vote.chat.id, self.data_list[0])
                bot.edit_message_text("Пользователь " + self.data_list[1] + " перманентно заблокирован "
                                      + "по милости пользователя " + self.data_list[2]
                                      + " и не сможет войти в чат до разблокировки."
                                      + self.data_list[5] + self.votes_counter,
                                      self.message_vote.chat.id, self.message_vote.message_id)
                sqlWorker.clear_rate(self.data_list[0])
            elif self.data_list[3] == 1:
                bot.ban_chat_member(self.message_vote.chat.id, self.data_list[0], until_date=until_date)
                rate = "" if not self.change_rate(-10) else f"\nРейтинг {self.data_list[1]} снижен на 10 пунктов."
                bot.edit_message_text(f"Пользователь {self.data_list[1]} заблокирован в чате по милости пользователя "
                                      + self.data_list[2] + until_text + self.data_list[5] + rate
                                      + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

            elif self.data_list[3] == 0:
                bot.restrict_chat_member(self.message_vote.chat.id, self.data_list[0],
                                         can_send_messages=False, can_change_info=False,
                                         can_invite_users=False, can_pin_messages=False, until_date=until_date)
                rate = "" if not self.change_rate(-5) else f"\nРейтинг {self.data_list[1]} снижен на 5 пунктов."

                bot.edit_message_text("Пользователь " + self.data_list[1]
                                      + " лишён права переписки в чате по милости пользователя " + self.data_list[2]
                                      + until_text + self.data_list[5] + rate + self.votes_counter,
                                      self.message_vote.chat.id, self.message_vote.message_id)

        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка блокировки пользователя " + self.data_list[1] + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
            raise e

    def decline(self):
        solution = ("ограничения", "кика", "блокировки")
        bot.edit_message_text("Вопрос " + solution[self.data_list[3]] + " " + self.data_list[1] + " отклонён"
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class UnBan(PostVote):
    _description = "снятие ограничений с пользователя"

    def accept(self):
        try:
            if (data.binary_chat_mode == 0 and
                    not bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).user.is_bot):
                sqlWorker.whitelist(self.data_list[0], add=True)
            sqlWorker.abuse_remove(self.data_list[0])
            bot.unban_chat_member(self.message_vote.chat.id, self.data_list[0], True)
            bot.restrict_chat_member(self.message_vote.chat.id, self.data_list[0], can_send_messages=True,
                                     can_change_info=True, can_invite_users=True, can_pin_messages=True,
                                     can_send_media_messages=True, can_send_polls=True,
                                     can_send_other_messages=True,
                                     can_add_web_page_previews=True)

            rate = "" if not self.change_rate(2) else f"\nРейтинг {self.data_list[1]} повышен на 2 пункта."
            bot.edit_message_text("Пользователю " + self.data_list[1] + " восстановлено право переписки в чате "
                                  + "по милости пользователя " + self.data_list[2] + rate
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Я не смог вынести из мута пользователя " + self.data_list[1]
                                  + ".  Недостаточно прав?" + self.votes_counter, self.message_vote.chat.id,
                                  self.message_vote.message_id)
            raise e

    def decline(self):
        bot.edit_message_text("Вопрос снятия ограничений с пользователя " + self.data_list[1] + " отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class Captcha(PostVote):
    _description = "капча"

    def accept(self):
        sqlWorker.abuse_update(self.data_list[1], timer=3600, force=True)
        try:
            bot.restrict_chat_member(self.message_vote.chat.id, self.data_list[1],
                                     None, True, True, True, True, True, True, True, True)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text(f"Я не смог снять ограничения с {self.data_list[2]} {self.data_list[0]}! "
                                  f"Недостаточно прав?", self.message_vote.chat.id, self.message_vote.message_id)
            raise e
        bot.edit_message_text(f"Вступление {self.data_list[2]} {self.data_list[0]} одобрено!" + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        sqlWorker.abuse_update(self.data_list[1], timer=self.data_list[3])
        try:
            bot.ban_chat_member(self.message_vote.chat.id, self.data_list[1],
                                until_date=int(time.time()) + self.data_list[3])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text(f"Я не смог заблокировать {self.data_list[2]} {self.data_list[0]}! "
                                  f"Недостаточно прав?", self.message_vote.chat.id, self.message_vote.message_id)
            raise e
        bot.edit_message_text(f"Вступление {self.data_list[2]} {self.data_list[0]} отклонено.\n" +
                              f"Следующая попытка будет возможна через {utils.formatted_timer(self.data_list[3])}" +
                              self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class Threshold(PostVote):
    votes_counter = ""
    ban_text = ""
    ban = False
    minimum = False
    _description = "смена порога голосов"

    def post_vote_child(self):
        button_data = json.loads(self.records[0][4])
        counters_yes = 0
        counters_no = 0
        for button in button_data:
            if 'vote!' in button["button_type"]:
                if button["name"] == "Да":
                    counters_yes = len(button["user_list"])
                elif button["name"] == "Нет":
                    counters_no = len(button["user_list"])
        self.ban = True if self.data_list[1] == "threshold_ban" else False
        self.minimum = True if self.data_list[1] == "threshold_min" else False
        if self.ban:
            self.ban_text = "голосований по вопросам бана"
        elif self.minimum:
            self.ban_text = "минимального количества голосов"
        else:
            self.ban_text = "голосований по стандартным вопросам"
        if self.data_list[1] == "threshold_min":
            self.votes_counter = "\nЗа: " + str(counters_yes) + "\n" + "Против: " + str(counters_no)
        if counters_yes > counters_no and self.data_list[1] == "threshold_min":
            self.is_accept = True

    def accept(self):
        if self.data_list[0] == 0:
            data.thresholds_set(0, self.ban, self.minimum)
            bot.edit_message_text(f"Установлен автоматический порог {self.ban_text}.\n"
                                  + "Теперь требуется " + str(data.thresholds_get(self.ban))
                                  + " голосов для решения." + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
        else:
            data.thresholds_set(self.data_list[0], self.ban, self.minimum)
            bot.edit_message_text(f"Установлен порог {self.ban_text}: "
                                  + str(self.data_list[0]) + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос смены порога {self.ban_text} отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class Timer(PostVote):
    _description = "смена таймера для стандартных опросов"
    timer_text = ""

    def accept(self):
        data.timer_set(self.data_list[0])
        bot.edit_message_text("Установлен таймер основного голосования на "
                              + utils.formatted_timer(self.data_list[0]) + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text("Вопрос смены таймера " + self.timer_text + "отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class TimerBan(Timer):
    _description = "смена таймера для бан-опросов"
    timer_text = "для бана "

    def accept(self):
        data.timer_set(self.data_list[0], True)
        bot.edit_message_text("Установлен таймер голосования за бан на " + utils.formatted_timer(self.data_list[0])
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class DelMessage(PostVote):
    _description = "удаление сообщения"

    def accept(self):
        try:
            bot.delete_message(self.message_vote.chat.id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            if "message to delete not found" in str(e):
                bot.edit_message_text("Сообщение, которое требуется удалить, не найдено." + self.votes_counter,
                                      self.message_vote.chat.id, self.message_vote.message_id)
            else:
                bot.edit_message_text("Ошибка удаления сообщения по голосованию." + self.votes_counter,
                                      self.message_vote.chat.id, self.message_vote.message_id)
            self.data_list[2] = False  # Disable silent mode
            raise e

        if self.data_list[2]:
            try:
                bot.delete_message(self.message_vote.chat.id, self.message_vote.message_id)
            except telebot.apihelper.ApiTelegramException as e:
                logging.error(f'In func postvote.DelMessage.accept: {e}')
        else:
            bot.edit_message_text("Сообщение пользователя " + self.data_list[1] + " удалено успешно."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text("Вопрос удаления сообщения отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)

    def final_hook(self, error=False):
        if self.data_list[2]:
            return
        super().final_hook(error)


class GlobalOp(PostVote):
    _description = "изменение разрешённых прав для выдачи"

    def accept(self):
        if data.admin_fixed:
            bot.edit_message_text("Настройки выдачи прав администратора не могут быть перезаписаны "
                                  "(запрещено хостером бота!)"
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            return

        data.admin_allowed = self.data_list[0]
        if not data.admin_fixed:
            sqlWorker.params("allowed_admins", self.data_list[0])
        bot.edit_message_text("Разрешённые для администраторов права успешно изменены на следующие:\n"
                              + utils.allowed_list(self.data_list[0]) + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)
        return

    def decline(self):
        bot.edit_message_text("Вопрос изменения разрешённых для администраторов прав отклонён" + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class OpSetup(PostVote):
    _description = "чек-лист выбора прав администратора"

    def post_vote(self, records, message_vote):
        self.data_list = json.loads(records[0][6])
        self.message_vote = message_vote
        button_data = json.loads(records[0][4])
        for button in button_data:
            if button["button_type"] == "op!_confirmed":
                if button["value"]:
                    return
        by_timer = "инициатором голосования" if int(time.time()) <= records[0][5] else "автоматическим таймером"
        bot.edit_message_text(f"<b>Чек-лист закрыт {by_timer}.</b>", self.message_vote.chat.id,
                              self.message_vote.message_id, parse_mode='html', reply_markup=None)


class GlobalOpSetup(OpSetup):
    _description = "чек-лист выбора глобальных прав"


class Op(PostVote):
    _description = "назначение администратора"

    def accept(self):
        status = bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).status
        if status not in ("member", "administrator"):
            bot.edit_message_text(f"Пользователь {self.data_list[1]} имеет статус, "
                                  f"не позволяющий назначить его администратором."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            raise InternalBotException(f'User {self.data_list[1]} is not a member or administrator.')
        try:
            bot.promote_chat_member(self.message_vote.chat.id, self.data_list[0], **self.data_list[2])
            if not bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).user.is_bot:
                sqlWorker.whitelist(self.data_list[0], add=True)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text(
                f"Ошибка назначения администратора {self.data_list[1]}. Недостаточно прав?" + self.votes_counter,
                self.message_vote.chat.id, self.message_vote.message_id)
            raise e

        rate = ""
        if status != "administrator":
            if self.change_rate(3):
                rate = f"\nРейтинг {self.data_list[1]} повышен на 3 пункта."

        bot.edit_message_text("Пользователь " + self.data_list[1] + " назначен администратором в чате."
                              + rate + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text(
            "Вопрос назначения " + self.data_list[1] + " администратором отклонён." + self.votes_counter,
            self.message_vote.chat.id, self.message_vote.message_id)

    def final_hook(self, error=False):
        try:
            bot.unpin_chat_message(self.message_vote.chat.id, self.message_vote.message_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"I can't unpin message in chat {self.message_vote.chat.id}!\n{e}")
        try:
            if error:
                bot.reply_to(self.message_vote, "Голосование завершено с ошибками. Информация сохранена в логи бота.")
            elif self.is_accept and not bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).user.is_bot:
                bot.reply_to(self.message_vote, f'Голосование завершено! <a href ="tg://user?id={self.data_list[0]}">'
                             + utils.html_fix(self.data_list[1])
                             + "</a>, пожалуйста, не забудь сменить звание!", parse_mode="html")
            else:
                bot.reply_to(self.message_vote, "Голосование завершено!")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())


class Rank(PostVote):
    _description = "смена звания бота"

    def accept(self):
        if bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).status == "administrator":
            try:
                bot.set_chat_administrator_custom_title(self.message_vote.chat.id, self.data_list[0], self.data_list[2])
                bot.edit_message_text("Звание \"" + self.data_list[2] + "\" успешно установлено для бота "
                                      + self.data_list[1] + " пользователем " + self.data_list[
                                          3] + "." + self.votes_counter,
                                      self.message_vote.chat.id, self.message_vote.message_id)
            except telebot.apihelper.ApiTelegramException as e:
                if "ADMIN_RANK_EMOJI_NOT_ALLOWED" in str(e):
                    bot.edit_message_text("Ошибка смены звания для бота " + self.data_list[1]
                                          + " - в звании не поддерживаются эмодзи." + self.votes_counter,
                                          self.message_vote.chat.id, self.message_vote.message_id)
                    return
                bot.edit_message_text("Ошибка смены звания для бота " + self.data_list[1] + "." + self.votes_counter,
                                      self.message_vote.chat.id, self.message_vote.message_id)
                raise e
        else:
            bot.edit_message_text("Бот " + self.data_list[1] + " не является администратором. Смена звания невозможна."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text("Вопрос смены звания бота " + self.data_list[1] + " отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class Deop(PostVote):
    _description = "снятие администратора"

    def accept(self):
        if bot.get_chat_member(self.message_vote.chat.id, self.data_list[0]).status != "administrator":
            bot.edit_message_text("Пользователь " + self.data_list[1] + " уже не является администратором."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            return
        try:
            bot.promote_chat_member(self.message_vote.chat.id, self.data_list[0], can_manage_chat=False)
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка снятия администратора " + self.data_list[1] + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
            raise e

        rate = "" if not self.change_rate(-3) else f"\nРейтинг {self.data_list[1]} снижен на 3 пункта."

        bot.edit_message_text("Пользователь " + self.data_list[1] + " разжалован из администраторов."
                              + rate + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text("Вопрос снятия " + self.data_list[1] + " из администраторов отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class Title(PostVote):
    _description = "смена названия чата"

    def accept(self):
        try:
            bot.set_chat_title(self.message_vote.chat.id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка установки названия чата. Недостаточно прав?" + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
            raise e
        bot.edit_message_text("Название чата успешно сменено на \"" + self.data_list[0]
                              + "\" пользователем " + self.data_list[1] + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text("Вопрос смены названия чата отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class Description(PostVote):
    _description = "смена описания чата"

    def accept(self):
        try:
            bot.set_chat_description(self.message_vote.chat.id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка установки описания чата. Недостаточно прав?" + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
            raise e
        if self.data_list[0] == "":
            bot.edit_message_text("Описание чата успешно сменено на пустое пользователем "
                                  + self.data_list[1] + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
        else:
            bot.edit_message_text("Описание чата успешно сменено на\n<code>" + utils.html_fix(self.data_list[0])
                                  + "</code>\nпользователем " + self.data_list[1] + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id, parse_mode="html")

    def decline(self):
        bot.edit_message_text("Вопрос смены описания чата отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class ChatPic(PostVote):
    _description = "смена аватарки чата"

    def accept(self):
        try:
            bot.set_chat_photo(self.message_vote.chat.id, open(data.path + 'tmp_img', 'rb'))
            bot.edit_message_text("Фотография чата успешно изменена пользователем " + self.data_list[0]
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
        except Exception as e:
            bot.edit_message_text("Ошибка установки новой фотографии чата." + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
            raise e

    def decline(self):
        bot.edit_message_text("Вопрос смены фотографии чата отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def final_hook(self, error=False):
        try:
            os.remove(data.path + "tmp_img")
        except IOError:
            logging.error(traceback.format_exc())
        super().final_hook(error)


class ChangeRate(PostVote):
    _description = "изменение рейтинга"

    def accept(self):
        button_data = json.loads(self.records[0][4])
        counters_yes = 0
        counters_no = 0
        for button in button_data:
            if 'vote!' in button["button_type"]:
                if button["name"] == "Да":
                    counters_yes = len(button["user_list"])
                elif button["name"] == "Нет":
                    counters_no = len(button["user_list"])

        if self.data_list[2] == "up":
            ch_rate = "увеличил на " + str(counters_yes - counters_no)
            sqlWorker.update_rate(self.data_list[1], counters_yes - counters_no)
        else:
            ch_rate = "уменьшил на " + str(counters_yes - counters_no)
            sqlWorker.update_rate(self.data_list[1], counters_no - counters_yes)
        bot.edit_message_text(f"Пользователь {self.data_list[3]} "
                              f"{ch_rate} социальный рейтинг пользователя {self.data_list[0]}."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос изменения социального рейтинга пользователя {self.data_list[0]} отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class AddAllies(PostVote):
    _description = "добавление союзного чата"

    def accept(self):
        sqlWorker.abuse_update(self.data_list[0], force=True)
        sqlWorker.add_ally(self.data_list[0])
        try:
            ally_title = bot.get_chat(self.data_list[0]).title
            invite = bot.get_chat(self.data_list[0]).invite_link
            if invite is None:
                invite = "Инвайт-ссылка на данный чат отсутствует."
            else:
                invite = f"Инвайт ссылка на данный чат: {invite}."
            invite_main = bot.get_chat(self.message_vote.chat.id).invite_link
            if invite_main is None:
                invite_main = "Ссылка для упрощённого перехода отсутствует (недостаточно прав в основном чате?)"
            else:
                invite_main = f"Ссылка для упрощённого перехода: {invite_main}"
            bot.send_message(self.data_list[0], f"Установлены союзные отношения с чатом <b>"
                                                f"{utils.html_fix(self.message_vote.chat.title)}</b>!\n{invite_main}",
                             parse_mode="html", message_thread_id=self.data_list[1])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка установки союзных отношений с чатом! Информация сохранена в логах бота."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            raise e

        bot.edit_message_text(f"Установлены союзные отношения с чатом "
                              f"<b>{utils.html_fix(ally_title)}!</b>\n{invite}"
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id,
                              parse_mode="html")

    def decline(self):
        sqlWorker.abuse_update(self.data_list[0])
        try:
            bot.edit_message_text(f"Вопрос установки союзных отношения с чатом "
                                  f"{bot.get_chat(self.data_list[0]).title} отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            bot.send_message(self.data_list[0], f"Вопрос установки союзных отношений с чатом "
                                                f"{self.message_vote.chat.title} отклонён." + self.votes_counter,
                             message_thread_id=self.data_list[1])
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Вопрос установки союзных отношения с чатом отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class RemoveAllies(PostVote):
    _description = "удаление союзного чата"

    def accept(self):
        sqlWorker.abuse_remove(self.data_list[0])
        sqlWorker.remove_ally(self.data_list[0])
        try:
            ally_title = f" <b>{utils.html_fix(bot.get_chat(self.data_list[0]).title)}</b> "
            if self.data_list[2]:
                bot.send_message(self.data_list[0],
                                 f"Cоюз с чатом <b>{utils.html_fix(self.message_vote.chat.title)}</b> разорван." +
                                 self.votes_counter, parse_mode="html", message_thread_id=self.data_list[1])
        except telebot.apihelper.ApiTelegramException:
            ally_title = " "
        bot.edit_message_text(f"Союзные отношения с чатом{ally_title}разорваны." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id, parse_mode="html")

    def decline(self):
        try:
            bot.edit_message_text(f"Вопрос разрыва союзных отношений с чатом "
                                  f"{bot.get_chat(self.data_list[0]).title} отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            if self.data_list[2]:
                bot.send_message(self.data_list[0], f"Вопрос разрыва союзных отношения с чатом "
                                                    f"{self.message_vote.chat.title} отклонён." + self.votes_counter)
        except telebot.apihelper.ApiTelegramException:
            bot.edit_message_text(f"Вопрос разрыва союзных отношения с чатом отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class RandomCooldown(PostVote):
    _description = "изменение кулдауна команды /random"

    def accept(self):
        sqlWorker.abuse_random(self.message_vote.chat.id, self.data_list[0])
        if self.data_list[0] == -1:
            bot.edit_message_text("Команда /random отключена." + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
        elif self.data_list[0] == 0:
            bot.edit_message_text("Кулдаун команды /random отключён." + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)
        else:
            bot.edit_message_text("Установлен порог кулдауна команды /random на значение " +
                                  utils.formatted_timer(self.data_list[0]) + self.votes_counter,
                                  self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        if self.data_list[0] == 1:
            bot.edit_message_text(f"Вопрос отключения команды /random отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
        else:
            bot.edit_message_text(f"Вопрос изменения таймера команды /random отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class Whitelist(PostVote):
    _description = "редактирование вайтлиста"

    def accept(self):
        if self.data_list[2] == "add":
            sqlWorker.whitelist(self.data_list[0], add=True)
            bot.edit_message_text(f"Пользователь {self.data_list[1]} добавлен в вайтлист."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
        else:
            sqlWorker.whitelist(self.data_list[0], remove=True)
            bot.edit_message_text(f"Пользователь {self.data_list[1]} удалён из вайтлиста."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        if self.data_list[2] == "add":
            bot.edit_message_text(f"Вопрос добавления пользователя {self.data_list[1]} в вайтлист отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
        else:
            bot.edit_message_text(f"Вопрос удаления пользователя {self.data_list[1]} из вайтлиста отклонён."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class PrivateMode(PostVote):
    _description = "изменение настроек приватности чата"

    def accept(self):
        if data.chat_mode != "mixed":
            bot.edit_message_text("Настройки приватности не могут быть перезаписаны (запрещено хостером бота!)"
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            return
        data.binary_chat_mode = self.data_list[0]
        sqlWorker.params("public_mode", self.data_list[0])
        bot.edit_message_text(f"Пользователь {self.data_list[1]} изменил режим приватности чата на {self.data_list[2]}."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос изменения настроек приватности чата отклонён."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class Topic(PostVote):
    _description = "удаление топика"

    def accept(self):
        try:
            bot.delete_forum_topic(data.main_chat_id, self.data_list[0])
        except telebot.apihelper.ApiTelegramException as e:
            bot.edit_message_text("Ошибка удаления топика! Информация сохранена в логах бота."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
            raise e
        try:
            bot.send_message(data.main_chat_id, f"Пользователь {self.data_list[1]} удалил топик {self.data_list[2]}."
                             + self.votes_counter, message_thread_id=data.thread_id)
        except telebot.apihelper.ApiTelegramException:
            pass
        raise SilentException

    def decline(self):
        bot.edit_message_text(f"Вопрос удаления топика отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class AddRules(PostVote):
    _description = "добавление правил"

    def accept(self):
        sqlWorker.params("rules", self.data_list[0])
        bot.edit_message_text(f"Пользователь {utils.html_fix(self.data_list[1])} установил следующие правила чата:\n"
                              f"<b>{utils.html_fix(self.data_list[0])}</b>" + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id, parse_mode="html")

    def decline(self):
        bot.edit_message_text(f"Вопрос добавления правил отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class RemoveRules(PostVote):
    _description = "удаление правил"

    def accept(self):
        sqlWorker.params("rules", "")
        bot.edit_message_text(f"Пользователь {self.data_list[1]} удалил правила чата!"
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        bot.edit_message_text(f"Вопрос удаления правил отклонён." + self.votes_counter,
                              self.message_vote.chat.id, self.message_vote.message_id)


class Shield(PostVote):
    _description = "перенастройка защиты чата"

    def accept(self):
        sqlWorker.params("shield", rewrite_value=int(time.time()) + self.data_list[0])
        if self.data_list[0] == 0:
            bot.edit_message_text(f"Пользователь {self.data_list[1]} отключил режим защиты чата."
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)
        else:
            bot.edit_message_text(f"Пользователь {self.data_list[1]} включил режим защиты чата на срок "
                                  f"{utils.formatted_timer(self.data_list[0])}"
                                  + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        vote_type = "отключения" if self.data_list[0] == 0 else "включения"
        bot.edit_message_text(f"Предложение {vote_type} режима защиты чата отклонено!"
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class VotePrivacy(PostVote):
    _description = "изменение типа приватности голосований"

    def accept(self):
        sqlWorker.params("vote_privacy", rewrite_value=self.data_list[0])
        data.vote_privacy = self.data_list[0]
        vote_type = "включил" if self.data_list[0] else "отключил"
        bot.edit_message_text(f"Пользователь {self.data_list[1]} {vote_type} приватность голосований."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)

    def decline(self):
        vote_type = "включения" if self.data_list[0] else "отключения"
        bot.edit_message_text(f"Предложение {vote_type} приватности голосований отклонено."
                              + self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id)


class CustomPoll(PostVote):
    _description = "пользовательский опрос"

    def post_vote(self, records, message_vote):
        self.data_list = json.loads(records[0][6])
        self.message_vote = message_vote
        votes_private = True
        button_data = json.loads(records[0][4])
        for button in button_data:
            if button["button_type"] == "user_votes":
                votes_private = False

        counters_yes = 0
        counters_no = 0
        if self.data_list[2]:
            self.votes_counter = "\nГолоса за варианты ответа:"
            for button in button_data:
                if 'vote!' in button["button_type"]:
                    if votes_private:
                        self.votes_counter += f'\n{button["name"]} - {len(button["user_list"])}'
                    else:
                        self.votes_counter += f'\n{button["name"]} - {self.get_voted_usernames(button["user_list"])}'
        else:
            for button in button_data:
                if 'vote!' in button["button_type"]:
                    if button["name"] == "Да":
                        if votes_private:
                            counters_yes = len(button["user_list"])
                        else:
                            counters_yes = self.get_voted_usernames(button["user_list"])
                    elif button["name"] == "Нет":
                        if votes_private:
                            counters_no = len(button["user_list"])
                        else:
                            counters_no = self.get_voted_usernames(button["user_list"])
            self.votes_counter = f"\nЗа: {counters_yes}\nПротив: {counters_no}"
        self.records = records
        self.accept()
        self.final_hook()

    def accept(self):
        bot.edit_message_text(f"Опрос завершён. Текст опроса: <b>{utils.html_fix(self.data_list[0])}</b>" +
                              f"\nДлительность опроса - {utils.formatted_timer(int(time.time()) - self.data_list[1])}" +
                              self.votes_counter, self.message_vote.chat.id, self.message_vote.message_id,
                              parse_mode="html")

    def final_hook(self, error=False):
        try:
            bot.unpin_chat_message(self.message_vote.chat.id, self.message_vote.message_id)
        except telebot.apihelper.ApiTelegramException as e:
            logging.error(f"I can't unpin message in chat {self.message_vote.chat.id}!\n{e}")
        try:
            bot.reply_to(self.message_vote, "Опрос завершён!")
        except telebot.apihelper.ApiTelegramException:
            logging.error(traceback.format_exc())


def post_vote_list_init():
    post_vote_list = {
        "invite": UserAdd(),
        "ban": Ban(),
        "unban": UnBan(),
        "threshold": Threshold(),
        "timer": Timer(),
        "timer for ban votes": TimerBan(),
        "delete message": DelMessage(),
        "op": Op(),
        "deop": Deop(),
        "title": Title(),
        "chat picture": ChatPic(),
        "description": Description(),
        "rank": Rank(),
        "captcha": Captcha(),
        "change rate": ChangeRate(),
        "add allies": AddAllies(),
        "remove allies": RemoveAllies(),
        "timer for random cooldown": RandomCooldown(),
        "whitelist": Whitelist(),
        "global op permissions": GlobalOp(),
        "private mode": PrivateMode(),
        "remove topic": Topic(),
        "add rules": AddRules(),
        "remove rules": RemoveRules(),
        "custom poll": CustomPoll(),
        "shield": Shield(),
        "vote_privacy": VotePrivacy(),
        "global op setup": GlobalOpSetup(),
        "op setup": OpSetup(),
    }

    PoolEngine.post_vote_list.update(post_vote_list)
