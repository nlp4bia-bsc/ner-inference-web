from app.config import Settings
from app.db import Database
from app.services.cleanup import cleanup
from app.storage import LocalStorage

if __name__ == "__main__":
    settings = Settings()
    cleanup(Database(settings), LocalStorage(settings.storage_root))
