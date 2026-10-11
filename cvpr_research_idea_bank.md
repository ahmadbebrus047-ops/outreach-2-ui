# CVPR Research Idea Bank — Multimodal / VLM
**Compiled:** September 2026 · **Horizon:** ~60 days · **Hardware assumption:** 3× NVIDIA A30 24GB

---

## How to use this document

Seventeen candidate ideas, grouped by the direction they came from. Each entry has a fixed structure so they can be compared directly. Ratings and a decision guide are at the end (§7).

Two things to read before anything else:

- **§1 (saturated areas)** tells you what not to spend 60 days on.
- **§7 (ratings)** is the actual decision tool.

Sections 2–6 are the idea pool. Sections marked *(deep)* have full experimental design; the rest are one-paragraph sketches that would need development before committing.

---

## 1. Saturated areas — avoid unless you have a genuinely orthogonal angle

These were checked against current literature. Entering them head-on means competing with well-resourced groups on their home turf.

| Area | Status | Key prior work |
|---|---|---|
| Visual grounding decay during reasoning | **Named and documented.** Attention to image tokens weakens as reasoning chains extend; relative weight on relevant tokens also declines. CoT shown to degrade spatial reasoning, with reasoning models underperforming their own base models. | ReGround, v1, "More Thinking Less Seeing", FastV, multiple 2025–2026 benchmark papers |
| Understanding–generation gap in unified models | **Claimed and being closed.** Understanding capabilities consistently stronger than generation, with several follow-up methods. | HermesFlow, Janus/Janus-Pro, Show-o, Emu3, plus 2026 self-improvement follow-ups |
| Temporal representation in video LLMs | **Covered from several directions.** Temporal info encoded by video-centric encoders but failing to transfer to the LLM; frame reversal hurts while removing positional encodings does not. | "Tracing the Arrow of Time", "Causality Matters", CircuitProbe, "Linear Mechanisms for Spatiotemporal Reasoning" |
| Continual learning for MLLMs (generic framing) | **Extremely crowded.** A survey analyzing 440 papers; a 2026 VLM-CL survey naming cross-modal feature drift, parameter interference, and zero-shot erosion as the three core failure modes. Established benchmarks (CoIN) and method families (LoRA, MoE-adapters, replay, merging, prompt pools). | 440-paper survey; VLM-CL survey (arXiv 2508.04227); CVPR 2024 MoE-adapters |
| Proposer–solver self-evolution | **Dense lineage, multimodal versions already exist.** | R-Zero, Absolute Zero, Socratic-Zero, SPICE, R-Few; **MM-Zero** and **V-Zero** for the multimodal case |

**Areas with more headroom right now:** pixel-level perception, multi-image binding, cross-model error structure, and the *failure modes* of self-evolution (as opposed to new self-evolution frameworks).

---

## 2. Section A — Ideas derived from the BlackboxNLP judge-bias paper

*These extend the existing line of work. Included for completeness; the main weakness of all three is that they read as NLP papers at a vision venue, which was the original submission's problem.*

### P1. Score fragility: the margin CDF predicts benchmark manipulability *(deep)*

**Hypothesis.** Every discriminative multimodal benchmark (POPE, AMBER-discriminative, MME yes/no, HallusionBench) resolves to an argmax over two label tokens. Let *m_i = z_yes − z_no* be the per-item margin with empirical CDF *F*. A prompt manipulation acting as a label prior adds an approximately item-independent bias *b*, so:

> A(b) = P(m + b > 0) = 1 − F(−b),  dA/db = f(−b)

Three consequences:
- **Fragility = density at the boundary.** *f(0)* is a one-shot, free predictor of how far any prompt perturbation moves the score.
- **Rectification falls out of asymmetry in *f*.** Upward swing under +δ = margin mass in (−δ, 0]; downward swing under −δ = mass in (0, +δ]. Inflation-only behaviour ⟺ dense borderline rejects, confident accepts.
- **Fragility is orthogonal to accuracy.** Two models with identical POPE F1 can differ 5× in manipulability.

**Experiment.** 6 small VLMs × 4 binary benchmarks × 10 prompt perturbations (demo label balance at 5 levels, instruction phrasing, option order, negation framing, leniency nudge). Measure *f* once zero-shot, then *predict* A(b) without fitting. Outputs: fragility score per cell; predicted-vs-measured swing correlation; ranking-flip table; mitigation via median-margin decisions or batch calibration.

**Optional representation arm (high payoff).** Linear probe on hidden states predicting ground-truth yes/no. If probe accuracy exceeds output accuracy by 10+ points *and* is invariant to perturbations that move the output 25 points, you've shown perception is intact and only the readout is corrupted.

**Why small VLMs.** Requires logit access (rules out APIs) and many models per GPU-hour. ~150 GPU-hours total.

