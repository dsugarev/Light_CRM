# ADR 0031: The Admin chooses the assistant's AI model

Status: Accepted · Date: 2026-11-22 · Phase 10 (Release 1.1) · Extends ADR 0007 (LLM routing) and ADR 0028 (data flow)

## Context
Release 1 used one model: `openai/gpt-oss-120b` through OpenRouter, served only by Cerebras. That data flow was approved with prompt logging off (ADR 0028). The owner added a Google `GEMINI_API_KEY`, and asked for:
- a free open-source alternative on OpenRouter;
- Gemini as an option;
- an Admin setting that chooses the model for everyone.

The model must support tool calling: the assistant reads through tools and proposes actions through tools (ADR 0030).

On 2026-11-22, OpenRouter listed 11 free models with tool support. Checked on the owner's account with a harmless prompt:
- NVIDIA Nemotron 3 Ultra (550B MoE, open weights, served by NVIDIA) made a correct tool call;
- Google Gemma 4 31B (free) was rate-limited (429).

The Gemini key lists `gemini-2.5-flash`, but Google refuses it to new users (`404`, "no longer available to new users"). Of the newer Flash models, `gemini-3.8-flash`, `gemini-3.7-flash` and `gemini-flash-latest` answered `503 high demand` or timed out on the free tier during the evaluation; `gemini-3.5-flash` answered, with tool calls over several rounds (LiteLLM keeps Gemini's thought signature in the tool-call id).

## Decision
1. **A fixed catalog of three models** in `app/llm/models.py`:
   - `gpt-oss-120b`: OpenRouter, Cerebras only. It was the default until 2026-11-22; `LLM_MODEL`/`LLM_PROVIDER` still override it.
   - `nemotron-3-ultra-free`: OpenRouter free endpoint, NVIDIA only. **The default since 2026-11-22** (owner's decision; migration `0014`).
   - `gemini-3.5-flash`: Google AI Studio, through LiteLLM's `gemini/` provider. No new library. (Approved as "Gemini 2.5 Flash"; changed because Google no longer serves 2.5 Flash to new keys.)
2. **One setting for everyone.** The runtime setting `ai_model` (Admin **Settings**; `PATCH /settings`) applies to the next question of every user, without a restart, and is audited as `settings.updated`. A model whose API key is not configured cannot be chosen (`422 settings.ai_model_unavailable`). `GET /settings/ai-models` lists the models with `available` and `data_note`.
3. **All calls still go through `backend/app/llm/client.py`.** It picks the model, key and provider routing per request. LiteLLM is imported nowhere else.
4. **Users see which model answers.** `GET /assistant/status` adds `model` and `model_label`, shown under the question box.
5. **Data protection is visible.** Free OpenRouter endpoints, and Gemini's free tier, may keep prompts or use them to improve the provider's products. Prompts contain customer data. The owner approved offering these options on 2026-11-22. The Settings screen labels them "The provider may keep or use prompts", and the operations guide asks for the provider terms (and, where needed, the DPO's approval) before using them with real data.
6. **Evaluation per model.** Every catalog model runs the live evaluation (`docs/assistant-eval.md`), and its result is recorded before it is used in production.

## Consequences
- Adding a model is a catalog entry plus an evaluation run; no other code changes.
- Free models have provider request caps and can be slower or less reliable at tool calling. The evaluation shows the difference.
- The rule in CLAUDE.md that allowed only gpt-oss via Cerebras now names the catalog.

## Amendment 2026-11-22: the free model is the default
The owner chose the free NVIDIA Nemotron 3 Ultra as the default. It passed the live evaluation 28/28 (run 6) and 37/38 (run 7, one provider error). Migration `0014` makes it the column default and switches installations still on `gpt-oss-120b`. That value had come from migration `0013`, not from an Admin, because Release 1.1 was not yet released.

The data note still applies: the free endpoint may keep or use prompts. The Settings screen shows the warning for the default, and the operations guide asks for the DPO's approval before the assistant is used with real customer data. An Admin can switch back to gpt-oss-120b at any time.
