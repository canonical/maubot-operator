#!/usr/bin/env python3

# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Maubot service."""

import logging

import requests

MAUBOT_ROOT_URL = "http://localhost:29316/_matrix/maubot"

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Exception raised when something fails while interacting with Maubot API.

    Attrs:
        msg (str): Explanation of the error.
    """

    def __init__(self, msg: str):
        """Initialize a new instance of the MaubotError exception.

        Args:
            msg (str): Explanation of the error.
        """
        self.msg = msg


def login(admin_name: str, admin_password: str) -> str:
    """Login in Maubot and returns a token.

    Args:
        admin_name: admin name that will do the login.
        admin_password: admin password.

    Raises:
        APIError: error while interacting with Maubot API.

    Returns:
        token to be used in further requests.
    """
    url = f"{MAUBOT_ROOT_URL}/v1/auth/login"
    payload = {"username": admin_name, "password": admin_password}
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        token = response.json().get("token")
        if not token:
            raise APIError("token not found in Maubot API response")
        return token
    except (requests.exceptions.RequestException, TimeoutError) as e:
        logger.exception("failed to request Maubot API: %s", str(e))
        raise APIError("error while interacting with Maubot API") from e


def register_account(
    token: str, account_name: str, account_password: str, matrix_server: str
) -> str:
    """Register account.

    Args:
        token: valid token for authentication.
        account_name: account name to be registered.
        account_password: account password to be registered.
        matrix_server: Matrix server where the account will be registered.

    Raises:
        APIError: error while interacting with Maubot API.

    Returns:
        Account access information.
    """
    url = f"{MAUBOT_ROOT_URL}/v1/client/auth/{matrix_server}/register"
    try:
        payload = {"username": account_name, "password": account_password}
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(url, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json()
    except (requests.exceptions.RequestException, TimeoutError) as e:
        logger.exception("failed to request Maubot API: %s", str(e))
        raise APIError("error while interacting with Maubot API") from e
