import random
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

CHANNEL_USERNAME = "siberia_tech"  # نام کانال بدون @
BOT_USERNAME = "AncientConverterBot"  # نام کاربری ربات بدون @ (جایگزین کنید)

conn = sqlite3.connect("referral.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    invitee_id INTEGER UNIQUE
)
""")
conn.commit()

def convert_to_avestan(text):
    replacements = {
        "a": ["𐬀"], "ā": ["𐬁"], "e": ["𐬆", "𐬈"], "ë": ["𐬇"], "ē": ["𐬉"],
        "o": ["𐬊"], "ō": ["𐬋"], "i": ["𐬌"], "ī": ["𐬍"], "u": ["𐬎"], "ū": ["𐬏"],
        "av": ["𐬃"], "k": ["𐬐"], "kh": ["𐬑"], "g": ["𐬔"], "q": ["𐬖"], "č": ["𐬗"],
        "j": ["𐬘"], "ṭ": ["𐬙"], "c": ["𐬚"], "d": ["𐬛"], "ď": ["𐬜"], "t": ["𐬝"],
        "p": ["𐬞"], "f": ["𐬟"], "b": ["𐬠"], "V": ["𐬎𐬎"], "v": ["𐬡"], "ang": ["𐬢"],
        "n": ["𐬥", "𐬧"], "m": ["𐬨"], "Y": ["𐬌𐬌"], "y": ["𐬫", "𐬪"], "r": ["𐬭"],
        "l": ["𐬦"], "s": ["𐬯"], "š": ["𐬱", "𐬳", "𐬴"], "z": ["𐬰"], "zh": ["𐬲"],
        "h": ["𐬵"], "x": ["𐬒"], "xu": ["𐬓"], ".": ["𐬼"], ",": ["𐬹"],
    }
    result = []
    i = 0
    while i < len(text):
        if i < len(text)-2 and text[i:i+3] == "ang":
            result.append("𐬢")
            i += 3
        elif i < len(text)-1 and text[i:i+2] == "kh":
            result.append("𐬑")
            i += 2
        elif i < len(text)-1 and text[i:i+2] == "zh":
            result.append("𐬲")
            i += 2
        elif i < len(text)-1 and text[i:i+2] == "av":
            result.append("𐬃")
            i += 2
        elif i < len(text)-1 and text[i:i+2] == "xu":
            result.append("𐬓")
            i += 2
        else:
            ch = text[i]
            if ch in replacements:
                result.append(random.choice(replacements[ch]))
            else:
                result.append(ch)
            i += 1
    return "".join(result)

def avestan_to_latin(text):
    replacements = {
        "𐬀": "a", "𐬁": "ā", "𐬆": "e", "𐬈": "e", "𐬇": "ë", "𐬉": "ē",
        "𐬊": "o", "𐬋": "ō", "𐬌": "i", "𐬍": "ī", "𐬎": "u", "𐬏": "ū",
        "𐬃": "av", "𐬐": "k", "𐬑": "kh", "𐬔": "g", "𐬖": "q",
        "𐬗": "č", "𐬘": "j", "𐬙": "ṭ", "𐬚": "c", "𐬛": "d", "𐬜": "ď",
        "𐬝": "t", "𐬞": "p", "𐬟": "f", "𐬠": "b", "𐬡": "v", "𐬢": "ang",
        "𐬥": "n", "𐬧": "n", "𐬨": "m", "𐬭": "r", "𐬦": "l",
        "𐬯": "s", "𐬱": "š", "𐬳": "š", "𐬴": "š", "𐬰": "z", "𐬲": "zh",
        "𐬵": "h", "𐬒": "x", "𐬓": "xu", "𐬼": ".", "𐬹": ",", "𐬫": "y", "𐬪": "y"
    }
    return "".join(replacements.get(ch, ch) for ch in text)

def convert_to_old_persian(text):
    replacements = {
        "ā": "𐎠", "a": "𐎠", "e": "𐎡", "i": "𐎡", "I": "𐎡", "u": "𐎢",
        "k": "𐎣", "g": "𐎥", "x": "𐎧", "t": "𐎫", "j": "𐎩", "d": "𐎭", "č": "𐎨",
        "p": "𐎱", "f": "𐎳", "b": "𐎲", "n": "𐎴", "m": "𐎶", "y": "𐎹", "v": "𐎺",
        "w": "𐎺", "r": "𐎼", "l": "𐎾", "L": "𐎾", "s": "𐎿", "c": "𐎰", "z": "𐏀",
        "h": "𐏃", "š": "𐏁", "ko": "𐎤", "go": "𐎦", "ch": "𐎨", "thra": "𐏂",
        "je": "𐎪", "to": "𐎬", "th": "𐎰", "ve": "𐎻", "de": "𐎮", "do": "𐎯",
        "no": "𐎵", "me": "𐎷", "ro": "𐎽", "mo": "𐎸", "sh": "𐏁"
    }
    result = ""
    i = 0
    while i < len(text):
        if i < len(text) - 3 and text[i:i+4] == "thra":
            result += replacements["thra"]
            i += 4
        elif i < len(text) - 1 and text[i:i+2] in replacements:
            result += replacements[text[i:i+2]]
            i += 2
        elif text[i] in replacements:
            result += replacements[text[i]]
            i += 1
        else:
            result += text[i]
            i += 1
    return result

def old_persian_to_latin(text):
    replacements = {
        "𐎠": "a", "𐎡": "e", "𐎢": "u", "𐎣": "k", "𐎥": "g", "𐎧": "x", "𐎫": "t",
        "𐎩": "j", "𐎭": "d", "𐎨": "č", "𐎱": "p", "𐎳": "f", "𐎲": "b", "𐎴": "n",
        "𐎶": "m", "𐎹": "y", "𐎺": "v", "𐎼": "r", "𐎾": "l", "𐎿": "s", "𐎰": "c",
        "𐏀": "z", "𐏃": "h", "𐏁": "š", "𐎤": "ko", "𐎦": "go", "𐏂": "thra",
        "𐎪": "je", "𐎬": "to", "𐎻": "ve", "𐎮": "de", "𐎯": "do", "𐎵": "no",
        "𐎷": "me", "𐎽": "ro", "𐎸": "mo"
    }
    result = []
    i = 0
    while i < len(text):
        current_char = text[i]
        if current_char == " ":
            result.append(" ")
            i += 1
            continue
        if i < len(text) - 1 and text[i:i+2] in replacements:
            result.append(replacements[text[i:i+2]])
            i += 2
            continue
        if current_char in replacements:
            result.append(replacements[current_char])
        else:
            result.append(current_char)
        i += 1
    return "".join(result)

def convert_to_parthian(text):
    replacements = {
        "a": ["𐭀"], "ā": ["𐭀"], "b": ["𐭁"], "g": ["𐭂"], "d": ["𐭃"], "j": ["𐭃"],
        "h": ["𐭄"], "v": ["𐭅"], "w": ["𐭅"], "o": ["𐭅"], "z": ["𐭆"], "x": ["𐭇"],
        "ṭ": ["𐭈"], "y": ["𐭉"], "i": ["𐭉"], "k": ["𐭊"], "l": ["𐭋"], "m": ["𐭌"],
        "n": ["𐭍"], "s": ["𐭎"], "e": ["𐭏"], "p": ["𐭐"], "f": ["𐭐"], "č": ["𐭑"],
        "c": ["𐭑"], "q": ["𐭒"], "r": ["𐭓"], "š": ["𐭔"], "ž": ["𐭔"], "zh": ["𐭔"],
        "sh": ["𐭔"], "t": ["𐭕"]
    }
    resultt = []
    i = 0
    while i < len(text):
        if i < len(text) - 1:
            two_chars = text[i:i+2]
            if two_chars in ["sh", "zh", "nd", "hw", "ch"]:
                if two_chars in ["sh", "zh", "ch"]:
                    resultt.append("𐭔")
                elif two_chars == "nd":
                    resultt.append("𐭍𐭃")
                elif two_chars == "hw":
                    resultt.append("𐭇𐭅")
                i += 2
                continue
        ch = text[i]
        if ch in replacements:
            options = replacements[ch]
            resultt.append(random.choice(options))
        else:
            resultt.append(ch)
        i += 1
    return "".join(resultt)

def parthian_to_latin(text):
    replacements = {
        "𐭀": ["a","ā"], "𐭁": ["b"], "𐭂": ["g"], "𐭃": ["d","j"], "𐭄": ["h"], "𐭅": ["v","w","o"],
        "𐭆": ["z"], "𐭇": ["x"], "𐭈": ["ṭ"], "𐭉": ["y","i"], "𐭊": ["k"], "𐭋": ["l"], "𐭌": ["m"],
        "𐭍": ["n"], "𐭎": ["s"], "𐭏": ["e"], "𐭐": ["p","f"], "𐭑": ["č","c","ch"], "𐭒": ["q"], "𐭓": ["r"],
        "𐭔": ["š","ž","zh","sh"], "𐭕": ["t"], "𐭍𐭃": ["nd"], "𐭇𐭅": ["hw"]
    }
    result = []
    i = 0
    while i < len(text):
        if i < len(text) - 1 and text[i:i+2] in replacements:
            opts = replacements[text[i:i+2]]
            result.append(random.choice(opts))
            i += 2
            continue
        ch = text[i]
        if ch in replacements:
            opts = replacements[ch]
            result.append(random.choice(opts))
        else:
            result.append(ch)
        i += 1
    return "".join(result)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    args = context.args

    if args and args[0].startswith("ref_"):
        try:
            referrer_id = int(args[0][4:])
            cursor.execute("SELECT 1 FROM referrals WHERE invitee_id=?", (user_id,))
            if cursor.fetchone() is None:
                member = await context.bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    cursor.execute("INSERT INTO referrals (referrer_id, invitee_id) VALUES (?, ?)", (referrer_id, user_id))
                    conn.commit()
        except Exception:
            pass

    keyboard = [
        [InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{CHANNEL_USERNAME}")],
        [InlineKeyboardButton("Done✅️", callback_data="check_membership")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "برای کار با ربات ابتدا عضویت در کانال شوید\nTo work with the bot, first subscribe to the channel",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_membership":
        try:
            member = await context.bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
            if member.status in ['member', 'administrator', 'creator']:
                keyboard = [
                    [InlineKeyboardButton("Avestan/Iranian", callback_data="show_avestan_iranian")],
                    [InlineKeyboardButton("OldPersian/Iranian", callback_data="show_oldpersian_iranian")],
                    [InlineKeyboardButton("Parthian/Iranian", callback_data="show_parthian_iranian")],
                    [InlineKeyboardButton("Parsig/Iranian", callback_data="show_parsig_iranian")]
                ]
                await query.edit_message_text("یکی از دکمه‌های زیر را انتخاب کنید", reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await query.edit_message_text("ابتدا باید عضو کانال شوید و سپس دکمه Done را بزنید.")
        except Exception:
            await query.edit_message_text("خطا در بررسی عضویت، لطفا دوباره تلاش کنید.")

    elif query.data == "show_avestan_iranian":
        keyboard = [
            [InlineKeyboardButton("A: English ➜ Avestan", callback_data="A_avestan")],
            [InlineKeyboardButton("B: Avestan ➜ English", callback_data="B_avestan")],
            [InlineKeyboardButton("back 🔙", callback_data="back_to_main")]
        ]
        await query.edit_message_text("یکی از دکمه‌های زیر را انتخاب کنید", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "A_avestan":
        await query.message.reply_text("لطفا متن خود را به حروف انگلیسی بنویسید")
        context.user_data["mode"] = "to_avestan"

    elif query.data == "B_avestan":
        await query.message.reply_text("لطفا متن خود را به حروف اوستایی وارد کنید")
        context.user_data["mode"] = "from_avestan"

    elif query.data == "show_oldpersian_iranian":
        keyboard = [
            [InlineKeyboardButton("A: English ➜ OldPersian", callback_data="A_oldpersian")],
            [InlineKeyboardButton("B: OldPersian ➜ English", callback_data="B_oldpersian")],
            [InlineKeyboardButton("back 🔙", callback_data="back_to_main")]
        ]
        await query.edit_message_text("یکی از دکمه‌های زیر را انتخاب کنید", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "A_oldpersian":
        await query.message.reply_text("لطفا متن خود را به حروف انگلیسی بنویسید")
        context.user_data["mode"] = "to_oldpersian"

    elif query.data == "B_oldpersian":
        await query.message.reply_text("لطفا متن خود را به کتیبه‌ای پارسی باستان وارد کنید")
        context.user_data["mode"] = "from_oldpersian"

    elif query.data == "show_parthian_iranian":
        keyboard = [
            [InlineKeyboardButton("A: English ➜ Parthian", callback_data="A_parthian")],
            [InlineKeyboardButton("B: Parthian ➜ English", callback_data="B_parthian")],
            [InlineKeyboardButton("back 🔙", callback_data="back_to_main")]
        ]
        await query.edit_message_text("یکی از دکمه‌های زیر را انتخاب کنید", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "A_parthian":
        await query.message.reply_text("لطفا متن خود را به حروف انگلیسی بنویسید")
        context.user_data["mode"] = "to_parthian"

    elif query.data == "B_parthian":
        await query.message.reply_text("لطفا متن خود را به حروف اشکانی وارد کنید")
        context.user_data["mode"] = "from_parthian"

    elif query.data == "show_parsig_iranian":
        cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,))
        invites = cursor.fetchone()[0]
        if invites < 3:
            personal_ref_link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
            await query.edit_message_text(f"برای کار با این بخش باید ۳ نفر را به ربات دعوت کنید\nلینک دعوت شما: {personal_ref_link}\nتعداد دعوت‌های موفق: {invites}/3")
        else:
            keyboard = [
                [InlineKeyboardButton("A: English ➜ Parsig", callback_data="A_parsig")],
                [InlineKeyboardButton("B: Parsig ➜ English", callback_data="B_parsig")],
                [InlineKeyboardButton("back 🔙", callback_data="back_to_main")]
            ]
            await query.edit_message_text("یکی از دکمه‌های زیر را انتخاب کنید", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "A_parsig":
        await query.message.reply_text("لطفا متن خود را به حروف انگلیسی بنویسید")
        context.user_data["mode"] = "to_parsig"

    elif query.data == "B_parsig":
        await query.message.reply_text("لطفا متن خود را به کتیبه‌ای پارسی باستان وارد کنید")
        context.user_data["mode"] = "from_parsig"

    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("Avestan/Iranian", callback_data="show_avestan_iranian")],
            [InlineKeyboardButton("OldPersian/Iranian", callback_data="show_oldpersian_iranian")],
            [InlineKeyboardButton("Parthian/Iranian", callback_data="show_parthian_iranian")],
            [InlineKeyboardButton("Parsig/Iranian", callback_data="show_parsig_iranian")]
        ]
        await query.edit_message_text("یکی از دکمه‌های زیر را انتخاب کنید", reply_markup=InlineKeyboardMarkup(keyboard))

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = context.user_data.get("mode")
    text = update.message.text
    if mode == "to_avestan":
        output = convert_to_avestan(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "from_avestan":
        output = avestan_to_latin(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "to_oldpersian":
        output = convert_to_old_persian(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "from_oldpersian":
        output = old_persian_to_latin(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "to_parthian":
        output = convert_to_parthian(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "from_parthian":
        output = parthian_to_latin(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "to_parsig":
        output = convert_to_old_persian(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    elif mode == "from_parsig":
        output = old_persian_to_latin(text)
        await update.message.reply_text(output)
        context.user_data["mode"] = None
    else:
        await update.message.reply_text("لطفا ابتدا یک گزینه از منو انتخاب کنید.")

def main():
    app = ApplicationBuilder().token("8367521765:AAEzs2RBi0iJUsSlJWa5m9bc667pCY-CNOw").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("ربات در حال اجراست...")
    app.run_polling()

if __name__ == "__main__":
    main()
