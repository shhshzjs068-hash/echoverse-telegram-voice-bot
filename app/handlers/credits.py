from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.keyboards.credits import credits_menu_kb
from app.keyboards.main_menu import back_main_kb
from app.services import credits as credits_service
from app.utils.helpers import format_credits

router = Router(name="credits")

_TXN_LABELS = {
    "welcome_bonus": "🎁 Welcome bonus",
    "referral_reward": "🎉 Referral reward",
    "generation_charge": "🎙 Generation",
    "refund": "↩️ Refund",
    "admin_adjustment": "🛠 Admin adjustment",
}


@router.callback_query(F.data == "menu:credits")
async def cb_credits_entry(callback: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await state.clear()
    text = _credits_text(db_user)
    await callback.message.edit_text(text, reply_markup=credits_menu_kb())
    await callback.answer()


@router.message(Command("balance"))
async def cmd_balance(message: Message, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(_credits_text(db_user), reply_markup=credits_menu_kb())


def _credits_text(db_user: User) -> str:
    return (
        "💰 <b>My Tokens</b>\n\n"
        f"💰 Available Tokens: <b>{format_credits(db_user.credits_balance)}</b>\n\n"
        f"Total received: {format_credits(db_user.total_credits_received)}\n"
        f"Total used: {format_credits(db_user.total_credits_used)}\n"
        f"Earned from referrals: {format_credits(db_user.referral_credits_earned)}"
    )


@router.callback_query(F.data == "credits:history")
async def cb_credits_history(callback: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    txns = await credits_service.get_transaction_history(session, db_user.telegram_user_id, limit=15)
    if not txns:
        await callback.message.edit_text("📜 <b>Token History</b>\n\nNo transactions yet.", reply_markup=back_main_kb())
        await callback.answer()
        return

    lines = ["📜 <b>Token History</b>\n"]
    for t in txns:
        label = _TXN_LABELS.get(t.transaction_type, t.transaction_type)
        sign = "+" if t.amount > 0 else ""
        lines.append(f"{label}: {sign}{t.amount} (balance {t.balance_after}) — {t.created_at.strftime('%Y-%m-%d %H:%M')}")
    await callback.message.edit_text("\n".join(lines), reply_markup=back_main_kb())
    await callback.answer()
