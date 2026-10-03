"""
MUSFIRA AI Support — Backend
============================
Real backend (not a toy/demo): SQLite-backed conversation logging, ticketing,
feedback, ratings, admin analytics, per-IP rate limiting, and CORS — the same
category of features Intercom/Zendesk sell, built free on your own Groq or
Gemini key.

EVERYTHING lives on one page (chat, settings, dashboard) — see
templates/app.html. There is no separate /setup or /admin window anymore;
/admin and /setup just redirect into the right tab of that same page.

API KEYS ARE NEVER SAVED TO DISK, ANYWHERE, BY THIS APP:
  Paste a Groq or Gemini key into the Settings tab and it lives only as a
  plain JS variable in that browser tab, sent along with each chat message.
  Refresh the page and it's gone — you'll need to paste it again. Nothing
  is written to config.json, no cookie, no localStorage. The ONLY way a key
  becomes permanent is a real environment variable (GROQ_API_KEY /
  GEMINI_API_KEY) set outside this app entirely, e.g. in Vercel's Project
  Settings for an actual production deployment.

  ADMIN_KEY (the dashboard password) is NOT a third-party credential, so it
  IS saved to config.json like the rest of the business settings (name,
  WhatsApp, email, colors, welcome message) — those aren't secrets, so
  there's no reason a page refresh should wipe them.

HONEST LIMITATION (read this before deploying):
  SQLite writes to a file on disk. On Vercel's serverless Python runtime,
  the filesystem is EPHEMERAL — every cold start can wipe the database file.
  This means: locally (via run_dashboard.bat) everything persists perfectly.
  Deployed on Vercel, conversations/tickets may reset between cold starts.
  For real production persistence, swap `DB_PATH` for a free managed DB
  (e.g. Turso — SQLite-compatible, has a free tier — or Supabase Postgres
  free tier) by changing the `get_db()` function below. I did not fake
  persistence to make this look more finished than it is.
"""

import os
import time
import sqlite3
import random
from datetime import datetime, timezone
from collections import defaultdict, deque

import requests
from flask import Flask, request, jsonify, render_template, g, redirect, send_from_directory

from config_store import get_setting, save_config, load_config, is_configured

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
# NOTE: GROQ_API_KEY / ADMIN_KEY / etc. are no longer read directly from
# os.environ here — they go through get_setting(), which checks a real
# environment variable first (Vercel/production) and falls back to
# config.json (written by a customer via the /setup wizard on their own
# machine). See config_store.py.
GROQ_MODEL_PRIMARY = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_MODEL_FALLBACK = os.environ.get("GROQ_MODEL_FALLBACK", "llama-3.1-8b-instant")
GEMINI_MODEL_PRIMARY = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_MODEL_FALLBACK = os.environ.get("GEMINI_MODEL_FALLBACK", "gemini-3.5-flash")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "musfira_support.db"))

def build_system_prompt():
    business_name = get_setting("BUSINESS_NAME") or "this business"
    return (
        f"You are an AI support assistant for {business_name} "
        "(an AI automation agency: AI chatbots, AI calling agents, booking bots, "
        "support bots, custom automation). Answer in 2-4 sentences. Match the "
        "user's language and tone (English or Roman Urdu/Hinglish) naturally. "
        "Never claim to be a human — if directly asked, say plainly you are an "
        "AI assistant. If you don't know something specific to the business "
        "(exact pricing, account/order details, contracts), say so honestly "
        "and offer to connect them to a human instead of guessing."
    )

# Default FAQ seed — used only to populate the `faqs` table the first time
# the database is created. After that, FAQs live in the DB and are fully
# editable from /admin (Settings tab) — no code changes needed to add one.
DEFAULT_FAQ_SEED = [
    ("price, cost, paisa, kitna", "Our automation packages are custom-priced based on scope. Want exact pricing from a human?"),
    ("free trial, trial", "Yes — we offer a free trial run on a small automation task before you commit to a full package."),
    ("onboard, how fast, turnaround", "Most bots can be built and deployed within a few days once requirements are locked in."),
    ("support hours, business hours, timing", "Our team is online 9 AM - 11 PM (Pakistan time). Outside that, messages are answered as soon as we're back."),
    ("custom bot, custom automation", "Absolutely — we build fully custom bots (chat, voice, booking, or workflow automation) tailored to your business."),
]

