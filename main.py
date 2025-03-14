import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

import config
import threading
import random
import csv
import json
import time
from database import DataBase

TOKEN = config.TOKEN
bot = telebot.TeleBot(TOKEN)
db = DataBase()

# Caches for storing temporary data during conversations
load_cache = {}      # For /add word flow
show_cache = {}      # For showing list of words
edit_cache = {}      # For editing a selected word
flash_cache = {}     # For flashcards session
reminder_cache = {}  # For reminder settings
user_sessions = {}

# Dictionary to keep track of reminder timers per chat
reminder_timers = {}


# -------------------------------
# Menu and /start command
# -------------------------------
@bot.message_handler(commands=["start", "menu"])
def send_instruction(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("Add Word", callback_data="menu_add"),
        InlineKeyboardButton("Edit Word", callback_data="menu_edit"),
        InlineKeyboardButton("Show Words", callback_data="menu_show"),
        InlineKeyboardButton("Flashcards", callback_data="menu_flash"),
        InlineKeyboardButton("Set Reminder", callback_data="menu_reminder"),
        InlineKeyboardButton("Export Words", callback_data="menu_export"),
        InlineKeyboardButton("Survey", callback_data="menu_survey")
    )
    bot.send_message(message.chat.id, "Welcome to the ForWordsBot! Choose an option:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def menu_handler(call):
    if call.data == "menu_add":
        start_input(call.message)
    elif call.data == "menu_edit":
        bot.send_message(call.message.chat.id, "Use /edit to edit words.")
    elif call.data == "menu_show":
        show_words(call.message)
    elif call.data == "menu_flash":
        start_flashcards(call.message)
    elif call.data == "menu_sort":
        bot.send_message(call.message.chat.id, "Sort words by which language? Type 'en' for foreign or 'ru' for native:")
        bot.register_next_step_handler(call.message, sort_words)
    elif call.data == "menu_reminder":
        bot.send_message(call.message.chat.id, "Enter the group for which to set a reminder (or type 'all'):")
        bot.register_next_step_handler(call.message, process_reminder_group)
    elif call.data == "menu_export":
        bot.send_message(call.message.chat.id, "Choose export format: txt, csv, or json:")
        bot.register_next_step_handler(call.message, upload_words_format)
    elif call.data == "menu_survey":
        bot.send_message(call.message.chat.id, "You can take a survey about this telegram bot:\n"
                                               "https://forms.gle/WTaK4Qed9GRKr8BcA")


def cancel_fsm(func):
    def wrapper(message):
        if message.text == "cancel":
            bot.send_message(message.chat.id, "Action has been canceled!")
            return
        else:
            func(message)
    return wrapper


# -------------------------------
# Adding new words (/add)
# -------------------------------
@bot.message_handler(commands=['add'])
def start_input(message):
    msg = bot.reply_to(message, "Let's add a new word or phrase!\n"
                                "Send to me the word or phrase in the foreign language.\n"
                                "If you want to input multiple translations,\n"
                                "just write words separating them using ', '(comma and space)")
    bot.register_next_step_handler(msg, process_foreign_word)


@cancel_fsm
def process_foreign_word(message):
    load_cache[message.chat.id] = [message.text.lower()]
    msg = bot.reply_to(message, "Send to me a code of foreign language (e.g en, ru, aa)")
    bot.register_next_step_handler(msg, process_language_name)


@cancel_fsm
def process_language_name(message):
    load_cache[message.chat.id].append(message.text)
    msg = bot.reply_to(message, "Send to me the translation in your native language")
    bot.register_next_step_handler(msg, process_native_word)


@cancel_fsm
def process_native_word(message):
    load_cache[message.chat.id].append(message.text)
    msg = bot.reply_to(message, "Send to me the group name for this word, or leave empty for default group")
    bot.register_next_step_handler(msg, process_group)


@cancel_fsm
def process_group(message):
    group = message.text.strip() if message.text.strip() != "" else "default"
    load_cache[message.chat.id].append(group)
    # Assume db.input_words now accepts three arguments: foreign, native, and group
    db.input_words(message.chat.id,
                   load_cache[message.chat.id][0],
                   load_cache[message.chat.id][2],
                   group,
                   load_cache[message.chat.id][1])
    load_cache.pop(message.chat.id)
    bot.send_message(message.chat.id, "The word has been added successfully!")


# -------------------------------
# Exporting words (/upload)
# -------------------------------
@bot.message_handler(commands=['upload'])
def upload_words(message):
    msg = bot.reply_to(message, "Choose export format: txt, csv, or json")
    bot.register_next_step_handler(msg, upload_words_format)


def upload_words_format(message):
    data = db.get_show_words(message.chat.id)  # Expecting list of tuples: (foreign, native, group)
    fmt = message.text.lower()
    if fmt == 'txt':
        filename = f'words.txt'
        with open(filename, 'w', encoding='utf-8') as file:
            for line in data:
                file.write(f"{line[0]} --- {line[1]}\n")
        bot.send_document(message.chat.id, open(filename, 'rb'))
    elif fmt == 'csv':
        filename = f'words.csv'
        with open(filename, 'w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            writer.writerow(["Foreign", "Native"])
            for line in data:
                writer.writerow([line[0], line[1]])
        bot.send_document(message.chat.id, open(filename, 'rb'))
    elif fmt == 'json':
        filename = f'words.json'
        words_list = [{"foreign": line[0], "native": line[1]} for line in data]
        with open(filename, 'w', encoding='utf-8') as file:
            json.dump(words_list, file, ensure_ascii=False, indent=2)
        bot.send_document(message.chat.id, open(filename, 'rb'))
    else:
        bot.send_message(message.chat.id, "Unsupported format. Please choose txt, csv, or json.")


# -------------------------------
# Showing words (/show)
# -------------------------------
@bot.message_handler(commands=['show'])
def show_words(message):
    msg = bot.reply_to(message,
                       "What group do you want to see?\n"
                       "If you want to see multiple groups\njust write them separating by ', '(comma and space)\n"
                       "If you want to see all groups write 'all'")
    bot.register_next_step_handler(msg, process_group_show)


@cancel_fsm
def process_group_show(message):
    groups = message.text.split(", ")
    if groups == ["all"]:
        show_cache[message.chat.id] = {"groups": []}
    else:
        show_cache[message.chat.id] = {"groups": groups}
    msg = bot.reply_to(message,
                       "What languages do you want to see?\n"
                       "If you want to see multiple langs\njust write them separating by ', '(comma and space)\n"
                       "If you want to see all lang write 'all'")
    bot.register_next_step_handler(msg, final_show)


@cancel_fsm
def final_show(message):
    langs = message.text.split(", ")
    if langs == ["all"]:
        show_cache[message.chat.id]["langs"] = []
    else:
        show_cache[message.chat.id]["langs"] = langs
    data = db.get_show_words(message.chat.id, show_cache[message.chat.id]["groups"], show_cache[message.chat.id]["langs"])
    msg_text = "Your words:\n\n"
    for line in data:
        msg_text += f"{line[1]}  --  {line[0]} \n    Group: {line[2]}, Lang: {line[3]}\n\n"
    bot.send_message(message.chat.id, msg_text)


# -------------------------------
# Editing words (/edit)
# -------------------------------
@bot.message_handler(commands=['edit'])
def edit_words(message):
    msg = bot.reply_to(message, "Write word in native language and foreign lang code (separated by space)")
    bot.register_next_step_handler(msg, select_edit_word)


@cancel_fsm
def select_edit_word(message):
    try:
        native, lang = message.text.split(" ")
        edit_cache[message.chat.id] = [native, lang]
    except (TypeError, KeyError, ValueError):
        msg = bot.reply_to(message,
                           'You need to write two words: word in native and lang code\nFor example: (target ru)')
        bot.register_next_step_handler(msg, edit_words)
        return
    data = db.get_word_for_editing(message.chat.id, native, lang)
    if data:
        edit_cache[message.chat.id] = data[0]
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton('Delete', callback_data='edit_cb_del'),
            InlineKeyboardButton('Change', callback_data='edit_cb_change')
        )
        bot.send_message(message.chat.id, f'Editing word:\n{edit_cache[message.chat.id]}', reply_markup=markup)
    else:
        msg = bot.reply_to(message, "There are no any words with this pair of native word and lang!\nEnter again:")
        bot.register_next_step_handler(msg, select_edit_word)


@cancel_fsm
def enter_foreign_change(message):
    db.change_foreign_word(message.chat.id,
                           edit_cache[message.chat.id][1],
                           message.text,
                           edit_cache[message.chat.id][3])
    bot.send_message(message.chat.id, "Foreign word has been changed!")
    edit_cache.pop(message.chat.id, None)


@cancel_fsm
def enter_native_change(message):
    db.change_native_word(message.chat.id,
                          edit_cache[message.chat.id][1],
                          message.text,
                          edit_cache[message.chat.id][3])
    bot.send_message(message.chat.id, "Native word has been changed!")
    edit_cache.pop(message.chat.id, None)


@cancel_fsm
def enter_group_change(message):
    db.change_group(message.chat.id,
                    edit_cache[message.chat.id][1],
                    message.text,
                    edit_cache[message.chat.id][3])
    bot.send_message(message.chat.id, "Group of word has been changed!")
    edit_cache.pop(message.chat.id, None)


@cancel_fsm
def enter_lang_change(message):
    db.change_lang_code(message.chat.id,
                        edit_cache[message.chat.id][1],
                        message.text,
                        edit_cache[message.chat.id][3])
    bot.send_message(message.chat.id, "Lang code of word has been changed!")
    edit_cache.pop(message.chat.id, None)


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def callback_query(call):
    if call.data == 'edit_cb_del':
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton('Yes', callback_data='edit_del_y'),
                   InlineKeyboardButton('No', callback_data='edit_del_n'))
        bot.edit_message_text(f'Deleting word:\n{edit_cache[call.message.chat.id]}\nConfirm?',
                              call.message.chat.id,
                              call.message.message_id,
                              reply_markup=markup)
    elif call.data == 'edit_del_y':
        db.delete_word(call.message.chat.id, edit_cache[call.message.chat.id][1], edit_cache[call.message.chat.id][3])
        bot.send_message(call.message.chat.id, "Word deleted successfully.")
        edit_cache.pop(call.message.chat.id, None)
    elif call.data == 'edit_del_n':
        bot.send_message(call.message.chat.id, "Deletion cancelled.")
    elif call.data == "edit_cb_change":  # Change word info
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(InlineKeyboardButton('Change foreign', callback_data='edit_change_fgn'),
                   InlineKeyboardButton('Change native', callback_data='edit_change_ntv'),
                   InlineKeyboardButton('Change group', callback_data='edit_change_grp'),
                   InlineKeyboardButton('Change lang code', callback_data='edit_change_lng'))
        bot.edit_message_text(f"Choose what to change:\n{edit_cache[call.message.chat.id]}",
                              call.message.chat.id,
                              call.message.message_id,
                              reply_markup=markup)
    elif call.data == "edit_change_fgn":  # Change foreign word
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("Back", callback_data='edit_cb_change'))
        bot.edit_message_text(call.message.text + "\nEnter new foreign word:",
                              call.message.chat.id,
                              call.message.message_id,
                              reply_markup=markup)
        bot.register_next_step_handler(call.message, enter_foreign_change)
    elif call.data == "edit_change_ntv":  # Change native word
        bot.edit_message_text(call.message.text + "\nEnter new native word:",
                              call.message.chat.id,
                              call.message.message_id)
        bot.register_next_step_handler(call.message, enter_native_change)
    elif call.data == "edit_change_grp":  # Change native word
        bot.edit_message_text("Enter new group:", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, enter_group_change)
    elif call.data == "edit_change_lng":  # Change native word
        bot.edit_message_text("Enter new lang code:", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, enter_lang_change)


