import re
import sqlite3
import os
import datetime
import logging
import urllib.parse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, Message
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.error import BadRequest, TelegramError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_FILE = 'multi.sqlite'
MANDATORY_CHANNELS = ['@s_member']
CHANNEL_MAIN = '@s_member'
CHANNEL_PAID = '@Channel_ssX'
CHANNEL_PENDING = '@qhkt0'
CHANNEL_BROADCAST = '@s_member'  # کانال جدید برای پخش پست‌های تایید شده
START_USERS = 580
DAILY_DIAMOND = 2
REFERRAL_DIAMOND = 10
VIEW_AD_DIAMOND = 2
MEMBER_CLAIM_DIAMOND = 5
PAID_BOT_ADMIN = '@SPARKADM'
LTC_WALLET = 'MLGU15wUF6RS4kLfRS5KMPbgQLCSW2qYBK'
ADS_COST = 30
BOT_TOKEN = '8079297511:AAGr0YDyLPrDy6hVPN8zAuyX2ZoLeiu2Lfw'
ADMIN_USER_ID = "5044461585"
ADMIN_DIAMOND_GIFT = 10000000
GET_MEMBER_COST = 100
LEFT_PENALTY = 10
CHECK_INTERVAL_SECONDS = 60
NEW_USER_BONUS = 30
MAX_AD_TEXT_LENGTH = 1500

def get_db():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def ensure_migrations():
    db = get_db()
    c = db.cursor()
    c.execute("PRAGMA table_info(free_ads_posts)")
    cols = [r[1] for r in c.fetchall()]

    if 'ad_type' not in cols:
        try:
            c.execute("ALTER TABLE free_ads_posts ADD COLUMN ad_type TEXT")
            db.commit()
            logger.info("Migration: added ad_type column to free_ads_posts")
            cols.append('ad_type')
        except Exception as e:
            logger.exception("Migration failed to add ad_type: %s", e)

    if 'approved' not in cols:
        try:
            c.execute("ALTER TABLE free_ads_posts ADD COLUMN approved INTEGER DEFAULT 0")
            db.commit()
            logger.info("Migration: added approved column to free_ads_posts")
        except Exception as e:
            logger.exception("Migration failed to add approved: %s", e)
    db.close()

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
      user_id TEXT PRIMARY KEY,
      first_name TEXT,
      username TEXT,
      diamonds INTEGER DEFAULT 0,
      referrals INTEGER DEFAULT 0,
      join_date TEXT,
      last_daily TEXT,
      referrer TEXT,
      verified INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, total_users INTEGER)""")
    if not c.execute("SELECT * FROM stats").fetchone():
        c.execute("INSERT INTO stats (total_users) VALUES (?)", (START_USERS,))
    c.execute("""CREATE TABLE IF NOT EXISTS free_ads (
        user_id TEXT PRIMARY KEY,
        transfers_in INTEGER DEFAULT 0,
        transfers_out INTEGER DEFAULT 0,
        diamonds INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS paid_orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        photo_id TEXT,
        photo_date TEXT,
        approved INTEGER DEFAULT 0,
        created_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS claimed_ads_free (
        user_id TEXT,
        ad_id TEXT,
        PRIMARY KEY (user_id, ad_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS free_ads_posts (
        ad_id TEXT PRIMARY KEY,
        owner_id TEXT,
        photo_id TEXT,
        description TEXT,
        link TEXT,
        created_at TEXT,
        ad_type TEXT,
        approved INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS free_posts (
        user_id TEXT PRIMARY KEY,
        posted_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS member_claims (
        user_id TEXT,
        ad_id TEXT,
        joined_at TEXT,
        active INTEGER DEFAULT 1,
        PRIMARY KEY (user_id, ad_id)
    )""")
    db.commit()
    admin = c.execute("SELECT diamonds FROM free_ads WHERE user_id=?", (ADMIN_USER_ID,)).fetchone()
    if not admin:
        c.execute("INSERT INTO free_ads (user_id, transfers_in, transfers_out, diamonds) VALUES (?,?,?,?)",
                  (ADMIN_USER_ID, 0, 0, ADMIN_DIAMOND_GIFT))
    else:
        c.execute("UPDATE free_ads SET diamonds=? WHERE user_id=?", (ADMIN_DIAMOND_GIFT, ADMIN_USER_ID))
    db.commit()
    db.close()

def db_query(query, args=(), fetch=False):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    res = cur.fetchall() if fetch else None
    db.commit()
    db.close()
    return res

def get_total_users():
    row = db_query("SELECT total_users FROM stats WHERE id=1", fetch=True)
    return int(row[0][0]) if row else START_USERS

def increment_total_users():
    db_query("UPDATE stats SET total_users = total_users + 1 WHERE id = 1")

def update_user_data(user):
    u = db_query("SELECT user_id FROM users WHERE user_id=?", (str(user.id),), fetch=True)
    if not u:
        db_query("INSERT INTO users (user_id, first_name, username, join_date, diamonds) VALUES (?, ?, ?, ?, 0)",
                 (str(user.id), user.first_name, user.username, datetime.datetime.now().strftime('%Y-%m-%d')))
        increment_total_users()
    fa = db_query("SELECT user_id FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
    if not fa:

        db_query("INSERT INTO free_ads (user_id, transfers_in, transfers_out, diamonds) VALUES (?,0,0,?)", (str(user.id), NEW_USER_BONUS))

def is_member(context, user_id):
    async def _check():
        for ch in MANDATORY_CHANNELS:
            try:
                m = await context.bot.get_chat_member(chat_id=ch, user_id=user_id)
                if m.status not in ['member', 'administrator', 'creator']:
                    return False
            except BadRequest:
                return False
            except Exception:
                continue
        return True
    return _check

def normalize_to_tme_link(link):
    if link.startswith('@'):
        return f'https://t.me/{link.lstrip("@")}'
    if link.startswith('http://') or link.startswith('https://'):
        return link
    return link

def extract_channel_username_from_link(link):
    """Return channel username without @ for @name or https://t.me/name or http://t.me/name"""
    if not link:
        return None
    if link.startswith('@'):
        return link.lstrip('@')
    m = re.match(r'https?://t\.me/([^/]+)', link)
    if m:
        return m.group(1).split('?')[0]
    return None

def chat_id_from_link(link):
    if not link:
        return None
    if link.startswith('@'):
        return link
    if link.startswith('https://t.me/'):
        path = link[len('https://t.me/'):]
        if path.startswith('joinchat') or path.startswith('+'):
            return None
        return '@' + path.split('/')[0].split('?')[0]
    if link.startswith('http://t.me/'):
        path = link[len('http://t.me/'):]
        if path.startswith('joinchat') or path.startswith('+'):
            return None
        return '@' + path.split('/')[0].split('?')[0]
    return None

def main_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Free Ad", callback_data="free_ad"),
         InlineKeyboardButton("Paid Ad", callback_data="paid_ad")],
        [InlineKeyboardButton("Help", callback_data="help")]
    ])

def back_btn(cb="main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=cb)]])

def free_ad_buttons():
    # New
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Order Ads", callback_data="free_order_ads"),
         InlineKeyboardButton("Order Member", callback_data="get_member")],
        [InlineKeyboardButton("Daily Diamonds", callback_data="daily_free_dia")],
        [InlineKeyboardButton("Transfer Diamonds", callback_data="transfer_dia"),
         InlineKeyboardButton("Referral Link", callback_data="ref_link")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])

def paid_ad_buttons(approved_cnt):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Order Ads", callback_data="paid_order_ads")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ])

def paid_prices_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="paid_ad")]
    ])

