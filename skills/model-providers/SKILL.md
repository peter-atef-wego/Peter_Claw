---
name: model-providers
description: Model provider specifics for OpenAI/ChatGPT and Claude usage (capabilities, rate limits, API patterns, safety constraints). Use when selecting or integrating provider models.
---

# Model Providers (OpenAI / Claude)

This skill is a provider‑aware guide to choosing, integrating, and operating OpenAI/ChatGPT and Anthropic Claude models. It focuses on reliable production patterns rather than marketing‑level comparisons.

## 1) Provider selection framework

Choose a provider/model based on **task requirements**, not preference:

- **Accuracy / reasoning depth**: pick stronger reasoning models for complex workflows.
- **Latency**: for near‑real‑time use cases, prefer lower‑latency models.
- **Context length**: long‑document tasks require large context windows.
- **Cost**: balance quality with token price; measure cost per successful output.
- **Safety**: select models whose safety features match the domain’s risk profile.

Start with a baseline model, then upgrade only if evaluation shows a clear gap.

## 2) OpenAI / ChatGPT (production notes)

**Strengths**
- Broad general‑purpose capability (summarization, reasoning, code)
- Strong structured output support
- Rapid evolution of models and tooling

**Usage patterns**
- Use **system messages** to enforce invariants (format, policy, role).
- Use **explicit output formats** (JSON schemas / templates) for reliability.
- Prefer **tool use** for deterministic actions (APIs, DB updates).

**Operational considerations**
- Monitor rate limits and quota; handle `429` gracefully.
- Log input/output hashes for traceability (avoid logging secrets).
- Version prompts and templates.

## 3) Anthropic Claude (production notes)

**Strengths**
- Strong long‑context reasoning
- Clear instruction adherence
- Useful for policy‑heavy or document‑heavy tasks

**Usage patterns**
- Start from a clear success criterion + evals (Anthropic emphasizes evaluation‑driven iteration).
- Keep prompts clean and structured; avoid unnecessary verbosity.
- Use prompt chaining if the task requires multi‑step reasoning.

**Operational considerations**
- Measure latency vs output quality; some tasks do better with shorter prompts.
- If quality is inconsistent, tighten instructions and reduce ambiguity.

## 4) Provider‑agnostic best practices

- **Prompt portability**: keep prompts readable and portable across providers.
- **Evaluation first**: maintain a small test set for regression checks.
- **Cost control**: set hard caps on token usage per task.
- **Safety**: redact or block sensitive data before sending to providers.

## 5) Tooling integration patterns

- Use **tool‑calling** or **function calling** for reliable actions.
- Keep tools deterministic and short‑running.
- Validate tool outputs before using them downstream.

## 6) Reliability checklist

- Deterministic output format enforced
- Logging + traceability
- Retry strategy for transient failures
- Fallback mode when model fails (simpler response or “insufficient data”)

## 7) Common failure patterns

- **Over‑verbose outputs** → tighten output constraints.
- **Hallucinations** → require citations or add retrieval.
- **Inconsistent formatting** → add explicit templates + examples.

## 8) Security and compliance

- Never send credentials or secrets to providers.
- Redact personal data where possible.
- Store only necessary logs.

## Official references

OpenAI:
- API docs: https://platform.openai.com/docs
- Prompting guide: https://platform.openai.com/docs/guides/prompting
- Safety & policy: https://platform.openai.com/docs/policies

Anthropic Claude:
- Claude docs: https://platform.claude.com/docs
- Prompt engineering overview: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview
- Safety guidance: https://www.anthropic.com/safety
