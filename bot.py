print("=== BOT STARTED: v12 FINAL STABLE ===")

import os, json, re, hashlib, requests
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
COMPANY_FILE = "company_ats.json"

USERS = {}

# -------------------- HELPERS --------------------

def load_companies():
    with open(COMPANY_FILE) as f:
        return json.load(f)

def hash_job(title, company, url):
    return hashlib.md5(f"{title}{company}{url}".encode()).hexdigest()

def extract_text_from_file(path):
    if path.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return " ".join(page.extract_text() or "" for page in pdf.pages)
    if path.endswith(".docx"):
        import docx
        doc = docx.Document(path)
        return " ".join(p.text for p in doc.paragraphs)
    return ""

def parse_profile(text):
    text = text.lower()
    skills = set(re.findall(r"\b[a-z]{4,}\b", text))
    titles = ["brand", "marketing", "manager", "lead", "growth", "strategy"]
    title = next((t for t in titles if t in text), "manager")
    return {"skills": list(skills), "title": title}

# -------------------- START FLOW --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USERS[update.effective_chat.id] = {"step": "cv"}
    await update.message.reply_text("👋 Upload CV (PDF or DOCX)")

async def handle_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    file = await update.message.document.get_file()
    path = f"/tmp/{update.message.document.file_name}"
    await file.download_to_drive(path)

    text = extract_text_from_file(path)
    profile = parse_profile(text)

    USERS[chat].update(profile)
    USERS[chat]["step"] = "ctc"

    buttons = [
        [InlineKeyboardButton("₹5–10 LPA", callback_data="ctc_5")],
        [InlineKeyboardButton("₹10–20 LPA", callback_data="ctc_10")],
        [InlineKeyboardButton("₹20+ LPA", callback_data="ctc_20")]
    ]

    await update.message.reply_text(
        "Select current CTC",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_ctc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = query.message.chat.id
    USERS[chat]["ctc"] = query.data
    USERS[chat]["step"] = "search"

    await query.message.reply_text("🔎 Searching ATS systems...")
    await run_job_search(chat, context)

# -------------------- JOB SEARCH --------------------

async def run_job_search(chat_id, context):
    user = USERS[chat_id]
    companies = load_companies()

    found = []
    seen = set()

    for name, cfg in companies.items():
        try:
            if cfg["ats"] == "greenhouse":
                url = f"https://boards-api.greenhouse.io/v1/boards/{cfg['slug']}/jobs"
            else:
                url = f"https://api.lever.co/v0/postings/{cfg['slug']}"

            res = requests.get(url, timeout=10)
            if res.status_code != 200:
                continue

            jobs = res.json().get("jobs") if "jobs" in res.json() else res.json()

            for job in jobs:
                title = job.get("title", "")
                location = job.get("location", {}).get("name", "")
                desc = (job.get("content") or "").lower()

                score = 0
                if user["title"] in title.lower():
                    score += 4
                for s in user["skills"][:20]:
                    if s in desc:
                        score += 1

                if score < 5:
                    continue

                h = hash_job(title, name, job.get("absolute_url", ""))
                if h in seen:
                    continue

                seen.add(h)
                found.append((score, title, name, job.get("absolute_url")))

        except Exception:
            continue

    if not found:
        await context.bot.send_message(
            chat_id,
            "❌ No relevant jobs right now.\nI will keep checking automatically."
        )
        return

    found.sort(reverse=True)
    await context.bot.send_message(chat_id, f"🔥 Found {len(found)} relevant jobs:\n")

    for score, title, company, link in found[:10]:
        await context.bot.send_message(
            chat_id,
            f"⭐ {score}/10\n{title}\n{company}\n🔗 {link}"
        )

# -------------------- ROUTER --------------------

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please follow the flow. Type /start")

# -------------------- APP --------------------

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_cv))
app.add_handler(CallbackQueryHandler(handle_ctc, pattern="ctc_"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

app.run_polling()
