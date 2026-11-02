# 연구 논문 조사: 하네스 레벨 자가 개선 (2026-11-02 기준)

> 리서치 서브에이전트 보고서 원문(영문). 요약과 설계 반영은 README.md 참고.

## A. Skill-library agents (procedural memory as executable/declarative artifacts)

| Work | Mechanism | Key result | Verdict / lesson |
|---|---|---|---|
| **Voyager** (2023, TMLR 2024) [arXiv 2305.16291](https://arxiv.org/abs/2305.16291) | Automatic curriculum; successful action programs stored in a skill library indexed by description embedding. No gradient updates. | 3.3x unique items, 15.3x faster tech-tree; library transfers to a new world. | *Files+shell.* A `SKILL.md` + script per verified routine. Lesson: **only admit a skill after it executed successfully**; index by description. |
| **Agent Workflow Memory (AWM)** (ICML 2025) [arXiv 2409.07429](https://arxiv.org/abs/2409.07429) | Induce reusable workflows from successful trajectories, offline or online; inject into prompt. | +24.6% / +51.1% relative success on WebArena / Mind2Web. | *Files+shell.* Stop hook → subagent summarizes a successful session into a workflow. Lesson: **induce from successes, abstract away task-specific values**. |
| **SkillWeaver** (COLM 2025) [arXiv 2504.07079](https://arxiv.org/abs/2504.07079) | Propose → synthesize skill as API → hone via tests. | 25-54% relative WebArena gains; skills transfer to weaker agents. | *Files+shell.* Lesson: **a skill ships with its own check**. |
| **Memp** (ACL Findings 2026) [arXiv 2508.06433](https://arxiv.org/abs/2508.06433) | Build/retrieve/update strategies for procedural memory; verbatim vs abstracted. | Success rises as repository is refined; transfers strong→weak model. | Lesson: **store a concrete exemplar and an abstracted script; keep an update/decay rule**. |
| **gskill** (2026) [DOI](https://dl.acm.org/doi/10.1145/3786335.3813196) | GEPA-style evolutionary optimisation of a repository SKILL.md against test pass rates. | Reported 24% → 93% resolve on some repos (secondary). | *Needs eval harness.* Lesson: **optimise skill text against a test signal, not vibes**. |
| **CODESKILL / MUSE-Autoskill / Dynamic Agent Skills survey** (2026) [2605.25430](https://arxiv.org/abs/2605.25430), [2605.27366](https://arxiv.org/abs/2605.27366), [2607.10113](https://arxiv.org/abs/2607.10113) | Distil skills from coding trajectories; skill-bank manager merges/prunes. Survey: 10 operators (ADD, REFINE, MERGE, SPLIT, PRUNE, DISTILL, ABSTRACT, COMPOSE, REWRITE, RERANK). | CODESKILL avg pass 29.57 → 39.26. | RL manager not reproducible, but **lifecycle operators are**: a periodic curator subagent. |

## B. Reflection and experience memory

| Work | Mechanism | Key result | Verdict / lesson |
|---|---|---|---|
| **Reflexion** (NeurIPS 2023) [2303.11366](https://arxiv.org/abs/2303.11366) | Verbal self-reflection after failure stored in episodic buffer. | HumanEval 91% pass@1. | **Reflect on failure in natural language and persist it**. |
| **ExpeL** (AAAI 2024) [2308.10144](https://arxiv.org/abs/2308.10144) | Cross-task insights with ADD/EDIT/UPVOTE/DOWNVOTE. | Beats ReAct on HotpotQA, ALFWorld, WebShop. | **Cross-task insights with vote counts as confidence**. |
| **Generative Agents** (2023) [2304.03442](https://arxiv.org/abs/2304.03442) | Memory stream; recency × importance × relevance; periodic reflection. | Qualitative. | **Periodic reflection writes abstractions back; score retrieval by recency+importance**. |
| **MemGPT / Letta sleep-time compute** [2310.08560](https://arxiv.org/abs/2310.08560), [2504.13171](https://arxiv.org/abs/2504.13171) | Core memory edited by model; background agent rewrites memory between turns. | ~5x less test-time compute. | **Consolidate off the critical path** (Stop hook / scheduled subagent). |
| **Mem0** (2025) [2504.19413](https://arxiv.org/abs/2504.19413) | Per-turn fact extraction; LLM decides add/update/delete/no-op. | +26% over OpenAI memory on LOCOMO; >90% token savings. | **Write-time conflict resolution, not append-only**. |
| **A-MEM** (2025) [2502.12110](https://arxiv.org/abs/2502.12110) | Zettelkasten notes; new notes evolve neighbours. | — | **New memory should update old memory**. |
| **Memento** (2025) [2508.16153](https://arxiv.org/abs/2508.16153) | Case-based reasoning with success/failure labels. | GAIA 87.88% Pass@3. | **Label cases with outcome; retrieve by similarity**. |
| **ReasoningBank** (Google, ICLR 2026) [2509.25140](https://arxiv.org/abs/2509.25140) | Distil reasoning strategies from successes AND failures; MaTTS contrastive attempts. | +8.3 WebArena, +4.6 SWE-Bench-Verified. | **Failures are memory too; parallel attempts give contrastive signal**. |
| **Dynamic Cheatsheet** (EACL 2026) [2504.07952](https://arxiv.org/abs/2504.07952) | Self-curated cheatsheet rewritten at inference. | Game-of-24 10% → 99%. | But whole-rewrite cheatsheets collapse (see ACE). |
| **ACE – Agentic Context Engineering** (Stanford/SambaNova, ICLR 2026) [2510.04618](https://arxiv.org/abs/2510.04618) | Generator / Reflector / Curator; **itemised delta updates** with ids + helpful/harmful counters; dedup/prune. Avoids brevity bias and context collapse. | +10.6% AppWorld; collapse case: 18,282 tokens/66.7 → 122 tokens/57.1 after one monolithic rewrite. | **Most directly transferable. Never let an LLM rewrite the whole CLAUDE.md/MEMORY.md; apply deltas, keep counters, prune separately.** |
| **Meta Context Engineering (MCE)** (ICML 2026) [2601.21557](https://arxiv.org/abs/2601.21557) | Meta-agent evolves the context-engineering skill itself. | mean +16.9% over SOTA. | **The curation procedure can be a SKILL.md that gets revised**. |

## C. Prompt / context optimisers
- **DSPy / GEPA** [2507.19457](https://arxiv.org/abs/2507.19457): reflective Pareto-front evolutionary prompt search; beats GRPO with 35x fewer rollouts. *Needs eval*; lesson: **keep a Pareto set of candidate instruction files, never collapse to one greedy best**.
- **TextGrad** [2406.07496](https://arxiv.org/abs/2406.07496): natural-language critiques as gradients; a reviewer subagent's critique applied as an edit.
- **Training-Free GRPO** (Tencent) [2510.08191](https://arxiv.org/abs/2510.08191): group rollouts, semantic advantage, experience library in prompt. ~$18 for measurable gains.
- **SEAL** (MIT) [2506.10943](https://arxiv.org/abs/2506.10943): *not reproducible* (weights). Only framing transfers: agent proposes its own harness edits, accepted by downstream performance.

## D. Self-modifying code agents and harness engineering
- **Darwin Gödel Machine** [2505.22954](https://arxiv.org/abs/2505.22954): archive + accept-if-better; SWE-bench 20% → 50%. **SICA** [2504.15228](https://arxiv.org/abs/2504.15228). **AlphaEvolve** (DeepMind). → git branches as archive, evolve CLAUDE.md/hooks/skills.
- **2026 harness-engineering cluster**: *Agentic Harness Engineering* [2604.25850](https://arxiv.org/abs/2604.25850) (each edit carries a falsifiable prediction); *Self-Harness* [2606.09498](https://arxiv.org/abs/2606.09498) (weakness mining → bounded proposal → regression validation); *Ouroboros* [2608.08311](https://arxiv.org/abs/2608.08311); **CORAL** [2604.01658](https://arxiv.org/abs/2604.01658), [code](https://github.com/Human-Agent-Society/CORAL): parallel Claude Code agents share `.coral/public/` of attempts/notes/skills; heartbeat triggers reflection and note→skill consolidation. Lilian Weng, *Harness Engineering for Self-Improvement* (2026-07-04) [post](https://lilianweng.github.io/posts/2026-07-04-harness/): "without evals, isolation and auditable traces, self-improvement becomes confident regression."
- Surveys: *A Survey of Self-Evolving Agents* [2507.21046](https://arxiv.org/abs/2507.21046); *Self-Evolving Coding Agents* [2608.03392](https://arxiv.org/abs/2608.03392).

## E. Cautionary evidence
- **Misevolution** (ICLR 2026) [2509.26354](https://arxiv.org/abs/2509.26354): memory accumulation raised confabulation (63.3% → 73.3%) and degraded safety.
- **Phantom Guardrails** [2607.13083](https://arxiv.org/abs/2607.13083): optimisers "fix" failures that never occurred when the prompt presupposes failure; a neutral charter cut fabrication 15/60 → 0/60.
- **EvoMal** [2608.25776](https://arxiv.org/abs/2608.25776): planted skills get copied into agent-authored skills (20-42%) and persist after removal → quarantine agent-authored skills.
- **Evaluating AGENTS.md** [2602.11988](https://arxiv.org/abs/2602.11988): context files generally do **not** raise SWE-bench success and add >20% cost; instructions help, repo overviews don't; developer-written beats LLM-generated.
- Index: [Awesome-Harness-Self-Improvement](https://github.com/leezythu/Awesome-Harness-Self-Improvement)

## Top 7 transferable design principles
1. **Delta updates, never whole-context rewrites (ACE).** Itemised bullets with ids and helpful/harmful counters; pruning as a separate pass.
2. **Induce procedures from verified successes, store with their check (AWM, Voyager, SkillWeaver, gskill).**
3. **Persist verbal reflections on failure, then abstract across tasks (Reflexion → ExpeL → ReasoningBank).**
4. **Separate generator / reflector / curator roles, off the critical path (ACE, MCE, Letta sleep-time).**
5. **Write-time reconciliation and lifecycle operators (Mem0, A-MEM, CODESKILL).**
6. **Accept harness edits only on measured improvement, with an archive (DGM, GEPA, Self-Harness).**
7. **Design for misevolution: neutral curation prompts that permit "nothing to fix"; quarantine agent-authored skills; measure cost as well as success.**
