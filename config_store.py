"""
Shared settings store.

IMPORTANT — what this file will and will NOT save to disk:
- API keys (GROQ_API_KEY, GEMINI_API_KEY) are NEVER written to config.json
  by this app. They only ever exist as a plain JS variable in the admin's
  own browser tab (see the Settings panel in templates/app.html) and are
  sent along with each chat request from that tab. Refreshing that tab
  wipes them, on purpose — that's the whole point.
- The ONLY way an API key becomes permanent is a real environment variable
  (GROQ_API_KEY / GEMINI_API_KEY) set outside this app entirely — e.g. in
  Vercel's Project Settings for a real production deployment. Env vars
  always win over anything typed in the browser.
- Everything else here (business name, WhatsApp/email, accent color,
  welcome message, which provider is selected, the admin dashboard
  password) is NOT a sensitive third-party credential, so it persists
  normally in config.json — a site's identity shouldn't reset every time
  someone refreshes the page.

This file has no Flask-specific code, so any future bot in this same
"multi agents" folder can import and reuse it the same way.
"""
import os
import json

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

# Fields config.json is allowed to hold. API keys are deliberately absent —
# see NEVER_PERSIST_KEYS below, which is enforced even if a future code
# change accidentally tries to pass one in.
DEFAULT_CONFIG = {
    "PROVIDER": "groq",
    "ADMIN_KEY": "",
    "WHATSAPP": "",
    "EMAIL": "",
    "BUSINESS_NAME": "",
    "ACCENT_COLOR": "#6c5ce7",
    "WELCOME_MESSAGE": "How can I help today?",
}

# Defense in depth: even if some future code calls save_config with one of
# these, it gets stripped before anything touches disk.
NEVER_PERSIST_KEYS = {"GROQ_API_KEY", "GEMINI_API_KEY"}


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
        return merged
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(updates):
    current = load_config()
    current.update({
        k: v for k, v in updates.items()
        if k in DEFAULT_CONFIG and k not in NEVER_PERSIST_KEYS
    })
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current


def get_setting(key, default=""):
    """A real environment variable always wins (this is how a genuine
    production deployment supplies its API key permanently). Otherwise
    falls back to config.json — which, for GROQ_API_KEY/GEMINI_API_KEY,
    will never actually have a value, by design."""
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    return load_config().get(key, default)


def is_configured(provider=None):
    """True once the given (or currently selected) provider has a key —
    which, locally, only ever comes from a real environment variable,
    since config.json never stores one."""
    provider = provider or get_setting("PROVIDER", "groq")
    key_name = "GEMINI_API_KEY" if provider == "gemini" else "GROQ_API_KEY"
    return bool(get_setting(key_name))
