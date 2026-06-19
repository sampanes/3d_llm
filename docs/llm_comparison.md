# LLM Comparison for 3D Model Generation

A practical comparison of large language models for generating OpenSCAD and CadQuery code, based on typical results, failure modes, and cost-effectiveness.

---

## Quick Summary

| Model              | OpenSCAD Quality | CadQuery Quality | Speed   | Cost       | Best For                    |
|--------------------|------------------|------------------|---------|------------|-----------------------------|
| GPT-4o             | ★★★★☆            | ★★★★☆            | Fast    | Medium     | General-purpose, iteration  |
| GPT-4              | ★★★★☆            | ★★★★★            | Slow    | High       | Complex assemblies          |
| Claude 3.5 Sonnet  | ★★★★★            | ★★★★☆            | Fast    | Medium     | Clean OpenSCAD, best first-try |
| Claude 3 Opus      | ★★★★★            | ★★★★★            | Slow    | High       | Complex logic, documentation |
| Gemini Pro         | ★★★☆☆            | ★★★☆☆            | Fast    | Low/Free   | Prototyping, cost-sensitive  |
| Gemini Ultra/1.5   | ★★★★☆            | ★★★★☆            | Medium  | Medium     | Balanced cost/quality        |
| CodeLlama 34B      | ★★★☆☆            | ★★☆☆☆            | Local   | Free       | Offline, privacy-sensitive   |
| DeepSeek Coder 33B | ★★★☆☆            | ★★★☆☆            | Local   | Free       | Offline, decent quality      |

---

## Detailed Analysis

### GPT-4o (OpenAI)

**Strengths:**
- Fast response times (3–8 seconds for typical models)
- Good at following dimensional constraints precisely
- Handles multi-part assemblies well
- Strong at interpreting vague descriptions ("make it look nice")
- Excellent at iterative refinement — responds well to "make X bigger" style follow-ups

**Weaknesses:**
- Occasionally produces non-manifold geometry in complex boolean operations
- Sometimes overcomplicates simple models with unnecessary abstractions
- Can hallucinate OpenSCAD functions that don't exist (e.g., `chamfer()`)
- Tends to use `linear_extrude()` when `rotate_extrude()` would be more appropriate

**Typical Issues:**
- Missing `$fn` on curved surfaces → faceted output
- Overlapping geometry in `difference()` operations → rendering artifacts
- Incorrect argument order for `rotate()` and `translate()`

**Estimated Cost:** ~$0.02–0.08 per model generation

---

### GPT-4 (OpenAI)

**Strengths:**
- Most reliable CadQuery code generation of any model
- Excellent understanding of mechanical constraints (threads, tolerances, fits)
- Produces well-commented, modular code
- Rarely makes syntax errors

**Weaknesses:**
- Slow (15–45 seconds per generation)
- Expensive ($0.06–0.20 per generation)
- Sometimes over-engineers simple requests
- Older training data may miss recent OpenSCAD features

**Best For:** Mission-critical parts, complex assemblies, when you need it right the first time.

---

### Claude 3.5 Sonnet (Anthropic)

**Strengths:**
- **Best first-try success rate for OpenSCAD** — frequently produces working code on the first attempt
- Excellent at parametric design — naturally creates configurable parameters
- Clean, well-structured code with thorough comments
- Good spatial reasoning for organic shapes
- Handles `minkowski()` and `hull()` operations correctly more often than GPT

**Weaknesses:**
- CadQuery output is good but occasionally uses deprecated API patterns
- Can be overly verbose in code comments (not a bad thing, but costs tokens)
- Sometimes adds unnecessary safety margins to tolerances
- Less willing to produce "quick and dirty" code — always wants to make it production-quality

**Typical Issues:**
- Rare; most common is slightly oversized tolerances
- Occasionally produces valid but computationally expensive geometry

**Estimated Cost:** ~$0.02–0.06 per generation

---

### Claude 3 Opus (Anthropic)

**Strengths:**
- Excellent for complex mechanical reasoning (gears, threads, linkages)
- Best documentation quality of any model
- Strong understanding of manufacturing constraints
- Can explain *why* it made specific design choices

**Weaknesses:**
- Slow (20–60 seconds per generation)
- Most expensive option ($0.08–0.25 per generation)
- Overkill for simple models

**Best For:** Complex parts requiring engineering knowledge, documentation generation, explaining designs to stakeholders.

---

### Gemini Pro (Google)

**Strengths:**
- Free tier is very generous for prototyping
- Fastest response times (~2–5 seconds)
- Good enough for simple models and rapid iteration
- Improving rapidly between versions

