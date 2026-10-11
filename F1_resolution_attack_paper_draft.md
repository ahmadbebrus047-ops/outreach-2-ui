# The Resolution Attack: VLM Perception Is Not a Monotone Function of Image Information

**Working title options**
- *Seeing More, Knowing Less: Non-Monotone Resolution Response in Vision-Language Models*
- *The Resize Attack: Semantics-Preserving Preprocessing Flips VLM Answers*
- *Tiles, Not Pixels: Layout-Induced Failure in Dynamic-Resolution VLMs*

**Status:** research plan / paper skeleton · **Target:** CVPR · **Budget:** ~60 days, 3× A30 24GB
**Convention:** `[EXPECT: …]` marks a predicted result. `[TBD]` marks a number to be filled from experiments. `[DECISION]` marks a go/no-go gate.

---

## 0. One-paragraph summary

Modern VLMs no longer resize images to a fixed square. They partition them into a variable number of tiles whose count and arrangement depend on the input's pixel dimensions. This makes the model's internal representation of an image a function of a preprocessing parameter that nobody reports, that every deployment pipeline silently sets, and that is semantically meaningless. We show that (i) accuracy as a function of input scale is **non-monotone**, with interior maxima aligned to tile-grid transitions; (ii) **upsampling alone** — an operation that adds no information — flips a substantial fraction of previously correct answers, making it an adversarial operation with an empty perturbation budget; and (iii) model confidence is **decoupled from available visual information**, remaining flat as accuracy decays toward the dataset answer prior under controlled degradation. We localize the cause by contrasting three preprocessing families (fixed-resolution, discrete-grid tiling, continuously-quantized tiling) and propose a cheap fix: cross-resolution agreement, which both recovers accuracy and provides a far better abstention signal than token probability.

---

## 1. Introduction

### 1.1 The shift nobody audited

Until roughly 2023, vision-language models resized every image to a fixed square. LLaVA-1.5 used 336×336. Preprocessing was input-agnostic: the token layout reaching the language model was identical regardless of the source image's dimensions.

That is no longer true. LLaVA-NeXT introduced *AnyRes*, selecting a grid configuration from `{2×2, 1×{2,3,4}, {2,3,4}×1}` and scaling the image to `(336·a) × (336·b)` to yield `n = a·b` local crops plus a global thumbnail, for a total token length of `(1+n)·N`. LLaVA-OneVision generalizes this to `anyres_max_9`. InternVL divides images into a variable number of tiles. Qwen2.5-VL uses naive dynamic resolution, mapping arbitrary input sizes to a variable token count. These designs were introduced to preserve fine detail, and they work: the LLaVA-NeXT release explicitly motivates AnyRes as reducing hallucination that "conjectures imagined visual content when confronted with low-resolution images."

The unexamined consequence is that **the model's visual input is now a discontinuous function of the source image's pixel dimensions**. Resize an image by 15% and a 2×2 grid may become a 2×3 grid: the number of crops changes, the content of each crop changes, the effective resolution inside each crop changes, and the sequence length changes. None of this corresponds to any change in what the image depicts.

### 1.2 Why this should produce non-monotone behavior

There is direct evidence in the literature that the thumbnail and the local crops play *different functional roles*. Analysis of LLaVA-NeXT finds that the global thumbnail alone performs better on holistic perception tasks (ScienceQA, MMBench) while local crops excel on fine-grained tasks (TextVQA, POPE), with the two serving complementary functions as a "comprehensive visual extractor" and a "detailed visual capturer" respectively.

If the thumbnail/crop balance shifts with input scale, and if the two channels are differentially useful per task, then accuracy as a function of scale has no reason to be monotone. It should have structure: plateaus within a grid configuration, and jumps at configuration boundaries. To our knowledge nobody has measured this curve.

### 1.3 Three claims

> **C1 — Non-monotonicity.** For a substantial fraction of items, accuracy as a function of input scale has interior maxima. Feeding a model *more pixels of the same image* reduces accuracy. The response is a function of token *layout*, not of information content.

> **C2 — Adversarial resizing under an empty budget.** Restricting to **upsampling only** (scale ≥ 1.0), which cannot add information, a search over scale factors flips a substantial fraction of correct answers to incorrect. Unlike pixel-space adversarial examples, this requires no optimization, no model access, and no perturbation of content.

> **C3 — Confidence is blind to information.** Sweeping a physically controlled information axis (scale, blur σ, JPEG quality, occlusion fraction), accuracy decays toward the dataset answer prior while model confidence stays approximately flat. The model does not know when it has stopped seeing.