def format_username(username):
    return f'@{username}' if username else "N/A"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_data(user)
    if not await is_member(context, user.id)():
        await update.message.reply_text(
            f"Please join the following channel(s) first and then press /start again:\n" +
            "\n".join(MANDATORY_CHANNELS)
        )
        return
    ref = (context.args[0] if context.args else None)
    awarded_referral = False
    if ref and ref.isdigit() and int(ref) != user.id:
        prev_ref_row = db_query("SELECT referrer FROM users WHERE user_id=?", (str(user.id),), fetch=True)
        prev_ref = prev_ref_row[0][0] if prev_ref_row and prev_ref_row[0] else None
        if not prev_ref:
            try:
                db_query("UPDATE users SET referrer=? WHERE user_id=?", (str(ref), str(user.id)))
                db_query("UPDATE users SET referrals = COALESCE(referrals,0) + 1 WHERE user_id=?", (str(ref),))
                db_query("INSERT OR IGNORE INTO free_ads (user_id, transfers_in, transfers_out, diamonds) VALUES (?,0,0,0)", (str(ref),))
                db_query("UPDATE free_ads SET diamonds = COALESCE(diamonds,0) + ? WHERE user_id=?", (REFERRAL_DIAMOND, str(ref)))
                awarded_referral = True
            except Exception as e:
                logger.exception("Error applying referral bonus: %s", e)
    tusers = get_total_users()
    username = format_username(user.username)
    name = user.first_name or "-"
    # inform user 
    user_diamonds_row = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
    user_diamonds = user_diamonds_row[0][0] if user_diamonds_row else 0
    await update.message.reply_text(
        f"🫆 Name: {name}\n"
        f"🆔 User ID: {user.id}\n"
        f"🪪 Username: {username}\n"
        f"👥 Total Of Bot Users: {tusers}",
        reply_markup=main_buttons()
    )
    if awarded_referral and ref:
        try:
            ref_chat_id = int(ref)
            referred_name = user.first_name or ""
            referred_username = format_username(user.username) if user.username else f"ID {user.id}"
            msg = (
                f"🎉 You have received {REFERRAL_DIAMOND} diamonds!\n\n"
                f"User {referred_name} ({referred_username}) has just joined the bot using your referral link.\n"
                f"Thank you for referring new users!"
            )
            await context.bot.send_message(chat_id=ref_chat_id, text=msg)
        except Exception as e:
            logger.info("Could not send referral notification to %s: %s", ref, e)

