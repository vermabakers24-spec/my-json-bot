import telebot
import json
import os
import re
import sys
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = "8727671406:AAGtcc8eAPcXrOA9jlxsEFUnWZF1FncSH7o"

bot = telebot.TeleBot(BOT_TOKEN)
DB_FILE = "master_database.json"
user_states = {}

def load_database():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_database(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

def universal_account_extractor(raw_text):
    extracted_items = []
    try:
        clean_data = json.loads(raw_text.strip())
        if isinstance(clean_data, list):
            return clean_data
        elif isinstance(clean_data, dict):
            return [clean_data]
    except:
        pass

    bracket_blocks = re.findall(r'\{.*?\}', raw_text, re.DOTALL)
    for block in bracket_blocks:
        num_match = re.search(r'["\'](?:number|phone|mobile|uid)["\']\s*:\s*["\']?(\d+)["\']?', block)
        if num_match:
            phone_num = num_match.group(1).strip()
            try:
                standardized_block = block.replace("'", '"')
                item_dict = json.loads(standardized_block)
            except:
                item_dict = {"number": phone_num, "raw_data_string": block}
            extracted_items.append(item_dict)
            
    if not extracted_items:
        lines = raw_text.split("\n")
        for line in lines:
            if line.strip():
                digits = re.findall(r'\b\d{10,12}\b', line)
                if digits:
                    extracted_items.append({"number": digits[0], "raw_line": line.strip()})
    return extracted_items

def get_buttons_markup():
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("🔢 Get 10", callback_data="get_10"),
        InlineKeyboardButton("🔢 Get 15", callback_data="get_15"),
        InlineKeyboardButton("🔢 Get 20", callback_data="get_20")
    )
    markup.add(
        InlineKeyboardButton("⚙️ Custom Account", callback_data="get_custom"),
        InlineKeyboardButton("📥 All Remaining", callback_data="get_all")
    )
    markup.add(InlineKeyboardButton("📊 Check Remaining Accounts", callback_data="check_bal"))
    return markup

def export_batch_logic(chat_id, limit, is_all=False):
    db = load_database()
    unsend_keys = [k for k, v in db.items() if v["status"] == "unsend"]
    
    if not unsend_keys:
        bot.send_message(chat_id, "❌ Database me ek bhi unsend account nahi bacha!")
        return

    if is_all:
        actual_extract_count = len(unsend_keys)
    else:
        actual_extract_count = min(limit, len(unsend_keys))
        
    keys_to_extract = unsend_keys[:actual_extract_count]
    
    if actual_extract_count == 0:
        bot.send_message(chat_id, "❌ Bhai, aapne 0 ya galat account count dala hai.")
        return

    exported_list = []
    for key in keys_to_extract:
        exported_list.append(db[key]["data"])
        db[key]["status"] = "used"
        
    save_database(db)
    
    temp_output = f"batch_{actual_extract_count}_{chat_id}.json"
    with open(temp_output, "w") as f:
        json.dump(exported_list, f, indent=4)
        
    remaining_bal = len(unsend_keys) - actual_extract_count
    caption_text = f"📦 [BATCH EXPORTED: {actual_extract_count} ACCOUNTS]\n\n✅ Ye {actual_extract_count} accounts automatic USED mark ho chuke hain.\n📊 Balance standby accounts bache: {remaining_bal}"
    
    with open(temp_output, "rb") as f:
        bot.send_document(chat_id, f, visible_file_name=f"batch_{actual_extract_count}_accounts.json", caption=caption_text)
        
    os.remove(temp_output)
    
    bot.send_message(
        chat_id, 
        f"📊 [DATABASE STATUS UPDATE]\n\nBatch successfully extracted. Current balance standby accounts: **{remaining_bal}**.\nAur nikaalne ke liye niche click karein:", 
        reply_markup=get_buttons_markup()
    )

def process_and_reply(chat_id, raw_text):
    new_items = universal_account_extractor(raw_text)
    if not new_items:
        bot.send_message(chat_id, "❌ Bhai, is file/text me kisi bhi format ka JSON ya numbers nahi mile.")
        return

    db = load_database()
    added_count = 0

    for item in new_items:
        number = item.get("number") or item.get("phone") or item.get("mobile")
        if not number:
            continue
        str_number = str(number).strip()
        
        if str_number not in db:
            db[str_number] = {"data": item, "status": "unsend"}
            added_count += 1

    save_database(db)

    total_unsend = sum(1 for k, v in db.items() if v["status"] == "unsend")

    reply_text = (
        f"📊 [DATABASE STATUS UPDATE]\n\n"
        f"➔ {added_count} naye unique accounts is file se save kiye gaye.\n"
        f"➔ Total **{total_unsend}** accounts abhi active/unsend standby par hain.\n\n"
        f"Niche diye gaye buttons se apna custom batch nikaaliye:"
    )
    bot.send_message(chat_id, reply_text, reply_markup=get_buttons_markup())

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    db = load_database()
    total_unsend = sum(1 for k, v in db.items() if v["status"] == "unsend")
    bot.reply_to(message, f"🚀 Universal Batch Bot Active!\n\n📋 Database me abhi **{total_unsend}** unsend accounts standby par hain. Nayi file forward kijiye ya niche se batch nikaaliye:", reply_markup=get_buttons_markup())

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        raw_text = downloaded_file.decode('utf-8', errors='ignore')
        process_and_reply(message.chat.id, raw_text)
    except Exception as e:
        bot.reply_to(message, f"❌ File read error: {e}")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    chat_id = message.chat.id
    if chat_id in user_states and user_states[chat_id] == "waiting_custom_count":
        if message.text.isdigit():
            count = int(message.text)
            del user_states[chat_id]
            export_batch_logic(chat_id, count, is_all=False)
        else:
            bot.reply_to(message, "❌ Bhai, sirf number (digits) likh kar bhejo. Jaise: 5 ya 25")
        return

    if not message.text.startswith('/'):
        process_and_reply(chat_id, message.text)

@bot.callback_query_handler(func=lambda call: call.data.startswith(('get_', 'check_bal')))
def callback_inline(call):
    db = load_database()
    chat_id = call.message.chat.id
    
    if call.data == "check_bal":
        total_unsend = sum(1 for k, v in db.items() if v["status"] == "unsend")
        bot.answer_callback_query(call.id, f"Remaining Accounts: {total_unsend}")
        return

    if call.data == "get_all":
        bot.answer_callback_query(call.id, "📥 Exporting all remaining accounts...")
        export_batch_logic(chat_id, 0, is_all=True)
        return

    if call.data == "get_custom":
        user_states[chat_id] = "waiting_custom_count"
        bot.answer_callback_query(call.id, "Custom Account Selected")
        bot.send_message(chat_id, "🔢 **Bhai, aapko kitne accounts chahiye?** Nichhe chat me sirf number type karke send kijiye (e.g. 7, 22, 35):")
        return

    limit = int(call.data.split('_')[1])
    bot.answer_callback_query(call.id, f"👍 Exporting {limit} accounts...")
    export_batch_logic(chat_id, limit, is_all=False)

print("🚀 Custom & Bulk Batch Queue Bot starting up...")
bot.infinity_polling(timeout=60, long_polling_timeout=30)
