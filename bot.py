from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date

from telegram import InputFile, Update
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from config import settings
from database import db
from matching import calculate_age, validate_date_of_birth, users_match
from moderation import admin_stats, contains_suspicious_content, list_recent_reports
from rate_limit import rate_limiter
from safety import safety_text, safety_warning

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROFILE_NICKNAME, PROFILE_DOB, PROFILE_GENDER, PROFILE_CITY, PROFILE_PHOTO, PROFILE_MIN_AGE, PROFILE_MAX_AGE, PROFILE_PREFERRED_GENDER, PROFILE_PREFERRED_LOCATION, PROFILE_MODE = range(10)

GENDERS = ["male", "female", "other", "prefer not to say"]
MODES = ["casual talk", "dating"]


def normalize_gender_choice(value: str) -> str:
    lowered = (value or "").strip().lower()
    mapping = {
        "m": "male",
        "male": "male",
        "f": "female",
        "female": "female",
        "other": "other",
        "prefer not to say": "prefer not to say",
        "prefer not to say ": "prefer not to say",
    }
    return mapping.get(lowered, lowered)


def profile_is_complete(user: dict | None) -> bool:
    if user is None:
        return False
    required = [
        "nickname",
        "date_of_birth",
        "gender",
        "city",
        "min_age",
        "max_age",
        "preferred_gender",
        "preferred_location",
        "mode",
    ]
    for key in required:
        if user.get(key) in (None, ""):
            return False
    return True


def user_profile_dict(row) -> dict:
    if row is None:
        return {}
    data = dict(row)
    dob_value = data.get("date_of_birth")
    if dob_value:
        try:
            data["age"] = calculate_age(date.fromisoformat(dob_value))
        except ValueError:
            data["age"] = None
    return data


async def start_profile_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"] = {}
    await update.message.reply_text(
        "Welcome to StrangerMatch. This service is for adults 18+ only.\n\n"
        "We will collect your anonymous profile to match you with compatible strangers.\n"
        "Please enter your nickname."
    )
    return PROFILE_NICKNAME


async def handle_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nickname = (update.message.text or "").strip()
    if len(nickname) < 2:
        await update.message.reply_text("Please enter a nickname with at least 2 characters.")
        return PROFILE_NICKNAME
    context.user_data["profile"]["nickname"] = nickname
    await update.message.reply_text(
        "Enter your date of birth in YYYY-MM-DD format.\nExample: 1998-07-25\nThis is self-declared age assurance only and is not identity verification."
    )
    return PROFILE_DOB


async def handle_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = (update.message.text or "").strip()
    try:
        validated = validate_date_of_birth(raw)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return PROFILE_DOB
    context.user_data["profile"]["date_of_birth"] = validated
    context.user_data["profile"]["age_verified_at"] = db.now_iso()
    await update.message.reply_text(
        "Choose your gender:",
    )
    await update.message.reply_text("Male\nFemale\nOther\nPrefer not to say")
    return PROFILE_GENDER


async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = normalize_gender_choice(update.message.text or "")
    if gender not in {"male", "female", "other", "prefer not to say"}:
        await update.message.reply_text("Please choose a valid gender from the options above.")
        return PROFILE_GENDER
    context.user_data["profile"]["gender"] = gender
    await update.message.reply_text("What city or area are you in? (General area only, not your exact home address.)")
    return PROFILE_CITY


async def handle_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = (update.message.text or "").strip()
    if len(city) < 2:
        await update.message.reply_text("Please enter a valid city or area.")
        return PROFILE_CITY
    context.user_data["profile"]["city"] = city
    await update.message.reply_text(
        "Profile photo is optional. Would you like to add one?\nSend a photo now, or type /skip to continue."
    )
    return PROFILE_PHOTO


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["profile"].setdefault("profile_photo_file_id", None)
    await update.message.reply_text("Preferred minimum age? Enter a number, for example 22.")
    return PROFILE_MIN_AGE


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo
    if photo:
        context.user_data["profile"]["profile_photo_file_id"] = photo[-1].file_id
    else:
        text = (update.message.text or "").strip().lower()
        if text not in {"skip", "/skip", "no", "next"}:
            await update.message.reply_text("Please send a photo, or type /skip to continue.")
            return PROFILE_PHOTO
    await update.message.reply_text("Preferred minimum age? Enter a number, for example 22.")
    return PROFILE_MIN_AGE


