# Lessons learned

What this project taught me, and what I would change.

## What broke

- **Not every model provider supports tool calling.** Some ignore `tools` and `response_format` without returning an error. I added `TOOL_MODE=prompt`: tools and the expected JSON schema are described in the prompt, then the reply is parsed, validated and retried if invalid.
- **Providers fail in the middle of a run.** Quotas run out and services go down, so a single model per role was not enough. Each role now accepts a fallback list, tried in order.
- **Infrastructure dependencies move.** MinIO stopped publishing Docker images, so storage moved to RustFS, which is S3-compatible.

## What worked

- **A checkpointed approval step.** Run state lives in Postgres through the LangGraph checkpointer, so a human can approve a deliverable days later.
- **Isolating failures.** One failed external action does not stop the others, and an unconfigured tool reports the gap in the deliverable instead of crashing the agent.
- **Testing without a real provider.** A mock gateway makes the end-to-end test free and repeatable.

## What I would change

- **Add dashboard authentication early.** The dashboard has none, so the project is only safe on a trusted machine or behind an authenticated proxy.
- **Pin Docker image versions from the start.** Several services still use `latest`, which is fine locally but not for a durable deployment.
- **Publish evaluation results with each release.** The evaluation command exists, but no reference scores are published yet.
- **Calibrate the evaluation judge.** The judge is itself a model, so its scores need a human-labelled baseline before they can be trusted as an absolute measure.