async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user

    if q.data.startswith('paid_confirm:'):
        try:
            # Only info
            if not (getattr(q.message, "chat", None) and getattr(q.message.chat, "username", None) == CHANNEL_PAID.lstrip('@')):
                # ignore clicks
                return
            _, oid = q.data.split(':', 1)
            # ensure only channel admins
            try:
                m = await context.bot.get_chat_member(chat_id=CHANNEL_PAID, user_id=user.id)
                if m.status not in ['administrator', 'creator'] and str(user.id) != ADMIN_USER_ID:
                    # silently ignore
                    return
            except Exception:
                # silently ignore
                return

            row = db_query("SELECT user_id, approved FROM paid_orders WHERE order_id=?", (oid,), fetch=True)
            if not row:
                # silently ignore
                return
            user_id, approved = row[0]
            if approved == 1:
                # already approved
                return
            db_query("UPDATE paid_orders SET approved=1 WHERE order_id=?", (oid,))
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"✅ Your payment has been approved by the admin and now you need to send the ad text to the admin with the username {PAID_BOT_ADMIN}"
                )
            except Exception:
                pass
            try:
                new_caption = (q.message.caption or "") + "\n\n✅ Approved"
                await q.message.edit_caption(new_caption, reply_markup=None)
            except Exception:
                try:
                    await q.message.edit_text((q.message.text or "") + "\n\n✅ Approved", reply_markup=None)
                except Exception:
                    pass
            # optionally acknowledge
            try:
                await q.answer("Order has been approved.", show_alert=False)
            except Exception:
                pass
        except Exception as e:
            logger.exception("Error handling paid_confirm callback: %s", e)
            try:
                await q.answer("Error approving the order.", show_alert=True)
            except Exception:
                pass
        return

    update_user_data(user)
    if not await is_member(context, user.id)():
        await q.answer("Join the required channels first.", show_alert=False, cache_time=2)
        await q.edit_message_text(
            f"Please join the channels below and run /start:\n" +
            "\n".join(MANDATORY_CHANNELS)
        )
        return

    if q.data == "main_menu":
        username = format_username(user.username)
        tusers = get_total_users()
        diamonds_row = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
        diamonds = diamonds_row[0][0] if diamonds_row else 0
        text = (f"🫆 Name: {user.first_name}\n"
                f"🆔 User ID: {user.id}\n"
                f"🪪 Username: {username}\n"
                f"👥 Total Of Bot Users: {tusers}\n")
        await safe_edit_or_send(q, text, main_buttons())
        return

    if q.data == "help":
        msg = """💎 In "Free Ad", you need to collect diamonds to place your ad, which will only be placed after admin approval and then broadcast to all users.

Methods to earn diamonds:
• Daily diamonds (2 diamonds per day)
• Referral (10 diamonds per referral)
• View ads and claim diamonds (inside the bot) and receive 2 diamonds
• Join and claim diamonds (inside the bot) and receive 5 diamonds

❓In Free Ad, you will see two sections: Order Ad and Order Member.  
❗️In Order Ad you can order any ad you want.  
❗️In Order Member you can only order members for your own channel/group; simply put this is a forced add.

💵 In "Paid Ad", payment is required and your ad will be placed in more channels/pages and admin will confirm payments."""
        await safe_edit_or_send(q, msg, back_btn())
        return

    if q.data == "free_ad":
        row = db_query("SELECT transfers_in, transfers_out, diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
        if not row or len(row[0]) < 3:
            db_query("INSERT OR IGNORE INTO free_ads (user_id, transfers_in, transfers_out, diamonds) VALUES (?,0,0,0)", (str(user.id),))
            tr_in = tr_out = diamonds = 0
        else:
            tr_in, tr_out, diamonds = row[0]
        r2 = db_query("SELECT referrals FROM users WHERE user_id=?", (str(user.id),), fetch=True)
        refer_c = int(r2[0][0]) if r2 and r2[0][0] else 0
        text = (f"💳 Transfers\n"
                f"📥 Received: {tr_in}\n"
                f"📤 Sent: {tr_out}\n\n"
                f"👥 Referrals\n"
                f"✔ Total: {refer_c}\n"
                f"✔ Referral commissions: {refer_c * REFERRAL_DIAMOND}\n\n"
                f"✅ Balance: {diamonds}")
        await safe_edit_or_send(q, text, free_ad_buttons())
        return

    if q.data == "daily_free_dia":
        today = datetime.date.today()
        last_row = db_query("SELECT last_daily FROM users WHERE user_id=?", (str(user.id),), fetch=True)
        last = last_row[0][0] if last_row and last_row[0] else ""
        if str(last) != today.strftime('%Y-%m-%d'):
            db_query("UPDATE users SET last_daily=? WHERE user_id=?", (today.strftime('%Y-%m-%d'), str(user.id)))
            db_query("UPDATE free_ads SET diamonds = diamonds + ? WHERE user_id=?", (DAILY_DIAMOND, str(user.id)))
            diamonds = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
            diamonds = diamonds[0][0] if diamonds else 0
            refer_c = db_query("SELECT referrals FROM users WHERE user_id=?", (str(user.id),), fetch=True)[0][0]
            await q.answer(f"+{DAILY_DIAMOND} diamonds added to your account!", show_alert=False, cache_time=2)
            tr_in = db_query('SELECT transfers_in FROM free_ads WHERE user_id=?',(str(user.id),),fetch=True)[0][0]
            tr_out = db_query('SELECT transfers_out FROM free_ads WHERE user_id=?',(str(user.id),),fetch=True)[0][0]
            text = (f"💳 Transfers\n"
                    f"📥 Received: {tr_in}\n"
                    f"📤 Sent: {tr_out}\n\n"
                    f"👥 Referrals\n"
                    f"✔ Total: {refer_c}\n"
                    f"✔ Referral commissions: {refer_c * REFERRAL_DIAMOND}\n\n"
                    f"✅ Balance: {diamonds}")
            await safe_edit_or_send(q, text, free_ad_buttons())
        else:
            await q.answer("You already claimed your daily reward today.", show_alert=False, cache_time=2)
        return

    if q.data == "transfer_dia":
        await safe_edit_or_send(q, "Send the user ID and diamond count separated by space:\n123456 10", back_btn("free_ad"))
        context.user_data['transfer_mode'] = True
        return

    if q.data == "ref_link":
        ref_link = f"https://t.me/Spark_ADBot?start={user.id}"
        await safe_edit_or_send(q, f"Your referral link:\n{ref_link}", back_btn("free_ad"))
        return

    if q.data == "free_order_ads":
        diamonds_q = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
        diamonds = diamonds_q[0][0] if diamonds_q and len(diamonds_q[0]) else 0
        if diamonds < ADS_COST:
            await q.answer("You need 30 diamonds to order.", show_alert=False, cache_time=2)
            return
        await q.answer("Please send the photo for your ad.", show_alert=False, cache_time=2)
        await safe_edit_or_send(q, "Please send the photo for your ad (images only).", back_btn("free_ad"))
        context.user_data['awaiting_free_ad_photo'] = True
        context.user_data.pop('awaiting_free_ad_text', None)
        context.user_data.pop('awaiting_free_ad_link', None)
        context.user_data.pop('free_ad_photo_id', None)
        context.user_data.pop('free_ad_text', None)
        return

    if q.data == "get_member":
        diamonds_q = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
        diamonds = diamonds_q[0][0] if diamonds_q and diamonds_q[0] else 0
        if diamonds < GET_MEMBER_COST:
            await q.answer(f"You need {GET_MEMBER_COST} diamonds to order.", show_alert=False, cache_time=2)
            return
        db_query("UPDATE free_ads SET diamonds = diamonds - ? WHERE user_id=?", (GET_MEMBER_COST, str(user.id)))
        await q.answer(f"{GET_MEMBER_COST} diamonds deducted. ⚠️ To get members, you must first make @Spark_ADBot the admin of your channel/Group and give it the \"Invite Users Via Link\" permission.", show_alert=False, cache_time=2)
        await safe_edit_or_send(q, "⚠️ To get members, you must first make @Spark_ADBot the admin of your channel/Geoup and give it the \"Invite Users Via Link\" permission.\n\nSend the photo for your member-order ad.", back_btn("free_ad"))
        context.user_data['awaiting_get_member_photo'] = True
        context.user_data.pop('awaiting_get_member_text', None)
        context.user_data.pop('awaiting_get_member_link', None)
        context.user_data.pop('get_member_photo_id', None)
        context.user_data.pop('get_member_text', None)
        return

    if q.data == "paid_ad":
        approved_cnt = db_query("SELECT COUNT(*) FROM paid_orders WHERE user_id=? AND approved=1", (str(user.id),), fetch=True)[0][0]
        text = f"✅ Number of times you have been approved:\n{approved_cnt}"
        await safe_edit_or_send(q, text, paid_ad_buttons(approved_cnt))
        return

    if q.data == "paid_order_ads":
        text = (f"""Select one of the options and complete the payment:
2 hours ad - $1
4 hours ad - $2
6 hours ad - $8
12 hours ad - $10
24 hours ad - $15

💳 Wallet address (LTC network):\n{LTC_WALLET}

⚠️ After payment, please 'send' your payment receipt here so that your payment can be confirmed by admin.""")
        await safe_edit_or_send(q, text, paid_prices_buttons())
        context.user_data['awaiting_paid_ad'] = True
        return

async def safe_edit_or_send(q, text, kb):
    try:
        await q.edit_message_text(text, reply_markup=kb)
    except Exception:
        await q.message.reply_text(text, reply_markup=kb)

async def try_copy_or_send_message_to_channel(message, context, channel, reply_markup=None):
    """
    Attempts to post the given `message` to `channel`.
    Returns (True, Message) on success where Message is the sent/copied Message object,
    or (False, error_string) on failure.
    """
    try:
        forward_chat = getattr(message, "forward_from_chat", None)
        forward_msg_id = getattr(message, "forward_from_message_id", None)
        if forward_chat and forward_msg_id:
            sent = await context.bot.copy_message(chat_id=channel, from_chat_id=forward_chat.id, message_id=forward_msg_id, reply_markup=reply_markup)
            return True, sent

        text_candidates = []
        if getattr(message, "text", None):
            text_candidates.append(message.text)
        if getattr(message, "caption", None):
            text_candidates.append(message.caption)

        for t in text_candidates:
            if not t:
                continue
            # t.me/c
            m = re.search(r'https?://t\.me/c/(\d+)/(\d+)', t)
            if m:
                chat_part, msg_part = m.group(1), m.group(2)
                try:
                    from_chat_id = int(f"-100{chat_part}")
                    sent = await context.bot.copy_message(chat_id=channel, from_chat_id=from_chat_id, message_id=int(msg_part), reply_markup=reply_markup)
                    return True, sent
                except TelegramError as e:
                    logger.warning("copy_message via t.me/c link failed: %s", e)
                except Exception as e:
                    logger.warning("copy_message via t.me/c link unexpected error: %s", e)
                break

            m2 = re.search(r'https?://t\.me/([A-Za-z0-9_]+)/(\d+)', t)
            if m2:
                username, msg_part = m2.group(1), m2.group(2)
                from_chat = f"@{username}"
                try:
                    sent = await context.bot.copy_message(chat_id=channel, from_chat_id=from_chat, message_id=int(msg_part), reply_markup=reply_markup)
                    return True, sent
                except TelegramError as e:
                    logger.warning("copy_message via t.me/<username> link failed: %s", e)
                except Exception as e:
                    logger.warning("copy_message via t.me/<username> link unexpected error: %s", e)
                break

        if getattr(message, "photo", None):
            file_id = message.photo[-1].file_id
            sent = await context.bot.send_photo(chat_id=channel, photo=file_id, caption=message.caption or "", reply_markup=reply_markup)
            return True, sent
        if getattr(message, "document", None):
            sent = await context.bot.send_document(chat_id=channel, document=message.document.file_id, caption=message.caption or "", reply_markup=reply_markup)
            return True, sent
        if getattr(message, "text", None):
            sent = await context.bot.send_message(chat_id=channel, text=message.text, reply_markup=reply_markup)
            return True, sent

        return False, "unsupported message type"
    except TelegramError as e:
        logger.exception("TelegramError while posting to channel: %s", e)
        return False, str(e)
    except Exception as e:
        logger.exception("Unexpected error while posting to channel: %s", e)
        return False, str(e)

async def msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_data(user)

    if context.user_data.get('transfer_mode'):
        context.user_data['transfer_mode'] = False
        try:
            tid, cnt = update.message.text.strip().split()
            cnt = int(cnt)
            current_q = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
            current = current_q[0][0] if current_q else 0
            exists = db_query("SELECT * FROM free_ads WHERE user_id=?", (tid,), fetch=True)
            if exists and cnt > 0 and current >= cnt:
                db_query("UPDATE free_ads SET diamonds = diamonds - ?, transfers_out=transfers_out+? WHERE user_id=?", (cnt, cnt, str(user.id)))
                db_query("UPDATE free_ads SET diamonds = diamonds + ?, transfers_in=transfers_in+? WHERE user_id=?", (cnt, cnt, tid))
                await update.message.reply_text("Transfer successful.", reply_markup=back_btn("free_ad"))
                try:
                    await context.bot.send_message(chat_id=int(tid), text=f'💎 {cnt} diamonds received from {user.id}.')
                except Exception:
                    pass
            else:
                await update.message.reply_text("Invalid info or not enough diamonds.", reply_markup=back_btn("free_ad"))
        except Exception:
            await update.message.reply_text("Wrong format.", reply_markup=back_btn("free_ad"))
        return

    if context.user_data.get('awaiting_free_ad_photo'):
        photo_id = None
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
        elif update.message.document and str(getattr(update.message.document, "mime_type", "")) .startswith("image/"):
            photo_id = update.message.document.file_id
        if photo_id:
            context.user_data['awaiting_free_ad_photo'] = False
            context.user_data['free_ad_photo_id'] = photo_id
            context.user_data['awaiting_free_ad_text'] = True
            await update.message.reply_text(f"Photo received. Now send a description for your ad (max {MAX_AD_TEXT_LENGTH} characters, no links).", reply_markup=back_btn("free_ad"))
        else:
            await update.message.reply_text("Please send an image for your ad.", reply_markup=back_btn("free_ad"))
        return

    if context.user_data.get('awaiting_free_ad_text'):
        text = update.message.text.strip() if update.message.text else ""
        if not text or len(text) > MAX_AD_TEXT_LENGTH:
            await update.message.reply_text(f"Ad text must be provided and less than {MAX_AD_TEXT_LENGTH} characters.", reply_markup=back_btn("free_ad"))
            return
        if '@' in text or 'http' in text:
            await update.message.reply_text("Ad text cannot contain links or @ mentions.", reply_markup=back_btn("free_ad"))
            return
        context.user_data['free_ad_text'] = text
        context.user_data.pop('awaiting_free_ad_text', None)
        context.user_data['awaiting_free_ad_link'] = True
        await update.message.reply_text("Description saved. Now send the link for the ad (must start with @durov or http/https).", reply_markup=back_btn("free_ad"))
        return

    if context.user_data.get('awaiting_free_ad_link'):
        link = update.message.text.strip() if update.message.text else ""
        if not link:
            await update.message.reply_text("Please send the link (must start with @ or http/https).", reply_markup=back_btn("free_ad"))
            return
        if not (link.startswith('@') or link.startswith('http://') or link.startswith('https://')):
            await update.message.reply_text("Link must start with @ or http/https. Example: @durov or https://example.com", reply_markup=back_btn("free_ad"))
            return
        diamonds_q = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
        diamonds = diamonds_q[0][0] if diamonds_q else 0
        if diamonds < ADS_COST:
            await update.message.reply_text("Not enough diamonds.", reply_markup=back_btn("free_ad"))
            context.user_data.pop('free_ad_photo_id', None)
            context.user_data.pop('free_ad_text', None)
            context.user_data.pop('awaiting_free_ad_link', None)
            return
        # deduct immediately
        db_query("UPDATE free_ads SET diamonds = diamonds - ? WHERE user_id=?", (ADS_COST, str(user.id)))
        photo_id = context.user_data.pop('free_ad_photo_id', None)
        description = context.user_data.pop('free_ad_text', "")
        context.user_data.pop('awaiting_free_ad_link', None)
        ad_created = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        ad_id = f"{user.id}:{ad_created}"
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_query("INSERT INTO free_ads_posts (ad_id, owner_id, photo_id, description, link, created_at, ad_type, approved) VALUES (?,?,?,?,?,?,?,?)",
                 (ad_id, str(user.id), photo_id, description, link, created_at, 'free', 0))
        db_query("INSERT OR REPLACE INTO free_posts (user_id, posted_at) VALUES (?, ?)", (str(user.id), created_at))
        caption = f"{description}\n\n{link}\n\nOwner ID: {user.id}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm", callback_data=f"free_confirm:{ad_id}")]
        ])
        try:

            await context.bot.send_photo(chat_id=CHANNEL_PENDING, photo=photo_id, caption=caption, reply_markup=kb)
        except Exception as e:
            logger.exception("Failed to post free ad to pending channel: %s", e)
            db_query("UPDATE free_ads SET diamonds = diamonds + ? WHERE user_id=?", (ADS_COST, str(user.id)))
            await update.message.reply_text("Failed to post to admin channel. Diamonds refunded. Please contact admin.", reply_markup=back_btn("free_ad"))
            return
        await update.message.reply_text("✅ Your ad has been submitted for admin approval.", reply_markup=back_btn("free_ad"))
        return


    if context.user_data.get('awaiting_get_member_photo'):
        photo_id = None
        if update.message.photo:
            photo_id = update.message.photo[-1].file_id
        elif update.message.document and str(getattr(update.message.document, "mime_type", "")) .startswith("image/"):
            photo_id = update.message.document.file_id
        if photo_id:
            context.user_data['awaiting_get_member_photo'] = False
            context.user_data['get_member_photo_id'] = photo_id
            context.user_data['awaiting_get_member_text'] = True
            await update.message.reply_text(f"Photo received. Now send a description for your ad (max {MAX_AD_TEXT_LENGTH} characters, no links).", reply_markup=back_btn("free_ad"))
        else:
            await update.message.reply_text("Please send an image for your ad.", reply_markup=back_btn("free_ad"))
        return

    if context.user_data.get('awaiting_get_member_text'):
        text = update.message.text.strip() if update.message.text else ""
        if not text or len(text) > MAX_AD_TEXT_LENGTH:
            await update.message.reply_text(f"Ad text must be provided and less than {MAX_AD_TEXT_LENGTH} characters.", reply_markup=back_btn("free_ad"))
            return
        if '@' in text or 'http' in text:
            await update.message.reply_text("Ad text cannot contain links or @ mentions.", reply_markup=back_btn("free_ad"))
            return
        context.user_data['get_member_text'] = text
        context.user_data.pop('awaiting_get_member_text', None)
        context.user_data['awaiting_get_member_link'] = True
        await update.message.reply_text("Description saved. Now send the link for the ad (must start with @durov or http/https).", reply_markup=back_btn("free_ad"))
        return

    if context.user_data.get('awaiting_get_member_link'):
        link = update.message.text.strip() if update.message.text else ""
        if not link:
            await update.message.reply_text("Please send the link (must start with @ or http/https).", reply_markup=back_btn("free_ad"))
            return
        if not (link.startswith('@') or link.startswith('http://') or link.startswith('https://')):
            await update.message.reply_text("Link must start with @ or http/https. Example: @durov or https://example.com", reply_markup=back_btn("free_ad"))
            return
        photo_id = context.user_data.pop('get_member_photo_id', None)
        description = context.user_data.pop('get_member_text', "")
        context.user_data.pop('awaiting_get_member_link', None)
        ad_created = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        ad_id = f"{user.id}:member:{ad_created}"
        created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        norm_link = normalize_to_tme_link(link)
        db_query("INSERT INTO free_ads_posts (ad_id, owner_id, photo_id, description, link, created_at, ad_type, approved) VALUES (?,?,?,?,?,?,?,?)",
                 (ad_id, str(user.id), photo_id, description, norm_link, created_at, 'member', 0))
        db_query("INSERT OR REPLACE INTO free_posts (user_id, posted_at) VALUES (?, ?)", (str(user.id), created_at))

        chan_username = extract_channel_username_from_link(link)
        encoded_chan = urllib.parse.quote_plus(chan_username) if chan_username else ''
        url_for_button = norm_link
        if url_for_button.startswith('@'):
            url_for_button = f'https://t.me/{url_for_button.lstrip("@")}'

        caption = f"{description}\n\n{norm_link}\n\nOwner ID: {user.id}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm", callback_data=f"free_confirm:{ad_id}")]
        ])
        try:
            await context.bot.send_photo(chat_id=CHANNEL_PENDING, photo=photo_id, caption=caption, reply_markup=kb)
        except Exception as e:
            logger.exception("Failed to post member ad to pending channel: %s", e)
            db_query("UPDATE free_ads SET diamonds = diamonds + ? WHERE user_id=?", (GET_MEMBER_COST, str(user.id)))
            await update.message.reply_text("Failed to post to admin channel. Diamonds refunded. Please contact admin.", reply_markup=back_btn("free_ad"))
            return
        await update.message.reply_text("✅ Your member-order has been submitted for admin approval.", reply_markup=back_btn("free_ad"))
        return

    if context.user_data.get('awaiting_paid_ad'):
        if update.message.photo or update.message.document:
            context.user_data.pop('awaiting_paid_ad')
            photo = update.message.photo[-1].file_id if update.message.photo else update.message.document.file_id
            pdate = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            db_query("INSERT INTO paid_orders (user_id, photo_id, photo_date, created_at) VALUES (?, ?, ?, ?)",
                     (str(user.id), photo, pdate, pdate))
            order_row = db_query("SELECT order_id FROM paid_orders WHERE user_id=? AND created_at=? ORDER BY order_id DESC LIMIT 1",
                                 (str(user.id), pdate), fetch=True)
            order_id = order_row[0][0] if order_row else None
            caption = (f"🫆 Name: {user.first_name}\n"
                       f"🆔 User ID: {user.id}\n"
                       f"⏳ Photo date and time: {pdate}")
            kb = None
            if order_id:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Confirm", callback_data=f"paid_confirm:{order_id}")]
                ])
            try:
                if kb:
                    await context.bot.send_photo(chat_id=CHANNEL_PAID, photo=photo, caption=caption, reply_markup=kb)
                else:
                    await context.bot.send_photo(chat_id=CHANNEL_PAID, photo=photo, caption=caption)
            except Exception as e:
                logger.exception("Failed to send paid order to paid channel: %s", e)
                await update.message.reply_text("Failed to forward your screenshot to admin. Please try again later.", reply_markup=back_btn("paid_ad"))
                return
            await update.message.reply_text(
                "Your screenshot has been sent to the admin for approval\n⏳Review time 5-20 minutes",
                reply_markup=back_btn("main_menu")
            )
            return
        await update.message.reply_text("Please upload a photo receipt.", reply_markup=back_btn("paid_ad"))

