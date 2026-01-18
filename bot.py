print("=== BOT STARTED: v12.1 FINAL MULTI-USER ===")

import os, json, re, asyncio, hashlib, requests
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

BASE_DIR = "profiles"
os.makedirs(BASE_DIR, exist_ok=True)

STRONG_SCORE = 7
MAYBE_SCORE = 5

CTC_RANGES = ["0-8","8-12","12-18","18-25","25-35","35+"]

ROLE_KEYWORDS = [
    "brand","marketing","digital","growth","strategy",
    "communications","category","portfolio",
    "manager","lead","head","director"
]

# ================= UTIL =================
def path_for(chat_id, name):
    return f"{BASE_DIR}/{chat_id}_{name}.json"

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def now():
    return datetime.now(timezone.utc).isoformat()

def job_hash(url):
    return hashlib.sha256(url.encode()).hexdigest()

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "👋 Welcome!\n\n"
        "This bot finds *real jobs* for you automatically.\n\n"
        "Step 1️⃣ Upload your CV (PDF or DOCX).",
        parse_mode="Markdown"
    )

# ================= CV =================
async def handle_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    tg_file = await update.message.document.get_file()
    data = await tg_file.download_as_bytearray()
    text = data.decode(errors="ignore").lower()

    roles = re.findall(
        r"(brand manager|marketing manager|account manager|key account manager|manager|lead)",
        text
    )

    profile = {
        "roles": list(set(roles)) or ["manager"]
    }

    save_json(path_for(chat_id, "profile"), profile)

    kb = [[InlineKeyboardButton(f"₹ {r} LPA", callback_data=f"ctc_{r}")]
          for r in CTC_RANGES]

    await update.message.reply_text(
        "Step 2️⃣ Select your current CTC range:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ================= CTC =================
async def handle_ctc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    chat_id = q.message.chat_id
    profile = load_json(path_for(chat_id, "profile"), {})
    profile["ctc"] = q.data.replace("ctc_", "")
    save_json(path_for(chat_id, "profile"), profile)

    await q.edit_message_text(
        "🚀 All set!\n\n"
        "🔎 Scanning real job systems now.\n"
        "You will receive alerts shortly."
    )

    context.application.create_task(run_discovery(chat_id))

# ================= DISCOVERY =================
async def run_discovery(chat_id):
    await app.bot.send_message(chat_id, "🔎 Searching ATS systems (Greenhouse + Lever)…")

    profile = load_json(path_for(chat_id, "profile"), {})
    seen = load_json(path_for(chat_id, "seen"), {})

    jobs = []
    jobs += fetch_greenhouse_jobs()
    jobs += fetch_lever_jobs()

    await app.bot.send_message(chat_id, f"📦 Retrieved {len(jobs)} raw jobs")

    strong, maybe = [], []

    for job in jobs:
        h = job_hash(job["url"])
        if h in seen:
            continue

        score = score_job(job["title"], profile)
        seen[h] = {**job, "score": score, "found_at": now()}

        if score >= STRONG_SCORE:
            strong.append((job, score))
        elif score >= MAYBE_SCORE:
            maybe.append((job, score))

    save_json(path_for(chat_id, "seen"), seen)

    if not strong and not maybe:
        await app.bot.send_message(
            chat_id,
            "❌ No relevant jobs found right now.\n"
            "Try again later."
        )
        return

    if strong:
        await app.bot.send_message(chat_id, "🔥 *Strong Matches*", parse_mode="Markdown")
        for j, s in strong[:5]:
            await app.bot.send_message(
                chat_id,
                f"*{j['title']}*\n"
                f"🏢 {j['company']}\n"
                f"⭐ {s}/10\n"
                f"🔗 {j['url']}",
                parse_mode="Markdown"
            )

    if maybe:
        await app.bot.send_message(chat_id, "🤔 *Possible Matches*", parse_mode="Markdown")
        for j, s in maybe[:5]:
            await app.bot.send_message(
                chat_id,
                f"*{j['title']}*\n"
                f"🏢 {j['company']}\n"
                f"⭐ {s}/10\n"
                f"🔗 {j['url']}",
                parse_mode="Markdown"
            )

# ================= ATS =================
def fetch_greenhouse_jobs():
    jobs = []
    try:
        boards = requests.get(
            "https://boards-api.greenhouse.io/v1/boards",
            timeout=10
        ).json()

        for b in boards[:25]:
            slug = b.get("slug")
            if not slug:
                continue

            postings = requests.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                timeout=10
            ).json().get("jobs", [])

            for p in postings:
                loc = (p.get("location") or {}).get("name","").lower()
                if "india" in loc:
                    jobs.append({
                        "title": p.get("title",""),
                        "company": slug,
                        "url": p.get("absolute_url")
                    })
    except:
        pass

    return jobs

def fetch_lever_jobs():
    jobs = []
    try:
        data = requests.get(
            "https://api.lever.co/v0/postings",
            timeout=10
        ).json()

        for p in data:
            loc = (p.get("categories") or {}).get("location","").lower()
            if "india" in loc:
                jobs.append({
                    "title": p.get("text",""),
                    "company": p.get("company","lever"),
                    "url": p.get("hostedUrl")
                })
    except:
        pass

    return jobs

# ================= SCORING =================
def score_job(title, profile):
    t = title.lower()
    s = 1

    if any(r in t for r in profile.get("roles", [])):
        s += 4
    if any(k in t for k in ROLE_KEYWORDS):
        s += 3
    if any(x in t for x in ["manager","lead","head","director"]):
        s += 2

    return min(s, 10)

# ================= APP =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_cv))
app.add_handler(CallbackQueryHandler(handle_ctc, pattern="^ctc_"))

app.run_polling()