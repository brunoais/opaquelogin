import base64
import time
import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

import requests
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError



API_BASE_URL = os.getenv("TRASHMAIL_API_URL", "https://trashmail.com").rstrip("/")
DEFAULT_LANG = os.getenv("TRASHMAIL_LANG", "en")[:2]
OPAQUE_CONTEXT = b""
OPAQUE_CONTEXT = b"pat_opaque_auth"


def build_url(api=True, lang='en', cmd=None, **paramss):
    params = {
        "lang": lang,
    }
    if api:
        params['api'] = int(api)
    if cmd:
        params['cmd'] = cmd
    return {
        "url": f"{API_BASE_URL}/",
        "params": {
            **params,
            **paramss
        }
    }


def _safe_json(response):
    try:
        return response.json()
    except RequestsJSONDecodeError:
        logging.exception("Failed to decode JSON response")
        return None


def is_pat_token(password: str) -> bool:
    return bool(password and isinstance(password, str) and password.startswith("tmpat_") and len(password) > 6)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _b64decode(data: str) -> bytes:
    padded = data + '=' * (-len(data) % 4)
    try:
        return base64.b64decode(padded)
    except Exception:
        return base64.urlsafe_b64decode(padded)


def opaque_check(session: requests.Session, username: str, lang: str = DEFAULT_LANG):
    try:
        response = session.post(**build_url(cmd="opaque_check", lang=lang), json={"username": username})
        result = _safe_json(response) or {}
        return {
            "opaque_enabled": result.get("opaque_enabled", False),
            "srp_enabled": result.get("srp_enabled", False),
            "migration_available": result.get("migration_available", False),
        }
    except Exception:
        logging.exception("OPAQUE capability probe failed for %s", username)
        return None


def pat_opaque_start(session: requests.Session, username: str, token: str, lang: str = DEFAULT_LANG):
    import opaque as opaque_lib

    start_pub, client_sec = opaque_lib.CreateCredentialRequest(token)
    start_login_request = _b64encode(start_pub)
    payload = {
        "username": username,
        "token_prefix": f"{token[:12]}..." if len(token) > 12 else token,
        "startLoginRequest": start_login_request,
    }

    response = session.post(**build_url(cmd="pat_opaque_auth_init", lang=lang), json=payload)
    result = response.json()

    if not result.get("success"):
        raise HTTPError(("400 Client Error: OPAQUE start failed", result), response=response)

    session.cookies.set("session_id", result['session_id'])

    login_response = result["loginResponse"]

    return client_sec, login_response, result['session_id']


def pat_opaque_finish(session: requests.Session, client_sec: bytes, login_response: str, session_id: Optional[str], lang: str = DEFAULT_LANG):
    import opaque as opaque_lib

    login_response_bytes = base64.urlsafe_b64decode(login_response + '===')

    try:
        _, auth_u, _ = opaque_lib.RecoverCredentials(login_response_bytes, client_sec, OPAQUE_CONTEXT)

    except ValueError:
        logging.exception(
            "OPAQUE RecoverCredentials failed (ke2_len=%s, sec_len=%s)",
            len(login_response_bytes),
            len(client_sec),
        )
        raise
    finish_request = base64.urlsafe_b64encode(auth_u)

    payload = {
        "session_id": session_id,
        "finishLoginRequest": finish_request,
    }

    response = session.post(**build_url(cmd="pat_opaque_auth_finish", lang=lang), json=payload)
    result = response.json()

    data = result['data']
    final_session_id = data.get("session_id") or result.get("session_id") or session_id
    if final_session_id:
        session.cookies.set("session_id", final_session_id)

    pat_token = data.get("pat")
    if pat_token:
        session.cookies.set("pat", pat_token)

    return True


auths = {}
cache_time = time.time()

def api_login(username, password):
    session = requests.Session()

    if is_pat_token(password):
        capability = opaque_check(session, username)
        if capability is None or capability.get("opaque_enabled", False):
            try:
                client_sec, login_response, session_id = pat_opaque_start(session, username, password)
                pat_opaque_finish(session, client_sec, login_response, session_id)
                logging.info("PAT-OPAQUE authentication succeeded for %s", username)
                return True, session
            except HTTPError as exc:
                logging.warning("PAT-OPAQUE HTTP error for %s: %s", username, exc)
                raise
            except Exception:
                logging.exception("PAT-OPAQUE authentication failed for %s", username)
                raise
        else:
            logging.info("OPAQUE explicitly disabled for %s; falling back to legacy login", username)

    if legacy_login(session, username, password):
        return True, session

    return False, None