# -------------------------------
# Sorting words (/sort)
# -------------------------------
def sort_words(message):
    sort_by = message.text.lower()
    data = db.get_show_words(message.chat.id)
    if sort_by == 'en':
        sorted_data = sorted(data, key=lambda x: x[0])
    elif sort_by == 'ru':
        sorted_data = sorted(data, key=lambda x: x[1])
    else:
        bot.send_message(message.chat.id, "Invalid sort option. Use 'en' or 'ru'.")
        return
    msg_text = "Sorted words:\n"
    for i, line in enumerate(sorted_data, 1):
        msg_text += f"{i}. {line[0]} --- {line[1]} (Group: {line[2]})\n"
    bot.send_message(message.chat.id, msg_text)


# -------------------------------
# Flashcards (/flash)
# -------------------------------
@bot.message_handler(commands=['flash'])
def start_flashcards(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Yes"), KeyboardButton("No"))
    msg = bot.send_message(message.chat.id, "Do you want the flashcards to be randomized?", reply_markup=markup)
    bot.register_next_step_handler(msg, process_flashcard_random)


@cancel_fsm
def process_flashcard_random(message):
    if message.text == "Yes":
        flash_cache[message.chat.id] = {"random": True}
    elif message.text == "No":
        flash_cache[message.chat.id] = {"random": False}
    else:
        msg = bot.reply_to(message, "Your answer isn't correct. You need to just write 'Yes' or 'No'.")
        bot.register_next_step_handler(msg, process_flashcard_random)
        return

    msg = bot.reply_to(message,
                       "Select groups for flashcards (comma with space separated) or type 'all' for all groups:")
    bot.register_next_step_handler(msg, process_flashcard_groups)


@cancel_fsm
def process_flashcard_groups(message):
    groups = message.text.split(", ") if message.text.lower() != "all" else []
    flash_cache[message.chat.id]["groups"] = groups

    msg = bot.reply_to(message, "Select languages (comma and space separated) or type 'all' for all languages:")
    bot.register_next_step_handler(msg, process_flashcard_languages)


@cancel_fsm
def process_flashcard_languages(message):
    langs = message.text.split(", ") if message.text.lower() != "all" else []
    flash_cache[message.chat.id]["langs"] = langs

    # Fetch filtered words from the database
    data = db.get_flash_words(message.chat.id, flash_cache[message.chat.id]["groups"], langs)

    if not data:
        bot.send_message(message.chat.id, "No words found for the selected filters.")
        return

    # Check if randomization is enabled and shuffle words
    if flash_cache[message.chat.id]["random"]:
        random.shuffle(data)

    flash_cache[message.chat.id]["words"] = data
    flash_cache[message.chat.id]["index"] = 0

    show_flashcard(message.chat.id)


def show_flashcard(chat_id, message_id=None):
    """Edits the current flashcard message instead of sending a new one."""
    index = flash_cache[chat_id]["index"]
    words = flash_cache[chat_id]["words"]

    if index >= len(words):  # All words checked
        offer_retry(chat_id, message_id)
        return

    word = words[index]
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Show Answer", callback_data="flash_show"))

    if message_id:
        bot.edit_message_text(f"Flashcard:\nWord: {word[0]}\nWhat is the translation?",
                              chat_id, message_id, reply_markup=markup)
    else:
        msg = bot.send_message(chat_id, f"Flashcard:\nWord: {word[0]}\nWhat is the translation?", reply_markup=markup)
        flash_cache[chat_id]["message_id"] = msg.message_id  # Store the message ID


def offer_retry(chat_id, message_id):
    """Edits the message to offer retry options."""
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔄 Retry These Words", callback_data="flash_retry"),
        InlineKeyboardButton("📂 Choose New Groups/Languages", callback_data="flash_new")
    )

    bot.edit_message_text("You've gone through all words! What do you want to do next?",
                          chat_id, message_id, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data in ["flash_retry", "flash_new"])