UNRESOLVED_HINTS = ("connect", "don't know", "not sure", "honestly")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT,
            text TEXT,
            source TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_code TEXT,
            session_id TEXT,
            user_text TEXT,
            reason TEXT,
            status TEXT DEFAULT 'open',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            message_text TEXT,
            verdict TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            stars INTEGER,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS faqs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keywords TEXT,
            answer TEXT
        );
        CREATE TABLE IF NOT EXISTS system_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            context TEXT,
            error_text TEXT,
            created_at TEXT
        );
        """
    )
    # Seed default FAQs only the very first time (table starts empty).
    existing = conn.execute("SELECT COUNT(*) c FROM faqs").fetchone()[0]
    if existing == 0:
        conn.executemany(
            "INSERT INTO faqs (keywords, answer) VALUES (?, ?)", DEFAULT_FAQ_SEED
        )
    conn.commit()
    conn.close()


init_db()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CORS — so a widget copied into your own agency site (different domain than
# this backend) is still allowed to call it.
# ---------------------------------------------------------------------------
@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Admin-Key"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


# ---------------------------------------------------------------------------
# Simple per-IP rate limiting (in-memory — resets on cold start on serverless,
# but works perfectly for a single always-on server, e.g. local .bat run or
# a persistent host). Protects your free Groq quota from abuse/spam.
# ---------------------------------------------------------------------------
_rate_buckets = defaultdict(lambda: deque(maxlen=30))
RATE_LIMIT_COUNT = 20
RATE_LIMIT_WINDOW_SECONDS = 60


def rate_limited(ip):
    bucket = _rate_buckets[ip]
    now = time.time()
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_COUNT:
        return True
    bucket.append(now)
    return False


# ---------------------------------------------------------------------------
# Admin auth
# ---------------------------------------------------------------------------
def require_admin():
    key = request.headers.get("X-Admin-Key", "")
    configured_key = get_setting("ADMIN_KEY", "change-me-please")
    return key == configured_key


# ---------------------------------------------------------------------------
# Core chat logic
# ---------------------------------------------------------------------------
def discover_groq_models(api_key, limit=5):
    """Asks the account itself which models it can actually use, instead of
    guessing — this is what fixes "model not found / no access" errors that
    are specific to one account's plan, even though the model ID is a real,
    current, officially-documented Groq model. Returns several ranked
    candidates (not just one) since a single account can have unusual
    restrictions on more than one model."""
    try:
        res = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        res.raise_for_status()
        ids = [m.get("id", "") for m in res.json().get("data", [])]

        # Exclude anything that clearly isn't a general text-chat model —
        # speech-to-text, text-to-speech, and moderation/guard models will
        # answer /v1/models but reject chat completions (or need separate
        # terms acceptance), so never pick these even as a last resort.
        skip_hints = ("whisper", "tts", "orpheus", "guard", "prompt-guard")
        candidates = [mid for mid in ids if mid and not any(h in mid.lower() for h in skip_hints)]

        # Among what's left, prefer well-known general-purpose chat model
        # families — these are the ones actually meant for assistant-style
        # conversation, same as the hardcoded primary/fallback above.
        prefer_hints = ("llama-3", "llama-4", "gpt-oss", "qwen", "kimi", "deepseek", "compound", "gemma", "mistral")
        preferred = [mid for mid in candidates if any(h in mid.lower() for h in prefer_hints)]
        rest = [mid for mid in candidates if mid not in preferred]
        return (preferred + rest)[:limit]
    except Exception:
        return []


def discover_gemini_model(api_key):
    """Same idea as discover_groq_models, for Gemini: ask the account which
    models actually support generateContent instead of guessing."""
    try:
        res = requests.get(
            f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
            timeout=10,
        )
        res.raise_for_status()
        for m in res.json().get("models", []):
            name = m.get("name", "").replace("models/", "")
            methods = m.get("supportedGenerationMethods", [])
            if name and "generateContent" in methods:
                return name
    except Exception:
        pass
    return None


def check_faq(text, db):
    rows = db.execute("SELECT keywords, answer FROM faqs").fetchall()
    lower_text = text.lower()
    for row in rows:
        keywords = [k.strip().lower() for k in row["keywords"].split(",") if k.strip()]
        if any(kw in lower_text for kw in keywords):
            return row["answer"]
    return None


def log_error(context, error_text, db):
    print(f"[MUSFIRA AI ERROR] {context}: {error_text}")  # visible in the "MUSFIRA AI Backend" console window
    db.execute(
        "INSERT INTO system_errors (context, error_text, created_at) VALUES (?, ?, ?)",
        (context, str(error_text)[:2000], now_iso()),
    )
    db.commit()


def call_groq(session_id, user_text, db, override_key=None):
    rows = db.execute(
        "SELECT role, text FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 10",
        (session_id,),
    ).fetchall()
    history = [{"role": ("user" if r["role"] == "user" else "assistant"), "content": r["text"]} for r in reversed(rows)]

    messages = [{"role": "system", "content": build_system_prompt()}] + history + [{"role": "user", "content": user_text}]
    api_key = override_key or get_setting("GROQ_API_KEY")

    def attempt(model):
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": 0.5, "max_tokens": 400},
            timeout=20,
        )
        if not res.ok:
            raise RuntimeError(f"Groq {res.status_code}: {res.text[:500]}")
        data = res.json()
        return data["choices"][0]["message"]["content"].strip()

    last_error = None
    for model in (GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK):
        try:
            return attempt(model)
        except Exception as e:
            last_error = e
            log_error(f"call_groq (model={model})", e, db)
            time.sleep(0.4)

    # Both known-good model IDs failed — most likely this specific account
    # has unusual restrictions. Ask the account what it CAN use, and try a
    # few ranked candidates rather than a single guess.
    already_tried = {GROQ_MODEL_PRIMARY, GROQ_MODEL_FALLBACK}
    for discovered in discover_groq_models(api_key):
        if discovered in already_tried:
            continue
        already_tried.add(discovered)
        try:
            return attempt(discovered)
        except Exception as e:
            last_error = e
            log_error(f"call_groq (model={discovered}, auto-discovered)", e, db)
    raise last_error


def call_gemini(session_id, user_text, db, override_key=None):
    rows = db.execute(
        "SELECT role, text FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT 10",
        (session_id,),
    ).fetchall()
    # Gemini's REST format: role is "user" or "model" (not "assistant"), and
    # history + the new message all live in one "contents" array; the system
    # prompt is passed separately as "systemInstruction".
    history = [{"role": ("user" if r["role"] == "user" else "model"), "parts": [{"text": r["text"]}]} for r in reversed(rows)]
    contents = history + [{"role": "user", "parts": [{"text": user_text}]}]
    api_key = override_key or get_setting("GEMINI_API_KEY")

    def attempt(model):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        res = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={
                "contents": contents,
                "systemInstruction": {"parts": [{"text": build_system_prompt()}]},
                "generationConfig": {"temperature": 0.5, "maxOutputTokens": 400},
            },
            timeout=20,
        )
        if not res.ok:
            raise RuntimeError(f"Gemini {res.status_code}: {res.text[:500]}")
        data = res.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    last_error = None
    for model in (GEMINI_MODEL_PRIMARY, GEMINI_MODEL_FALLBACK):
        try:
            return attempt(model)
        except Exception as e:
            last_error = e
            log_error(f"call_gemini (model={model})", e, db)
            time.sleep(0.4)

    discovered = discover_gemini_model(api_key)
    if discovered and discovered not in (GEMINI_MODEL_PRIMARY, GEMINI_MODEL_FALLBACK):
        try:
            return attempt(discovered)
        except Exception as e:
            last_error = e
            log_error(f"call_gemini (model={discovered}, auto-discovered)", e, db)
    raise last_error


def call_llm(session_id, user_text, db, provider=None, override_key=None):
    """Single entry point the rest of the app calls — routes to whichever
    provider is configured (or an explicit override for /api/test-key and
    for the widget's temporary "test key, don't save it" mode)."""
    provider = provider or get_setting("PROVIDER", "groq")
    if provider == "gemini":
        return call_gemini(session_id, user_text, db, override_key=override_key)
    return call_groq(session_id, user_text, db, override_key=override_key)


def make_ticket_code():
    return "MSF-" + datetime.now().strftime("%y%m%d") + "-" + str(random.randint(1000, 9999))


# ---------------------------------------------------------------------------
# Routes — the single unified page (chat + settings + dashboard, one URL,
# switched between with JS tabs — never a separate window/tab)
# ---------------------------------------------------------------------------
@app.route("/")
def app_page():
    return render_template("app.html")


# Old bookmarks/links to the previous separate pages still land somewhere
# sensible — same page, just auto-opens that tab via the URL hash.
@app.route("/admin")
def admin_redirect():
    return redirect("/#dashboard")


@app.route("/setup")
def setup_redirect():
    return redirect("/#settings")


@app.route("/api/settings", methods=["POST"])
def api_settings():
    """Business/display settings ONLY — name, WhatsApp, email, colors,
    welcome message, which provider to prefer, and the admin dashboard
    password. Deliberately does NOT accept or store any API key: those are
    never sent to this endpoint at all (see the Settings panel in
    app.html) — they live only in the browser tab that typed them in, for
    that one /api/chat call. Any field left blank here keeps its previous
    saved value instead of wiping it out."""
    body = request.get_json(silent=True) or {}
    existing = load_config()

    provider = (body.get("provider") or existing.get("PROVIDER") or "groq").strip()
    if provider not in ("groq", "gemini"):
        provider = "groq"

    updates = {
        "PROVIDER": provider,
        "ADMIN_KEY": (body.get("admin_key") or "").strip() or existing.get("ADMIN_KEY") or "change-me-please",
        "WHATSAPP": (body.get("whatsapp") or "").strip() or existing.get("WHATSAPP", ""),
        "EMAIL": (body.get("email") or "").strip() or existing.get("EMAIL", ""),
        "BUSINESS_NAME": (body.get("business_name") or "").strip() or existing.get("BUSINESS_NAME", ""),
        "ACCENT_COLOR": (body.get("accent_color") or "").strip() or existing.get("ACCENT_COLOR", "#6c5ce7"),
        "WELCOME_MESSAGE": (body.get("welcome_message") or "").strip() or existing.get("WELCOME_MESSAGE", "How can I help today?"),
    }
    save_config(updates)
    return jsonify({"ok": True})


@app.route("/api/test-key", methods=["POST"])
def api_test_key():
    """Validates a key against the real provider API immediately, without
    saving it anywhere — this key is used for this one check and then
    forgotten by the server; it was never written to disk."""
    body = request.get_json(silent=True) or {}
    provider = (body.get("provider") or "groq").strip()
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "No key provided."}), 400

    db = get_db()
    try:
        reply = call_llm("__keytest__", "Say OK.", db, provider=provider, override_key=api_key)
        return jsonify({"ok": True, "sample_reply": reply[:200]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:500]})


