# ViralWatch — Live Demo Script

**Slot:** 10 minutes · Friday 15:30 · Solo presenter, one laptop
**Goal:** show a working system on real outbreak data, and be honest about the two places we adapted the brief to match what the real data allowed.

---

## Before you walk up (do this ~30 min before your slot)

1. Terminal, from repo root:
   ```bash
   source venv/bin/activate
   uvicorn api.main:app --port 8000
   ```
   (No `--reload` for the actual demo — a stray autosave shouldn't restart your server mid-sentence.)

2. Open exactly **two** browser tabs, in this order, and close everything else:
   - Tab 1: `http://127.0.0.1:8000/dashboard/`
   - Tab 2: `http://127.0.0.1:8000/docs`

3. Click "Predict" once on any zone in Tab 1 to warm up the model (first inference can be a touch slower than the rest).

4. Have your backup screen recording ready to switch to (see bottom of this doc) in case anything breaks live.

5. Silence notifications on the laptop. A Slack popup mid-share is worse than any bug in the code at this point.

---

## The script

### 0:00 – 1:00 — Frame the problem
Don't open with "we built a FastAPI service." Open with the outbreak itself:

> "On May 15th 2026, the DRC declared its 17th Ebola outbreak — Bundibugyo virus, no licensed vaccine, no approved treatment. WHO declared a Public Health Emergency two days later. But the signal existed weeks before that lab confirmation. ViralWatch is built to close that gap."

### 1:00 – 3:00 — Cross-border watchlist (Tab 1, already open)
- Point at the **Nord-Kivu / Sud-Kivu chips** at the top. Say this is the brief's explicit ask: a live watchlist for the zones bordering Rwanda.
- **Click a red/high-severity chip** (currently Katwa).
- Let the **Zone Lookup panel** populate — point out it's a real API call happening live, not a screenshot.
- Say: *"That's two models agreeing — a Keras network and a RandomForest baseline — both trained on the real outbreak data."*

### 3:00 – 5:30 — The anomaly detection proof point
This is the brief's own words: *"the hardest, most important technical result."* Give it real time, don't rush it.

- Scroll to the **"Early warning — all zones"** panel. Point at the line: *"Ranked by One-Class SVM anomaly score."* **That table is the SVM's output** — the ranked list with the colored bars.
- Say: *"This SVM was trained only on each zone's own first two weeks of reporting — its early baseline. It never saw what happened after. That's what makes this a genuine early-warning signal instead of hindsight."*
- **Be upfront about the adaptation** (this is a strength, not a weakness, if you say it plainly):
  > "The brief asks whether this would have flagged the April 24th–May 5th signal window before the May 15th confirmation. Our actual case data starts May 14th — one day before confirmation — so there's no true pre-outbreak national data to test that exact window against. We adapted the exercise to the health-zone framing already in the brief: each zone's own early period is its baseline, and we test whether the SVM catches that zone's later acceleration early. That's a documented, honest adaptation, not a shortcut."

### 5:30 – 7:00 — NLP briefing
- Scroll to the **bottom panel** — latest WHO bulletin.
- Point at the **severity badge** and the **auto-flagged most-severe paragraph** (currently the PHEIC declaration line).
- Say: *"This is Hugging Face NER and zero-shot classification running on the actual bulletin text — not a keyword lookup. It correctly picked out the single most severe sentence in the entire bulletin."*

### 7:00 – 8:30 — Prove it's real engineering (Tab 2 — `/docs`)
- Switch tabs (`Ctrl+Tab`).
- Say, in one breath, don't dwell:
  > "This is auto-generated documentation, straight from our code — proof this is a real, typed API contract, not a mockup. While building this, we actually found our model was collapsing to near-100% confidence on every single zone. Traced it to a training/inference feature mismatch, fixed it, and average precision went from 0.89 to 0.93."
- Optionally click **`/predict/{zone}`** to expand it and show the "Try it out" button — skip this if you're running short on time.

### 8:30 – 10:00 — Close
- One sentence on what's next: more zones, a retraining cadence, alerting.
- Stop talking. A clean early finish beats a rushed one.

---

## If something breaks live

Don't debug on stage. Say: *"Let me switch to a recording of this running against live data from earlier today,"* and play the backup. This is a normal, professional move for any live-data demo — assume something might go sideways, because outbreak data pipelines have off days.

**Record this backup today**, while everything is confirmed working — not the morning of the demo.

---

## One-line cheat sheet (keep this in your pocket, not on screen)

```
1. Dashboard loads → point at watchlist chips
2. Click Katwa chip → point at Predict panel populating
3. Scroll to ranking table → say SVM caveat
4. Scroll to briefing panel → point at severity badge + quote
5. Ctrl+Tab → /docs → say the bug-fix line
6. Close
```
