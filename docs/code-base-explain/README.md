
# Agent Runtime — Codebase Documentation Suite

ဤ directory (`docs/code-base-explain/`) သည် **Agent Runtime** ၏ Architecture, Codebase Explanations နှင့် Source Code Snapshot များကို လိုအပ်ချက်အလိုက် သီးခြားစီ အလွယ်တကူ ဖတ်ရှုအသုံးပြုနိုင်ရန် ဖိုင် ၃ ခုအဖြစ် ခွဲခြမ်းစိတ်ဖြာ စီစဉ်ထားသော Documentation ဖြစ်ပါသည်။

---

## စာရွက်စာတမ်းများ ဖွဲ့စည်းပုံ

| File Name | အဓိက ပါဝင်သောအကြောင်းအရာများ | အသုံးပြုရန် အကောင်းဆုံး အခြေအနေ |
|:---|:---|:---|
| [`01_architecture_workflow.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/01_architecture_workflow.md) | **System Architecture & Lifecycle Pipeline (W1 – W4)**<br>- Framework-free native Python 3.12 design<br>- Strict Layering Rules (`evals -> agent -> llm -> tools`) with AST tests<br>- Full Mermaid System Flowchart with Upfront Planner & Reactive Nudges<br>- Multi-layer Runtime Guard & Stopping Criteria Pipeline<br>- Real-time Lifecycle Tracing (`TraceEvent`, `JsonlFileSink`) & CLI Viewer<br>- Automated Evaluation Subsystem (`evals/`) & Benchmark Architecture | System Design, Cognitive Architecture, Guard Pipeline နှင့် Lifecycle flow များကို ခြုံငုံနားလည်လိုသည့်အခါ |
| [`02_codebase_explanation.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/02_codebase_explanation.md) | **Deep Technical Codebase Explanation (W1 – W4)**<br>- Module, Class, Function တစ်ခုချင်းစီ၏ အတွင်းပိုင်းအလုပ်လုပ်ပုံ<br>- Upfront Planning (`Planner`, `PlanSpec`, structured schema)<br>- Native CoT Reasoning Capture (`reasoning.py`)<br>- Code-derived Evidence Ledger (`ledger.py`)<br>- Reactive Nudges & Give-up Policy (`nudges.py`)<br>- Automated Evals Engine (`spec.py`, `graders.py`, `runner.py`, `compare.py`)<br>- Test Suite Architecture (281 tests in 39 modules) | Component တစ်ခုချင်းစီ၏ ကုဒ်အလုပ်လုပ်ပုံနှင့် Design Decisions များကို နက်နက်နဲနဲ လေ့လာလိုသည့်အခါ |
| [`03_codebase_snapshot.md`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/03_codebase_snapshot.md) | **Modular Codebase Snapshots Gateway**<br>- [`code-base-snapshot/`](file:///c:/Users/uaung/aung_sann_phyo/person/agentic-ai-learning/agent-runtime/docs/code-base-explain/code-base-snapshot) အောက်ရှိ subsystem အလိုက် ခွဲထားသော snapshot ဖိုင် ၆ ခု<br>- `01_root.md`, `02_llm.md`, `03_tools.md`, `04_agent.md`, `05_tests_fixtures.md`, `06_evals.md`<br>- Token-efficient context feeding for AI/LLMs | LLM / AI Prompts များတွင် **Context Window** အဖြစ် သက်ဆိုင်ရာ Subsystem Snapshot ကိုသာ ရွေးချယ် ထည့်သွင်းလိုသည့်အခါ |

---

## လက်ရှိ Codebase အခြေအနေ (Active Status)

- **Milestone**: Week 4 / Day 6 Complete (W4 D6 DONE) — next: W5 D1 (Agent-Computer Interface design)
- **Test Suite**: **278 passed, 3 xfailed** (100% deterministic, ~1.9s)
- **Linter**: `ruff check .` Clean (zero issues)
- **Type Checker**: `mypy app evals` Clean (**49 source files**)
