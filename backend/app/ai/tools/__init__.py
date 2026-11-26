"""The assistant's 8 typed tools (spec 13.2). `TOOLS` is the only list the model is offered."""

from app.ai.tools.base import Action, Tool, ToolArgumentError, ToolContext
from app.ai.tools.deadlines import GET_INSTALLMENT_SCHEDULE, GET_UPCOMING_DEADLINES
from app.ai.tools.products import FIND_DOCUMENTS, GET_PRODUCT_DETAILS, SEARCH_PRODUCTS
from app.ai.tools.spending import AGGREGATE_SPENDING, COMPARE_PERIODS, QUERY_TRANSACTIONS

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        QUERY_TRANSACTIONS,
        AGGREGATE_SPENDING,
        COMPARE_PERIODS,
        SEARCH_PRODUCTS,
        GET_PRODUCT_DETAILS,
        GET_UPCOMING_DEADLINES,
        GET_INSTALLMENT_SCHEDULE,
        FIND_DOCUMENTS,
    )
}

__all__ = ["TOOLS", "Action", "Tool", "ToolArgumentError", "ToolContext"]