**Strong result.** r > 0.85 predicted vs. measured on held-out perturbation types; ≥1 *deflation-only* cell (proves it's geometry, not a universal law); ≥3 ranking reversals on a cited benchmark; near-zero fragility/accuracy correlation.

**Biggest risk.** "The bias isn't item-independent." Measure per-item Δm variance; if structured, report it as a finding. Secondary: "prompt sensitivity is known" — differentiator is *prediction from a free measurement*.

---

### P2. Few-shot prompting buys format, not perception

**Hypothesis.** As *k* grows, VideoQA benchmark accuracy rises while reliance on the *query* video falls. Define visual reliance VR(k) = A_k(true frames) − A_k(mismatched frames). Prediction: A_k ↑ while VR(k) ↓, and the judge-scored/human-scored gap widens with *k*.

**Novelty risk — significant.** Text-dominance in multimodal ICL is established (demo images can be removed or blanked with little loss). Differentiators must be stated in the abstract: (1) grounding measured on the **query**, not the context; (2) video; (3) the evaluation coupling — the metric reporting the gain is blind to the loss.

**Experiment.** k ∈ {0,1,2,4,8} × 5 exemplar draws × ablation ladder (true / shuffled / different-video / black / single frame). Plus exemplar-content corruption (correct vs. wrong vs. empty answers), attention mass to video tokens, and gain decomposition ΔA_judge = ΔA_human + Δ_format.

**Strong result.** Two crossing curves: reported accuracy climbing with *k*, visual reliance falling. Headline: "at k=8, 70% of the reported gain survives replacing the query video."

**Biggest risk.** The effect may not exist at usable magnitude; few-shot was *below* zero-shot on MSVD-QA in the source paper. Run a 2-day pilot before committing.

---

### P3. Prompt-side benchmark forgery in training-free VideoQA

**Hypothesis.** A four-exemplar prompt can be *constructed* to inflate a frozen pipeline's reported accuracy 20–30 points with human-verified accuracy flat, and that inflation envelope exceeds the reported gains of most published training-free VideoQA methods.

**Experiment.** Search exemplar sets to maximize (judge acceptance − human acceptance) against a small labelled pool. Three levers: verdict balance, verbosity/format, rubric-boundary cases. Report inflation vs. exemplar budget. Then survey published training-free deltas and overlay the envelope. Defense stack: balanced labels, contextual/batch calibration, margin-median decisions, 100-item human spot-check.

**Strong result.** 25-point forgery; ~60% of surveyed published gains inside the envelope; defense removing 80% for <1% of eval cost.

**Biggest risk.** "This is an attack paper." Defuse by showing the *naive* protocol already lands in the inflating regime (demos are usually chosen as illustrative good cases, so predominantly accept-labelled). Survey component is labor-intensive and subjective — pre-register inclusion criteria.

---

## 3. Section B — Fresh vision-centric ideas

### F1. The resolution attack: VLM perception is not monotone in image information *(deep)*

**Hypothesis.** Modern VLMs use dynamic-resolution tiling (AnyRes, NaViT-style, Qwen native-resolution ViT). Three claims:
1. **Non-monotonicity.** Accuracy vs. input resolution has interior maxima — more pixels of the same image can hurt, because resolution changes tile count and therefore token layout. Behaviour is a function of layout, not just information content.
2. **Adversarial resizing.** A search over resize factors in a semantically null range (0.7×–1.6×, no crop) flips a large fraction of correct answers. Zero pixel-space perturbation budget, one-line implementation.
3. **Confidence decoupled from information.** Sweep a controlled information axis (resolution, blur σ, JPEG Q, occlusion). Accuracy falls toward the dataset answer prior while confidence stays flat.

**Why novel.** VLM adversarial robustness is almost entirely pixel perturbations and typographic attacks. Resizing is in nobody's threat model because it is semantically null — yet it fires constantly in deployment, since every real pipeline resizes. The vulnerability lives in *tokenization geometry*, not pixels.

**Experiment.**
- *Models (6–8):* Qwen2.5-VL-3B/7B, LLaVA-OneVision-0.5B/7B, InternVL2.5-2B, SmolVLM-2B, Idefics3-8B, plus **LLaVA-1.5-7B @336px as fixed-resolution control** (essential — if the effect vanishes there, the cause is localized to dynamic tiling).
- *Benchmarks:* TextVQA or DocVQA (fine detail), CV-Bench or BLINK (spatial), VQAv2 subset (coarse negative control).
- *Sweep:* 20 resize factors per image spanning 1–4 tile-count changes. Log accuracy, answer identity, answer-token probability.
- *Measurements:* flip rate; adversarial flip rate; **tile-boundary alignment** (do flips cluster at tile-count increments? — this is the mechanism figure); information–response curves with the answer-prior floor drawn in.
- *Human reference (optional, powerful):* 100 items × 5 degradation levels × 3 annotators, allowed to answer "can't tell." Human accuracy should track information and abstention should rise.
- *The fix (required for acceptance):* multi-resolution self-consistency — modal answer over 3–5 resolutions, with cross-resolution agreement as a confidence signal. Expect +2–5 points accuracy and a large selective-prediction AUROC gain.

**Why small VLMs.** The tiling mechanism is identical at 2B and 72B. 20 resolutions × many models is a 20× inference multiplier, only affordable below 8B. Include a 2B/7B same-family pair to pre-empt "it goes away at scale."

**Strong result.** 20%+ adversarial flip rate; flips concentrated at tile transitions with the fixed-resolution control much flatter; confidence flat while accuracy falls to the prior on three independent axes; agreement-based abstention beating token confidence. **Takeaway:** *reported VLM accuracy is conditional on an unreported preprocessing choice, and models cannot tell when they have stopped seeing.*

**Biggest risk.** "Models aren't resolution-robust — known." Defense is the tile-boundary mechanism plus the fixed-resolution control; run it in week two, not week eight. Secondary: "flips are borderline noise" — counter by restricting flip rate to items answered with high confidence at native resolution.

**60-day plan.**

| Days | Work |
|---|---|
| 1–4 | Harness; reproduce each model's published number within 1 point at default preprocessing |
| 5–9 | Pilot: 2 models, 1 benchmark, 20 resolutions, 1k items. **Go/no-go if flip rate <8%** |
| 10–20 | Full sweep, all models × 3 benchmarks |
| 21–27 | Tile-boundary analysis + fixed-resolution control → mechanism figure |
| 28–36 | Degradation axes (blur, JPEG, occlusion) with confidence logging |
| 37–43 | Human reference study |
| 44–50 | Multi-resolution self-consistency + selective prediction |
| 51–56 | Scale check (2B vs 7B same family), ablations |
| 57–60 | Writing, figures, release |

---

### F2. Universal blind spots: error correlation grows with capability *(deep)*

**Hypothesis.** Across ~20 architecturally diverse VLMs, chance-corrected error-set overlap **increases** with pair mean accuracy. As models improve, the errors that remain are increasingly the *same* errors. Consequences: the residual on saturating benchmarks is shared structure, not noise; ensembling gains decline faster than accuracy gains; judge protocols using one model to grade another are increasingly correlated with what they grade.

**Second claim (what makes it a CVPR paper).** The universal error set is predictable from **model-free** image properties — object scale in pixels, clutter/entropy, answer-entity rarity in public caption corpora, negation/counting in the question. Identifying likely-universal failures without running any model is both a usable artifact and a claim about what visual structure sits outside current coverage.

**Novelty.** Convergence has been argued for *representations* (Platonic Representation Hypothesis). That *failures* converge, and that convergence rises with capability, is a different and more consequential statement, not established for VLMs.

**Experiment.**
- *Models:* 20 VLMs, 0.5B–8B, maximizing diversity across vision encoder (SigLIP/CLIP/native ViT/Mamba), connector (MLP/Q-Former/perceiver/token-merging), and corpus lineage. Diversity is the independent variable — document it.
- *Data:* 4–5 benchmarks including one near-saturated (VQAv2) and several far from it (BLINK, MMVP, CV-Bench).
- *Analysis:* pairwise chance-corrected overlap vs. pair mean accuracy, against a **permutation null** where each model's errors are randomly assigned at its own accuracy; universal error set (failed by ≥90% of models); ensemble-gain curve vs. k for low- and high-accuracy pools; feature-based predictor with held-out AUROC and feature importances; a qualitative panel of universal-error images (reviewers look at this first).

**Why small VLMs.** You need *many* models, not big ones. Forward passes only, no training. Scale works against you — fewer distinct large models, less independent lineages.

**Strong result.** Positive slope surviving the permutation null and surviving the non-saturated benchmarks; a named, released, characterized error set with an interpretable profile; model-free prediction at AUROC > 0.75; ensemble-gain collapse. **Takeaway:** *the visual competence of open VLMs is converging, and what it converges around is a stable, describable set of things none of them see.*

**Biggest risk.** **"Overlap must rise with accuracy for arithmetic reasons."** Half-right and paper-killing if unaddressed — two models at 95% can overlap in at most 5% of items. Requires chance-corrected measure, permutation null, explicit treatment in the abstract, and survival within accuracy-matched bands. **Run this on day 5, on pilot data.** Secondary: "universal errors are just label noise" — audit 300 items with two annotators by day 20.

**60-day plan.** Days 1–6 harness + 20-model inference on one benchmark. 7–12 pilot correlation + permutation null (**go/no-go**). 13–22 full grid. 23–30 universal error set + label-noise audit. 31–40 predictor and interpretation. 41–48 ensemble curves + judge-correlation section. 49–55 qualitative figure + release. 56–60 writing.

---

### F3. Multi-image source amnesia *(deep)*

**Hypothesis.** Given N images and a question requiring knowledge of *which* image a property came from, decompose errors into **content errors** (property never perceived) and **source errors** (perceived correctly, attributed to the wrong image). Claim: source errors dominate and grow steeply with N while content errors stay flat; the knee sits at a small N (3–5) that is **invariant to model scale and to tokens-per-image**. Invariance implies an architectural binding limit, not a resource constraint.

**Second claim.** Source errors are systematically biased: attributes migrate toward first and last images (visual primacy/recency) and toward the image most visually similar to the query description.

**Novelty.** Multi-image benchmarks (BLINK, Mantis-Eval, MuirBench) report aggregate accuracy. The content/source decomposition separates "can't see" from "can't remember where" — everyone currently attributes multi-image failure to the former.

**Experiment.**
- Synthetic controlled bundles (Blender/Kubric, or COCO-crop composites) where exactly one image carries the queried property.
- Accuracy vs. N ∈ {2,3,4,5,6,8,12}.
- **Content probe:** ask each image *in isolation*. A source error = isolated answer correct, bundle attribution wrong. Cheap and decisive.
- Position bias (mis-attributed index vs. true index); similarity bias (mis-attribution vs. CLIP similarity of distractors).
- **Invariance checks:** 2B vs. 7B same family; full vs. halved tokens-per-image; with and without explicit "Image 1:" indexing. If explicit labels don't fix it, that's a strong result.
- Real-data replication on BLINK/Mantis-Eval. Agent extension on GUI or embodied trajectories.

**Why small VLMs.** N up to 12 is token-expensive; small models make the sweep possible at all. The central claim is an invariance claim, needing a 2B/7B comparison, not a frontier model.

**Strong result.** Source errors 3–5× content errors at N=6; same knee at 0.5B and 7B; explicit indexing failing; clean primacy/recency signature; real-benchmark replication; a cheap mitigation (per-image summarization or query-then-aggregate) recovering most of the gap.

**Biggest risk.** **"This is just long-context degradation."** Must dissociate: hold total image tokens constant while varying N (many low-token images vs. few high-token images). If the knee tracks N rather than token count, it's a binding limit. Design this in from day one — it is the difference between acceptance and rejection. Secondary: synthetic data smells like a toy, hence the mandatory real replication.

**60-day plan.** Days 1–7 generator + validate N=1 near ceiling. 8–15 N-sweep + isolated content probe, 5 models. 16–22 **token-budget dissociation (critical control)**. 23–30 position/similarity bias. 31–38 indexing and prompting ablations. 39–46 real-benchmark replication. 47–53 mitigation. 54–60 writing.

---

### F4. Perspective-taking is absent and unpromptable

Render controlled scenes; ask spatial questions from the camera's viewpoint vs. an in-scene object's viewpoint. Hypothesis: models silently answer egocentrically regardless of framing, and neither CoT, few-shot, nor explicit instruction moves them. Cheap with Blender/Kubric. Partially covered by 3DSRBench and spatial-cognition papers, so the **"unpromptable"** part has to carry the paper.

### F5. The aspect-ratio prior in text-to-image models

Small T2I models (SD-Turbo, SDXL-Lightning, Pixart-Σ) produce systematically different **content**, not just framing, as a function of requested aspect ratio: a 16:9 "a dog" is a different dog in a different context than a 1:1 "a dog." If content shifts predictably with a parameter users think is purely geometric, that's clean, visual, and quotable. Very cheap. Risk: the effect may be small, and reviewers may call it a dataset-statistics observation.

### F6. Binding failure is shared between understanding and generation via the text encoder

Show that the attribute pairs a T2I model swaps are the pairs a discriminative VLM cannot verify, and trace both to shared text-encoder geometry. Attractive but partly implied by the CLIP bag-of-words literature.

### F7. Counting obeys Weber's law then collapses to a frequency prior

Measure the psychometric function of VLM counting against controlled set sizes; pair with a probe testing whether the count is linearly decodable above output accuracy. Nice cognitive framing, but counting papers are common and reviewers are jaded.

### F8. Agent state confusion across screenshots

The applied version of F3: VLM agents given a history of screenshots misattribute objects across timesteps. Best used as a downstream section of F3 rather than as its own paper.

---

## 4. Section C — Continual learning in VLMs

> **Framing warning.** "Continual learning for small VLMs" as a topic is close to unpublishable at CVPR right now (see §1). All three ideas below work by attacking a *specific* question inside the area, not the area itself.
>
> **On building a model from scratch:** don't. On 3× A30 24GB you could pretrain 100M–300M params on a few billion tokens, far below the capability floor where interesting multimodal behaviour exists. Every finding would be answered with "artifact of an undertrained model." From-scratch training only pays when the *architecture* is the contribution. Use pretrained 0.5–3B models instead. **SmolVLM's 256M → 500M → 2.2B ladder inside one family is a research asset almost nobody uses.**

### C1. Does RL's Razor survive contact with the visual pathway? *(deep)*

**Background.** RL's Razor (MIT Improbable AI, Sept 2025, arXiv 2509.04259): at matched new-task accuracy, RL forgets less than SFT, and the degree of forgetting is determined by the KL divergence between fine-tuned and base policy on the new task, because on-policy updates are implicitly biased toward KL-minimal solutions while SFT can converge arbitrarily far from base. Validated on LLMs and robotic foundation models — **not on VLMs.**

**Hypothesis.** RL's Razor is a law about a policy over *output tokens*. In a VLM the output policy is text, but what breaks during adaptation is also the alignment between vision encoder output and LLM input space. A VLM can preserve its text policy almost exactly while visual capability collapses, because the connector drifted — and token-level KL would not see it.

> **In VLMs, text-policy KL predicts linguistic forgetting but systematically underestimates visual forgetting. RL's Razor holds for one modality and fails for the other, with the residual explained by a measurable cross-modal drift term.**

**Secondary prediction (possibly the more surprising one).** RL's protective effect should be **pathway-dependent**: RL on the LLM preserves vision well; RL on the connector does not, because the connector's output is not something the policy samples from, so the on-policy KL argument never reaches it.

**Quantities.**
- *D_text* = KL(π_θ ‖ π_0) over output tokens on the new task — RL's Razor's predictor.
- *D_vis* = drift between connector outputs / joint image-token representations on held-out images.
- *F_lang*, *F_vis* = forgetting on language-only and perception-heavy probes.

Predictions: D_text predicts F_lang well (replication); D_text predicts F_vis poorly; D_vis closes the gap; RL's advantage is smaller on the visual axis.

**Experiment.**
- *Models:* Qwen2.5-VL-3B, SmolVLM-2.2B, LLaVA-OneVision-0.5B.
- *New tasks:* rule-based verifiable rewards only — counting (exact match), referring-expression grounding (IoU), chart/doc QA (exact match), spatial relation QA. No reward model.
- ***Critical control: matched new-task accuracy.*** Train SFT and RL to several checkpoints each and interpolate matched-accuracy pairs. This doubles the run count and is the whole experiment.
- *Probes:* language-only (MMLU subset, GSM8K), vision-heavy (POPE, CV-Bench, BLINK, MMVP), cross-modal alignment (image-text retrieval using the model's own representations).
- *Per checkpoint:* D_text, D_vis, all forgetting metrics, per-module weight-change norms (vision encoder / connector / LLM).
- *Parameter-scope ablation:* LoRA on LLM only / connector only / both / full connector fine-tune, crossed with RL vs. SFT (2×4 grid).

**Compute reality.** LoRA rank 16–32; vLLM for rollouts on one GPU, training on the others; TRL GRPO or verl; group size 4–8; short max generation; low training-time image resolution; gradient checkpointing, bf16. Debug on LLaVA-OneVision-0.5B in a day. 0.5B runs ≈ a couple of hours; 3B runs 8–12 hours. 40–60 runs fits **only** if no single run exceeds 12 hours.

**Strong result.** D_text vs. F_lang on a tight line, D_text vs. F_vis a cloud; composite predictor with a large visual coefficient restoring the fit; RL's advantage quantified separately per modality; pathway dependence; a practical recipe with numbers.

**Biggest risks.** (a) RL instability at 0.5–3B with sparse rewards — pick tasks where the base model is already at 20–40%; test day 3, not day 30. (b) "Just a replication in a new domain" — defense is the modality split and the pathway result; decide by day 25 whether the break exists. (c) Matched-accuracy comparison is fiddly and reviewers will attack any mismatch.

**60-day plan.**

| Days | Work |
|---|---|
| 1–4 | SFT + GRPO end-to-end on LLaVA-OneVision-0.5B, one task |
| 5–8 | Reward-viability check, 4 tasks × 3 models; pick 2 tasks |
| 9–14 | Eval harness: all probes, D_text, D_vis, per-module deltas, automated per checkpoint |
| 15–28 | Main grid: 3 models × 2 tasks × {SFT, RL} × checkpoints for accuracy matching |
| 29–34 | Analysis. **Go/no-go on the modality break** |
| 35–45 | Pathway ablation (2×4) |
| 46–52 | Sequential 3-task stream + replay baseline (makes it genuinely continual) |
| 53–60 | Writing, figures, release |

### C2. Label-free continual RL via invariance rewards

The adaptation stream is unlabeled images; the reward is self-consistency across semantically null transformations (resize, crop, flip, frame subsampling). No labels, no teacher, fully continual. **The hypothesis worth testing is the deflationary one:** the model becomes more *consistent* without becoming more *accurate*, converging to confident agreement on wrong answers. Either branch publishes, and the negative branch is more interesting. Shares infrastructure with F1.

### C3. The accumulation audit

Run a task stream through small VLMs under five published CL methods and ask whether **anything transfers forward**. Hypothesis: forward transfer is near zero or negative; all reported gains are recency plus reduced forgetting; and a trivial retrieval baseline (keep raw examples, retrieve k-nearest at inference, no weight updates) matches or beats every gradient method at small data scales. Needs the crossover analysis — *at what data volume does weight updating finally beat retrieval?* — to avoid reading as pure critique.

---

## 5. Section D — Self-evolution, multi-agent, and "learning to learn"

### Feasibility verdict on the general vision

| Component | Verdict |
|---|---|
| Adapter/LoRA as the only updated block | Trivially possible, but that's PEFT, not a contribution |
| A learned module that *outputs weight updates* (hypernetwork / learned optimizer) | Real research, but needs enormous meta-training to beat Adam and famously fails to generalize. **Will not work in 60 days on this hardware.** |
| A learned controller deciding *whether, when, and how* to adapt per example | **Possible, novel, interesting.** The honest version of the intuition → S2 |
| Multiple agents pushing each other to evolve | Mechanically possible, already done. The machinery isn't the hard part — the information is |
| "Finding loopholes in itself" | Possible, but only with access to a signal the model can't already produce. Otherwise the model's idea of its weakness is exactly as wrong as the weakness |
| "Think like a human" | A motivation, not a research target. Keep it as why you care, not as a claim |

### The framing that determines whether any of this works

Self-improvement can only draw from one of three sources. State which one in the abstract; papers that can't are the ones that get rejected.

1. **Compute-for-search.** The answer is already latent; search surfaces it and training distills it back. Real, but bounded. Most "self-improvement" gains are this.
2. **A free verifier.** Math and code have one: execution. This is *why* the self-evolution literature is almost entirely math and code.
3. **An external oracle or physical structure.** A tool, simulator, renderer, second sensor, known geometry.

Now re-read the multimodal papers with that lens: MM-Zero has its Coder *render* the images, so the generating code is the ground truth. V-Zero reports gains on visual *mathematical* reasoning. Neither creates verified supervision about a real photograph. And R-Zero's own paper reports pseudo-label accuracy falling from 79% to 63% by iteration three as the curriculum hardens, which it calls a critical trade-off and potential bottleneck.

**That gap is the paper.**

---

### S1. The Verifier Gap *(deep — recommended)*

**Claim.** *Multimodal self-evolution improves reasoning-over-perception but cannot improve perception itself, because vision has no free verifier. Every reported gain in this literature decomposes into the reasoning component; the perception component is flat or negative.*

This explains in one stroke why every multimodal self-evolution paper evaluates on visual math rather than perception benchmarks. Nobody has said it out loud, and it is checkable.

**Why it's strong.** It is a discovery about a whole research program, not a tweak to one method. Negative-but-constructive, which reviewers respect when the measurement is clean. Vision-centric by construction: the ceiling exists *because of a fact about the modality*. And it rewards care rather than scale, which is exactly the asymmetry a small lab should exploit.

**Experiment.**
1. **Reproduce two published loops at small scale** — a V-Zero-style questioner–solver on unlabeled images, and a simplified MM-Zero-style rendered-image loop — with Qwen2.5-VL-3B and LLaVA-OneVision-0.5B. You need the dynamics, not their numbers.
2. **Decompose the gains, which they don't do.**
   - *Perception axis:* direct-readout benchmarks (POPE, MMVP, CV-Bench, counting, OCR). No multi-step reasoning.
   - *Reasoning axis:* MathVista, visual math, multi-hop VQA.
   - ***Oracle-perception control (decisive).*** Supply ground-truth perceptual facts as text ("there are 4 chairs; the mug is left of the laptop") and re-run the reasoning benchmarks. If self-evolution gains persist under oracle perception, the gain lives entirely in the reasoning layer. This single control does most of the work.
3. **Track verifier decay directly.** Per iteration, human- or tool-label a sample of self-generated QA pairs and measure pseudo-label accuracy. Prediction: in vision it starts lower than R-Zero's 79% and decays faster, because nothing in the loop executes.
4. **Curriculum drift analysis.** Embed self-generated questions and track the distribution across iterations. Prediction: the proposer drifts toward question types where its own pseudo-labels are easy — which are exactly the ones requiring no perception. **Show that the fraction of generated questions that actually require looking at the image declines monotonically.** That figure alone is the paper's most-shared image.
5. **Constructive half — lift the ceiling.** Give the proposer tools the solver lacks (SAM for counting/spatial, Depth-Anything for ordering, an OCR engine for text). Now it can generate *verified* perceptual questions about real photographs. If perception gains appear only in this condition, the mechanism is proven: **the bottleneck is the verifier, not the algorithm.**

**Why small VLMs.** Many short instrumented runs, not one big run. 0.5B and 3B with LoRA + GRPO, group size 4–8, short answers. Frozen off-the-shelf tools run in a few GB.

**Biggest risks.** (a) "Strawman / reproductions too small" — reproduce the *directional* result before claiming anything; say plainly you're studying dynamics. If gains don't reproduce at 3B, the paper dies, so test by day 15. (b) The oracle arm read as "just distillation from specialist models" — pre-empt by testing whether the solver beats the tools *in composition* and whether gains transfer to tasks the tools can't do.

---

### S2. A controller that learns *when* to learn

**Claim.** Attach a small policy network (10–50M params) that observes each incoming example plus features (base-model uncertainty, disagreement across augmented views, retrieval distance to stored examples, per-module gradient norms) and emits one action: **ignore / store in memory / gradient step / gradient step + consolidate.** Train with RL where reward = improvement on a held-out probe minus forgetting on a retention probe.

This is a block attached to a frozen pretrained VLM that learns how to adapt — the intuition, scoped to something trainable in 60 days.

**Why interesting rather than plumbing.** The scientific content is *what the controller learns*, not the system. Extract and characterize the policy. Predicted surprise: **the learned policy is non-monotone in uncertainty** — it updates on medium-surprise examples and refuses on the most surprising ones, having learned that maximal surprise usually means a broken or out-of-distribution example rather than a learning opportunity.

**Second finding worth hunting:** does the policy **transfer**? Train on stream A, freeze, apply to unseen tasks. Beating hand-designed heuristics on unseen tasks shows "when to learn" is a learnable, transferable skill separable from "what to learn."

**Baselines you must beat — this list is the whole ballgame.** Update-on-everything; update-on-random-k%; **update-on-high-uncertainty**; update-on-high-loss; pure retrieval with no updates. If you don't beat update-on-high-uncertainty, you have nothing. Test that comparison in the first two weeks.

**Biggest risk.** The controller converges to something trivial (always update, or a simple threshold) and the contribution evaporates. This is the *most likely* outcome. Design for it — a trivial policy is still reportable as "when-to-learn is not learnable beyond a threshold rule," but it's a much weaker paper. Decide by day 25.

---

### S3. Asymmetric-information co-evolution

Build the co-evolution loop with **asymmetric information** as the differentiator: the Proposer has tool access (depth, segmentation, OCR, geometry) that the Solver does not. It can therefore generate unlimited *verified* questions about real images, rewarded for finding questions the Solver gets wrong while the tools get right. This is a rigorous version of "finding the loopholes in itself," because the loophole detector has genuine external information rather than the model's own opinion of itself.

**The interesting question inside it:** does the Solver internalize a capability the tools have, or only imitate their output format? Test on compositions the tools cannot do.

**Ranking caveat.** Competes directly with MM-Zero and V-Zero, and competing on framework quality is competing on compute. Note that **S1's constructive half is this system** — same code, evaluated as science rather than sold as a method, which is the better paper.

---

## 6. Cross-cutting notes

### 6.1 The gauntlet every self-improvement paper must survive

Write these on a wall before starting:

1. **Random curriculum baseline.** Replace the clever proposer with random question generation at matched volume. An alarming number of self-improvement gains vanish here.
2. **Matched-compute baseline.** Spend the same GPU-hours on plain RL against existing labeled data. If that wins, the loop is a worse use of compute.
3. **Multiple seeds.** Self-evolution runs are high variance. Three minimum, report the spread.
4. **Where did the information come from?** Answer in the abstract.

### 6.2 Generic acceptance heuristics for CVPR

- Reviewers reward **analysis + a method that improves something**. Pure phenomenon papers can get in but need a big phenomenon.
- The **qualitative figure** gets looked at before the text. Budget real time for it.
- **Reproduce published numbers first.** Verifying you match a model's reported benchmark score at default settings catches roughly half of all harness bugs and buys enormous credibility.
- Every deep-dive plan above has a **hard go/no-go inside the first two weeks.** Respect them.

### 6.3 Shared infrastructure

- **F1 + F3** share a unified multi-model inference harness with preprocessing control and per-item logging. Build it in week one, run both pilots in week two, commit to whichever returns the larger effect. Cost: nine days. Buys a real choice instead of a guess.
- **F1 + C2** share the invariance-transformation machinery.
- **S1 + S3** are the same codebase with different framing.
- **F2** needs only the multi-model harness, so it's a cheap fallback from F1.

---

## 7. Ratings

### 7.1 Metric definitions

| Metric | Meaning | Scale |
|---|---|---|
| **Novelty** | Crowding-adjusted. How much clear space is left after the literature check | 1–5 |
| **Feasibility** | Realistically completable to submission quality in ~60 days | 1–5 |
| **Compute fit** | Fits 3× A30 24GB comfortably (5) vs. painfully (1) | 1–5 |
| **CVPR fit** | Is the contribution vision-centric, or does it read as an NLP paper | 1–5 |
| **Impact ceiling** | How big the result is if everything works | 1–5 |
| **Acceptance safety** | Inverse of "one obvious objection kills it" | 1–5 |
| **Downside protection** | Does a null/negative result still yield a paper | 1–5 |
| **Total** | Sum, max 35 | — |

### 7.2 Full rating table

| ID | Idea | Novelty | Feasibility | Compute fit | CVPR fit | Impact ceiling | Acceptance safety | Downside protection | **Total** |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **F1** | Resolution attack | 4 | 5 | 5 | 5 | 4 | 4 | 4 | **31** |
| **F2** | Universal blind spots | 4 | 4 | 5 | 4 | 5 | 3 | 4 | **29** |
| **F3** | Multi-image source amnesia | 5 | 4 | 4 | 4 | 5 | 3 | 3 | **28** |
| **P1** | Score fragility / margin CDF | 4 | 5 | 5 | 2 | 5 | 3 | 4 | **28** |
| **S1** | The Verifier Gap | 5 | 3 | 2 | 4 | 5 | 3 | 4 | **26** |
| **F5** | T2I aspect-ratio prior | 4 | 5 | 5 | 4 | 3 | 2 | 2 | **25** |
| **C1** | RL's Razor in VLMs | 4 | 3 | 2 | 4 | 4 | 4 | 4 | **25** |
| **F4** | Perspective-taking unpromptable | 3 | 4 | 4 | 4 | 3 | 3 | 3 | **24** |
| **F6** | Shared binding failure | 2 | 4 | 5 | 4 | 3 | 3 | 3 | **24** |
| **C2** | Invariance-reward continual RL | 4 | 3 | 2 | 4 | 4 | 2 | 4 | **23** |
| **F7** | Counting psychometrics | 2 | 5 | 5 | 3 | 2 | 2 | 3 | **22** |
| **F8** | Agent state confusion | 3 | 3 | 4 | 3 | 3 | 3 | 3 | **22** |
| **P2** | Format not perception | 2 | 3 | 4 | 4 | 4 | 2 | 3 | **22** |
| **C3** | Accumulation audit | 3 | 4 | 3 | 3 | 3 | 2 | 3 | **21** |
| **P3** | Benchmark forgery | 3 | 3 | 4 | 2 | 3 | 2 | 3 | **20** |
| **S2** | Learned "when to learn" controller | 4 | 2 | 3 | 3 | 3 | 2 | 2 | **19** |
| **S3** | Asymmetric co-evolution | 3 | 2 | 2 | 4 | 4 | 2 | 2 | **19** |

### 7.3 Winners by individual metric

| Metric | Winner | Runner-up |
|---|---|---|
| **Most novel** | F3 Source amnesia · S1 Verifier Gap (tie, 5) | F1, F2, P1, C1, C2, S2 (4) |
| **Most feasible in 60 days** | F1 Resolution · F5 Aspect ratio · F7 Counting · P1 Fragility (tie, 5) | F2, F3, F4, F6, C3 (4) |
| **Best compute fit** | F1, F2, F5, F6, F7, P1 (tie, 5) | F3, F4, F8, P2, P3 (4) |
| **Best CVPR fit** | F1 Resolution (5) | F2, F3, F4, F5, F6, S1, S3, C1, C2, P2 (4) |
| **Highest impact ceiling** | F2 Blind spots · F3 Source amnesia · P1 Fragility · S1 Verifier Gap (tie, 5) | F1, C1, C2, S3, P2 (4) |
| **Safest bet (acceptance)** | F1 Resolution · C1 RL's Razor (tie, 4) | F2, F3, F4, F6, F8, S1, P1, C3 (3) |
| **Best downside protection** | F1, F2, P1, S1, C1, C2 (tie, 4) | F3, F4, F6, F7, F8, C3, P2, P3 (3) |
| **Best value per GPU-hour** | F5 Aspect ratio | F1 Resolution |
| **Highest variance (boom or bust)** | F2 Universal blind spots | S1 Verifier Gap |

### 7.4 Decision guide

| If your priority is… | Pick | Why |
|---|---|---|
| **Maximum probability of acceptance** | **F1 — Resolution attack** | Pixels (CVPR-native), trivially reproducible, has a mechanism (tile boundaries), a control (fixed-resolution models), and a practical fix with numbers. Pilot resolves in a week. More "important" than "shocking" |
| **A result people cite for years** | **F2 — Universal blind spots** | Highest ceiling, but the arithmetic objection must be neutralized by day 5 or it's fatal |
| **Maximum surprise-per-dollar** | **F3 — Source amnesia** | Cognitive-psychology-flavored capacity limit, cleanest story arc. Risk: could be long-context decay in costume |
| **To pursue the self-evolution / multi-agent instinct** | **S1 — Verifier Gap** | Keeps the co-evolution interest, but competes on care rather than compute. Turns the skeptical reviewer into an ally |
| **To pursue continual learning specifically** | **C1 — RL's Razor in VLMs** | The one open wedge in a saturated field; both outcomes publish; tightest compute |
| **Fastest possible pilot signal** | **F5 — Aspect-ratio prior** | Days of compute, not weeks. Weak as a standalone paper but a good week-one probe |
| **To hedge** | Build the multi-model harness (week 1) → pilot **F1 and F3** (week 2) → commit | Costs 9 days, buys a real choice instead of a guess |

### 7.5 Overall recommendation

**Primary: F1 (Resolution attack).** Best expected value: highest total, best CVPR fit, best acceptance safety among high-scoring options, and the pilot is decisive within nine days.

**If the F1 pilot fails (flip rate <8%): F2 (Universal blind spots)** — shares the harness, so the pivot costs almost nothing.

**If the self-evolution direction is non-negotiable: S1 (Verifier Gap).** Same intellectual territory the co-evolution instinct was reaching for, but structured so that limited compute is an advantage rather than a handicap.

---

## 8. Week-one checklist (applies to every path)

- [ ] Verify the CVPR deadline and the exact submission date; recount the 60 days against it
- [ ] Build the unified multi-model inference harness with preprocessing control and per-item logging
- [ ] Reproduce at least one published benchmark number per model at default settings, within 1 point
- [ ] Run the pilot for the two top candidates in parallel
- [ ] Write the killer objection for your chosen idea at the top of the repo README, and schedule the experiment that answers it before day 25
- [ ] If pursuing any RL path: get GRPO running end-to-end on LLaVA-OneVision-0.5B with a rule-based reward before committing to anything else
- [ ] If pursuing S1: read MM-Zero, V-Zero and R-Zero and check whether *any* of them reports a perception benchmark. If none do, the hypothesis gains strong free support in an afternoon
