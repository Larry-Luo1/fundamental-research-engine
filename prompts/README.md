# Prompt Templates

This folder is reserved for LLM-assisted pipeline stages.

The intended contract is:

1. The engine provides a fixed schema and evidence bundle.
2. The model fills or critiques one structured stage.
3. The engine validates output shape and renders the final memo.

Do not let model-specific free-form prose become the source of record. Store structured intermediate outputs first, then render prose.
