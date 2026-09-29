"""
Authorisation — role-based access control.
Maps agent actions to required roles. Fail-closed (unknown = denied).
"""
import logging

logger = logging.getLogger("authorization")

ACTION_ROLE_MAP = {
    # Accounts agent
    "balance_enquiry": "view_accounts",
    "list_accounts": "view_accounts",
    # Transaction agent
    "get_transactions": "view_transactions",
    "get_statement": "view_transactions",
    # Service agent
    "change_address": "request_services",
    "request_chequebook": "request_services",
    "update_kyc": "request_services",
}


def check_authorisation(user_roles: list[str], action: str) -> bool:
    """
    Return True if the user's roles permit the action.
    Unknown actions are denied by default (fail-closed).
    """
    required_role = ACTION_ROLE_MAP.get(action)
    if required_role is None:
        logger.warning(f"[AUTHZ] Unknown action '{action}' — denied")
        return False

    allowed = required_role in user_roles
    logger.info(
        f"[AUTHZ] action={action} required={required_role} "
        f"roles={user_roles} → {'ALLOW' if allowed else 'DENY'}"
    )
    return allowed