async def handle_min_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = int((update.message.text or "").strip())
    except ValueError:
        await update.message.reply_text("Please enter a valid integer age.")
        return PROFILE_MIN_AGE
    if value < 18:
        await update.message.reply_text("Minimum age must be 18 or older.")
        return PROFILE_MIN_AGE
    context.user_data["profile"]["min_age"] = value
    await update.message.reply_text("Preferred maximum age? Enter a number, for example 35.")
    return PROFILE_MAX_AGE


async def handle_max_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = int((update.message.text or "").strip())
    except ValueError:
        await update.message.reply_text("Please enter a valid integer age.")
        return PROFILE_MAX_AGE
    if value < 18:
        await update.message.reply_text("Maximum age must be 18 or older.")
        return PROFILE_MAX_AGE
    context.user_data["profile"]["max_age"] = value
    await update.message.reply_text("Preferred gender? Choose: male, female, other, any")
    return PROFILE_PREFERRED_GENDER


async def handle_preferred_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = normalize_gender_choice(update.message.text or "")
    valid = {"male", "female", "other", "any"}
    if value not in valid:
        await update.message.reply_text("Please choose one of: male, female, other, any")
        return PROFILE_PREFERRED_GENDER
    context.user_data["profile"]["preferred_gender"] = value
    await update.message.reply_text("Preferred location or city area? For example: Chennai or Central Chennai")
    return PROFILE_PREFERRED_LOCATION


async def handle_preferred_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = (update.message.text or "").strip()
    if len(location) < 2:
        await update.message.reply_text("Please enter a valid location.")
        return PROFILE_PREFERRED_LOCATION
    context.user_data["profile"]["preferred_location"] = location
    await update.message.reply_text("Choose your conversation mode: Casual Talk or Dating")
    return PROFILE_MODE


async def handle_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = (update.message.text or "").strip().lower()
    mode = "dating" if "dating" in value else "casual talk" if "casual" in value else ""
    if mode not in MODES:
        await update.message.reply_text("Please say either 'Casual Talk' or 'Dating'.")
        return PROFILE_MODE
    context.user_data["profile"]["mode"] = mode
    profile = context.user_data["profile"]
    profile["active"] = 1
    profile["banned"] = 0
    profile["partner_id"] = None
    db.upsert_user_profile(update.effective_user.id, profile)
    await update.message.reply_text(
        "Your profile is ready.\n\nUse /find to search for a compatible stranger.\nUse /help for all commands."
    )
    return ConversationHandler.END


async def cancel_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("profile", None)
    await update.message.reply_text("Profile setup cancelled.")
    return ConversationHandler.END


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    existing = db.get_user_by_telegram_id(user.id)
    if existing is not None:
        await update.message.reply_text(
            "Welcome back to StrangerMatch.\nUse /find to meet someone new, /profile to view your current profile, or /start to refresh your setup."
        )
        if not profile_is_complete(dict(existing)):
            return await start_profile_flow(update, context)
        return
    return await start_profile_flow(update, context)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_by_telegram_id(update.effective_user.id)
    if not user:
        await update.message.reply_text("Your profile is not set up yet. Use /start to create one.")
        return
    profile = user_profile_dict(user)
    text = (
        f"Nickname: {profile.get('nickname') or 'N/A'}\n"
        f"Age: {profile.get('age') or 'Not verified'}\n"
        f"Gender: {profile.get('gender') or 'N/A'}\n"
        f"City: {profile.get('city') or 'N/A'}\n"
        f"Min age: {profile.get('min_age') or 'N/A'}\n"
        f"Max age: {profile.get('max_age') or 'N/A'}\n"
        f"Preferred gender: {profile.get('preferred_gender') or 'N/A'}\n"
        f"Preferred location: {profile.get('preferred_location') or 'N/A'}\n"
        f"Mode: {profile.get('mode') or 'N/A'}"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "/start - Create or refresh your profile\n"
        "/find - Find a compatible stranger\n"
        "/next - End current chat and find another\n"
        "/stop - End the current conversation\n"
        "/block - Block the current stranger\n"
        "/report - Report the current stranger\n"
        "/profile - Show your profile\n"
        "/safety - Display safety guidance\n"
        "/delete - Permanently delete your profile\n"
        "/help - Show this menu"
    )
    if update.effective_user.id in settings.ADMIN_IDS:
        message += "\n\nAdmin commands:\n/admin_help - Show admin commands\n/admin_stats - Show bot statistics\n/admin_report - Show recent reports\n/admin_users - List users\n/admin_user USER_ID - Inspect a user\n/ban USER_ID [reason]\n/unban USER_ID"
    await update.message.reply_text(message)


