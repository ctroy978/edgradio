# Name Scrubbing Issue: Nicknames and Preferred Names

## Problem

Students may use a different name on their papers than what appears in the official roster CSV.

**Example:**
- Roster has: `Kate Bue`
- Student writes: `Kaitlyn Bue` (MLA format, first line, no label)

The scrubber will remove "Kate" and "Bue" but **not** "Kaitlyn" - a FERPA compliance gap.

## Why Current Detection Fails

The name detection uses two methods:

1. **Pattern matching** - Looks for `Name: XYZ` or `ID: XYZ` labels (MLA format doesn't use these)
2. **Roster matching** - Checks first 10 lines against known roster names (fails when nickname differs)

When both fail, the name becomes "Unknown Student 01". The user manually corrects it to the roster name, but the **actual name written on the paper is never captured**.

## Potential Solutions

1. **Capture first line as potential name** - Store the first non-empty line (likely the name in MLA format) even when detection fails, and scrub it during processing

2. **Add "as written" field during correction** - When correcting a name, also capture what name actually appears on the paper
   - Roster name: "Kate Bue"
   - As written: "Kaitlyn Bue"

3. **Fuzzy matching during scrubbing** - If roster has "Kate", also scrub phonetically similar names like "Katie", "Kaitlyn", "Katherine"

4. **Common nickname database** - Maintain a mapping of common nicknames (Kate -> Kaitlyn, Katie, Katherine, etc.)

## Current Workaround

None - names that differ from the roster will pass through to AI evaluation unscrubbed.
