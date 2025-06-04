import os
from app import app


def str_to_bool(value: str) -> bool:
    """Convert a string environment variable to a boolean."""
    return value.lower() in {"1", "true", "t", "yes", "y"}


if __name__ == "__main__":
    debug_env = os.getenv("FLASK_DEBUG")
    debug_mode = str_to_bool(debug_env) if debug_env is not None else False
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
