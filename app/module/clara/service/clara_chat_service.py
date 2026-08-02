import asyncio
import json
import logging
import uuid
from datetime import date
from typing import Any, Optional

from fastapi import Depends
from openai import OpenAI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.clients.openai_client import get_openai_client
from app.common.dto.pagination import PageQueryDto
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
                "Get the user's income/expense summary for one month: total spent, "
                "month-over-month change, category breakdown, monthly income, and a "
                "6-month income-vs-expense trend suitable for charting. Use this for "
                "any question about spending, income, or budget usage in a given period."
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
    }
]


def _system_prompt(username: str, symbol: str) -> str:
    today = date.today().isoformat()
    return (
        f"You are Clara, {username}'s friendly AI financial companion inside the Finclair app. "
        "You don't just report numbers, you interpret them: explain what happened, why it "
        "matters, and what to do next. Keep replies short (2-4 sentences), warm, and direct — "
        f"address {username} by name occasionally, not in every message. "
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
        "Call get_expense_summary whenever the user asks about spending, income, or a time period, "
        "even implicitly (e.g. 'how did I do?' refers to the period already discussed). "
        "You only discuss the user's personal finances: spending, income, budgets, saving habits, "
        "and financial advice grounded in their data. If asked about anything else (general trivia, "
        "coding, news, other people, unrelated requests), politely decline in one short sentence and "
        "steer the conversation back to their finances — do not answer the off-topic question."
    )


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
                reply = choice.content or "I'm not sure how to respond to that — could you rephrase?"
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
            reply = "I'm having trouble putting that together right now — please try again in a moment."

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
        if name != "get_expense_summary":
            return json.dumps({"error": f"Unknown tool '{name}'."}), None

        try:
            args = json.loads(raw_arguments) if raw_arguments else {}
        except json.JSONDecodeError:
            args = {}

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