async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    await update.message.reply_text(
        "/admin_help - Show admin commands\n"
        "/admin_stats - Show bot statistics\n"
        "/admin_report - Show recent reports\n"
        "/admin_users - List users\n"
        "/admin_user USER_ID - Inspect a specific user\n"
        "/ban USER_ID [reason] - Ban a user\n"
        "/unban USER_ID - Unban a user"
    )


async def admin_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    users = db.get_all_users()
    if not users:
        await update.message.reply_text("No users found.")
        return
    lines = ["Users:"]
    for user in users[:20]:
        status = "banned" if user["banned"] == 1 else "active" if user["active"] == 1 else "inactive"
        nickname = user["nickname"] or "No nickname"
        lines.append(
            f"{user['telegram_user_id']} | {nickname} | {user['gender'] or 'Unknown'} | {user['city'] or 'Unknown'} | {status}"
        )
    await update.message.reply_text("\n".join(lines))


async def admin_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /admin_user USER_ID")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("USER_ID must be a number.")
        return
    user = db.get_by_telegram_id(target_id)
    if not user:
        await update.message.reply_text(f"No user found with telegram ID {target_id}.")
        return
    profile = user_profile_dict(user)
    status = "banned" if user["banned"] == 1 else "active" if user["active"] == 1 else "inactive"
    details = (
        f"Telegram ID: {user['telegram_user_id']}\n"
        f"Nickname: {profile.get('nickname') or 'N/A'}\n"
        f"Gender: {profile.get('gender') or 'N/A'}\n"
        f"City: {profile.get('city') or 'N/A'}\n"
        f"Age: {profile.get('age') or 'N/A'}\n"
        f"Mode: {profile.get('mode') or 'N/A'}\n"
        f"Status: {status}\n"
        f"Partner ID: {user['partner_id'] if user['partner_id'] is not None else 'None'}\n"
        f"Created: {user['created_at'] or 'N/A'}\n"
        f"Updated: {user['updated_at'] or 'N/A'}"
    )
    await update.message.reply_text(details)


