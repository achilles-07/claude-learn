---
name: visualize
description: "Only during a teaching session (the teach skill is active or the user is studying a topic) — not for coding or other work. Add a correct, minimal visual to a lesson — a diagram or geometric picture — that renders inline in the Markdown lesson note. Use when an idea is genuinely clearer as a picture: a dependency graph, system/flow, sequence, state machine, tree, comparison, or a spatial/geometric thing (coordinate geometry, number line, vectors, a plot, a physical layout). Outsources authoring+rendering to a maker subagent that verifies the image by looking at it, then you embed the returned file."
---

# Visualize

A picture earns its place only when it shows something words can't — shape, structure, direction, relationship, geometry. This skill produces ONE such picture, guarantees it is **correct** (the maker renders it and looks at it before returning), and drops it into the lesson so it renders inline in the lesson note that `md-log` writes.

You are the **creative director**. You decide the exact idea and distill it to its fewest carrying elements. A **maker subagent** does the authoring, rendering, visual verification, and saving, then returns a filename. You embed that filename in your reply.

## When to visualize (and when not to)

This teaching system builds a **dependency graph in the learner's head** — axioms at the root, derived facts hanging off them. A visual is powerful exactly when it makes that structure (or a geometry) visible. Reach for one when:

- The idea is a **structure or relationship**: dependencies, a system with parts and arrows, a flow/pipeline, a sequence of exchanges, a state machine, a tree/hierarchy, a comparison, a containment (what's inside vs outside).
- The idea is **spatial or geometric**: coordinate geometry, a number line, vectors, a function's shape, a physical arrangement.

Do NOT visualize when prose or a single equation already carries it. A decorative diagram that just restates the sentence next to it adds noise and a chance to be wrong.

But in **structure-heavy subjects** — design patterns, system design and architecture, networking and protocols, data structures, algorithms, geometry — the core structure of each concept *is* the idea, and a learner who has only read it in prose hasn't seen it. There, drawing each concept's core structure is expected, not optional. The teach skill plans these visuals up front (Phase 2) and commissions them all in the background as soon as the plan is approved.

The real risk is a *false* picture, not a missing one: that's what the maker's render-and-inspect loop guards against. Decide based on whether the idea has shape, not on caution.

## Choose the maker

Two makers, bundled with this plugin (`learn:mermaid-maker`, `learn:svg-maker`):

- **`mermaid-maker`** — structural/relational visuals: dependency graphs, flowcharts, sequence/state/ER/class diagrams, trees, mindmaps, timelines. This is the default and fits the dependency-graph pedagogy directly.
- **`svg-maker`** — spatial/geometric visuals Mermaid can't lay out: exact coordinates, geometry figures, number lines, vectors, plots, custom shapes.

Rule of thumb: if it's *nodes-and-edges / relationships*, use mermaid-maker. If it's *positions-and-shapes / geometry*, use svg-maker.

## Brief the maker well: one idea, fewest elements

The most common failure is **cramming** — every extra label makes the picture harder to read AND harder to lay out correctly. Before briefing, prune to the fewest elements that carry the idea, and for each ask: *"if I delete this, is the idea still clear?"* If yes, delete it.

Give the maker the concept AND the concrete elements you want — not a vague topic, and not a long checklist.

- BAD: "make a diagram about how TCP works"
- GOOD: "graph TD: a node 'packet' at the top; arrows down to 'ordering' and 'retransmit on loss'; both arrows down into 'reliable stream'. No title. Show that reliability is built FROM packets, not alongside them."

Keep the idea intact but trust the maker to compose; if your brief lists more than ~5–7 elements, cut it first.

## Invoke

Dispatch the maker with the `Agent` tool — with `run_in_background: true` whenever you can keep teaching meanwhile (the usual case; the teach skill commissions all planned visuals at once this way). Several makers can run in parallel: one call per visual, all in the same message.

```
Agent(subagent_type: "learn:mermaid-maker", prompt: "<your minimal, concrete brief>")
```
```
Agent(subagent_type: "learn:svg-maker", prompt: "<your minimal, concrete brief>")
```

The maker owns its own render toolchain — it authors the source, renders it to a PNG, **looks at the PNG and iterates until it is correct and clean**, publishes it into the lesson's viz/ folder with a unique filename, and returns:

```
RESULT:
filename: viz-<slug>-<timestamp>.png
path: <lesson folder>/viz/viz-<slug>-<timestamp>.png
```

If it returns `RESULT: NONE`, it couldn't make a correct picture of the brief — simplify or rethink, or decide the visual isn't worth it. Never hand-author or fake a diagram yourself; correctness depends on the maker's render-and-inspect loop.

## Embed it in the lesson

Put the embed directly in your teaching reply as a standard Markdown image, with a short description as the alt text and the returned **filename** under `viz/`:

```
![Observer: subject notifies observers through an interface](viz/viz-<slug>-<timestamp>.png)
```

That's all. `md-log` mirrors your reply text verbatim into the lesson note, and the maker saved the PNG into the `viz/` folder right next to that note — so the relative link renders inline in any Markdown reader. Use standard Markdown only (no wiki-style `![[…]]` embeds or size suffixes). Introduce the visual in a sentence, then let it carry the idea — don't narrate every element back in prose.

## Why this is reliable

- The maker never returns a picture it hasn't **looked at**, so "renders fine but says something false" is caught before it reaches the learner.
- PNG embed means **what the maker verified is pixel-identical to what the learner sees** — no re-render drift.
- Unique filenames mean a later diagram never overwrites an earlier one.

> The makers render through the plugin's `scripts/render.py` (Mermaid via `mmdc`; SVG via `rsvg-convert`, ImageMagick or headless Chrome). You don't render anything yourself — you only brief the maker and embed the filename it returns.
