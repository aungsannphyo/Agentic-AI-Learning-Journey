import json
from pathlib import Path

from dotenv import load_dotenv

from app.llm import OpenAIClient
from app.llm.types import user_message
from app.tools import ListFilesTool, Workspace

load_dotenv()
client = OpenAIClient(system_prompt="You inspect the workspace with tools.")
r = client.complete(
    messages=[user_message("List the root directory.")],
    tools=[ListFilesTool(Workspace(Path.cwd()))],
)
print(json.dumps(list(r.assistant_items), indent=2))
print(r.usage)
