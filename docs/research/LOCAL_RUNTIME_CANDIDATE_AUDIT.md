# Local Runtime and Agent-Evaluation Candidate Audit

Verified: 2026-07-31. Sources are official repositories, vendor
documentation, or primary papers. “8 GB feasible” means a bounded 1B–4B,
4-bit workload, not unrestricted context or concurrent agents.

## Runtime candidates

### Ollama

- **Official source:** [ollama/ollama](https://github.com/ollama/ollama)
- **Latest verified release:** v0.32.5 (2026-07-27); installed CLI v0.32.5.
- **Licence:** MIT.
- **Apple Silicon:** native macOS/Metal support.
- **8 GB feasibility:** yes for Qwen2.5 1.5B Q4_K_M; larger installed models
  were not benchmarked.
- **Installation:** already installed; no change.
- **Security:** local HTTP service must remain loopback-bound and governed;
  model output is untrusted.
- **Maintenance:** active.
- **Architecture overlap:** already has a SaathiOS provider adapter, model
  router, circuit breaker, cost policy, and audit boundary.
- **Decision:** **INTEGRATE** — retain as default.

### MLX and MLX-LM

- **Official source:** [ml-explore/mlx](https://github.com/ml-explore/mlx) and
  [ml-explore/mlx-lm](https://github.com/ml-explore/mlx-lm).
- **Latest verified:** MLX-LM v0.31.3 (2026-04-22); installed isolated MLX-LM
  0.31.3 with MLX 0.32.0.
- **Licence:** MIT.
- **Apple Silicon:** purpose-built for Apple silicon unified memory.
- **8 GB feasibility:** yes with
  `mlx-community/Qwen2.5-1.5B-Instruct-4bit` (840 MiB local cache).
- **Installation:** isolated Python 3.12 virtual environment; no global
  Python packages and no service.
- **Security:** Hugging Face model downloads are supply-chain inputs; remote
  code is not trusted/enabled.
- **Maintenance:** active.
- **Architecture overlap:** inference runtime only; no SaathiOS provider
  installed because the benchmark did not justify replacing Ollama.
- **Decision:** **BENCHMARK_ONLY**.

### llama.cpp

- **Official source:** [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp)
- **Latest verified upstream release:** b10199 (2026-07-30); Homebrew stable
  installed b10180/commit `11b068d06`.
- **Licence:** MIT.
- **Apple Silicon:** native arm64 and Metal.
- **8 GB feasibility:** yes for the existing Qwen2.5 1.5B GGUF; peak measured
  process footprint was about 1.94 GB.
- **Installation:** Homebrew formula; benchmark reuses the existing Ollama
  blob read-only.
- **Security:** raw CLI lacks SaathiOS routing, permission, audit, and service
  controls; it must not be called from business logic.
- **Maintenance:** active.
- **Architecture overlap:** low at runtime level, but exposing another server
  would duplicate the established Ollama boundary.
- **Decision:** **BENCHMARK_ONLY**.

### OpenJarvis

- **Official source:** [open-jarvis/OpenJarvis](https://github.com/open-jarvis/OpenJarvis)
- **Latest verified release:** `desktop-v1.0.2` (2026-05-25).
- **Licence:** Apache-2.0.
- **Apple Silicon:** project documents macOS/Apple Silicon support.
- **8 GB feasibility:** its local-runtime concepts can be feasible with small
  models, but the full desktop/agent stack is unnecessary.
- **Installation:** not installed.
- **Security:** it includes its own agents, memory, scheduler, routing, and
  desktop execution surfaces.
- **Maintenance:** active.
- **Architecture overlap:** direct duplication of ExecutionGateway, missions,
  model routing, memory, scheduling, and audit responsibilities.
- **Decision:** **ADAPT_CONCEPT** — follow existing ADR; do not run it as a
  parallel control plane.

## Model candidate

### Qwen2.5-1.5B-Instruct

- **Official source:** [Qwen/Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct).
- **Verified variants:** existing Ollama Q4_K_M GGUF and
  [MLX 4-bit conversion](https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit).
- **Licence:** Apache-2.0.
- **Apple Silicon / 8 GB:** yes; measured with all three runtimes.
- **Security:** output can violate policy (the Ollama run failed the
  memory-write decision), so it cannot authorize actions.
- **Decision:** **INTEGRATE** as the existing bounded local model; MLX copy is
  benchmark-only.

## Remote provider candidates

### Kimi K3

- **Official source:** [Moonshot platform model documentation](https://platform.moonshot.ai/docs/guide/kimi-k3).
- **Latest verified model ID:** `kimi-k3`; 1,048,576-token context and native
  vision documented.
- **Licence:** proprietary hosted API terms; no weights are installed.
- **Apple Silicon / 8 GB:** remote-only, therefore client-compatible.
- **Installation:** no SDK required; OpenAI-compatible HTTPS API at the exact
  official `/v1` base URL.
- **Verified price:** cache hit $0.30/M tokens, cache-miss input $3/M, output
  $15/M.
- **Security:** external data transfer, prompt sensitivity, cost, and
  availability risks; default disabled and expensive-model approval required.
- **Maintenance:** current official offering.
- **Architecture overlap:** must use the existing model-provider interface and
  budget/approval boundaries.
- **Decision:** **BENCHMARK_ONLY** — adapter contract tested; no credential was
  present and no live request was made.

### Kimi K2.7 Code

- **Official source:** [Moonshot K2.7 documentation](https://platform.moonshot.ai/docs/guide/kimi-k2-7).
- **Latest verified model ID:** `kimi-k2.7-code`; 262,144-token context.
- **Licence:** proprietary hosted API terms.
- **Apple Silicon / 8 GB:** remote client only.
- **Verified price:** cache hit $0.19/M, cache-miss input $0.95/M, output $4/M.
  The high-speed variant costs twice as much and is not selected.
- **Security/overlap:** same governed external-provider risks as K3.
- **Maintenance:** current; older K2 series is documented for deprecation on
  2026-05-25.
- **Decision:** **BENCHMARK_ONLY** as the lowest-cost verified Kimi coding
  candidate; not an active default.

## Long-horizon workflow candidates

### Microsoft OdysseyBench

- **Source:** [microsoft/OdysseyBench](https://github.com/microsoft/OdysseyBench)
- **Licence / status:** MIT; maintained research repository.
- **Fit:** useful long-horizon memory and office-workflow ideas, but external
  services and benchmark machinery do not fit deterministic offline SaathiOS
  evaluation.
- **Decision:** **ADAPT_CONCEPT**.

### AgencyBench

- **Source:** [HKUDS/AgencyBench](https://github.com/HKUDS/AgencyBench)
- **Licence / status:** MIT; ACL 2026 project.
- **Fit:** 138 long-horizon tasks and roughly 90 tool calls per task are too
  resource- and token-heavy for this 8 GB governed local evaluation.
- **Decision:** **ADAPT_CONCEPT**; do not import framework.

### ALE-Bench and AgentBench

- **Sources:** [microsoft/ALE-Bench](https://github.com/microsoft/ALE-Bench),
  [THUDM/AgentBench](https://github.com/THUDM/AgentBench).
- **Licence / status:** Apache-2.0 for ALE-Bench; AgentBench is established
  research software. Both rely on heavyweight/containerized environments for
  important scenarios.
- **Fit:** unsupported or unnecessary infrastructure for the five SaathiOS
  fixtures.
- **Decision:** **DEFER** framework installation; adapt scoring principles.

## Human-agent collaboration candidates

### HumanAgencyBench

- **Source:** primary paper
  [arXiv:2509.08494](https://arxiv.org/abs/2509.08494).
- **Fit:** agency dimensions inform user-control and correction metrics; it is
  not a drop-in SaathiOS runtime.
- **Decision:** **ADAPT_CONCEPT**.

### Common-ground benchmark

- **Source:** primary paper
  [arXiv:2602.21337](https://arxiv.org/abs/2602.21337).
- **Fit:** informs intent retention and correction acceptance.
- **Decision:** **ADAPT_CONCEPT**.

### ColBench / SWEET-RL

- **Source:** [facebookresearch/colbench](https://github.com/facebookresearch/colbench)
- **Licence / status:** official Meta research repository.
- **Fit:** training/evaluation recipes depend on vLLM and large GPU models,
  which are inappropriate for an 8 GB Apple Silicon Mac.
- **Decision:** **REJECT** runtime installation; adapt only bounded concepts.

## Copyright and provenance candidates

### C2PA

- **Sources:** [C2PA specification](https://spec.c2pa.org/) and
  [contentauth/c2pa-rs](https://github.com/contentauth/c2pa-rs).
- **Latest verified:** specification 2.x; Rust SDK is active, dual
  Apache-2.0/MIT.
- **Apple Silicon:** Rust tooling can support it, but no binary is needed for
  the manifest gate.
- **Fit/security:** strong authenticity/provenance primitive, not proof of
  licence, copyright ownership, or permission. Independent primary research
  also documents high-stakes limitations
  ([arXiv:2601.22925](https://arxiv.org/abs/2601.22925)).
- **Decision:** **ADAPT_CONCEPT**; defer signing SDK until a real publication
  pipeline and key-management design exist.

### Generative-AI IP-infringement and CPDM benchmarks

- **Sources:** [GAI IP Infringement](https://github.com/ZhentingWang/GAI_IP_Infringement)
  and primary [CPDM paper](https://arxiv.org/abs/2403.12052).
- **Fit:** useful similarity-review research, but datasets/models cannot
  establish legal clearance and would add heavyweight dependencies.
- **Decision:** **ADAPT_CONCEPT**; require explicit similarity and human
  review fields instead of importing the frameworks.
