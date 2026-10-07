# Codebase Snapshot Index

ဤ directory သည် Agent Runtime codebase တစ်ခုလုံးရှိ active source code များကို LLM / AI context အဖြစ် လိုအပ်သည့် subsystem အလိုက် သီးခြားစီ သုံးစွဲနိုင်ရန် ဖိုင်ခွဲထားသော snapshots များ ဖြစ်ပါသည်။

## Modular Snapshot Files

| File | Module / Layer | Files Included | Use Case / Context |
|:---|:---|:---:|:---|
| [`01_root.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/01_root.md) | Root & Entry Layer | 3 files | `main.py`, `trace_view.py`, `conftest.py` |
| [`02_llm.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/02_llm.md) | LLM Subsystem Layer | 10 files | `app/llm/*` (clients, retry, errors, types) |
| [`03_tools.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/03_tools.md) | Tools & Sandbox Layer | 14 files | `app/tools/*` (schemas, validation, workspace, file/search tools) |
| [`04_agent.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/04_agent.md) | Agent Runtime Layer | 9 files | `app/agent/*` (loop, state, guards, budgets, trace) |
| [`05_tests_fixtures.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot/05_tests_fixtures.md) | Tests & Fixtures | 1 file | `tests/builders.py` (shared fixtures & doubles) |

---

## Context Window Usage Tip

- LLM ကို Prompt ပို့သည့်အခါ တစ်ခုလုံး အကုန်ထည့်စရာမလိုဘဲ သက်ဆိုင်ရာ Subsystem Snapshot (ဥပမာ `04_agent.md` သို့မဟုတ် `02_llm.md`) ကိုသာ ရွေးချယ် ထည့်သွင်းခြင်းဖြင့် token ကုန်ကျစရိတ်ကို ၇၀-၈၀% အထိ သက်သာစေပြီး LLM ၏ focus ကို တိကျစေပါသည်။