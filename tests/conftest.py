"""Keep automated tests offline and independent from a developer's local env file."""

import os

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["LLM_PROVIDER"] = "none"