### 1.4 Why C2's upsampling restriction is the paper's load-bearing design choice

The obvious objection to any resolution-robustness result is "you removed information, of course accuracy fell." Restricting the headline attack to **upsampling** eliminates it entirely. Bicubic upsampling of an image adds no visual information; the resulting image is a deterministic, invertible-in-expectation interpolation of the original. Any accuracy change under upsampling is therefore *purely* a layout effect. This turns a robustness observation into a statement about the architecture.

Downsampling is still measured, but as a secondary condition and as the bridge to the information-response curves in C3.

### 1.5 Contributions

1. The first systematic characterization of the **accuracy-vs-scale response curve** for dynamic-resolution VLMs, across three preprocessing families and [8] models.
2. **Upsample-only adversarial resizing**: an answer-flipping operation with an empty perturbation budget, requiring no model access.
3. A **mechanistic localization**: flip events align with tile-grid transitions, and flip rate is ordered `discrete-grid > continuously-quantized > fixed-resolution`, exactly as the tiling hypothesis predicts.
4. An **information–response analysis** showing confidence is approximately invariant to a controlled reduction in available visual evidence, contrasted against a human reference that abstains appropriately.
5. A cheap **mitigation**: cross-resolution self-consistency, which improves accuracy and substantially improves selective-prediction AUROC over token-probability confidence.
6. Public release of the sweep protocol, per-item logs, and a **resolution-fragility score** per model.

---

## 2. Related work

### 2.1 Dynamic-resolution visual encoding

AnyRes-style tiling (LLaVA-NeXT, LLaVA-OneVision), tile-count-variable encoding (InternVL series), and native/naive dynamic resolution (Qwen2-VL, Qwen2.5-VL, NaViT-derived designs) are now standard. HiRes-LLaVA notes that pre-trained visual encoders predominantly reshape images into squares via cropping or padding, which fails on non-square images, and proposes dynamic slicing with a maximum slice count *M*, selecting `m = ⌈H/r⌉`, `n = ⌈W/r⌉` rows and columns against the encoder's base resolution *r*.

**What this literature establishes:** tiling improves average benchmark numbers.
**What it does not ask:** what the response *curve* looks like within a model, or whether the discretization introduces instability.

### 2.2 Resolution as an evaluation variable

The closest work is NativeRes-LLaVA, which states plainly that existing benchmarks "fall short in evaluating VLMs under varied visual conditions, often neglecting resolution as a critical factor," and that the field "lacks a systematic ablation framework for resolution-centric evaluation of dynamic visual encoding strategies, such as aspect ratio sensitivity and adaptability to extreme resolutions."

**This is our gap statement, written by someone else.** Their response is to build a better *training* framework. Ours is to characterize the failure in existing deployed models and explain it.

### 2.3 Adversarial preprocessing and image-scaling attacks

There is a respected security lineage here, which is both our closest relative and our sharpest contrast. Xiao et al. (USENIX Security '19) demonstrated camouflage attacks on image scaling algorithms: an attacker crafts image `A = S + Δ` such that `A` resembles a decoy at full size but becomes an entirely different payload image after downscaling, exploiting which pixels nearest/bilinear/bicubic resampling retains versus discards. Quiring et al. (USENIX Security '20) formalized this as *adversarial preprocessing*; follow-ups cover backdoor injection via scaling, detection (Decamouflage), and RAW-pipeline variants.

**The contrast is total and should be stated in the abstract.** That line of work *crafts pixels* so that a fixed scaling operation yields different content. We craft nothing. The pixels are the dataset's. We change only the *target size*, and the content after resampling is the same scene. Their attack changes the image; ours changes the tiling.

A recent adjacent result exploits AnyRes as a **side channel**: because AnyRes maps aspect ratios to different grid configurations and patch counts, an observer can infer properties of a private image from computational workload. This confirms that the grid discretization is externally visible and exploitable, but targets confidentiality rather than correctness.

### 2.4 Token pruning and the roles of thumbnail vs. crops

Work on inference acceleration for high-resolution LVLMs (FastV, Global Compression Commander, layer-wise token selection) has characterized visual-token redundancy and, importantly for us, the *functional asymmetry* between thumbnail and crops described in §1.2. This literature treats that asymmetry as an opportunity for compression. We treat it as the mechanism of an instability.

### 2.5 VLM calibration, consistency, and selective prediction

