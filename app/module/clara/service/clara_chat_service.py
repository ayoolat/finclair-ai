import asyncio
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Optional

from fastapi import Depends
from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clients.google_docs_client import get_app_help_content
from app.common.clients.openai_client import get_openai_client
from app.common.dto.pagination import PageQueryDto
from app.common.timezone import APP_TZ
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.clara.dto.clara import ClaraChatResponseDto, ClaraMessageDto
from app.module.clara.schema.clara_message import ClaraMessage
from app.module.expense.dto.expense import ExpenseSummaryDto
from app.module.expense.service.expense_service import ExpenseService, get_expense_service
from app.module.user.schema.user import User

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"
_HISTORY_LIMIT = 20  # messages (≈10 turns) kept in the prompt, to bound token usage
_MAX_TOOL_ITERATIONS = 3

_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_expense_summary",
            "description": (
                "Get the user's income/expense summary for ONE WHOLE CALENDAR MONTH: total "
                "spent, month-over-month change, category breakdown, monthly income, and a "
                "6-month income-vs-expense trend suitable for charting. Use this ONLY when the "
                "user asks about a full calendar month ('this month', 'August', 'last month') "
                "or their overall/monthly picture. For a week, a few days, 'today', "
                "'yesterday', 'last 7 days', a year, or any custom date range, use "
                "get_spending_for_period instead, never this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 12,
                        "description": "1-12. Omit for the current month.",
                    },
                    "year": {
                        "type": "integer",
                        "description": "e.g. 2026. Omit for the current year.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_spending_for_period",
            "description": (
                "Get the user's spending over a specific window that is NOT a whole calendar "
                "month: a week, a few days, today, yesterday, the last N days, a year, or a "
                "custom date range. Returns total spent, transaction count, category breakdown, "
                "and the change vs. the immediately preceding window of the same length. Use "
                "this for 'this week', 'last week', 'today', 'yesterday', 'the last 7 days', "
                "'so far this year', 'between the 1st and the 15th', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": [
                            "today",
                            "yesterday",
                            "this_week",
                            "last_week",
                            "last_7_days",
                            "last_30_days",
                            "this_year",
                            "last_year",
                            "custom",
                        ],
                        "description": (
                            "The window to summarize. Weeks run Monday to Sunday. Use 'custom' "
                            "only when the user gives explicit start and end dates."
                        ),
                    },
                    "start_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Required only when period is 'custom'.",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Required only when period is 'custom'.",
                    },
                },
                "required": ["period"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_app_help",
            "description": (
                "Get help content explaining the Finclair app itself: its screens, buttons, "
                "features, and terminology (e.g. 'Clara FAB', 'sheet', 'tab bar'), and how to "
                "do things like logging an expense, creating a budget, or joining a savings "
                "group. Use this for ANY question about the app as a product — how to do "
                "something, what a screen/button/feature is or is called, what happens when "
                "you tap/do something, where to find something, or why something looks a "
                "certain way. Covers 'how do I...', 'what is...', 'what does...', 'what "
                "happens if/when I...', and 'where is...' style questions about the app."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _system_prompt(username: str, symbol: str) -> str:
    today = date.today().isoformat()
    return (
        f"You are Clara, {username}'s friendly AI financial companion inside the Finclair app. "
        "You don't just report numbers, you interpret them: explain what happened, why it "
        "matters, and what to do next. Keep replies short (2-4 sentences), warm, and direct. "
        f"Address {username} by name occasionally, not in every message. Never use em dashes "
        "in your replies, use a period or comma instead. "
        f"Today's date is {today}. The user's currency symbol is '{symbol}' — always format "
        "amounts with it. "
        "Only state numbers returned by a tool call; never estimate or invent financial figures. "
        "Be transparent about what you're working with: you can only analyze information already "
        "saved in the user's Finclair account (expenses, income, budgets) — text typed into this "
        "chat is not automatically saved as financial data. If the user states a figure in the "
        "conversation instead of it coming from a tool call, don't treat it as part of their saved "
        "history or use it to answer questions about their broader spending — you can acknowledge "
        "what they said, but say plainly that it won't show up in their insights unless they log it "
        "as an actual expense or income in the app. If get_expense_summary comes back with nothing "
        "for a period, say so plainly (e.g. 'I don't have anything saved for that month yet') rather "
        "than leaving it ambiguous whether you checked. "
        "You have two spending tools. Use get_expense_summary ONLY for a whole calendar month "
        "('this month', 'last month', 'August', overall monthly picture). Use "
        "get_spending_for_period for anything else: a week, 'today', 'yesterday', 'last 7 days', "
        "a year to date, or a custom date range. Pick the tool that matches the period the user "
        "asked for, never substitute a different period because a tool is more convenient. Call "
        "a tool whenever the user asks about spending, income, or a time period, even implicitly "
        "(e.g. 'how did I do?' refers to the period already discussed). "
        "Always report results for the exact period the tool covered, and name that period or "
        "its date range in your reply (e.g. 'This week so far (Sep 1 to Sep 4)...'). Never call "
        "a month's figures a week's, or a week's a month's. If you could not get data for the "
        "period the user actually asked about, say so plainly instead of answering with a "
        "different period's numbers. "
        "Call get_app_help for ANY question about the app itself, not just explicit 'how do I' "
        "requests — this includes 'what is [screen/button/feature]', 'what does X do', 'what "
        "happens if/when I tap/do X', and 'where do I find X'. If a question could plausibly be "
        "answered by app-help content, call the tool before answering rather than guessing or "
        "saying you don't know — only fall back to 'I don't have that help content yet' after "
        "checking the tool and finding it genuinely doesn't cover it. Answer strictly from what "
        "the tool returns. "
        "Outside of their personal finances (spending, income, budgets, saving habits, financial "
        "advice grounded in their data) and app navigation/how-to questions, if asked about anything "
        "else (general trivia, coding, news, other people, unrelated requests), politely decline in "
        "one short sentence and steer the conversation back to their finances or the app — do not "
        "answer the off-topic question."
    )


def _fmt(d: date) -> str:
    # "Sep 1" / "Sep 1, 2026" is added by the caller where the year matters.
    return f"{d.strftime('%b')} {d.day}"


def _resolve_period(
    period: str, start_raw: Optional[str], end_raw: Optional[str]
) -> Optional[tuple[date, date, str]]:
    """Map a period name (and optional explicit dates) to an inclusive
    (start, end, human label) triple, anchored to today in the app's timezone.
    Returns None if a custom range is requested without valid dates."""
    today = datetime.now(APP_TZ).date()

    if period == "custom":
        if not start_raw or not end_raw:
            return None
        try:
            start = date.fromisoformat(start_raw)
            end = date.fromisoformat(end_raw)
        except ValueError:
            return None
        if end < start:
            start, end = end, start
        label = f"{_fmt(start)} to {_fmt(end)}, {end.year}"
        return start, end, label

    if period == "today":
        return today, today, "today"
    if period == "yesterday":
        y = today - timedelta(days=1)
        return y, y, "yesterday"
    if period == "this_week":
        start = today - timedelta(days=today.weekday())
        label = "this week" if today.weekday() == 6 else "this week so far"
        return start, today, label
    if period == "last_week":
        this_monday = today - timedelta(days=today.weekday())
        start = this_monday - timedelta(days=7)
        return start, start + timedelta(days=6), "last week"
    if period == "last_7_days":
        return today - timedelta(days=6), today, "the last 7 days"
    if period == "last_30_days":
        return today - timedelta(days=29), today, "the last 30 days"
    if period == "this_year":
        return date(today.year, 1, 1), today, "so far this year"
    if period == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), f"{today.year - 1}"

    return None


def _to_message_dto(m: ClaraMessage) -> ClaraMessageDto:
    return ClaraMessageDto(
        role=m.role,  # type: ignore[arg-type]
        content=m.content,
        data=m.extra_data,
        created_at=m.created_at,
    )


class ClaraChatService:
    def __init__(self, db: AsyncSession, expense_service: ExpenseService) -> None:
        self._db = db
        self._expenses = expense_service
        self._client: OpenAI = get_openai_client()

    async def get_history(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[ClaraMessageDto]]:
        base = select(ClaraMessage).where(ClaraMessage.user_id == user_id)
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        rows = await self._db.execute(
            base.order_by(ClaraMessage.created_at.asc())
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        dtos = [_to_message_dto(m) for m in rows.scalars().all()]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def _recent_messages(self, user_id: uuid.UUID, limit: int) -> list[ClaraMessageDto]:
        rows = await self._db.execute(
            select(ClaraMessage)
            .where(ClaraMessage.user_id == user_id)
            .order_by(ClaraMessage.created_at.desc())
            .limit(limit)
        )
        messages = list(rows.scalars().all())
        messages.reverse()
        return [_to_message_dto(m) for m in messages]

    async def chat(self, user_id: uuid.UUID, message: str) -> Result[ClaraChatResponseDto]:
        user_row = await self._db.execute(select(User).where(User.id == user_id))
        user = user_row.scalar_one_or_none()
        if user is None:
            return Result.fail("User not found.", error_code="NOT_FOUND", status_code=404)

        symbol = "₦" if user.default_currency == "NGN" else user.default_currency
        history = await self._recent_messages(user_id, limit=_HISTORY_LIMIT)

        messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt(user.display_name, symbol)}]
        messages.extend({"role": h.role, "content": h.content} for h in history)
        messages.append({"role": "user", "content": message})

        reply: Optional[str] = None
        widget_data: Optional[ExpenseSummaryDto] = None

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = await asyncio.to_thread(self._call_openai, messages)
            choice = response.choices[0].message

            if not choice.tool_calls:
                reply = choice.content or "I'm not sure how to respond to that. Could you rephrase?"
                break

            messages.append(
                {
                    "role": "assistant",
                    "content": choice.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in choice.tool_calls
                    ],
                }
            )

            for tool_call in choice.tool_calls:
                tool_result, dto = await self._run_tool(user_id, tool_call.function.name, tool_call.function.arguments)
                if dto is not None:
                    widget_data = dto
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )
        else:
            reply = "I'm having trouble putting that together right now. Please try again in a moment."

        assert reply is not None

        self._db.add(ClaraMessage(user_id=user_id, role="user", content=message))
        self._db.add(
            ClaraMessage(
                user_id=user_id,
                role="assistant",
                content=reply,
                extra_data=widget_data.model_dump(mode="json") if widget_data else None,
            )
        )
        await self._db.commit()

        return Result.ok(ClaraChatResponseDto(reply=reply, data=widget_data))

    def _call_openai(self, messages: list[dict[str, Any]]) -> Any:
        return self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=_TOOLS,
            max_tokens=400,
        )

    async def _run_tool(
        self, user_id: uuid.UUID, name: str, raw_arguments: str
    ) -> tuple[str, Optional[ExpenseSummaryDto]]:
        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            args = {}

        if name == "get_app_help":
            content = await asyncio.to_thread(get_app_help_content)
            if not content:
                return json.dumps({"error": "No app-help content is available yet."}), None
            return json.dumps({"app_help": content}), None

        if name == "get_spending_for_period":
            resolved = _resolve_period(
                args.get("period", ""), args.get("start_date"), args.get("end_date")
            )
            if resolved is None:
                return json.dumps({
                    "error": "Could not resolve that period. Ask the user for exact start and end dates."
                }), None
            start, end, label = resolved
            result = await self._expenses.get_period_spending(user_id, start, end, label)
            if result.is_err or result.data is None:
                logger.error("Clara tool get_spending_for_period failed for %s: %s", user_id, result.error)
                return json.dumps({"error": result.error or "Failed to fetch spending."}), None
            return result.data.model_dump_json(), None

        if name != "get_expense_summary":
            return json.dumps({"error": f"Unknown tool '{name}'."}), None

        result = await self._expenses.get_summary(
            user_id, year=args.get("year"), month=args.get("month")
        )
        if result.is_err or result.data is None:
            logger.error("Clara tool get_expense_summary failed for %s: %s", user_id, result.error)
            return json.dumps({"error": result.error or "Failed to fetch summary."}), None

        return result.data.model_dump_json(), result.data


def get_clara_chat_service(
    db: AsyncSession = Depends(get_db),
    expense_service: ExpenseService = Depends(get_expense_service),
) -> ClaraChatService:
    return ClaraChatService(db, expense_service)
