"""
day4_nlp_extraction.py — ViralWatch Day 4, morning session

Runs Hugging Face pipelines on the real WHO DON bulletins to extract:
  1. Health zones / locations mentioned (NER)
  2. Case counts and death counts (regex, paired with nearby location mentions)
  3. Severity language, classified per paragraph (zero-shot classification)

Output feeds the /briefing FastAPI endpoint built on Day 5.

Run with:
    source venv/bin/activate
    python src/fetch_who_bulletins.py      # run this first if you haven't
    python src/day4_nlp_extraction.py
"""

import re
import json
from pathlib import Path
from transformers import pipeline

IN_DIR = Path("data/who_bulletins")
OUT_DIR = Path("data/processed")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# =========================================================================
# STEP 1: Load the downloaded bulletin text files
# =========================================================================
bulletin_files = sorted(IN_DIR.glob("*.txt"))
if not bulletin_files:
    raise SystemExit(
        "No bulletin .txt files found in data/who_bulletins/. "
        "Run src/fetch_who_bulletins.py first."
    )
print(f"[1/5] Found {len(bulletin_files)} bulletin files: "
      f"{[f.name for f in bulletin_files]}")

# =========================================================================
# STEP 2: Load Hugging Face pipelines
# =========================================================================
# NER: identifies named entities (people, organizations, locations) in text.
# We use it to find health zone / province / country mentions.
print("[2/5] Loading NER pipeline (dslim/bert-base-NER)...")
ner = pipeline("ner", model="dslim/bert-base-NER", aggregation_strategy="simple")

# Zero-shot classification: classifies text into labels it was never
# specifically trained on, by comparing the text's meaning to each label.
# We use it to score how severe/urgent each paragraph sounds.
print("      Loading zero-shot classification pipeline (facebook/bart-large-mnli)...")
severity_classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
SEVERITY_LABELS = ["routine update", "concerning escalation", "emergency-level crisis"]

# =========================================================================
# STEP 3: Regex patterns for case/death counts
# =========================================================================
# WHO bulletins consistently phrase counts like "3605 confirmed cases" or
# "880 cases" or "1587 deaths" -- simple, reliable regex, no ML needed here.
CASE_PATTERN = re.compile(r"(\d[\d,]*)\s+(?:confirmed\s+|suspected\s+)?cases?", re.IGNORECASE)
DEATH_PATTERN = re.compile(r"(\d[\d,]*)\s+deaths?", re.IGNORECASE)


def extract_case_counts(text: str) -> list[dict]:
    """Find every 'N cases' / 'N deaths' mention with a bit of surrounding
    context, so a human (or the /briefing endpoint) can see what it refers to."""
    results = []
    for pattern, label in [(CASE_PATTERN, "cases"), (DEATH_PATTERN, "deaths")]:
        for m in pattern.finditer(text):
            start = max(0, m.start() - 60)
            end = min(len(text), m.end() + 20)
            context = text[start:end].replace("\n", " ").strip()
            results.append({
                "value": int(m.group(1).replace(",", "")),
                "type": label,
                "context": f"...{context}...",
            })
    return results


# =========================================================================
# STEP 4: Process each bulletin
# =========================================================================
all_results = []

for filepath in bulletin_files:
    text = filepath.read_text(encoding="utf-8")
    print(f"\n[3/5] Processing {filepath.name} ({len(text)} characters)")

    # --- NER: extract location entities ---
    entities = ner(text)
    locations = sorted(set(
        e["word"] for e in entities if e["entity_group"] in ("LOC", "ORG")
    ))
    print(f"      Found {len(locations)} unique location/org entities: {locations[:10]}"
          + (" ..." if len(locations) > 10 else ""))

    # --- Regex: extract case/death counts with context ---
    counts = extract_case_counts(text)
    print(f"      Found {len(counts)} case/death count mentions")

    # --- Zero-shot: classify severity per paragraph ---
    paragraphs = [p.strip() for p in text.split("\n") if len(p.strip()) > 60]
    severities = []
    for para in paragraphs:
        result = severity_classifier(para, SEVERITY_LABELS)
        severities.append({
            "paragraph": para[:150] + ("..." if len(para) > 150 else ""),
            "label": result["labels"][0],
            "confidence": round(result["scores"][0], 3),
        })
    print(f"      Classified {len(severities)} paragraphs by severity")

    all_results.append({
        "bulletin": filepath.stem,
        "locations_mentioned": locations,
        "case_death_counts": counts,
        "paragraph_severity": severities,
    })

# =========================================================================
# STEP 5: Save structured output for the /briefing endpoint
# =========================================================================
out_path = OUT_DIR / "nlp_bulletin_extractions.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)

print(f"\n[5/5] Saved structured extractions to {out_path}")
print("\n=== Day 4 morning (NLP) complete ===")

# Quick human-readable preview of the most recent bulletin
latest = all_results[-1]
print(f"\n--- Preview: {latest['bulletin']} ---")
print(f"Locations mentioned: {', '.join(latest['locations_mentioned'][:8])}")
if latest["case_death_counts"]:
    biggest = max(latest["case_death_counts"], key=lambda c: c["value"])
    print(f"Largest count mentioned: {biggest['value']} {biggest['type']} "
          f"({biggest['context']})")
most_severe = max(latest["paragraph_severity"], key=lambda p: p["confidence"]
                   if p["label"] == "emergency-level crisis" else 0)
print(f"Most severe paragraph ({most_severe['label']}, "
      f"{most_severe['confidence']:.0%} confidence):\n  \"{most_severe['paragraph']}\"")