async def claim_free_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    logger.info("claim_free_handler called with data=%s from user=%s", q.data, user.id)
    try:
        _, ad_id = q.data.split(':', 1)
        ad_row = db_query("SELECT owner_id, approved FROM free_ads_posts WHERE ad_id=?", (ad_id,), fetch=True)
        if not ad_row:
            await q.answer("Ad not found or not approved yet.", show_alert=False)
            return
        owner_id = ad_row[0][0]
        approved_flag = ad_row[0][1]
        if not approved_flag:
            await q.answer("This ad is not yet approved.", show_alert=False)
            return
        if owner_id and str(user.id) == str(owner_id):
            await q.answer("❌ You can't claim diamonds on your own ad.", show_alert=False)
            return
        claimed = db_query("SELECT * FROM claimed_ads_free WHERE user_id=? AND ad_id=?", (str(user.id), ad_id), fetch=True)
        if claimed:
            await q.answer("❌ You have already claimed for this ad.", show_alert=False)
            return
        db_query("INSERT INTO claimed_ads_free (user_id, ad_id) VALUES (?,?)", (str(user.id), ad_id))
        cur = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
        cur_amount = cur[0][0] if cur else 0
        db_query("UPDATE free_ads SET diamonds=? WHERE user_id=?", (cur_amount + VIEW_AD_DIAMOND, str(user.id)))
        await q.answer(f"🎉 +{VIEW_AD_DIAMOND} diamonds credited.", show_alert=False)
    except Exception as e:
        logger.exception("Error in claim_free handler: %s", e)
        await q.answer("❌ Error while claiming diamond!", show_alert=False)

