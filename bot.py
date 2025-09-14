# bot.py
import os
import json
import random
import logging
from datetime import datetime, timedelta

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackQueryHandler, CallbackContext
)
import telegramcalendar

# ---------------------- Logging ----------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------------- Constants ----------------------
REMINDER_FILE = "reminder.json"
NAME, DATE_Q, TIME_Q, INFO, OPT = range(5)
UTC_1 = 0

# ---------------------- JSON Helpers ----------------------
def load_store(path=REMINDER_FILE):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_store(data, path=REMINDER_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------------- Reminder JSON Utilities ----------------------
def json_editor(user, key, value):
    user = str(user)
    data = load_store()
    if "reminder" not in data:
        data["reminder"] = {}
    if user not in data["reminder"]:
        data["reminder"][user] = {"utc": 0, "reminder": []}
    if key == "name":
        data["reminder"][user]["reminder"].insert(0, {})
    data["reminder"][user]["reminder"][0][key] = value
    save_store(data)

def json_getter(user):
    user = str(user)
    data = load_store()
    if user not in data.get("reminder", {}) or not data["reminder"][user]["reminder"]:
        return None
    element = data["reminder"][user]["reminder"][0]
    name = element.get("name")
    date = element.get("date")
    _time = element.get("time")
    r_id = element.get("id")
    opt_inf = element.get("opt_inf")
    return name, date, _time, r_id, opt_inf

def json_deleter(user, r_id=None, current=False):
    user = str(user)
    data = load_store()
    if user not in data.get("reminder", {}):
        return
    reminder_list = data["reminder"][user]["reminder"]
    if current:
        if reminder_list:
            reminder_list.pop(0)
    elif r_id is not None:
        data["reminder"][user]["reminder"] = [r for r in reminder_list if r.get("id") != r_id]
    save_store(data)

def json_utc(user, utc=None):
    user = str(user)
    data = load_store()
    if user not in data.get("reminder", {}):
        data.setdefault("reminder", {})[user] = {"utc": 0, "reminder": []}
    if utc is None:
        return data["reminder"][user].get("utc", 0)
    else:
        data["reminder"][user]["utc"] = utc
        save_store(data)

# ---------------------- Reminder Filter ----------------------
def passes_filter(reminder_obj: dict, chat_id: int) -> bool:
    data = load_store()
    filters = data.get("filters", {})
    keyword = filters.get(str(chat_id))
    if not keyword:
        return True
    description = reminder_obj.get("description", "")
    return keyword.lower() in description.lower()

# ---------------------- Reminder Notification ----------------------
def notification(context: CallbackContext):
    job = context.job
    chat_id = str(job.context[0])
    name, date, _time, username, r_id, *rest = job.context[1:]
    information = rest[0] if rest else None

    reminder_obj = {"description": information or name}
    if not passes_filter(reminder_obj, chat_id):
        logger.info(f"Skipping reminder for chat {chat_id} due to filter")
        json_deleter(username, r_id=r_id)
        return

    message_text = f"\U0001F4A1 *Reminder*\U0001F4A1\n\nAppointment: {name}"
    if information:
        message_text += f"\nInformation: {information}"
    message_text += f"\nScheduled for {date} - {_time}\nYour appointment is in 30 minutes!"

    reply_keyboard = [["/start", "/list", "/time"]]
    context.bot.send_message(chat_id=chat_id, text=message_text, parse_mode="markdown",
                             reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    json_deleter(username, r_id=r_id)

# ---------------------- Command Handlers ----------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "*\U0001F4CD Reminder Setup *\U0001F4CD\n\nWhat should be the name of the appointment?",
        parse_mode="markdown"
    )
    return NAME

def name(update: Update, context: CallbackContext):
    appointment_name = update.message.text
    if appointment_name == "/cancel":
        return cancel(update, context)
    chat_id = update.message.chat_id
    json_editor(chat_id, "name", appointment_name)

    update.message.reply_text(
        f"\U0001F4C5 *Reminder Setup*\U0001F4C5\n\nWhen do you want to be reminded for *{appointment_name}*?",
        parse_mode="markdown",
        reply_markup=telegramcalendar.create_calendar()
    )
    return DATE_Q

def inline_handler(update: Update, context: CallbackContext):
    selected, date = telegramcalendar.process_calendar_selection(context.bot, update)
    if selected:
        chat_id = update.callback_query.from_user.id
        json_editor(chat_id, "date", date.strftime("%d/%m/%Y"))
        context.bot.send_message(chat_id=chat_id, text=f"You selected {date.strftime('%d/%m/%Y')}", reply_markup=ReplyKeyboardRemove())
        context.bot.send_message(chat_id=chat_id,
                                 text="\U0001F553 *Reminder Setup* \U0001F553\nWhich *time* do you want to be reminded?",
                                 parse_mode="markdown",
                                 reply_markup=telegramcalendar.create_clock(user=chat_id))
        return TIME_Q

def inline_handler2(update: Update, context: CallbackContext):
    selected, _time = telegramcalendar.process_clock_selection(context.bot, update)
    if selected:
        chat_id = update.callback_query.from_user.id
        r_id = random.randint(0, 100000)
        formatted_time = f"{_time[0]}:{_time[1]} {_time[2]}"
        json_editor(chat_id, "time", formatted_time)
        json_editor(chat_id, "id", r_id)

        context.bot.send_message(chat_id=chat_id, text=f"You selected {formatted_time}", reply_markup=ReplyKeyboardRemove())
        reply_keyboard = [["Yes", "No"]]
        context.bot.send_message(chat_id=chat_id,
                                 text="\U0001F530 *Reminder Setup* \U0001F530\nDo you want to add additional information to the reminder?",
                                 reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
                                 parse_mode="markdown")
        return INFO

def info(update: Update, context: CallbackContext):
    text = update.message.text
    chat_id = update.message.chat_id
    if text.lower() == "yes":
        update.message.reply_text("\U00002139 Send the additional information for your reminder:", parse_mode="markdown")
        return OPT
    else:
        return schedule_reminder(chat_id, context)

def opt_info(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    information = update.message.text
    json_editor(chat_id, "opt_inf", information)
    return schedule_reminder(chat_id, context, info=information)

def schedule_reminder(chat_id, context, info=None):
    data = json_getter(chat_id)
    if not data:
        return ConversationHandler.END
    name, date, time_str, r_id, _ = data
    utc_offset = json_utc(chat_id)

    hour, minute, ampm = parse_time(time_str)
    reminder_dt = datetime.strptime(date, "%d/%m/%Y") + timedelta(hours=hour, minutes=minute)
    reminder_dt -= timedelta(minutes=30)  # 30 minutes before
    reminder_dt -= timedelta(hours=utc_offset)  # adjust UTC offset
    seconds = (reminder_dt - datetime.now()).total_seconds()

    reply_keyboard = [["/start", "/list", "/time"]]
    if seconds < 0:
        context.bot.send_message(chat_id=chat_id, text="\U0000274C *Reminder Error*\U0000274C\nThe date/time is too close or in the past.", parse_mode="markdown",
                                 reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        json_deleter(chat_id, r_id=r_id)
        return ConversationHandler.END

    context.bot.send_message(chat_id=chat_id,
                             text=f"\U0001F4CC *Saved Reminder*\U0001F4CC\nAppointment: {name}\nDate: {date}\nTime: {time_str}",
                             parse_mode="markdown",
                             reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
    job_context = [chat_id, name, date, time_str, chat_id, r_id]
    if info:
        job_context.append(info)
    context.job_queue.run_once(notification, seconds, context=job_context, name=str(chat_id))
    return ConversationHandler.END

def parse_time(time_str):
    """Return (hour24, minute, ampm)"""
    parts = time_str.split()
    hour, minute = map(int, parts[0].split(":"))
    ampm = parts[1].lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    return hour, minute, ampm

def cancel(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    json_deleter(chat_id, current=True)
    update.message.reply_text("\U0001F53A *Reminder Setup*\U0001F53A\nYou canceled the reminder!", reply_markup=ReplyKeyboardRemove(), parse_mode="markdown")
    return ConversationHandler.END

def all_reminder(update: Update, context: CallbackContext):
    chat_id = str(update.message.chat_id)
    data = load_store()
    reminders = data.get("reminder", {}).get(chat_id, {}).get("reminder", [])
    reply_keyboard = [["/start", "/list", "/time"]]
    if not reminders:
        update.message.reply_text("📃 *Reminder List*\nYou don't have any reminders!", parse_mode="markdown", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return
    update.message.reply_text("📋 *Reminder List*\n", parse_mode="markdown")
    for i, r in enumerate(reminders):
        msg = f"{i+1}: Appointment: {r['name']}\nDate: {r['date']}\nTime: {r['time']}"
        if "opt_inf" in r:
            msg += f"\nInformation: {r['opt_inf']}"
        update.message.reply_text(msg)

# ---------------------- Filter Commands ----------------------
def setfilter(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        update.message.reply_text("Usage: /setfilter <text>")
        return
    keyword = " ".join(context.args).strip()
    data = load_store()
    filters = data.get("filters", {})
    filters[chat_id] = keyword
    data["filters"] = filters
    save_store(data)
    update.message.reply_text(f"Filter set to: \"{keyword}\"")

def clearfilter(update: Update, context: CallbackContext):
    chat_id = str(update.effective_chat.id)
    data = load_store()
    filters = data.get("filters", {})
    if chat_id in filters:
        del filters[chat_id]
        data["filters"] = filters
        save_store(data)
        update.message.reply_text("Filter cleared.")
    else:
        update.message.reply_text("No filter set.")

# ---------------------- UTC Selection ----------------------
def utc_time(update: Update, context: CallbackContext):
    update.message.reply_text("Choose your timezone:", reply_markup=telegramcalendar.create_timezone())
    return UTC_1

def utc_time_selector(update: Update, context: CallbackContext):
    selected, num = telegramcalendar.process_utc_selection(context.bot, update)
    if selected:
        chat_id = str(update.callback_query.from_user.id)
        json_utc(chat_id, utc=num)
        reply_keyboard = [["/start", "/list", "/time"]]
        context.bot.send_message(chat_id=chat_id,
                                 text=f"You selected UTC {'+' if num>=0 else '-'}{abs(num)}",
                                 reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return ConversationHandler.END

# ---------------------- Main ----------------------
def main():
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Conversation handler for reminders
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NAME: [MessageHandler(Filters.text & ~Filters.command, name)],
            DATE_Q: [CallbackQueryHandler(inline_handler)],
            TIME_Q: [CallbackQueryHandler(inline_handler2)],
            INFO: [MessageHandler(Filters.text & ~Filters.command, info)],
            OPT: [MessageHandler(Filters.text & ~Filters.command, opt_info)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # UTC handler
    conv_utc = ConversationHandler(
        entry_points=[CommandHandler("time", utc_time)],
        states={UTC_1: [CallbackQueryHandler(utc_time_selector)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dp.add_handler(conv_handler)
    dp.add_handler(conv_utc)
    dp.add_handler(CommandHandler("list", all_reminder))
    dp.add_handler(CommandHandler("setfilter", setfilter))
    dp.add_handler(CommandHandler("clearfilter", clearfilter))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
