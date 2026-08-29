from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.database import get_session
from app.database.models import (
    CreditTransaction,
    GenerationHistory,
    Referral,
    ReferralStatus,
    User,
)
from app.keyboards.admin import admin_back_kb, admin_menu_kb, broadcast_confirm_kb
from app.keyboards.main_menu import back_main_kb
from app.services import credits as credits_service
from app.states.states import AdminBroadcastStates, AdminCreditStates
from app.utils.helpers import escape_html

logger = logging.getLogger(__name__)
router = Router(name="admin")


class IsAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        user = event.from_user
        return bool(user) and user.id in settings.admin_ids


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def show_admin_menu(target) -> None:
    text = "🛠 <b>Admin Panel</b>"
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=admin_menu_kb())
        await target.answer()
    else:
        await target.answer(text, reply_markup=admin_menu_kb())


@router.callback_query(F.data == "menu:admin")
async def cb_admin_entry(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await show_admin_menu(callback)


@router.callback_query(F.data == "adm:stats")
async def cb_admin_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    total_users = (await session.execute(select(func.count(User.telegram_user_id)))).scalar_one()
    total_generations = (await session.execute(select(func.count(GenerationHistory.id)))).scalar_one()
    total_credits_issued = (await session.execute(select(func.sum(User.total_credits_received)))).scalar() or 0
    total_credits_used = (await session.execute(select(func.sum(User.total_credits_used)))).scalar() or 0
    blocked = (await session.execute(select(func.count(User.telegram_user_id)).where(User.is_blocked == True))).scalar_one()  # noqa: E712

    text = (
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Total users: {total_users}\n"
        f"📵 Blocked users: {blocked}\n"
        f"🎙 Total generations: {total_generations}\n"
        f"💰 Tokens issued: {total_credits_issued}\n"
        f"💸 Tokens used: {total_credits_used}"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:usage")
async def cb_admin_usage(callback: CallbackQuery, session: AsyncSession) -> None:
    stmt = (
        select(GenerationHistory.voice_name, func.count(GenerationHistory.id))
        .group_by(GenerationHistory.voice_name)
        .order_by(func.count(GenerationHistory.id).desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        text = "📈 <b>Usage Statistics</b>\n\nNo generations yet."
    else:
        lines = ["📈 <b>Usage Statistics</b>\n", "Top voices:"]
        for name, count in rows:
            lines.append(f"• {escape_html(name)}: {count}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:referral_stats")
async def cb_admin_referral_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    total = (await session.execute(select(func.count(Referral.id)))).scalar_one()
    rewarded = (
        await session.execute(select(func.count(Referral.id)).where(Referral.status == ReferralStatus.REWARDED.value))
    ).scalar_one()
    total_reward_credits = (
        await session.execute(select(func.sum(Referral.reward_credits)).where(Referral.status == ReferralStatus.REWARDED.value))
    ).scalar() or 0
    text = (
        "🎁 <b>Referral Statistics</b>\n\n"
        f"Total referrals: {total}\n"
        f"Rewarded referrals: {rewarded}\n"
        f"Tokens paid out: {total_reward_credits}"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()


@router.callback_query(F.data == "adm:users")
async def cb_admin_users(callback: CallbackQuery, session: AsyncSession) -> None:
    stmt = select(User).order_by(User.created_at.desc()).limit(10)
    users = (await session.execute(stmt)).scalars().all()
    lines = ["👥 <b>Recent Users</b>\n"]
    for u in users:
        uname = f"@{u.username}" if u.username else str(u.telegram_user_id)
        lines.append(f"• {uname} — {u.credits_balance} credits")
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_back_kb())
    await callback.answer()


# ------------------------------------------------------------- credit mgmt

@router.callback_query(F.data == "adm:credit_mgmt")
async def cb_admin_credit_mgmt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminCreditStates.waiting_for_user_id)
    await callback.message.edit_text(
        "💰 <b>Token Management</b>\n\nSend the Telegram user ID to adjust.",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminCreditStates.waiting_for_user_id, IsAdmin())
async def on_admin_credit_user_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        target_id = int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Please send a numeric Telegram user ID.")
        return
    target = await session.get(User, target_id)
    if target is None:
        await message.answer("⚠️ No user found with that ID.")
        return
    await state.update_data(target_user_id=target_id)
    await state.set_state(AdminCreditStates.waiting_for_amount)
    await message.answer(
        f"Current balance for {target_id}: {target.credits_balance} credits.\n\n"
        "Send a signed amount to adjust (e.g. 50 or -20)."
    )


@router.message(AdminCreditStates.waiting_for_amount, IsAdmin())
async def on_admin_credit_amount(message: Message, state: FSMContext, session: AsyncSession) -> None:
    try:
        delta = int((message.text or "").strip())
    except ValueError:
        await message.answer("⚠️ Please send a whole number, e.g. 50 or -20.")
        return
    data = await state.get_data()
    target_id = data.get("target_user_id")
    try:
        new_balance = await credits_service.admin_adjust_credits(
            session, telegram_user_id=target_id, delta=delta, admin_id=message.from_user.id
        )
    except (ValueError, credits_service.InsufficientCreditsError) as exc:
        await message.answer(f"⚠️ Could not adjust balance: {exc}")
        await state.clear()
        return
    await state.clear()
    await message.answer(f"✅ New balance for {target_id}: {new_balance} tokens.", reply_markup=back_main_kb())


# ---------------------------------------------------------------- broadcast

@router.callback_query(F.data == "adm:broadcast")
async def cb_admin_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcastStates.waiting_for_content)
    await callback.message.edit_text(
        "📢 <b>Broadcast</b>\n\nSend the text, photo (with caption), or video (with caption) to broadcast.",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminBroadcastStates.waiting_for_content, IsAdmin())
async def on_admin_broadcast_content(message: Message, state: FSMContext) -> None:
    if message.photo:
        await state.update_data(kind="photo", file_id=message.photo[-1].file_id, caption=message.caption or "")
    elif message.video:
        await state.update_data(kind="video", file_id=message.video.file_id, caption=message.caption or "")
    elif message.text:
        await state.update_data(kind="text", text=message.text)
    else:
        await message.answer("⚠️ Please send text, a photo with caption, or a video with caption.")
        return

    await state.set_state(AdminBroadcastStates.waiting_for_confirmation)
    await message.answer("Ready to send this to all users?", reply_markup=broadcast_confirm_kb())


@router.callback_query(AdminBroadcastStates.waiting_for_confirmation, F.data == "adm:broadcast_send")
async def cb_admin_broadcast_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.message.edit_text("📢 Broadcasting... this may take a while.")
    await callback.answer()

    stmt = select(User.telegram_user_id).where(User.is_blocked == False, User.is_banned == False)  # noqa: E712
    user_ids = [row[0] for row in (await session.execute(stmt)).all()]

    sent = failed = blocked = 0
    bot = callback.bot
    delay = 1.0 / max(settings.broadcast_rate_per_second, 1)

    for uid in user_ids:
        try:
            if data.get("kind") == "photo":
                await bot.send_photo(uid, data["file_id"], caption=data.get("caption") or None)
            elif data.get("kind") == "video":
                await bot.send_video(uid, data["file_id"], caption=data.get("caption") or None)
            else:
                await bot.send_message(uid, data.get("text", ""))
            sent += 1
        except Exception as exc:
            error_text = str(exc).lower()
            if "blocked" in error_text or "deactivated" in error_text or "not found" in error_text:
                blocked += 1
                async with get_session() as s2:
                    u = await s2.get(User, uid)
                    if u:
                        u.is_blocked = True
                        await s2.commit()
            else:
                failed += 1
                logger.warning("Broadcast failed for %s: %s", uid, exc)
        await asyncio.sleep(delay)

    summary = (
        "📢 <b>Broadcast Complete</b>\n\n"
        f"✅ Sent: {sent}\n"
        f"⚠️ Failed: {failed}\n"
        f"📵 Blocked: {blocked}\n"
        f"🎯 Total: {len(user_ids)}"
    )
    await callback.message.answer(summary, reply_markup=admin_back_kb())
