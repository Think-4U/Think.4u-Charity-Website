import traceback

from flask import Flask


def _fallback_app(error_message):
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def _startup_error(path):
        return (
            "Application startup failed.\n\n"
            f"{error_message}\n\n"
            "Check Vercel Runtime Logs for details.",
            500,
            {"Content-Type": "text/plain; charset=utf-8"},
        )

    return app


try:
    from app import app as _loaded_app
except Exception as exc:
    trace = traceback.format_exc()
    _loaded_app = _fallback_app(f"{exc}\n{trace}")


# Vercel Python runtime expects one of: app / application / handler at top-level.
app = _loaded_app
application = app