async def member_claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    logger.info("member_claim_handler called with data=%s from user=%s", q.data, user.id)
    try:
        parts = q.data.split(':', 2)
        if len(parts) < 2:
            await q.answer("Invalid callback", show_alert=True)
            return

        ad_id = urllib.parse.unquote_plus(parts[1])

        chan_username = None
        if len(parts) == 3 and parts[2]:
            chan_username = urllib.parse.unquote_plus(parts[2])

        ad = db_query("SELECT owner_id, link, approved FROM free_ads_posts WHERE ad_id=?", (ad_id,), fetch=True)
        if not ad:
            await q.answer("Order not found.", show_alert=False, cache_time=2)
            return
        owner_id, link, approved_flag = ad[0]
        if not approved_flag:
            await q.answer("This ad is not yet approved.", show_alert=False)
            return
        if str(user.id) == str(owner_id):
            await q.answer("❌ You cannot claim your own order.", show_alert=False, cache_time=2)
            return

        if chan_username:
            chat_ref = f"@{chan_username}"
        else:
            chat_ref = chat_id_from_link(link)
        if not chat_ref:
            await q.answer("Cannot verify joins for invite links. Please provide a channel username like @durov.", show_alert=True)
            return

        try:
            m = await context.bot.get_chat_member(chat_id=chat_ref, user_id=user.id)
            if m.status in ['member', 'administrator', 'creator']:
                claimed = db_query("SELECT * FROM claimed_ads_free WHERE user_id=? AND ad_id=?", (str(user.id), ad_id), fetch=True)
                if claimed:
                    await q.answer("❌ You have already claimed for this ad.", show_alert=False, cache_time=2)
                    return
                db_query("INSERT INTO claimed_ads_free (user_id, ad_id) VALUES (?,?)", (str(user.id), ad_id))
                cur = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (str(user.id),), fetch=True)
                cur_amount = cur[0][0] if cur else 0
                db_query("UPDATE free_ads SET diamonds=? WHERE user_id=?", (cur_amount + MEMBER_CLAIM_DIAMOND, str(user.id)))
                db_query("INSERT OR IGNORE INTO member_claims (user_id, ad_id, joined_at, active) VALUES (?,?,?,1)", (str(user.id), ad_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                await q.answer(f"🎉 +{MEMBER_CLAIM_DIAMOND} diamonds credited.", show_alert=False, cache_time=2)
            else:
                await q.answer("You haven't joined yet", show_alert=True)
        except Exception as e:
            logger.exception("Error checking membership: %s", e)
            await q.answer("You haven't joined yet", show_alert=True)
    except Exception as e:
        logger.exception("Error in member_claim_handler: %s", e)
        await q.answer("Error while claiming.", show_alert=True)

async def periodic_check_members(context: ContextTypes.DEFAULT_TYPE):
    rows = db_query("SELECT user_id, ad_id FROM member_claims WHERE active=1", fetch=True)
    if not rows:
        return
    for user_id, ad_id in rows:
        try:
            ad = db_query("SELECT link FROM free_ads_posts WHERE ad_id=?", (ad_id,), fetch=True)
            if not ad:
                db_query("UPDATE member_claims SET active=0 WHERE user_id=? AND ad_id=?", (user_id, ad_id))
                continue
            link = ad[0][0]
            chat_ref = chat_id_from_link(link)
            if not chat_ref:
                continue
            try:
                m = await context.bot.get_chat_member(chat_id=chat_ref, user_id=int(user_id))
                if m.status not in ['member', 'administrator', 'creator']:
                    raise Exception("left")
            except Exception:
                db_query("UPDATE member_claims SET active=0 WHERE user_id=? AND ad_id=?", (user_id, ad_id))
                cur = db_query("SELECT diamonds FROM free_ads WHERE user_id=?", (user_id,), fetch=True)
                cur_amount = cur[0][0] if cur else 0
                new_amount = max(0, cur_amount - LEFT_PENALTY)
                db_query("UPDATE free_ads SET diamonds=? WHERE user_id=?", (new_amount, user_id))
                try:
                    await context.bot.send_message(chat_id=int(user_id), text=f"🚷 You left the channel/group of one of the orderers and {LEFT_PENALTY} diamonds were deducted from you.")
                except Exception:
                    pass
        except Exception as e:
            logger.exception("Error in periodic_check_members loop: %s", e)

async def admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.username != CHANNEL_PAID.replace('@',''):
        return
    # Ensure only
    try:
        m = await context.bot.get_chat_member(chat_id=CHANNEL_PAID, user_id=update.effective_user.id)
        if m.status not in ['administrator', 'creator'] and str(update.effective_user.id) != ADMIN_USER_ID:
            await update.message.reply_text("You are not authorized to confirm.")
            return
    except Exception:
        await update.message.reply_text("You are not authorized to confirm.")
        return

    args = update.message.text.strip().split()
    if len(args) != 2 or args[0].lower() != '/confirm' or not args[1].isdigit():
        await update.message.reply_text("Usage: /confirm USER_ID")
        return
    user_id = args[1]
    order = db_query(
        "SELECT order_id FROM paid_orders WHERE user_id=? AND approved=0 ORDER BY order_id DESC LIMIT 1",
        (user_id,), fetch=True
    )
    if not order:
        await update.message.reply_text("No unapproved paid order found.")
        return
    db_query("UPDATE paid_orders SET approved=1 WHERE order_id=?", (order[0][0],))
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"✅ Your payment has been approved by the admin and now you need to send the ad text to the admin with the username {PAID_BOT_ADMIN}"
        )
        await update.message.reply_text("User has been notified and marked as approved.")
    except Exception as e:
        await update.message.reply_text("User approved; bot could not deliver notification.")

async def free_admin_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for admin confirm button posted in the admin panel.
    When admin confirms an ad (free or member), mark it approved, notify owner, and broadcast the ad to the s_member channel
    with inline claim buttons so users can claim diamonds inside the bot.
    """
    q = update.callback_query
    user = q.from_user
    try:
        # Only accept confirmations
        if not (getattr(q.message, "chat", None) and getattr(q.message.chat, "username", None) == CHANNEL_PENDING.lstrip('@')):
            # ignore clicks
            return

        _, ad_id = q.data.split(':', 1)
        # Ensure
        try:
            m = await context.bot.get_chat_member(chat_id=CHANNEL_PENDING, user_id=user.id)
            if m.status not in ['administrator', 'creator'] and str(user.id) != ADMIN_USER_ID:
                # silently ignore for non
                return
        except Exception:
            # silently ignoreAdm
            return

        row = db_query("SELECT owner_id, photo_id, description, link, ad_type, approved FROM free_ads_posts WHERE ad_id=?", (ad_id,), fetch=True)
        if not row:
            # ignore not found
            return
        owner_id, photo_id, description, link, ad_type, approved_flag = row[0]
        if approved_flag == 1:
            # already approved, ignore
            return

        db_query("UPDATE free_ads_posts SET approved=1 WHERE ad_id=?", (ad_id,))
        # notify owner
        try:
            await context.bot.send_message(chat_id=int(owner_id), text="Your order has been approved.")
        except Exception:
            logger.info("Could not send approval message to owner %s", owner_id)

        try:
            new_caption = (q.message.caption or "") + "\n\n✅ Approved"
            await q.message.edit_caption(new_caption, reply_markup=None)
        except Exception:
            try:
                await q.message.edit_text((q.message.text or "") + "\n\n✅ Approved", reply_markup=None)
            except Exception:
                pass
        try:
            await q.answer("Order approved and will be broadcast to s_member channel.", show_alert=False)
        except Exception:
            pass
        
        # broadcast to s_member channel
        caption = f"{description}\n\n{link}"
        if ad_type == 'free':
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("View ad and claim diamonds", callback_data=f"claim_free:{ad_id}")]
            ])
        else:  # member
            chan_username = extract_channel_username_from_link(link)
            encoded_chan = urllib.parse.quote_plus(chan_username) if chan_username else ''
            url_for_button = link
            if url_for_button.startswith('@'):
                url_for_button = f'https://t.me/{url_for_button.lstrip("@")}'
            # callback dont forget
            quoted_ad_id = urllib.parse.quote_plus(ad_id)
            callback_data_claim = f"member_claim:{quoted_ad_id}"
            if encoded_chan:
                callback_data_claim = f"{callback_data_claim}:{encoded_chan}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Subscribe to order", url=url_for_button)],
                [InlineKeyboardButton("Join and claim diamonds", callback_data=callback_data_claim)]
            ])
        
        # post to s_member channel instead of broadcasting to all users
        try:
            await context.bot.send_photo(chat_id=CHANNEL_BROADCAST, photo=photo_id, caption=caption, reply_markup=kb)
            logger.info("Ad %s posted to %s", ad_id, CHANNEL_BROADCAST)
        except Exception as e:
            logger.exception("Failed to post ad %s to %s: %s", ad_id, CHANNEL_BROADCAST, e)
            
    except Exception as e:
        logger.exception("Error in free_admin_confirm_handler: %s", e)
        try:
            await q.answer("Error while approving.", show_alert=True)
        except Exception:
            pass

def main():
    if not os.path.exists(DB_FILE):
        init_db()
    else:
        ensure_migrations()
        db = get_db()
        c = db.cursor()
        c.execute("INSERT OR IGNORE INTO free_ads (user_id, diamonds) VALUES (?,?)", (ADMIN_USER_ID, ADMIN_DIAMOND_GIFT))
        c.execute("UPDATE free_ads SET diamonds=? WHERE user_id=?", (ADMIN_DIAMOND_GIFT, ADMIN_USER_ID))
        # ensure tables exist
        c.execute("""CREATE TABLE IF NOT EXISTS free_ads_posts (
            ad_id TEXT PRIMARY KEY,
            owner_id TEXT,
            photo_id TEXT,
            description TEXT,
            link TEXT,
            created_at TEXT,
            ad_type TEXT,
            approved INTEGER DEFAULT 0
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS free_posts (
            user_id TEXT PRIMARY KEY,
            posted_at TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS member_claims (
            user_id TEXT,
            ad_id TEXT,
            joined_at TEXT,
            active INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, ad_id)
        )""")
        db.commit()
        db.close()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('confirm', admin_confirm))
    # handlers for callbacks
    application.add_handler(CallbackQueryHandler(claim_free_handler, pattern=r'^claim_free:'))
    application.add_handler(CallbackQueryHandler(member_claim_handler, pattern=r'^member_claim:'))
    application.add_handler(CallbackQueryHandler(free_admin_confirm_handler, pattern=r'^free_confirm:'))
    application.add_handler(CallbackQueryHandler(cb_handler))
    application.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.Document.IMAGE) & ~filters.COMMAND, msg_handler))
    application.job_queue.run_repeating(periodic_check_members, interval=CHECK_INTERVAL_SECONDS, first=CHECK_INTERVAL_SECONDS)
    application.run_polling()
    print("Bot started.")

if __name__ == '__main__':
    main()