def handle_retry_option(call):
    chat_id = call.message.chat.id
    if call.data == "flash_retry":
        flash_cache[chat_id]["index"] = 0  # Reset index
        show_flashcard(chat_id)
    elif call.data == "flash_new":
        bot.send_message(chat_id, "Let's choose new words! Enter the groups you want to study:")
        bot.register_next_step_handler(call.message, process_flashcard_groups)


@bot.callback_query_handler(func=lambda call: call.data.startswith("flash_"))
def flash_callback(call):
    chat_id = call.message.chat.id
    index = flash_cache[chat_id]["index"]
    word = flash_cache[chat_id]["words"][index]

    if call.data == "flash_show":
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Next", callback_data="flash_next"))
        bot.edit_message_text(f"Flashcard:\nWord: {word[0]}\nTranslation: {word[1]}",
                              chat_id, call.message.message_id, reply_markup=markup)
    elif call.data == "flash_next":
        flash_cache[chat_id]["index"] += 1
        show_flashcard(chat_id, call.message.message_id)  # Pass the existing message ID


# -------------------------------
# Reminder Functionality
# -------------------------------
@bot.message_handler(commands=["set_reminder"])
def make_reminder(message):
    msg = bot.send_message(message.chat.id, "Enter the group for which to set a reminder (or type 'all'):")
    bot.register_next_step_handler(msg, process_reminder_group)


