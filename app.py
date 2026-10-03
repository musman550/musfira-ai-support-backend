"""Local development entry point. Run with: python app.py
(run_dashboard.bat does this for you automatically)."""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed yet — .bat file installs it from requirements.txt

from bot_app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