@app.route("/api/config")
def api_config():
    """Public, safe subset — no secrets — used by the page to personalize
    itself. "configured" reflects a REAL environment variable only (e.g. a
    genuine Vercel deployment) — never anything typed into the browser,
    since browser-entered keys are never saved server-side at all."""
    return jsonify({
        "configured": is_configured(),
        "provider": get_setting("PROVIDER") or "groq",
        "business_name": get_setting("BUSINESS_NAME") or "MUSFIRA AI Support",
        "whatsapp": get_setting("WHATSAPP") or "https://wa.me/920000000000",
        "email": get_setting("EMAIL") or "mailto:support@musfiraai.com",
        "accent_color": get_setting("ACCENT_COLOR") or "#6c5ce7",
        "welcome_message": get_setting("WELCOME_MESSAGE") or "How can I help today?",
    })


@app.route("/widget.js")
def widget_js():
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    return send_from_directory(static_dir, "widget.js", mimetype="application/javascript")


# ---------------------------------------------------------------------------
# Routes — chat API
# ---------------------------------------------------------------------------
@app.route("/api/chat", methods=["POST", "OPTIONS"])
def api_chat():
    if request.method == "OPTIONS":
        return ("", 204)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    if rate_limited(ip):
        return jsonify({"error": "rate_limited", "reply": "You're sending messages too fast — please wait a moment."}), 429

    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "unknown")[:64]
    text = (body.get("message") or "").strip()[:500]
    if not text:
        return jsonify({"error": "empty_message"}), 400

    db = get_db()
    db.execute(
        "INSERT INTO messages (session_id, role, text, source, created_at) VALUES (?, 'user', ?, NULL, ?)",
        (session_id, text, now_iso()),
    )
    db.commit()

    faq_answer = check_faq(text, db)
    if faq_answer:
        reply, source = faq_answer, "faq"
    else:
        # A "test key" sent directly from the widget (not saved anywhere,
        # lost on page refresh) always takes priority over the saved config
        # — this is the "just testing, don't persist it" mode.
        test_provider = (body.get("test_provider") or "").strip()
        test_api_key = (body.get("test_api_key") or "").strip()
        if test_api_key:
            try:
                reply, source = call_llm(session_id, text, db, provider=test_provider or "groq", override_key=test_api_key), "llm-test"
            except Exception as e:
                log_error("api_chat test-key failure", e, db)
                reply, source = f"Test key failed: {str(e)[:300]}", "error"
        elif is_configured():
            try:
                reply, source = call_llm(session_id, text, db), "llm"
            except Exception as e:
                log_error("api_chat final failure", e, db)
                reply, source = "Sorry, something went wrong reaching the AI. Please try again or talk to a human.", "error"
        else:
            # No AI key is active for this session yet. This is shown to a
            # real visitor previewing the chat, so it must read like a
            # normal (if limited) assistant reply — never like an error or
            # an obviously unfinished "demo mode" placeholder.
            reply, source = (
                "Thanks for reaching out! I can answer common questions "
                "right away, and for anything else I'll connect you with "
                "our team — try \"Talk to a human\" below, or ask me about "
                "our services, pricing, or free trial.",
                "demo",
            )

    ticket_id = None
    if any(hint in reply.lower() for hint in UNRESOLVED_HINTS) or source == "error":
        ticket_id = make_ticket_code()
        db.execute(
            "INSERT INTO tickets (ticket_code, session_id, user_text, reason, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
            (ticket_id, session_id, text, f"Auto-flagged ({source})", now_iso()),
        )

    db.execute(
        "INSERT INTO messages (session_id, role, text, source, created_at) VALUES (?, 'bot', ?, ?, ?)",
        (session_id, reply, source, now_iso()),
    )
    db.commit()

    return jsonify({"reply": reply, "source": source, "ticket_id": ticket_id})


