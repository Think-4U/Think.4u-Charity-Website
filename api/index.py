import traceback

try:
    from app import app as app
except Exception as exc:
    startup_trace = traceback.format_exc()

    def app(environ, start_response):
        body = f"Application startup failed: {exc}\n\n{startup_trace}"
        start_response("500 INTERNAL SERVER ERROR", [("Content-Type", "text/plain; charset=utf-8")])
        return [body.encode("utf-8")]
