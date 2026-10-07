
# Agent Runtime — Codebase Documentation Suite

ဤ directory (`docs/code-base-explain/`) သည် **Agent Runtime** ၏ Architecture, Codebase Explanations နှင့် Source Code Snapshot များကို လိုအပ်ချက်အလိုက် သီးခြားစီ အလွယ်တကူ ဖတ်ရှုအသုံးပြုနိုင်ရန် ဖိုင် ၃ ခုအဖြစ် ခွဲခြမ်းစိတ်ဖြာ စီစဉ်ထားသော Documentation ဖြစ်ပါသည်။

---

## စာရွက်စာတမ်းများ ဖွဲ့စည်းပုံ

| File Name | အဓိက ပါဝင်သောအကြောင်းအရာများ | အသုံးပြုရန် အကောင်းဆုံး အခြေအနေ |
|:---|:---|:---|
| [`01_architecture_workflow.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/01_architecture_workflow.md) | **System Architecture & Lifecycle Pipeline**<br>- No external frameworks & native Python 3.12 design<br>- Strict Layering Rules (`agent -> llm -> tools`) with AST tests<br>- Complete Mermaid System Flowchart<br>- 9-Stage Runtime Guard Order & Safety Pipeline<br>- Lifecycle Tracing (`TraceEvent`, `JsonlFileSink`) & CLI Viewer<br>- Resiliency, `Retry-After` hint override & fail-fast cap | System Design, Guard Logic နှင့် Lifecycle flow များကို ခြုံငုံနားလည်လိုသည့်အခါ |
| [`02_codebase_explanation.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/02_codebase_explanation.md) | **Deep Technical Codebase Explanation**<br>- Layer တစ်ခုချင်းစီရှိ ဖိုင်များ၊ class များ၊ function များ၏ အတွင်းပိုင်းအလုပ်လုပ်ပုံ<br>- Single source of truth `Tool.args_model` & Pydantic validation<br>- Stateless `ResilientClient` & dynamic deadline abort<br>- Low cognitive complexity refactoring (AgentLoop helper methods)<br>- Test Suite Architecture (151 tests in 25 modules) | Component တစ်ခုချင်းစီ၏ ကုဒ်အလုပ်လုပ်ပုံနှင့် Design Decisions များကို နက်နက်နဲနဲ လေ့လာလိုသည့်အခါ |
| [`03_codebase_snapshot.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/03_codebase_snapshot.md) | **Consolidated Single-File Codebase Snapshot**<br>- Active source files ၃၇ ခုလုံး၏ current source code အပြည့်အစုံ<br>- `app/main.py`, `app/trace_view.py`, `app/llm/*`, `app/tools/*`, `app/agent/*`, `conftest.py`, `tests/builders.py`<br>- Zero external noise / clean fenced code blocks | LLM / AI Prompts များတွင် **Context Window** အဖြစ် တိုက်ရိုက် ထည့်သွင်းပြီး လက်ရှိ codebase အခြေအနေကို ပေးပို့လိုသည့်အခါ |

---

## လက်ရှိ Codebase အခြေအနေ (Active Status)

- **Milestone**: Week 3 / Day 2 Complete
- **Test Suite**: **151 tests passed** (100% deterministic, ~1.0s)
- **Linter**: `ruff check .` Clean (zero issues)
- **Type Checker**: `mypy app` Clean (**36 source files**)