def build_users_export(users: list[dict], file_format: str) -> bytes:
    normalized = (file_format or "json").strip().lower()
    if normalized in {"excel", "csv"}:
        fieldnames = [
            "telegram_user_id",
            "nickname",
            "date_of_birth",
            "gender",
            "city",
            "profile_photo_file_id",
            "min_age",
            "max_age",
            "preferred_gender",
            "preferred_location",
            "mode",
            "active",
            "partner_id",
            "banned",
            "created_at",
            "updated_at",
            "age_verified_at",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for user in users:
            row = {key: user.get(key, "") for key in fieldnames}
            writer.writerow(row)
        return buffer.getvalue().encode("utf-8")
    payload = json.dumps(users, indent=2, ensure_ascii=False, default=str)
    return payload.encode("utf-8")


async def admin_export_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    file_format = (context.args[0].lower() if context.args else "json")
    if file_format not in {"json", "csv", "excel"}:
        await update.message.reply_text("Usage: /admin_export_users [json|csv|excel]")
        return
    users = db.get_all_users()
    export_bytes = build_users_export([dict(user) for user in users], file_format)
    extension = "json" if file_format == "json" else "csv"
    filename = f"users_export.{extension}"
    await context.bot.send_document(
        chat_id=update.effective_chat.id,
        document=InputFile(io.BytesIO(export_bytes), filename=filename),
        caption=f"Users export as {file_format.upper()}"
    )


async def safety_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(safety_text())


async def delete_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if args and args[0].lower() in {"confirm", "yes"}:
        db.delete_user_profile(update.effective_user.id)
        await update.message.reply_text("Your profile and related data have been deleted.")
        return
    await update.message.reply_text("To delete your profile permanently, run /delete confirm")


async def find_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not rate_limiter.is_allowed(user_id, "find", 10, 60):
        await update.message.reply_text("You have made too many /find requests. Please wait a minute and try again.")
        return
    rate_limiter.record_event(user_id, "find")
    current_user = db.get_by_telegram_id(user_id)
    if not current_user or not profile_is_complete(dict(current_user)):
        await update.message.reply_text("Please complete your profile with /start before using /find.")
        return
    current_profile = user_profile_dict(current_user)
    current_profile["active"] = 1
    db.upsert_user_profile(user_id, current_profile)
    for candidate in db.get_all_users():
        if candidate["telegram_user_id"] == user_id:
            continue
        if candidate["banned"] == 1:
            continue
        if candidate["partner_id"] is not None:
            continue
        if db.has_blocked(user_id, int(candidate["telegram_user_id"])):
            continue
        candidate_profile = user_profile_dict(candidate)
        if users_match(current_profile, candidate_profile):
            db.set_partner(user_id, int(candidate["telegram_user_id"]))
            db.set_partner(int(candidate["telegram_user_id"]), user_id)
            db.set_active(user_id, 1)
            db.set_active(int(candidate["telegram_user_id"]), 1)
            await update.message.reply_text(
                "🎉 You have been matched!\n\nYou are chatting anonymously.\nUse /next, /stop, /block, or /report."
            )
            await context.bot.send_message(
                int(candidate["telegram_user_id"]),
                "🎉 You have been matched!\n\nYou are chatting anonymously.\nUse /next, /stop, /block, or /report."
            )
            return
    await update.message.reply_text("No compatible stranger is available right now. Please try again in a moment.")


async def end_conversation(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    user = db.get_by_telegram_id(user_id)
    if user and user["partner_id"] is not None:
        partner_id = int(user["partner_id"])
        db.set_partner(user_id, None)
        db.set_partner(partner_id, None)
        db.set_active(user_id, 0)
        db.set_active(partner_id, 0)
        try:
            await context.bot.send_message(partner_id, "The conversation ended. You may search for another match with /find.")
        except Exception:
            pass


async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await end_conversation(user_id, context)
    await update.message.reply_text("The conversation has ended. Use /find to look for another stranger.")


async def next_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await end_conversation(user_id, context)
    await update.message.reply_text("You have ended the conversation. Searching for another match...")
    await find_match(update, context)


async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_by_telegram_id(user_id)
    if not user or not user["partner_id"]:
        await update.message.reply_text("There is no active match to block.")
        return
    partner_id = int(user["partner_id"])
    db.add_block(user_id, partner_id)
    await end_conversation(user_id, context)
    await update.message.reply_text("You have blocked this user. This conversation is over and you will not be matched again.")
    try:
        await context.bot.send_message(partner_id, "This user blocked the conversation. You can search again with /find.")
    except Exception:
        pass


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_by_telegram_id(user_id)
    if not user or not user["partner_id"]:
        await update.message.reply_text("There is no active chat to report.")
        return
    if not rate_limiter.is_allowed(user_id, "report", 5, 3600):
        await update.message.reply_text("You have reached the report limit for this hour. Please wait and try again later.")
        return
    reason = " ".join(context.args).strip() if context.args else "inappropriate content"
    rate_limiter.record_event(user_id, "report")
    target_id = int(user["partner_id"])
    db.record_report(user_id, target_id, reason)
    await end_conversation(user_id, context)
    await update.message.reply_text("Your report has been submitted. The current conversation has ended.")
    for admin_id in settings.ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, f"New report: reporter {user_id}, reported {target_id}, reason: {reason}")
        except Exception:
            pass


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    stats = admin_stats()
    await update.message.reply_text(
        f"Total users: {stats['total_users']}\n"
        f"Active users: {stats['active_users']}\n"
        f"Currently matched users: {stats['currently_matched']}\n"
        f"Banned users: {stats['banned_users']}\n"
        f"Total reports: {stats['total_reports']}\n"
        f"Pending reports: {stats['pending_reports']}"
    )


async def admin_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    reports = list_recent_reports(20)
    if not reports:
        await update.message.reply_text("No reports found.")
        return
    lines = []
    for report in reports:
        lines.append(
            f"ID: {report['id']} | Reporter: {report['reporter_id']} | Reported: {report['reported_id']} | "
            f"Reason: {report['reason']} | Date: {report['created_at']} | Status: {report['status']}"
        )
    await update.message.reply_text("\n".join(lines))


async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban USER_ID [reason]")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("USER_ID must be a number.")
        return
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    db.set_ban(target_id, 1)
    db.record_moderation_action(update.effective_user.id, target_id, "ban", reason)
    user = db.get_by_telegram_id(target_id)
    if user and user["partner_id"] is not None:
        await end_conversation(target_id, context)
    try:
        await context.bot.send_message(target_id, "You have been banned from StrangerMatch.")
    except Exception:
        pass
    await update.message.reply_text(f"User {target_id} has been banned.")


async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in settings.ADMIN_IDS:
        await update.message.reply_text("You do not have admin access.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban USER_ID")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("USER_ID must be a number.")
        return
    db.set_ban(target_id, 0)
    db.record_moderation_action(update.effective_user.id, target_id, "unban", "Ban removed")
    await update.message.reply_text(f"User {target_id} has been unbanned.")


async def relay_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db.get_by_telegram_id(user_id)
    if not user or not user["partner_id"]:
        return
    if update.message.text and update.message.text.startswith("/"):
        return
    partner_id = int(user["partner_id"])
    text = update.message.text
    if text and contains_suspicious_content(text):
        await update.message.reply_text(safety_warning())
    if update.message.text:
        try:
            await context.bot.send_message(chat_id=partner_id, text=text)
        except Exception:
            pass
        return
    if update.message.photo:
        try:
            await context.bot.send_photo(chat_id=partner_id, photo=update.message.photo[-1].file_id, caption=update.message.caption or "")
        except Exception:
            await update.message.reply_text("This photo type cannot be relayed safely in this version.")
        return
    if update.message.sticker:
        try:
            await context.bot.send_sticker(chat_id=partner_id, sticker=update.message.sticker.file_id)
        except Exception:
            await update.message.reply_text("This sticker cannot be relayed safely in this version.")
        return
    if update.message.voice:
        try:
            await context.bot.send_voice(chat_id=partner_id, voice=update.message.voice.file_id)
        except Exception:
            await update.message.reply_text("This voice message cannot be relayed safely in this version.")
        return
    if update.message.video:
        try:
            await context.bot.send_video(chat_id=partner_id, video=update.message.video.file_id, caption=update.message.caption or "")
        except Exception:
            await update.message.reply_text("This video cannot be relayed safely in this version.")
        return
    await update.message.reply_text("This message type cannot be safely relayed. Please send text or a supported media type.")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Bot error for update %s: %s", update, context.error)


def build_application() -> Application:
    return Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()


def create_handlers(application):
    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            PROFILE_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_nickname)],
            PROFILE_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dob)],
            PROFILE_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gender)],
            PROFILE_CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_city)],
            PROFILE_PHOTO: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_photo),
                CommandHandler("skip", skip_photo),
            ],
            PROFILE_MIN_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_min_age)],
            PROFILE_MAX_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_max_age)],
            PROFILE_PREFERRED_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_preferred_gender)],
            PROFILE_PREFERRED_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_preferred_location)],
            PROFILE_MODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mode)],
        },
        fallbacks=[CommandHandler("cancel", cancel_profile)],
    )
    application.add_handler(conversation)
    application.add_handler(CommandHandler("find", find_match))
    application.add_handler(CommandHandler("next", next_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("safety", safety_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("delete", delete_profile))
    application.add_handler(CommandHandler("admin_help", admin_help_command))
    application.add_handler(CommandHandler("admin_stats", admin_stats_command))
    application.add_handler(CommandHandler("admin_report", admin_report_command))
    application.add_handler(CommandHandler("admin_users", admin_users_command))
    application.add_handler(CommandHandler("admin_user", admin_user_command))
    application.add_handler(CommandHandler("admin_export_users", admin_export_users_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, relay_message))
    application.add_error_handler(on_error)


def main():
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured. Add it to your .env file before running the bot.")
    app = build_application()
    create_handlers(app)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
