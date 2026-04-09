"""Generate .streamlit/secrets.toml from environment variables at Railway startup.

Railway doesn't have a secrets file on disk. This script reads the OAuth
credentials from env vars and writes secrets.toml before Streamlit starts.

Required env vars:
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    COOKIE_SECRET          (random 32+ char string for cookie signing)
    RAILWAY_PUBLIC_DOMAIN  (set automatically by Railway)
    REDIRECT_URI           (optional override; auto-derived from RAILWAY_PUBLIC_DOMAIN)
"""

from __future__ import annotations

import os
import sys
import textwrap


def main() -> None:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    cookie_secret = os.getenv("COOKIE_SECRET", "")

    if not all([client_id, client_secret, cookie_secret]):
        print(
            "[generate_secrets] WARNING: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, "
            "or COOKIE_SECRET not set — skipping secrets.toml generation. "
            "The app will run without authentication.",
            file=sys.stderr,
        )
        return

    # Derive redirect_uri from Railway domain or explicit override
    redirect_uri = os.getenv("REDIRECT_URI", "")
    if not redirect_uri:
        railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
        if railway_domain:
            redirect_uri = f"https://{railway_domain}/oauth2callback"
        else:
            redirect_uri = "http://localhost:8501/oauth2callback"

    secrets_toml = textwrap.dedent(f"""\
        [auth]
        redirect_uri = "{redirect_uri}"
        cookie_secret = "{cookie_secret}"
        client_id = "{client_id}"
        client_secret = "{client_secret}"
        server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
    """)

    os.makedirs(".streamlit", exist_ok=True)
    with open(".streamlit/secrets.toml", "w") as f:
        f.write(secrets_toml)

    print(f"[generate_secrets] secrets.toml written. redirect_uri={redirect_uri}")


if __name__ == "__main__":
    main()
