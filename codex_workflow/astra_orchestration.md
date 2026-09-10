# Astra Heavy Orchestration Policy

Use this policy only when the active Heavy parent is GPT-6 Astra. It is an Astra-specific overlay on `heavy_route.md`; all ordinary Heavy ownership, repair, acceptance, and closure rules still apply.

Keep Astra on high-value orchestration and treat OpenAI parent quota as scarce. Delegate repository-scale exploration, bounded implementation, routine testing, serious repair, and deep review to the configured specialists instead of duplicating their work in the parent.

- After delegation, wait for lifecycle or completion events. Do not poll workers at fixed short intervals or repeatedly reread large parent context merely to observe progress. If a true blocking wait is unavailable, use the sparsest practical checks.
- Keep worker packets and upward reports compact. Retain only decision-relevant state in the parent; keep raw logs, large diffs, and repeated status summaries with the responsible worker unless they are needed to resolve a concrete failure or decision.
- For substantial implementation that cleanly separates by module, feature, or ownership boundary, prefer a small number of bounded direct executors, typically 2–3, over one monolithic long-running executor. Do not split tightly coupled work merely to create parallelism.
- Astra owns worker topology. In every worker capsule, explicitly state that the worker must not create subagents unless Astra has authorized a concrete nested delegation. If a package materially expands beyond its authority, the worker returns the dependency or scope expansion to Astra instead of silently absorbing it.
- Optimize for bounded worker context and useful parallelism, not minimum worker count and not maximum fan-out. Do not spawn redundant workers merely for reassurance.
- Give Tester the changed surfaces, acceptance criteria, required checks, and identified risks. Start with proportionate verification and broaden only for concrete risk, failure, cross-cutting impact, or an explicit acceptance requirement.
- Do not add Sol or additional Astra sessions merely for another opinion. Use the configured DeepSeek and Luna specialists first; escalate expensive OpenAI reasoning only when it can materially change an architectural, integration, or acceptance decision.
- Bias toward completion on routine ambiguity. Ask the user only when ambiguity materially changes product behavior, authority, security, destructive side effects, or a consequential architecture decision.

The objective is not to minimize the number of workers. It is to minimize duplicated high-cost parent inference while preventing both recursive worker fan-out and giant long-lived executor contexts.
