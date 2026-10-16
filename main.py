import os
import re
import time
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.filters import Command
from aiogram.types import ChatPermissions, Message

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
CHAT_TITLE = "чатик gingerxyyyyyt"

FLOOD_LIMIT = 6
FLOOD_WINDOW = 8
SPAM_REPEAT_LIMIT = 4
SPAM_WINDOW = 30
WARNINGS_BEFORE_MUTE = 3
MUTE_MINUTES = 10
BAN_AFTER_WARNINGS = 6

BANNED_PATTERNS = [
    r"(?:^|\s)@everyone(?:\s|$)",
    r"(?:^|\s)@here(?:\s|$)",
]

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)

router = Router()
message_times = defaultdict(deque)
recent_messages = defaultdict(deque)
warnings = defaultdict(int)


def get_name(user):
    return user.first_name or user.username or str(user.id)


async def send_log(bot: Bot, text: str):
    if not OWNER_ID:
        return
    try:
        await bot.send_message(OWNER_ID, text)
    except Exception:
        pass


async def notify_user(bot: Bot, user, action: str):
    text = f"{user.first_name}, Вы получили «{action}» в чате «{CHAT_TITLE}»."
    try:
        await bot.send_message(user.id, text)
    except Exception:
        pass


async def is_admin(message: Message):
    if not message.from_user:
        return False
    member = await message.chat.get_member(message.from_user.id)
    return member.status in {
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.CREATOR,
    }


async def target_from_reply(message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None


async def punish_warning(message: Message, reason: str):
    user = message.from_user
    if not user:
        return

    warnings[user.id] += 1
    count = warnings[user.id]

    try:
        await message.delete()
    except Exception:
        pass

    if count >= BAN_AFTER_WARNINGS:
        warnings[user.id] = 0
        await ban_user(message, reason=f"{reason}; {BAN_AFTER_WARNINGS} предупреждений")
        return

    await notify_user(message.bot, user, "нарушение")
    await send_log(
        message.bot,
        "🚨 НАРУШЕНИЕ\n\n"
        f"👤 Участник: {get_name(user)}\n"
        f"🆔 ID: {user.id}\n"
        f"⚠️ Нарушений: {count}/{BAN_AFTER_WARNINGS}\n"
        f"📋 Причина: {reason}\n"
        f"💬 Чат: {CHAT_TITLE}",
    )

    if count == WARNINGS_BEFORE_MUTE:
        await mute_user(message, MUTE_MINUTES, "3 нарушения")


async def mute_user(message: Message, minutes: int, reason: str):
    user = message.from_user
    if not user:
        return

    until_date = int(time.time() + minutes * 60)
    permissions = ChatPermissions(can_send_messages=False)

    try:
        await message.chat.restrict(user.id, permissions=permissions, until_date=until_date)
    except Exception as exc:
        await send_log(message.bot, f"❌ Не удалось выдать мут пользователю {user.id}: {exc}")
        return

    await notify_user(message.bot, user, "мут")
    await send_log(
        message.bot,
        "🔇 МУТ\n\n"
        f"👤 Участник: {get_name(user)}\n"
        f"🆔 ID: {user.id}\n"
        f"⏱ Срок: {minutes} минут\n"
        f"📋 Причина: {reason}\n"
        f"💬 Чат: {CHAT_TITLE}",
    )


async def ban_user(message: Message, reason: str):
    user = message.from_user
    if not user:
        return

    try:
        await message.chat.ban(user.id)
    except Exception as exc:
        await send_log(message.bot, f"❌ Не удалось выдать бан пользователю {user.id}: {exc}")
        return

    await notify_user(message.bot, user, "бан")
    await send_log(
        message.bot,
        "🔨 БАН\n\n"
        f"👤 Участник: {get_name(user)}\n"
        f"🆔 ID: {user.id}\n"
        f"📋 Причина: {reason}\n"
        f"💬 Чат: {CHAT_TITLE}",
    )


@router.message(F.new_chat_members)
async def welcome(message: Message):
    for user in message.new_chat_members:
        await message.answer(
            f"👋 Добро пожаловать, {user.first_name}!\n\n"
            f"🔥 Ты попал в «{CHAT_TITLE}»!"
        )


@router.message(Command("warn"))
async def manual_warn(message: Message):
    if not await is_admin(message):
        return
    user = await target_from_reply(message)
    if not user:
        await message.answer("⚠️ Используй /warn ответом на сообщение участника.")
        return
    warnings[user.id] += 1
    await message.answer(f"⚠️ {get_name(user)} получил предупреждение: {warnings[user.id]}/{BAN_AFTER_WARNINGS}")
    await send_log(message.bot, f"⚠️ РУЧНОЕ ПРЕДУПРЕЖДЕНИЕ\n👤 {get_name(user)}\n🆔 {user.id}\n💬 {CHAT_TITLE}")


@router.message(Command("mute"))
async def manual_mute(message: Message):
    if not await is_admin(message):
        return
    user = await target_from_reply(message)
    if not user:
        await message.answer("🔇 Используй /mute ответом на сообщение участника.")
        return
    parts = message.text.split()
    minutes = 10
    if len(parts) > 1 and parts[1].isdigit():
        minutes = max(1, min(int(parts[1]), 1440))
    try:
        await message.chat.restrict(user.id, permissions=ChatPermissions(can_send_messages=False), until_date=int(time.time() + minutes * 60))
        await message.answer(f"🔇 {get_name(user)} получил мут на {minutes} мин.")
        await notify_user(message.bot, user, "мут")
        await send_log(message.bot, f"🔇 РУЧНОЙ МУТ\n👤 {get_name(user)}\n🆔 {user.id}\n⏱ {minutes} минут\n💬 {CHAT_TITLE}")
    except Exception as exc:
        await message.answer("❌ Не удалось выдать мут.")
        await send_log(message.bot, f"❌ Ошибка ручного мута: {exc}")


@router.message(Command("unmute"))
async def manual_unmute(message: Message):
    if not await is_admin(message):
        return
    user = await target_from_reply(message)
    if not user:
        await message.answer("🔊 Используй /unmute ответом на сообщение участника.")
        return
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=False,
    )
    try:
        await message.chat.restrict(user.id, permissions=permissions)
        await message.answer(f"🔊 Мут с {get_name(user)} снят.")
        await notify_user(message.bot, user, "снятие мута")
    except Exception as exc:
        await message.answer("❌ Не удалось снять мут.")
        await send_log(message.bot, f"❌ Ошибка снятия мута: {exc}")


