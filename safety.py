from __future__ import annotations

SAFETY_GUIDANCE = [
    "Never share passwords.",
    "Never share OTPs.",
    "Never send money.",
    "Avoid sharing your home address.",
    "Do not share private documents.",
    "Be cautious with links.",
    "Report harassment.",
    "Block suspicious users.",
    "Meet strangers only in safe, public places.",
    "Tell someone you trust before meeting someone offline.",
    "The bot does not verify that another user is truthful.",
    "The service is strictly 18+ only.",
]


def contains_safety_guidance(text: str) -> bool:
    if not text:
        return False
    lower = text.lower().replace(".", "").replace("!", "").replace("?", "")
    return any(item.lower().rstrip(".").replace("!", "").replace("?", "") in lower for item in SAFETY_GUIDANCE)


def contains_suspicious_content(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    suspicious_terms = [
        "send money",
        "pay me",
        "investment",
        "otp",
        "bank account",
        "crypto",
        "bitcoin",
        "ethereum",
        "wallet",
        "deposit",
        "cash app",
        "buy me",
        "refund",
        "gift card",
        "pay via",
    ]
    return any(term in lower for term in suspicious_terms)


def safety_warning() -> str:
    return (
        "Be careful. Never send money, OTPs, passwords, bank details, or other financial information to strangers."
    )


def safety_text() -> str:
    return "\n".join(SAFETY_GUIDANCE)
