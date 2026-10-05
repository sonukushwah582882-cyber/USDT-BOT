import os
import logging
from datetime import datetime
from collections import defaultdict
from threading import Thread
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Fixed Exchange Rate
EXCHANGE_RATE = 112

# Flask server for 24/7 uptime via UptimeRobot
app_flask = Flask('')

@app_flask.route('/')
def home():
    return "USDT Work Bot is active and running 24/7!"

def run_flask():
    app_flask.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# Har group ka alag data aur start time rakhne ke liye
group_data = defaultdict(lambda: {"transactions": [], "start_time": datetime.now()})

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
        
    text = update.message.text.strip()
    user = update.effective_user
    chat = update.effective_chat
    chat_id = chat.id
    bot_username = context.bot.username

    # 1. Mention Handling, Reset Command & Auto-Delete
    if bot_username and f"@{bot_username.lower()}" in text.lower():
        try:
            await update.message.delete()
        except Exception:
            pass

        clean_text = text.replace(f"@{bot_username}", "").replace(f"@{bot_username.lower()}", "").strip()
        lower_clean = clean_text.lower()
        
        # Reset Command (Admin Only)
        if "reset" in lower_clean or "clear" in lower_clean or "delete" in lower_clean:
            if chat.type in ["group", "supergroup"]:
                try:
                    member = await chat.get_member(user.id)
                    if member.status not in ["administrator", "creator"]:
                        await chat.send_message("Only group administrators can reset the records.")
                        return
                except Exception:
                    return
            
            group_data[chat_id] = {"transactions": [], "start_time": datetime.now()}
            await chat.send_message("🔄 Records have been successfully reset! A new day/bill has started.")
            return

        if clean_text.startswith('+') or "u" in lower_clean or "usdt" in lower_clean or clean_text.isdigit():
            text = clean_text 
        else:
            if "how are you" in lower_clean or "hello" in lower_clean or "hi" in lower_clean:
                await chat.send_message("I am doing great! Ready for USDT WORK ✈️️💸.")
            elif "help" in lower_clean:
                await chat.send_message("Send deposit in INR like 5000 or +6000, or credit in USDT like 45.5u. Type @bot_username reset to clear records.")
            else:
                await chat.send_message("I'm here and listening. How can I help you?")
            return

    # 2. Transaction Validation
    cleaned_val = text.replace('+', '').strip()
    is_credit = ('u' in text.lower() or 'usdt' in text.lower())
    is_deposit = cleaned_val.isdigit()

    if not (is_credit or is_deposit):
        return

    if chat.type in ["group", "supergroup"]:
        try:
            member = await chat.get_member(user.id)
            if member.status not in ["administrator", "creator"]:
                return  
        except Exception:
            return

    # 3. Process Transaction
    try:
        current_time = datetime.now()
        time_str = current_time.strftime("%H:%M:%S")

        if is_credit:
            # Credit (Incoming USDT, e.g., 45.5u)
            clean_num = "".join([c for c in text if c.isdigit() or c == '.'])
            usdt_val = float(clean_num)
            inr_val = usdt_val * EXCHANGE_RATE  # 45.5 x 112 = 5096
            
            group_data[chat_id]["transactions"].append({
                "type": "credit",
                "usdt": usdt_val,
                "inr": inr_val,
                "time": time_str
            })
        else:
            # Deposits / Additions in INR (e.g., 5000 or +6000)
            clean_num = "".join([c for c in text if c.isdigit() or c == '.'])
            inr_val = float(clean_num)
            usdt_val = inr_val / EXCHANGE_RATE  # e.g., 5000 / 112 = 44.643
            
            group_data[chat_id]["transactions"].append({
                "type": "deposit",
                "usdt": usdt_val,
                "inr": inr_val,
                "time": time_str
            })

        data = group_data[chat_id]
        transactions = data["transactions"]

        deposits = [t for t in transactions if t["type"] == "deposit"]
        credits = [t for t in transactions if t["type"] == "credit"]

        total_deposit_inr = sum(t["inr"] for t in deposits)
        total_deposit_usdt = sum(t["usdt"] for t in deposits)

        total_credit_inr = sum(t["inr"] for t in credits)
        total_credit_usdt = sum(t["usdt"] for t in credits)

        # Remaining Calculation (Total Credit minus Total Deposits)
        remaining_inr = total_credit_inr - total_deposit_inr
        remaining_usdt = total_credit_usdt - total_deposit_usdt

        worked_minutes = int((current_time - data["start_time"]).total_seconds() / 60)

        # Exact Screenshot Format Matching
        report = ""
        
        report += f"Deposits: ({len(deposits)} transaction{'s' if len(deposits) != 1 else ''})\n"
        for d in deposits:
            report += f"{d['time']} {d['inr']:,.0f} / {EXCHANGE_RATE} = {d['usdt']:.3f}U\n"
            
        report += f"\nCredit: ({len(credits)} item{'s' if len(credits) != 1 else ''})\n"
        for c in credits:
            report += f"{c['time']} {c['usdt']}U ({c['inr']:,.1f})\n"

        report += f"\nTotal deposits: {total_deposit_inr:,.0f}\n"
        report += f"Input Usage: {total_deposit_usdt:.2f}\n"
        report += f"\nUSD exchange rate: {EXCHANGE_RATE}\n"
        report += f"\n{total_credit_inr:,.0f} | {total_credit_usdt:.3f} USDT to be issued\n"
        report += f"Total issued: {total_deposit_inr:,.0f} | {total_deposit_usdt:.3f} USDT\n"
        report += f"Remaining: {remaining_inr:,.0f} | {remaining_usdt:.3f} USDT\n"
        report += f"\n{worked_minutes} minutes have been worked"

        await update.message.reply_text(report)
    except ValueError:
        pass

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    data = group_data[chat_id]
    transactions = data["transactions"]

    if not transactions:
        await update.message.reply_text("No transactions have been recorded in this group yet.")
        return

    deposits = [t for t in transactions if t["type"] == "deposit"]
    credits = [t for t in transactions if t["type"] == "credit"]

    total_deposit_inr = sum(t["inr"] for t in deposits)
    total_deposit_usdt = sum(t["usdt"] for t in deposits)

    total_credit_inr = sum(t["inr"] for t in credits)
    total_credit_usdt = sum(t["usdt"] for t in credits)

    remaining_inr = total_credit_inr - total_deposit_inr
    remaining_usdt = total_credit_usdt - total_deposit_usdt

    worked_minutes = int((datetime.now() - data["start_time"]).total_seconds() / 60)

    report = ""
    
    report += f"Deposits: ({len(deposits)} transaction{'s' if len(deposits) != 1 else ''})\n"
    for d in deposits:
        report += f"{d['time']} {d['inr']:,.0f} / {EXCHANGE_RATE} = {d['usdt']:.3f}U\n"
        
    report += f"\nCredit: ({len(credits)} item{'s' if len(credits) != 1 else ''})\n"
    for c in credits:
        report += f"{c['time']} {c['usdt']}U ({c['inr']:,.1f})\n"

    report += f"\nTotal deposits: {total_deposit_inr:,.0f}\n"
    report += f"Input Usage: {total_deposit_usdt:.2f}\n"
    report += f"\nUSD exchange rate: {EXCHANGE_RATE}\n"
    report += f"\n{total_credit_inr:,.0f} | {total_credit_usdt:.3f} USDT to be issued\n"
    report += f"Total issued: {total_deposit_inr:,.0f} | {total_deposit_usdt:.3f} USDT\n"
    report += f"Remaining: {remaining_inr:,.0f} | {remaining_usdt:.3f} USDT\n"
    report += f"\n{worked_minutes} minutes have been worked"

    await update.message.reply_text(report)

if __name__ == '__main__':
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        exit(1)
        
    keep_alive()
        
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.run_polling()
