from .base import BaseDispatcher, DispatchResult
from .email import EmailDispatcher
from .tchap import TchapDispatcher
from .webhook import WebhookDispatcher


def get_dispatcher(channel) -> BaseDispatcher:
    """Factory to get the appropriate dispatcher for a notification channel."""
    dispatchers = {
        "webhook": WebhookDispatcher,
        "email_smtp": EmailDispatcher,
        "tchap_bot": TchapDispatcher,
    }
    dispatcher_cls = dispatchers.get(channel.type)
    if not dispatcher_cls:
        raise ValueError(f"Unknown channel type: {channel.type}")
    return dispatcher_cls(channel.config_json)
