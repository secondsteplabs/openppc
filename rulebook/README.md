# Rulebook

The rules OpenPPC applies, one row each, with where each one comes from. `tests/test_rulebook.py` checks every threshold here against the code, so a row can't say one thing while the tool does another.

| File | What's in it |
|---|---|
| `rules.csv` | Every rule: the live ones the tool runs today and the planned ones, each with its source |
| `metrics.csv` | How each metric is computed |
| `sources.csv` | The pages each rule comes from |
| `taxonomy.csv` | Campaign types and areas, mapped to Google's own Skillshop courses |

Columns in `rules.csv` worth knowing:

- **status**: `live` (the tool runs it), `planned`, or `reference` (guidance an export can't check)
- **evidence**: `google` (Google's own guidance), `expert` (practitioners, cited), `openppc` (our own reasoning, in code) or `benchmark` (public averages)
- **code_ref** and **value**: the constant or default argument in the code, and its value. The test compares the two.
- **confidence**: for researched rules, how plainly the source states it (`high`, `medium`, `low`)
- **calibration**: what the paid tier tunes on live accounts instead of using one number for everyone
- **conflicts_with**: rules that disagree with this one, most often Google's advice against practitioners'

To change a threshold, change the code and its row in the same pull request. To argue with a rule, open an issue with its `rule_id`.

`python tools/build_rulebook.py rulebook.xlsx` turns the whole thing into a spreadsheet (needs `pip install openpyxl`).
