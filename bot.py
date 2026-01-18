print("=== BOT STARTED: v12.3 FINAL PRACTICAL ===")

import os, json, re, hashlib, requests, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
COMPANY_FILE = "company_ats.json"
SEEN_FILE = "seen_jobs.json"

USERS = {}

ROLE_KEYWORDS = [
    "brand", "marketing", "growth", "category",
    "communications", "digital", "strategy", "content"
]

SENIORITY_KEYWORDS = [
    "manager", "lead", "head", "senior", "principal"
]

# -------------------- UTILS --------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def hash_job(title, company, link):
    return hashlib.md5(f"{title}{company}{link}".encode()).hexdigest()

# -------------------- CV PARSING --------------------

def extract_text(path):
    if path.endswith(".pdf"):
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return " ".join(p.extract_text() or "" for p in pdf.pages)
    if path.endswith(".docx"):
        import docx
        doc = docx.Document(path)
        return " ".join(p.text for p in doc.paragraphs)
    return ""

def parse_profile(text):
    text = text.lower()
    skills = list(set(re.findall(r"\b[a-z]{4,}\b", text)))
    return {
        "skills": skills[:20],
        "role_focus": "brand"
    }

# -------------------- TELEGRAM FLOW --------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USERS[update.effective_chat.id] = {"step": "cv"}
    await update.message.reply_text("👋 Upload your CV (PDF or DOCX)")

async def handle_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id

    file = await update.message.document.get_file()
    path = f"/tmp/{update.message.document.file_name}"
    await file.download_to_drive(path)

    profile = parse_profile(extract_text(path))
    USERS[chat].update(profile)
    USERS[chat]["step"] = "ctc"

    buttons = [
        [InlineKeyboardButton("₹5–10 LPA", callback_data="ctc_5")],
        [InlineKeyboardButton("₹10–20 LPA", callback_data="ctc_10")],
        [InlineKeyboardButton("₹20+ LPA", callback_data="ctc_20")]
    ]

    await update.message.reply_text(
        "Select your current CTC",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_ctc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat = query.message.chat.id
    USERS[chat]["ctc"] = query.data
    USERS[chat]["active"] = True

    await query.message.reply_text(
        "✅ Setup complete.\n"
        "🔔 I will now send you relevant job alerts every 6 hours."
    )

    await run_job_search(chat, context, notify=True)

# -------------------- JOB SEARCH CORE --------------------

async def run_job_search(chat_id, context, notify=False):
    user = USERS.get(chat_id)
    if not user:
        return

    companies = load_json(COMPANY_FILE, {})
    seen_all = load_json(SEEN_FILE, {})
    seen_user = set(seen_all.get(str(chat_id), []))
    new_seen = set(seen_user)

    matches = []

    for company, cfg in companies.items():
        try:
            if cfg["ats"] == "greenhouse":
                url = f"https://boards-api.greenhouse.io/v1/boards/{cfg['slug']}/jobs"
                res = requests.get(url, timeout=10)
                jobs = res.json().get("jobs", [])
            else:
                url = f"https://api.lever.co/v0/postings/{cfg['slug']}"
                res = requests.get(url, timeout=10)
                jobs = res.json()

            for job in jobs:
                title = job.get("title", "")
                link = job.get("absolute_url") or job.get("hostedUrl") or ""
                location = (
                    job.get("location", {}).get("name", "")
                    if isinstance(job.get("location"), dict)
                    else ""
                )

                t = title.lower()
                score = 0

                # Core role match (MOST IMPORTANT)
                if any(k in t for k in ROLE_KEYWORDS):
                    score += 5

                # Seniority
                if any(s in t for s in SENIORITY_KEYWORDS):
                    score += 2

                # India bias (soft)
                if "india" in location.lower():
                    score += 1

                # Optional skill hint
                desc = (job.get("content") or "").lower()
                if any(sk in desc for sk in user["skills"][:5]):
                    score += 1

                if score < 4:
                    continue

                h = hash_job(title, company, link)
                if h in seen_user:
                    continue

                new_seen.add(h)
                matches.append((score, title, company, link))

        except:
            continue

    if matches and notify:
        matches.sort(reverse=True)
        await context.bot.send_message(
            chat_id,
            f"🔥 New relevant jobs found: {len(matches)}"
        )
        for score, title, company, link in matches[:10]:
            await context.bot.send_message(
                chat_id,
                f"⭐ {score}/10\n{title}\n{company}\n🔗 {link}"
            )

    seen_all[str(chat_id)] = list(new_seen)
    save_json(SEEN_FILE, seen_all)

# -------------------- DAILY SCHEDULER --------------------

async def scheduler(app):
    while True:
        await asyncio.sleep(6 * 60 * 60)  # every 6 hours
        for chat_id in list(USERS.keys()):
            await run_job_search(chat_id, app, notify=True)

# -------------------- APP --------------------

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_cv))
app.add_handler(CallbackQueryHandler(handle_ctc, pattern="ctc_"))

app.post_init = lambda app: asyncio.create_task(scheduler(app))
app.run_polling()
