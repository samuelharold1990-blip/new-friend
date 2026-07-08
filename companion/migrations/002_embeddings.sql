-- Semantic memory: embedding vectors for facts (JSON-encoded float arrays,
-- computed by a local Ollama embedding model; NULL until embedded).
ALTER TABLE facts ADD COLUMN embedding TEXT;
