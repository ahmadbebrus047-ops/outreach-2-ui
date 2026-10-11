"""
Email copy. Replace the LOREM bodies with your own. The footer block is
appended automatically to every message and contains the physical address
and opt-out instructions required by CAN-SPAM -- do not remove it.
"""
from __future__ import annotations

from core import config

_LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod "
    "tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, "
    "quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo."
)


def _footer() -> str:
    return (
        "\n\n---\n"
        f"{config.SENDER_NAME}\n"
        f"{config.PHYSICAL_ADDRESS}\n\n"
        "You received this because you are a healthcare provider listed in the "
        "public NPI registry. If you'd prefer not to hear from us, reply with "
        f"\"UNSUBSCRIBE\" or email {config.UNSUBSCRIBE_CONTACT} and we'll remove "
        "you immediately."
    )


def initial_email(prospect: dict) -> tuple[str, str]:
    name = prospect.get("name") or "there"
    subject = "Streamline your practice's medical billing"
    body = f"Hi {name},\n\n{_LOREM}\n\n{_LOREM}{_footer()}"
    return subject, body


def reminder_email(prospect: dict) -> tuple[str, str]:
    name = prospect.get("name") or "there"
    subject = "Following up: medical billing for your practice"
    body = (
        f"Hi {name},\n\nJust following up on my note from last week.\n\n"
        f"{_LOREM}{_footer()}"
    )
    return subject, body
