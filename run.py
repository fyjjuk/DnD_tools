"""Arranque del servidor del MVP."""
import uvicorn

import config

if __name__ == "__main__":
    uvicorn.run("backend.app:app", host="0.0.0.0", port=config.PORT, log_level="info")