@app.route("/api/handoff", methods=["POST", "OPTIONS"])
def api_handoff():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    session_id = (body.get("session_id") or "unknown")[:64]
    db = get_db()
    ticket_id = make_ticket_code()
    db.execute(
        "INSERT INTO tickets (ticket_code, session_id, user_text, reason, status, created_at) VALUES (?, ?, '(manual handoff button)', 'User requested human agent', 'open', ?)",
        (ticket_id, session_id, now_iso()),
    )
    db.commit()
    return jsonify({"ticket_id": ticket_id})


@app.route("/api/feedback", methods=["POST", "OPTIONS"])
def api_feedback():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        "INSERT INTO feedback (session_id, message_text, verdict, created_at) VALUES (?, ?, ?, ?)",
        ((body.get("session_id") or "unknown")[:64], (body.get("message_text") or "")[:1000], body.get("verdict", ""), now_iso()),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/rating", methods=["POST", "OPTIONS"])
def api_rating():
    if request.method == "OPTIONS":
        return ("", 204)
    body = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        "INSERT INTO ratings (session_id, stars, created_at) VALUES (?, ?, ?)",
        ((body.get("session_id") or "unknown")[:64], int(body.get("stars", 0)), now_iso()),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "time": now_iso()})


# ---------------------------------------------------------------------------
# Routes — admin analytics (protected by ADMIN_KEY header)
# ---------------------------------------------------------------------------
@app.route("/api/admin/stats")
def admin_stats():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    total_sessions = db.execute("SELECT COUNT(DISTINCT session_id) c FROM messages").fetchone()["c"]
    total_messages = db.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
    total_tickets = db.execute("SELECT COUNT(*) c FROM tickets").fetchone()["c"]
    open_tickets = db.execute("SELECT COUNT(*) c FROM tickets WHERE status = 'open'").fetchone()["c"]
    avg_rating = db.execute("SELECT AVG(stars) a FROM ratings").fetchone()["a"] or 0
    faq_hits = db.execute("SELECT COUNT(*) c FROM messages WHERE source = 'faq'").fetchone()["c"]
    llm_calls = db.execute("SELECT COUNT(*) c FROM messages WHERE source = 'llm'").fetchone()["c"]
    fb_up = db.execute("SELECT COUNT(*) c FROM feedback WHERE verdict = 'up'").fetchone()["c"]
    fb_down = db.execute("SELECT COUNT(*) c FROM feedback WHERE verdict = 'down'").fetchone()["c"]

    return jsonify({
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "avg_rating": round(avg_rating, 2),
        "faq_hits": faq_hits,
        "llm_calls": llm_calls,
        "feedback_up": fb_up,
        "feedback_down": fb_down,
    })