@router.message(Command("ban"))
async def manual_ban(message: Message):
    if not await is_admin(message):
        return
    user = await target_from_reply(message)
    if not user:
        await message.answer("🔨 Используй /ban ответом на сообщение участника.")
        return
    try:
        await message.chat.ban(user.id)
        await message.answer(f"🔨 {get_name(user)} забанен.")
        await notify_user(message.bot, user, "бан")
        await send_log(message.bot, f"🔨 РУЧНОЙ БАН\n👤 {get_name(user)}\n🆔 {user.id}\n💬 {CHAT_TITLE}")
    except Exception as exc:
        await message.answer("❌ Не удалось выдать бан.")
        await send_log(message.bot, f"❌ Ошибка ручного бана: {exc}")


@router.message(Command("unban"))
async def manual_unban(message: Message):
    if not await is_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("🔓 Используй /unban USER_ID.")
        return
    user_id = int(parts[1])
    try:
        await message.chat.unban(user_id)
        await message.answer(f"🔓 Пользователь {user_id} разбанен.")
        await send_log(message.bot, f"🔓 РАЗБАН\n🆔 {user_id}\n💬 {CHAT_TITLE}")
    except Exception as exc:
        await message.answer("❌ Не удалось снять бан.")
        await send_log(message.bot, f"❌ Ошибка разбана {user_id}: {exc}")


@router.message(Command("warns"))
async def warns_command(message: Message):
    if not await is_admin(message):
        return
    user = await target_from_reply(message)
    user_id = user.id if user else message.from_user.id
    await message.answer(f"⚠️ Нарушений: {warnings[user_id]}/{BAN_AFTER_WARNINGS}")


@router.message(F.text)
async def moderation(message: Message):
    user = message.from_user
    if not user or user.is_bot or await is_admin(message):
        return

    user_id = user.id
    now = time.monotonic()
    text = message.text.strip().lower()

    for pattern in BANNED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            await punish_warning(message, "запрещённая конструкция")
            return

    # Link spam: several URLs in one message are treated as spam.
    if len(URL_RE.findall(text)) >= 3:
        await punish_warning(message, "антиспам: слишком много ссылок")
        return

    # Excessive caps: only trigger on longer messages with very high uppercase ratio.
    letters = [char for char in message.text if char.isalpha()]
    if len(letters) >= 12:
        upper_ratio = sum(char.isupper() for char in letters) / len(letters)
        if upper_ratio >= 0.85:
            await punish_warning(message, "антиспам: чрезмерный CAPS LOCK")
            return

    # Anti-flood.
    times = message_times[user_id]
    times.append(now)
    while times and now - times[0] > FLOOD_WINDOW:
        times.popleft()

    if len(times) > FLOOD_LIMIT:
        await punish_warning(message, "антифлуд: слишком много сообщений")
        return

    # Anti-spam: repeated identical messages.
    texts = recent_messages[user_id]
    texts.append((now, text))
    while texts and now - texts[0][0] > SPAM_WINDOW:
        texts.popleft()

    same_messages = sum(1 for _, old_text in texts if old_text == text)
    if same_messages >= SPAM_REPEAT_LIMIT:
        await punish_warning(message, "антиспам: одинаковые сообщения")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задан BOT_TOKEN")
    if not OWNER_ID:
        raise RuntimeError("Не задан OWNER_ID")

    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    print("🤖 GingerXYT Mod Bot запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