# Step 1: Process the group for the reminder
@cancel_fsm
def process_reminder_group(message):
    group = message.text.strip()
    reminder_cache[message.chat.id] = {"group": group}
    bot.send_message(message.chat.id, "Enter the time interval for the reminder (e.g., '10m', '2h', '1d'):")
    bot.register_next_step_handler(message, process_reminder_time)


# Step 2: Process the time interval for the reminder
@cancel_fsm
def process_reminder_time(message):
    time_input = message.text.strip().lower()
    chat_id = message.chat.id

    # Parse the time input
    time_mapping = {"m": 60, "h": 3600, "d": 86400}
    try:
        unit = time_input[-1]
        value = int(time_input[:-1])
        if unit not in time_mapping:
            raise ValueError("Invalid time unit")
        interval = value * time_mapping[unit]
        if interval < 60 or interval > 2592000:  # Minimum 1 minute, maximum 1 month
            raise ValueError("Time out of range")
    except (ValueError, IndexError):
        bot.send_message(chat_id, "Invalid time format. Please try again (e.g., '10m', '2h', '1d'):")
        bot.register_next_step_handler(message, process_reminder_time)
        return

    # Save the interval and start the reminder
    reminder_cache[chat_id]["interval"] = interval
    reminder_cache[chat_id]["time_input"] = time_input
    group = reminder_cache[chat_id]["group"]
    start_reminder(chat_id, group, interval, time_input)
    bot.send_message(chat_id, f"Reminder set for group '{group}' every {time_input}. Use /reminders to manage reminders.")