@app.route("/api/admin/tickets")
def admin_tickets():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    status_filter = request.args.get("status", "open")
    if status_filter == "all":
        rows = db.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 200").fetchall()
    else:
        rows = db.execute("SELECT * FROM tickets WHERE status = ? ORDER BY id DESC LIMIT 200", (status_filter,)).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/tickets/<int:ticket_id>/resolve", methods=["POST"])
def admin_resolve_ticket(ticket_id):
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    db.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
    db.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Routes — FAQ management (the "customize it yourself" feature: add/edit/
# delete your own Q&A pairs from the browser, no code editing needed)
# ---------------------------------------------------------------------------
@app.route("/api/admin/faqs", methods=["GET", "POST"])
def admin_faqs():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        keywords = (body.get("keywords") or "").strip()
        answer = (body.get("answer") or "").strip()
        if not keywords or not answer:
            return jsonify({"error": "keywords and answer are both required"}), 400
        db.execute("INSERT INTO faqs (keywords, answer) VALUES (?, ?)", (keywords, answer))
        db.commit()
        return jsonify({"ok": True})
    rows = db.execute("SELECT * FROM faqs ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/admin/faqs/<int:faq_id>", methods=["PUT", "DELETE"])
def admin_faq_edit(faq_id):
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    if request.method == "DELETE":
        db.execute("DELETE FROM faqs WHERE id = ?", (faq_id,))
        db.commit()
        return jsonify({"ok": True})
    body = request.get_json(silent=True) or {}
    keywords = (body.get("keywords") or "").strip()
    answer = (body.get("answer") or "").strip()
    if not keywords or not answer:
        return jsonify({"error": "keywords and answer are both required"}), 400
    db.execute("UPDATE faqs SET keywords = ?, answer = ? WHERE id = ?", (keywords, answer, faq_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/admin/errors")
def admin_errors():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    rows = db.execute("SELECT * FROM system_errors ORDER BY id DESC LIMIT 50").fetchall()
    return jsonify([dict(r) for r in rows])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
