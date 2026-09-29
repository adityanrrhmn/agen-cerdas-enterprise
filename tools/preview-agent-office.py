"""Backend khusus preview robot, tanpa membaca .env atau kredensial pengguna."""
import sys
from pathlib import Path
from tempfile import mkdtemp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn
import app.main as main
from app.config import Settings

if __name__ == "__main__":
    settings = Settings(simulate_integrations=True, delivery_mode="draft", data_backend="local",
                        local_store_path=Path(mkdtemp(prefix="office-preview-")) / "store.json")
    main.load_settings = lambda: settings
    uvicorn.run(main.app, host="127.0.0.1", port=8006)
