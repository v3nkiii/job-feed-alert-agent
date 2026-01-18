from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import pdfplumber
import docx
import re
import json
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

PROFILE_FILE = "profile.json"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["step"] = "cv"

    await update.message.reply_text(
        "👋 Welcome!\n\n"
        "Step 1️⃣: Upload your CV (PDF or DOCX)."
    )


async def handle_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    path = f"/tmp/{update.message.document.file_name}"
    await file.download_to_drive(path)

    text = extract_text(path)
    profile = parse_profile(text)

    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    context.user_data["step"] = "mode"

await update.message.reply_text(
    "✅ CV processed.\n\n"
    "Step 2️⃣: Preferred work mode?\n"
    "Type one:\n"
    "Remote / Hybrid / Onsite / All"
)

async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "mode":
        return

    mode = update.message.text.strip().lower()

    if mode not in ["remote", "hybrid", "onsite", "all"]:
        await update.message.reply_text(
            "❌ Please type one of:\nRemote / Hybrid / Onsite / All"
        )
        return

    # save mode
    with open(PROFILE_FILE) as f:
        profile = json.load(f)

    profile["work_mode"] = mode

    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    # ✅ CASE 1: REMOTE
    if mode == "remote":
        context.user_data["step"] = "done"
        await update.message.reply_text(
            "🚀 All set!\n\n"
            "I will now start sending relevant jobs automatically (score ≥ 5)."
        )
        return   # ⬅️ IMPORTANT

    # ✅ CASE 2: NOT REMOTE (hybrid / onsite / all)
    context.user_data["step"] = "location"
    await update.message.reply_text(
        "Step 3️⃣: Preferred location(s)?\n"
        "Example: Bangalore, Mumbai"
    )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("step") != "location":
        return

    location = update.message.text.strip()

    with open(PROFILE_FILE) as f:
        profile = json.load(f)

    profile["location"] = location

    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    context.user_data["step"] = "done"

    await update.message.reply_text(
        "🚀 All set!\n\n"
        f"Preferred location(s): {location}\n\n"
        "I will now start sending relevant jobs automatically "
        "(score ≥ 5)."
    )


def extract_text(path):
    if path.endswith(".pdf"):
        with pdfplumber.open(path) as pdf:
            return " ".join(page.extract_text() or "" for page in pdf.pages)
    elif path.endswith(".docx"):
        doc = docx.Document(path)
        return " ".join(p.text for p in doc.paragraphs)
    return ""

def parse_profile(text):
    years = re.findall(r'(\d+)\+?\s+years', text.lower())
    experience = max(map(int, years)) if years else 0

    titles = re.findall(r'(manager|lead|engineer|consultant|account manager)', text.lower())
    title = titles[0] if titles else "unknown"

    skills = list(set(re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())))

    return {
        "title": title,
        "experience": experience,
        "skills": skills[:40]
    }

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.Document.ALL, handle_cv))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mode))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location))

app.run_polling()
