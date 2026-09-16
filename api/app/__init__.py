"""React DocChat API."""

from pathlib import Path

from dotenv import load_dotenv

api_root = Path(__file__).resolve().parents[1]
project_root = api_root.parent

# The root environment is the public configuration contract. The API-local file
# remains a compatibility fallback for an existing development checkout.
load_dotenv(project_root / ".env", override=False)
load_dotenv(api_root / ".env", override=False)