**Weaknesses:**
- Higher failure rate on complex geometry
- Struggles with boolean operations involving many parts
- CadQuery code often has import errors or API misuse
- Less consistent output quality — sometimes great, sometimes unusable
- Weaker spatial reasoning for 3D transformations

**Typical Issues:**
- Incorrect `rotate()` axis specification
- Missing `center = true` on OpenSCAD primitives
- Generates Python syntax in OpenSCAD code (and vice versa)

**Estimated Cost:** Free tier available; paid ~$0.01–0.03 per generation

---

### Gemini Ultra / 1.5 Pro (Google)

**Strengths:**
- Significant improvement over base Gemini Pro
- Large context window (1M+ tokens) useful for complex multi-file projects
- Good at batch processing multiple related models
- Competitive quality with GPT-4o at lower cost

**Weaknesses:**
- Still less reliable than Claude for OpenSCAD specifically
- Availability and pricing can change frequently
- Long context doesn't always translate to better spatial reasoning

**Estimated Cost:** ~$0.01–0.05 per generation

---

### Local Models via Ollama

#### CodeLlama 34B

**Strengths:**
- Completely free and private
- No rate limits
- Decent OpenSCAD syntax knowledge
- Good for iterative prompt refinement (no cost per try)

**Weaknesses:**
- Requires 20+ GB RAM (34B model)
- Much higher failure rate than cloud models
- Struggles with complex assemblies
- Limited understanding of 3D manufacturing constraints
- Often produces code that is syntactically valid but geometrically wrong

#### DeepSeek Coder 33B

**Strengths:**
- Better code quality than CodeLlama for structured output
- Good at following template patterns (give it an example, it extends well)
- Free and private

**Weaknesses:**
- Similar hardware requirements
- Less spatial reasoning ability than cloud models
- CadQuery support is weak — mainly useful for OpenSCAD

**General Local Model Tips:**
- Always provide a template/example in the prompt
- Keep requests simple — one feature at a time
- Use higher temperature (0.3–0.5) for more creative variations
- Budget for 3–5x more iterations than cloud models

---

## Cost Comparison

Estimated costs for generating a moderately complex model (parametric box with features):

| Model              | Input Tokens | Output Tokens | Est. Cost | Generations/Dollar |
|--------------------|--------------|---------------|-----------|---------------------|
| GPT-4o             | ~800         | ~1,500        | $0.03     | ~33                 |
| GPT-4              | ~800         | ~1,500        | $0.10     | ~10                 |
| Claude 3.5 Sonnet  | ~800         | ~1,800        | $0.04     | ~25                 |
| Claude 3 Opus      | ~800         | ~2,000        | $0.12     | ~8                  |
| Gemini Pro         | ~800         | ~1,200        | Free*     | Unlimited*          |
| Gemini 1.5 Pro     | ~800         | ~1,500        | $0.02     | ~50                 |
| Local (Ollama)     | ~800         | ~1,200        | $0.00     | Unlimited           |

*Free tier has rate limits (typically 60 requests/minute)

---

## Recommendations by Use Case

### Rapid Prototyping / Exploration
> **Gemini Pro (free tier)** or **Local models**
>
> When you're experimenting with prompts and don't care about first-try success, use the cheapest option and iterate.

### Production Parts / Functional Prints
> **Claude 3.5 Sonnet**
>
> Highest first-try success rate for OpenSCAD. The code it generates is clean, well-parameterized, and usually prints successfully.

### Complex Mechanical Parts
> **GPT-4** or **Claude 3 Opus**
>
> When the model needs threads, snap fits, gear teeth, or precise tolerances, the premium models justify their cost.

### Batch Generation (Many Simple Parts)
> **GPT-4o** or **Gemini 1.5 Pro**
>
> Fast response times and reasonable cost make these ideal for generating many variations.

### Offline / Privacy-Sensitive
> **DeepSeek Coder 33B via Ollama**
>
> Best quality among local models. Combine with template-based prompting for best results.

### Learning / Education
> **Claude 3.5 Sonnet**
>
> Produces the best-commented code with explanations of design decisions. Great for understanding how 3D modeling code works.

---

## Tips for All Models

1. **Always provide dimensions** — don't say "small box", say "50x30x20mm box"
2. **Specify the target format** — "Generate OpenSCAD code" at the start of your prompt
3. **Mention print constraints** — "suitable for FDM printing, no overhangs > 45°"
4. **Request parameters** — "make all dimensions parametric with sensible defaults"
5. **Include a template** — giving the model an example of working code dramatically improves output quality
6. **Iterate, don't start over** — fixing specific issues is usually faster than regenerating from scratch
