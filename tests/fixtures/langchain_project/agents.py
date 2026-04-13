from langchain_core.tools import tool


@tool
def lookup_account(account_id: str) -> str:
    """Look up account health, contract tier, and recent support activity."""
    return account_id


SUPPORT_ROUTER = {
    "name": "support_router",
    "system_prompt": "Route support requests to billing, platform, or success workflows.",
}

