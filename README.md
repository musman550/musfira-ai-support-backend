# MUSFIRA AI Support — Backend

**[👀 Live Preview](https://musman550.github.io/musfira-ai-support-backend/)** — see the chat UI live, no install needed
**[⬇ Download ZIP](https://github.com/musman550/musfira-ai-support-backend/archive/refs/heads/main.zip)** — the full self-hosted bot, free

Real Python (Flask) backend for the MUSFIRA AI Support bot: chat API,
ticketing, feedback, ratings, an inline admin dashboard, and a live
key-test tool — free, running on your own Groq or Gemini key.

The live preview above is a static, backend-free demo (GitHub Pages) so it's
always online with nothing that can go down — it shows the exact same chat
experience, just with canned replies instead of a live AI connection. The
full version you download connects to your own free Groq/Gemini key.

**Everything — chat, settings, dashboard — lives on ONE page.** There is
no separate `/setup` or `/admin` window; they're just tabs at the top of
the same screen (hidden automatically when this page is embedded as a
widget on someone else's site, so a real visitor only ever sees the chat).

**API keys are never saved anywhere.** Paste a Groq/Gemini key into the
Settings tab and it lives only as a variable in that browser tab — sent
with each chat message, never written to a file, cookie, or browser
storage. Refresh the page and it's gone; paste it again. Only non-secret
business details (name, WhatsApp, email, colors, welcome message, the
Dashboard password) are remembered across refreshes — nothing that counts
as a credential.

## Folder placement

Put this whole folder on the Desktop inside your **"multi agents"** folder,
e.g. `Desktop\multi agents\musfira-support-backend\`. Nothing inside it uses
a hardcoded path. `config_store.py` has no bot-specific code, so your next
bot (Booking, Calling Agent) can reuse the same file.

## 1. Run it locally (double-click)

1. Make sure Python 3.10+ is installed (`python --version` in cmd).
2. Double-click **run_dashboard.bat**. First run creates an isolated
   virtual environment and installs dependencies (only once). It opens
   `http://127.0.0.1:5000/` automatically.
3. The page opens straight into the **Chat** tab, already usable in demo
   mode (canned replies, so you can see the UI even with zero setup).

## 2. Try it with a real key (Settings tab)

1. Click the **⚙️ Settings** tab (top of the page — not a new window).
2. Pick a provider (Groq or Gemini), paste a free key, and click
   **"🔍 Test this key right now"** — it tells you immediately whether the
   key works, and if not, the exact reason (bad key, no access to that
   model, quota, network block, etc.) instead of a vague error.
3. As soon as you type a working key, go back to the **💬 Chat** tab and
   start talking — it's live for this tab, no save button needed.
4. While you're there, fill in Business Name / WhatsApp / Email / accent
   color / welcome message and click **"Save business settings"** — these
   aren't secrets, so they stick around after a refresh (unlike the key).

## 3. Live-test it like a real first-time user

1. Refresh the page. Go to Settings — confirm the API key field is empty
   again (it should ask you to paste it again), but confirm your business
   name/WhatsApp/email are still filled in from step 2.
2. Chat a little — confirm replies actually come from your provider, not
   "(Demo mode...)".
3. Click "Talk to a human" — confirm it opens *your* WhatsApp/email.
4. Click the **📊 Dashboard** tab — it should ask for a password (the one
   you set in Settings). Enter it and confirm stats/tickets/FAQs/errors
   render right there on the same page, no new window.
5. Refresh again, click Dashboard — confirm it asks for the password again
   (not remembered either — every refresh starts clean for anything
   credential-shaped).
6. Add a custom FAQ (e.g. keywords "refund, cancel"), then ask the chat
   that exact question — confirm it answers instantly from your FAQ, not
   from the AI provider.
7. Check "Recent Errors" — if a reply ever fails, the exact reason shows
   up here (and in the "MUSFIRA AI Backend" console window), never hidden.

If all of that behaves, it's ready to give away.

## 4. Deploy to Vercel for real (so it works for actual visitors)

The in-browser Settings key is for trying it out — a page that nobody has
open isn't answering anyone. A real, always-on deployment needs the key as
a genuine environment variable instead:

1. Push this folder to a GitHub repo.
2. Import it in Vercel — it auto-detects `vercel.json` + `api/index.py`.
3. Project Settings -> Environment Variables: add `GROQ_API_KEY` (or
   `GEMINI_API_KEY`), and optionally `ADMIN_KEY` / `ALLOWED_ORIGIN` (your
   real domain, e.g. `https://musfiraai.com`).
4. Deploy. The bot is live at `https://<your-project>.vercel.app/`, and the
   Settings tab there will show it's already configured — env vars always
   win over anything typed in a browser.

## 5. Add it to your agency site (native, not an iframe)

Copy `templates/app.html`'s contents directly into a page/section of your
own site (matching your site's own header/nav) — don't wrap it in an
`<iframe>` for your own integration.

## 6. Embed it on ANY OTHER website with one line

For handing this out to someone else (so it drops into their site without
them touching any code), the Settings tab shows a ready-to-copy snippet:

```html
<script src="https://<your-deployed-backend>/widget.js"></script>
```

Paste that one line anywhere in a site's HTML and a floating chat icon
appears bottom-right — click to open, click again (or the ✕ in the header)
to close. It's an iframe pointing back at this backend, so it never
conflicts with the host site's own CSS/JS, is fully responsive, and never
shows the Settings/Dashboard tabs to that site's visitors.

## About the "auto-redirect to musfiraai.com" idea

One thing deliberately NOT built: forcing the widget to silently redirect
a customer's own website visitors to musfiraai.com. That would mean a
stranger clicks a support chat button on someone else's site and gets
bounced to your site without asking — that's a hijack of someone else's
traffic, not a backlink, and the kind of thing that gets a domain flagged
by browsers/search engines.

What actually works, legitimately — real marketing credit every time
someone uses a bot you built — is the honest, clickable "Powered by
MUSFIRA AI" link in the chat footer, on every copy that goes out. Same
mechanic Typeform/Vercel/Carrd use on their free tiers.

## Privacy & data — stated plainly

This bot is self-hosted: it runs on your (or your customer's) own computer
or Vercel account. An API key is used only to call Groq/Gemini directly
from wherever it's running — never sent to musfiraai.com, to me, or to
Anthropic, and (as covered above) never written to disk from the browser
at all. Conversation data (messages, tickets, ratings) stays in the local
`musfira_support.db` file on whichever machine is running it.

## Honest limitation

SQLite (`musfira_support.db`) and `config.json` persist perfectly when run
locally via the .bat file or on any always-on server. On Vercel's
serverless Python runtime, the filesystem resets between cold starts — so
conversation/ticket history may not persist long-term there. For
production-grade persistence, swap `get_db()` in `bot_app.py` for a free
managed DB (Turso — SQLite-compatible, free tier — or Supabase's free
Postgres tier). Flagging this now rather than letting it surprise anyone.

<!-- BRANDING:START -->

---

🌐 Website: [musfiraai.com](https://musfiraai.com/)

* ▶️ YouTube: [Automate With Musfira AI](https://www.youtube.com/@automatewithmusfiraai)
* 💼 LinkedIn: [Musfira AI](https://www.linkedin.com/in/musfira-ai-b3218b39b)
* 📸 Instagram: [@musma_n55](https://instagram.com/musma_n55)

<!-- BRANDING:END -->
