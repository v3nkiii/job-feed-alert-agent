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
    await update.message.reply_text(
        "👋 Welcome!\n\nStep 1️⃣: Upload your CV (PDF or DOCX)."
    )

async def handle_cv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    path = f"/tmp/{update.message.document.file_name}"
    await file.download_to_drive(path)

    text = extract_text(path)
    profile = parse_profile(text)

    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    await update.message.reply_text(
        "✅ CV processed.\n\nStep 2️⃣: Preferred work mode?\n"
        "Type one:\nRemote / Hybrid / Onsite / All"
    )

async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text.lower()
    if mode not in ["remote", "hybrid", "onsite", "all"]:
        return

    with open(PROFILE_FILE) as f:
        profile = json.load(f)

    profile["work_mode"] = mode

    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    if mode == "remote":
        await update.message.reply_text(
            "🎯 Setup complete!\nI will now send you relevant jobs automatically."
        )
    else:
        await update.message.reply_text(
            "Step 3️⃣: Preferred location(s)?\nExample: Bangalore, India"
        )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.text

    with open(PROFILE_FILE) as f:
        profile = json.load(f)

    profile["location"] = location

    with open(PROFILE_FILE, "w") as f:
        json.dump(profile, f, indent=2)

    await update.message.reply_text(
        "🚀 All set!\nI will now start sending relevant jobs (score ≥ 5)."
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