VLMs are documented as overconfident; verbalized-uncertainty evaluations and calibration methods (VL-Calibration's decoupling of visual from reasoning confidence, object-level verbalized calibration via semantic perturbation) address it. Consistency-based reliability is an active line: identifying unreliable responses from black-box VLMs via consistency and uncertainty, task-decomposition consistency comparison, and selective prediction with abstention (ReCoVERR / "Selective 'Selective Prediction'"), which also notes that product-of-token-likelihood confidence can severely underestimate confidence due to surface-form competition.

**Our distinction is relational, not magnitude-based.** The existing claim is *confidence is too high*. Our claim is *confidence does not respond to a controlled physical reduction in available evidence* — we report the slope of confidence against an information axis and show it is near zero while accuracy's slope is steep. And our proposed abstention signal, cross-resolution disagreement, is free, requires no training, and exploits the very instability we document.

### 2.6 Novelty risk register (be honest about this in the paper)

| Closest work | Overlap | Our differentiator |
|---|---|---|
| Image-scaling attacks (Xiao '19, Quiring '20) | Both target preprocessing | They perturb pixels; we perturb only the target size. Empty perturbation budget |
| NativeRes-LLaVA | Both say resolution is an unaudited evaluation axis | They fix it by training; we characterize and mechanistically localize the failure in deployed models |
| AnyRes side-channel work | Both exploit grid discretization | Confidentiality vs. correctness |
| Token-pruning analyses | Both study thumbnail/crop asymmetry | They compress; we show the asymmetry produces answer instability |
| VLM calibration literature | Both measure confidence failure | Magnitude vs. *responsiveness to a controlled information axis* |
| Generic robustness-to-corruption (ImageNet-C lineage) | Both perturb inputs | Corruption removes information; upsampling does not. Non-monotonicity is the novel shape |

---

## 3. Preliminaries and formalization

### 3.1 The preprocessing map

Let `I ∈ R^(H×W×3)` be a source image and `s ∈ R⁺` a scale factor. Define `I_s = resize(I, sH, sW; κ)` with kernel `κ ∈ {bicubic, bilinear, nearest, lanczos}`.

A VLM's processor implements a map `Φ: I_s ↦ (G, T)` where `G = (a, b)` is the selected tile grid and `T` the resulting visual token sequence. Three families:

| Family | Behavior of Φ | Examples |
|---|---|---|
| **F-fix** (fixed) | `G` constant; `T` constant length | LLaVA-1.5 (336²), BLIP-2 |
| **F-grid** (discrete grid) | `G` selected from a finite pinpoint set; `\|T\| = (1+ab)·N` jumps discontinuously | LLaVA-NeXT, LLaVA-OneVision (anyres_max_9), InternVL2/2.5 |
| **F-cont** (quantized continuous) | `\|T\|` varies near-continuously, quantized to a patch multiple, clipped at `min_pixels`/`max_pixels` | Qwen2-VL, Qwen2.5-VL, SmolVLM, Idefics3 |

**This taxonomy is the mechanism test.** The tiling hypothesis predicts flip rate ordered `F-grid > F-cont > F-fix`, and predicts that within F-grid the flips *concentrate at grid transitions* rather than being uniformly distributed over `s`.

### 3.2 Definitions

For item `i`, model `m`, and a scale set `S = {s_1, …, s_K}`:

- `y_i(s)` — predicted answer at scale `s`; `y*_i` — ground truth; `c_i(s)` — correctness indicator.
- `p_i(s)` — model confidence (see §4.6 for the definition used).
- **Flip Rate** `FR = (1/n) Σ_i 1[|{y_i(s) : s ∈ S}| > 1]` — fraction of items whose answer is not constant across the sweep.
- **Adversarial Flip Rate** `AFR = P(∃s ∈ S⁺ : ¬c_i(s) | c_i(1))` where `S⁺ = {s ≥ 1}` — the headline number.
- **Recovery Rate** `RR = P(∃s : c_i(s) | ¬c_i(1))` — items fixable by rescaling. `AFR` vs. `RR` symmetry is a noise diagnostic; `RR` also yields the oracle-resolution upper bound.
- **Oracle-scale accuracy** `Acc_oracle = (1/n) Σ_i max_s c_i(s)` — the ceiling the mitigation chases.
- **Resolution Fragility** `ρ_m = FR` restricted to items answered at high confidence at native scale. This is the headline per-model statistic and the noise-objection killer.
- **Transition Alignment** `τ` — mutual information (or a permutation-tested excess rate) between the event "answer flipped between `s_k` and `s_{k+1}`" and the event "grid configuration changed between `s_k` and `s_{k+1}`".

---

## 4. Methodology

### 4.1 Models

Eight models, chosen to populate the taxonomy and to include one within-family scale pair.

| # | Model | Params | Family | Encoder | Notes |
|---|---|---|---|---|---|
| 1 | LLaVA-1.5-7B | 7B | **F-fix** | CLIP-ViT-L/336 | Control. Effect should be near-zero |
| 2 | LLaVA-NeXT-7B | 7B | **F-grid** | CLIP-ViT-L/336 | Canonical AnyRes, grid `{2×2, 1×{2,3,4}, {2,3,4}×1}` |
| 3 | LLaVA-OneVision-0.5B | 0.5B | **F-grid** | SigLIP | anyres_max_9 |
| 4 | LLaVA-OneVision-7B | 7B | **F-grid** | SigLIP | Scale pair with #3 |
| 5 | InternVL2.5-2B | 2B | **F-grid** | InternViT | Different tiling implementation |
| 6 | Qwen2.5-VL-3B | 3B | **F-cont** | Native-res ViT | Naive dynamic resolution |
| 7 | SmolVLM-2.2B | 2.2B | **F-cont** | SigLIP | Small, permissive |
| 8 | Idefics3-8B | 8B | **F-cont/grid** | SigLIP | Upper size bound for 24GB in bf16 |

**Why small models suffice.** The claim concerns the preprocessing map `Φ`, which is *identical code* across sizes within a family. The 0.5B/7B pair (#3/#4) directly pre-empts "it disappears at scale" with evidence rather than assertion. Running eight models at 20 scales each is a 20× inference multiplier that is only affordable below ~8B.

### 4.2 Datasets

| Benchmark | Sample size | Why | Expected effect |
|---|---|---|---|
| **TextVQA** | 1,500 | Fine text detail; maximally crop-dependent | **Large** |
| **DocVQA** (or ChartQA) | 1,000 | Dense small text; extreme detail dependence | **Large** |
| **CV-Bench** (2D+3D) or **BLINK** | 1,500 | Spatial relations; layout-dependent | **Medium** |
| **POPE** (all three splits) | 1,500 | Binary yes/no → clean two-token logits for confidence analysis | **Medium** |
| **MMVP** | 300 (full) | Fine-grained paired items; known-hard | **Medium-large** |
| **VQAv2** subset | 1,500 | Coarse, holistic → **negative control** | **Small** |

The negative control matters as much as the positive cases. A reviewer who sees a large effect everywhere suspects a bug. A predicted-small effect that *is* small on a coarse benchmark is evidence of a real, task-dependent mechanism.

Stratify each sample by source-image resolution and aspect ratio, and record both. Aspect ratio is a covariate that directly determines grid selection, so it must be logged per item.

### 4.3 The scale sweep

**Primary (upsample-only) sweep:** `s ∈ {1.00, 1.05, 1.10, …, 1.95, 2.00}` — 21 points. No information added, no content removed.

**Secondary (full) sweep:** `s ∈ {0.5, 0.6, 0.7, 0.8, 0.9} ∪ primary` — 26 points, used for the information-response analysis and the oracle ceiling.

**Kernel axis:** run the full sweep with bicubic (default); repeat the primary sweep with bilinear and nearest on two models × two benchmarks, to show the effect is not an artifact of one resampling kernel.

**Aspect-preserving:** all resizes preserve aspect ratio. A separate small study varies aspect ratio at constant pixel count, since grid selection depends on aspect ratio; this isolates "shape" from "size."

### 4.4 Pipeline (implementation detail that determines correctness)

```
for model m:
  for benchmark b:
    for item i in sample(b):
      I  ← load_original_image(i)          # NEVER the pre-resized dataset copy
      for s in S:
        I_s ← resize(I, s, kernel=κ)       # our only intervention
        inputs ← m.processor(I_s, prompt_i) # the model's OWN processor runs unmodified
        log:
          grid_config(inputs)              # a, b, tile count
          num_visual_tokens(inputs)
          out ← m.generate(inputs, greedy, seed fixed)
          answer, per-token logprobs, answer-token prob
```

**Five implementation rules that reviewers will check:**

1. **Intervene before the processor, never inside it.** The contribution is that a *legitimate deployment choice* destabilizes the model. Patching the processor would make it an artificial ablation.
2. **Load original images, not benchmark-provided resized copies.** Many benchmark distributions ship pre-resized images; resizing those compounds resampling artifacts.
3. **Greedy decoding, fixed seed, identical prompt.** The only free variable is `s`.
4. **Log the grid configuration and token count at every scale.** Without this there is no mechanism section.
5. **Reproduce each model's published benchmark number at `s = 1.0` to within ~1 point** before running anything else. This catches most harness bugs and is the first thing a reviewer wants to see.

### 4.5 Experiment 1 — The response curve (C1)

Full grid: 8 models × 6 benchmarks × 21 scales.

*Outputs:* per-model per-benchmark accuracy-vs-scale curves; distribution of the number of interior local maxima; `FR`, `AFR`, `RR`, `Acc_oracle`, `ρ_m`.

*Statistics:* McNemar's test on paired native-vs-best-adversarial-scale correctness; bootstrap CIs over items; Benjamini–Hochberg correction across the model × benchmark grid.

**[EXPECT]** `AFR` in the range **15–35%** on TextVQA/DocVQA for F-grid models, **5–15%** for F-cont, **< 5%** for LLaVA-1.5. `Acc_oracle − Acc_native` of **+8 to +20 points**, establishing how much accuracy is being left on the table by an arbitrary preprocessing choice.

**[DECISION — day 9]** If upsample-only `AFR < 8%` on the two strongest benchmarks for the two strongest F-grid models, the headline claim is weak. Fall back to F2 (Universal Blind Spots), which shares the harness.

### 4.6 Experiment 2 — Mechanism: tile transitions and the family ordering

This is the section that converts a robustness table into a paper.

**(a) Transition alignment.** For each consecutive scale pair, record whether the grid changed and whether the answer flipped. Compute the excess flip rate at transitions over the within-plateau baseline, with a permutation null that shuffles transition positions.

**[EXPECT]** Flip rate at grid transitions **2–5×** the within-plateau rate, `p < 0.001`.

**(b) Family ordering.** Compare `ρ_m` across F-fix / F-cont / F-grid.

**[EXPECT]** `ρ_F-grid > ρ_F-cont > ρ_F-fix`, with the fixed-resolution control near the floor set by decoding nondeterminism.

**(c) Token-count control.** Because `|T|` changes with `s`, a reviewer will ask whether the effect is really "more tokens = more confusion." Dissociate by finding scale pairs with **equal token count but different grid shape** (e.g. a 1×4 and a 4×1 grid, or two configurations with the same `ab`). If flips persist at matched token count, the cause is layout, not sequence length. **This control is mandatory.**

**(d) Thumbnail/crop attribution.** For F-grid models, re-run with the thumbnail ablated and with crops ablated. Relate per-item flip susceptibility to which channel the item depends on, connecting to the known complementary-roles result.

**(e) Scale invariance.** `ρ` for LLaVA-OneVision-0.5B vs. 7B.

**[EXPECT]** `ρ` differs by **< 30% relative** between 0.5B and 7B — the instability is architectural, not a capacity artifact.

### 4.7 Experiment 3 — Information–response curves (C3)

Four controlled degradation axes applied at native scale:

| Axis | Levels | Interpretation |
|---|---|---|
| Downsample-then-upsample | effective resolution ÷ {1, 1.5, 2, 3, 4, 6} | Removes high-frequency detail at constant token layout |
| Gaussian blur | σ ∈ {0, 0.5, 1, 2, 4, 8} px | Continuous band-limiting |
| JPEG quality | Q ∈ {95, 70, 50, 30, 15, 5} | Perceptually structured loss |
| Occlusion | {0, 10, 25, 40, 60, 80}% area, random or object-centric | Spatially structured loss |

**Crucially, the downsample-then-upsample axis holds token layout fixed while varying information**, which is the exact complement of the upsample sweep (fixed information, varying layout). Together the two isolate the two variables cleanly. This pairing is the paper's cleanest experimental logic and should be a figure.

*Confidence definition.* Report three, since the choice is contested: (i) mean per-token logprob of the answer span; (ii) for binary/MC items, the normalized probability of the selected option token (the cleanest, hence POPE's inclusion); (iii) self-prompted verbalized confidence. Report the primary result under (ii) and the others in an appendix.

*Key statistic.* The slope of confidence vs. normalized information, `dp/dI`, against the slope of accuracy vs. information, `dAcc/dI`, with the dataset answer prior drawn as a floor line.

**[EXPECT]** `|dp/dI|` within a small factor of zero while accuracy falls **20–40 points** toward the prior. Expected figure: two lines, one steeply descending to the prior floor, one nearly flat.

### 4.8 Experiment 4 — Human reference

*Design.* 150 items × 5 degradation levels × 3 annotators. Annotators answer or select "can't tell." Instructions and rubric fixed and released.

*Purpose.* Establish that (a) humans' accuracy tracks the information axis and (b) human abstention *rises* as information falls. This is the contrast that makes C3 a statement about perception rather than about calibration hyperparameters.

*Second, smaller study — the nullity audit.* 100 items at the extreme upsample scale, annotators asked whether the image is still fully answerable. **This is the direct evidence that the upsample range is semantics-preserving**, and one reviewer will demand it. Budget for it.

*Ethics/logistics.* Two annotators plus a tiebreaker, blinded to model outputs; report inter-annotator agreement (κ).

### 4.9 Experiment 5 — Mitigation

**(a) Cross-resolution self-consistency.** Predict at `K ∈ {3, 5}` scales spanning at least two grid configurations; take the modal answer (for free-form, cluster by normalized string / embedding similarity).

**[EXPECT]** `+2 to +6` points over native-scale accuracy at 3–5× inference cost, larger on detail-heavy benchmarks. Report the accuracy-vs-cost curve, and compare against the trivially-matched baseline of *K samples at the same scale with temperature > 0*, which controls for "any ensembling helps."

**(b) Cross-resolution agreement as an abstention signal.** Define `α_i = ` fraction of scales agreeing with the modal answer. Evaluate selective prediction: risk–coverage curves and AUROC for correctness prediction, against baselines of token probability, mean logprob, verbalized confidence, and same-scale sampling agreement.

**[EXPECT]** AUROC improvement of **+0.08 to +0.15** over token probability. This is likely the most *useful* result in the paper and costs almost nothing to produce once Experiment 1 is done — the logs already contain everything needed.

**(c) Cheap practical variant.** Report the best fixed-`K` schedule and a "snap to nearest grid centroid" heuristic that costs one extra forward pass.

### 4.10 Controls and confound checklist

Track this as a living table in the repo. Reviewers reject on unchecked confounds far more often than on weak effects.

| # | Confound | Control |
|---|---|---|
| 1 | "You removed information" | Upsample-only headline condition |
| 2 | "Flips are borderline noise" | `ρ_m` restricted to high-confidence-at-native items |
| 3 | "It's just more tokens" | Matched-token-count, different-grid pairs (§4.6c) |
| 4 | "It's the resize kernel" | Bicubic / bilinear / nearest replication |
| 5 | "It's decoding nondeterminism" | Greedy + fixed seed; F-fix model as empirical floor |
| 6 | "It's answer-string matching" | Manual audit of 200 flip events; report matching-artifact rate |
| 7 | "It's a bug in your harness" | Reproduce published numbers at `s = 1.0` within ~1 point |
| 8 | "Only happens on weird aspect ratios" | Stratify by source aspect ratio; report effect within strata |
| 9 | "Only on one benchmark" | 6 benchmarks incl. a predicted-small negative control |
| 10 | "Disappears at scale" | 0.5B vs 7B same-family pair |

### 4.11 Compute budget

Primary grid: 8 models × 6 benchmarks × ~1,300 items × 21 scales ≈ **1.3M forward passes**. Batched short-output generation on a 2–3B model runs roughly 8–15 items/s per A30; larger models 3–6/s.

| Block | Estimated GPU-hours |
|---|---|
| Primary sweep (Exp 1) | 60–90 |
| Mechanism ablations (Exp 2) | 20–30 |
| Degradation axes (Exp 3) | 25–40 |
| Mitigation (Exp 5, reuses logs) | 5–10 |
| Slack / reruns | 40 |
| **Total** | **~150–210 GPU-hours** |

On 3× A30 that is roughly **3–4 wall-clock weeks at 70% utilization**, which fits with margin. Trim by reducing per-benchmark sample size before reducing the number of models — model diversity carries the mechanism claim.

---

## 5. Expected results

### 5.1 The five figures the paper lives on

| Fig | Content | Why it matters |
|---|---|---|
| **1** | Teaser: one image, three scales, three different answers, all three images visually identical to a human | The 3-second version of the paper |
| **2** | Accuracy-vs-scale curves, grid transitions marked as vertical lines, one panel per family | C1 + the mechanism in one plot |
| **3** | Flip rate at transitions vs. within plateaus, by family, with permutation null | The mechanism, statistically |
| **4** | Accuracy and confidence vs. normalized information, prior floor drawn, human reference overlaid | C3, and the paper's emotional center |
| **5** | Risk–coverage curves: cross-resolution agreement vs. token probability | The usable contribution |

### 5.2 Quantitative expectations

| Quantity | Weak | **Expected** | Strong |
|---|---|---|---|
| Upsample-only `AFR`, best F-grid model, TextVQA | 8% | **20%** | 35%+ |
| `ρ_m` (high-confidence-only flip rate) | 5% | **12%** | 25%+ |
| Transition vs. plateau flip ratio | 1.5× | **3×** | 5×+ |
| `Acc_oracle − Acc_native` | +5 | **+12** | +20 |
| F-fix control `ρ` | 5% | **<2%** | <1% |
| 0.5B vs 7B `ρ` relative difference | 60% | **<30%** | <15% |
| Confidence slope vs. information (normalized) | −0.3 | **≈ −0.05** | ≈ 0 |
| Accuracy drop to prior under degradation | 10 pts | **30 pts** | 40 pts |
| Self-consistency accuracy gain | +1 | **+4** | +6 |
| Selective-prediction AUROC gain | +0.03 | **+0.10** | +0.15 |

### 5.3 What each outcome means

- **All expectations met.** Strong paper. The narrative is complete: phenomenon, mechanism, family ordering, human contrast, fix.
- **Effect real but small (`AFR` ~8–12%).** Still publishable if the *mechanism* is clean. Reframe from "attack" to "an unreported source of benchmark variance," lead with the selective-prediction contribution, and emphasize that the effect concentrates on exactly the fine-grained tasks the community cares most about.
- **Effect large but not transition-aligned.** The phenomenon is real, the explanation is wrong. Dig: check encoder-side interpolation of positional embeddings, check `max_pixels` clipping, check padding behavior. A wrong-but-corrected mechanism is fine; an absent mechanism is a rejection.
- **F-fix control also shows large flips.** Danger sign — likely a harness or answer-matching bug. Stop and audit before proceeding.
- **Confidence *does* track information.** Drop C3 to an appendix and make the paper purely about C1/C2 plus the mitigation. The paper survives; this is why C3 is third, not first.

### 5.4 What counts as a strong CVPR result

**Tier 1 — minimum viable (borderline accept).**
Non-monotone curves demonstrated across ≥4 models; upsample-only `AFR` ≥ 10% on ≥2 benchmarks; fixed-resolution control near floor; a working mitigation with positive numbers. This is a solid, useful, slightly unsurprising robustness paper.

**Tier 2 — comfortable accept.**
Tier 1, plus: statistically significant transition alignment with a permutation null; the family ordering `F-grid > F-cont > F-fix`; the matched-token-count dissociation; scale invariance across a 0.5B/7B pair; selective-prediction AUROC gain ≥ +0.08. At this point you are not reporting a weakness, you are explaining an architecture.

**Tier 3 — highlight / strong-accept territory.**
Tier 2, plus **at least two** of:
- The **human reference contrast** in Fig. 4: humans abstain, models don't, on the same controlled information axis.
- An `Acc_oracle − Acc_native` gap large enough (≥ +15) to reframe resolution as a *free unexploited accuracy source* rather than only a vulnerability.
- Demonstration that **published leaderboard orderings change** under legitimate alternative preprocessing — two models whose rank reverses between two defensible resize policies. This converts the paper from "models are fragile" into "reported numbers are conditional," which is the version people cite.
- A **predictive fragility score**: `ρ_m` measured cheaply on 200 items predicting full-benchmark instability, offered as a diagnostic others can run in minutes.

**The single highest-leverage addition** is the ranking-flip result. If two models in your set reverse order under two defensible preprocessing policies, put it in the abstract.

### 5.5 Reviewer objections and prepared responses

| Objection | Response | Where it's answered |
|---|---|---|
| "Resolution sensitivity is known" | Nobody has measured the *curve*, shown *non-monotonicity*, or localized it to grid transitions. And upsample-only flips cannot be explained by information loss | §4.5, §4.6 |
| "This is just image-scaling attacks" | Those craft pixels to change content after downscaling. We craft nothing and the content is unchanged | §2.3 |
| "Flips are noise near the decision boundary" | `ρ_m` is computed only on high-confidence-at-native items and remains substantial | §4.10 #2 |
| "It's token count, not layout" | Matched-token-count, different-grid pairs still flip | §4.6c |
| "It disappears at scale" | 0.5B vs 7B same-family `ρ` differs by <30% | §4.6e |
| "No method contribution" | Cross-resolution consistency: accuracy gain plus a large selective-prediction gain, zero training | §4.9 |
| "Small models only" | The preprocessing map is identical code across sizes; the F-fix control isolates the cause independent of capacity | §4.1 |
| "Cherry-picked benchmarks" | Pre-registered a negative control that behaves as predicted | §4.2 |

---

## 6. Sixty-day plan

| Days | Milestone | Gate |
|---|---|---|
| 1–4 | Harness: unified loader, resize hook before processor, grid/token logging, per-item output store. Reproduce published numbers at `s=1.0` for all 8 models | **Must reproduce within ~1 pt** |
| 5–9 | Pilot: 2 F-grid models × TextVQA + POPE × 21 upsample scales × 1,000 items | **[DECISION] `AFR ≥ 8%`?** If no → pivot to F2 |
| 10–20 | Full primary sweep: 8 models × 6 benchmarks | — |
| 21–27 | Mechanism: transition alignment, family ordering, **matched-token-count control**, thumbnail/crop ablation, scale invariance | **[DECISION] Is the effect transition-aligned?** If no, spend 3 days finding the real mechanism before proceeding |
| 28–36 | Degradation axes with confidence logging; kernel replication; aspect-ratio study | — |
| 37–43 | Human studies: main reference (150×5×3) + nullity audit (100 items) | Start annotator recruitment on day 20, not day 37 |
| 44–50 | Mitigation: self-consistency, agreement-based abstention, cost curves, ranking-flip analysis | — |
| 51–56 | Ablations, confound table completion, fragility-score release, figure polish | Figure 1 teaser must be genuinely striking |
| 57–60 | Writing, supplementary, code release | — |

**Parallelization note.** Human-study recruitment (day 20) and figure design (day 30 onward) run alongside compute. The compute blocks are GPU-bound, not attention-bound, so use that time.

**Slack.** Roughly 8 days of float is embedded. Spend it on the mechanism section, not the sweep.

---

## 7. Release plan

- Code: sweep harness, resize hook, per-model grid-logging adapters.
- Data: per-item, per-scale logs (answer, correctness, grid config, token count, confidence) for all 1.3M inferences. This is the artifact others will reuse.
- The **resolution-fragility benchmark**: a 200-item-per-benchmark protocol producing `ρ_m` in minutes, with a leaderboard seeded by the 8 models.
- Human annotations and rubric.

---

## 8. Open extensions (mention in Discussion, do not attempt in 60 days)

- **Video.** Frame-level resize interacts with temporal token budgets; the same instability likely compounds across frames.
- **Targeted resizing.** Is there a scale that reliably induces a *specific* wrong answer, rather than merely any wrong answer? That would upgrade the attack from untargeted to targeted.
- **Training-time fix.** Scale augmentation across grid configurations, or a consistency loss across tilings. Natural follow-up paper.
- **Encoder-side localization.** Does the instability live in positional-embedding interpolation, in the projector, or in the LLM's handling of variable-length visual spans? Requires layer-wise probing.
- **Aspect-ratio twin.** Same phenomenon under aspect-ratio change at constant pixel count; possibly a standalone paper (see F5 in the idea bank).

---

## 9. Draft abstract (to be revised once numbers exist)

> Vision-language models have largely abandoned fixed-resolution preprocessing in favor of dynamic tiling, in which an image is partitioned into a variable number of crops whose count and arrangement depend on its pixel dimensions. We show that this makes model behavior a discontinuous function of a preprocessing parameter that is semantically meaningless and almost never reported. Across [8] models spanning three preprocessing families and [6] benchmarks, we find that accuracy as a function of input scale is non-monotone, and that **upsampling alone** — an operation that adds no visual information — flips [TBD]% of previously correct answers on detail-heavy tasks. We localize the cause: flip events concentrate at tile-grid transitions, flip rates are ordered discrete-grid > continuously-quantized > fixed-resolution, and the effect persists at matched visual-token count, implicating token *layout* rather than sequence length. It is also invariant to model scale within a family. Separately, sweeping a controlled information axis, we find model confidence is approximately flat while accuracy decays toward the dataset answer prior, in contrast to human annotators who abstain as evidence is removed. Finally, we show that the instability is exploitable as a remedy: agreement across resolutions improves accuracy by [TBD] points and improves selective-prediction AUROC by [TBD] over token-probability confidence, at no training cost. Reported VLM accuracy is conditional on an unreported preprocessing choice, and current models cannot tell when they have stopped seeing.