# Step 3: Start the reminder
def start_reminder(chat_id, group, interval, time_input):
    if chat_id in reminder_timers:
        reminder_timers[chat_id].append({"group": group,
                                         "interval": interval,
                                         "time_input": time_input,
                                         "active": True})
    else:
        reminder_timers[chat_id] = [{"group": group,
                                     "interval": interval,
                                     "time_input": time_input,
                                     "active": True}]

    # Start a background thread for the reminder
    def reminder_thread():
        while any(r["active"] for r in reminder_timers[chat_id]):
            for reminder in reminder_timers[chat_id]:
                if reminder["active"]:
                    bot.send_message(chat_id, f"Reminder: Review your words in group '{reminder['group']}'!")
                    time.sleep(reminder["interval"])

    threading.Thread(target=reminder_thread, daemon=True).start()


# Step 4: List active reminders
@bot.message_handler(commands=["reminders"])
def list_reminders(message):
    chat_id = message.chat.id
    if chat_id not in reminder_timers or not reminder_timers[chat_id]:
        bot.send_message(chat_id, "You have no active reminders.")
        return

    response = "Your active reminders:\n"
    for i, reminder in enumerate(reminder_timers[chat_id], start=1):
        status = "Active" if reminder["active"] else "Inactive"
        response += f"{i}. Group: {reminder['group']}, Interval: {reminder['time_input']}, Status: {status}\n"
    response += "\nTo stop a reminder, use /stop_reminder <number>."
    response += "\nTo run a reminder, use /run_reminder <number>."
    response += "\nTo delete a reminder, use /delete_reminder <number>."
    bot.send_message(chat_id, response)


@bot.message_handler(commands=["stop_reminder"])
def stop_reminder(message):
    chat_id = message.chat.id
    if chat_id not in reminder_timers or not reminder_timers[chat_id]:
        bot.send_message(chat_id, "You have no active reminders to stop.")
        return

    try:
        index = int(message.text.split()[1]) - 1
        if index < 0 or index >= len(reminder_timers[chat_id]):
            raise IndexError("Invalid index")
        reminder_timers[chat_id][index]["active"] = False
        bot.send_message(chat_id, f"Reminder {index + 1} has been stopped.")
    except (IndexError, ValueError):
        bot.send_message(chat_id, "Invalid command. Use /stop_reminder <number> to stop a reminder.")


@bot.message_handler(commands=["run_reminder"])
def run_reminder(message):
    chat_id = message.chat.id
    if chat_id not in reminder_timers or not reminder_timers[chat_id]:
        bot.send_message(chat_id, "You have no inactive reminders to run.")
        return

    try:
        index = int(message.text.split()[1]) - 1
        if index < 0 or index >= len(reminder_timers[chat_id]):
            raise IndexError("Invalid index")
        reminder_timers[chat_id][index]["active"] = True
        bot.send_message(chat_id, f"Reminder {index + 1} has been launched.")
    except (IndexError, ValueError):
        bot.send_message(chat_id, "Invalid command. Use /stop_reminder <number> to run a reminder.")


# Step 5: Delete a reminder
@bot.message_handler(commands=["delete_reminder"])
def delete_reminder(message):
    chat_id = message.chat.id
    if chat_id not in reminder_timers or not reminder_timers[chat_id]:
        bot.send_message(chat_id, "You have no reminders to delete.")
        return

    try:
        index = int(message.text.split()[1]) - 1
        if index < 0 or index >= len(reminder_timers[chat_id]):
            raise IndexError("Invalid index")
        reminder_timers[chat_id].pop(index)
        bot.send_message(chat_id, f"Reminder {index + 1} has been deleted.")
    except (IndexError, ValueError):
        bot.send_message(chat_id, "Invalid command. Use /delete_reminder <number> to delete a reminder.")


# -------------------------------
# Start polling
# -------------------------------
bot.infinity_polling()
