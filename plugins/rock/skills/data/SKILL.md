---
name: data
description: Pull numbers and rosters out of Rock RMS — data views, reports, attendance occurrences and headcounts, background check status, check-in configuration. Use for "how many", "who attended", "run that report", "what is the check-in setup".
---

# Get data out of Rock

```bash
R="${CLAUDE_PLUGIN_ROOT}/runtime/rock.sh"
"$R" query dataviews --category "volunteer"
"$R" query dataview "Active Volunteers" --json
```

| To get | Command |
| --- | --- |
| Data views | `query dataviews [--category <substring>]`, `query dataview "<name or id>"` |
| Reports | `query report "<name or id>"` |
| Attendance occurrences | `query attendance [--group "<name or id>"] [--date YYYY-MM-DD]` |
| One occurrence, with attendees | `query occurrence <id> [--names] [--limit 200]` |
| Background checks | `query bgc [--status <substring>] [--person "<name or id>"]` |
| Check-in configuration | `query checkin [--area "<name or id>"]` |

## Give the number, and what it covers

"How many kids checked in on Sunday" wants a number and the date it covers:
fetch the raw rows with `--json` from the single-entity commands, compute, and
report the figure. Show the rows when they are the answer, or when the count is
small enough to be worth seeing.

Every number ships with its boundaries — the dates it covers, the limit in
play, and what was left out. An attendance query without `--date` returns the
most recent occurrences up to `--limit`, not all of them, and a report that
silently truncated is worse than no answer:

```
Sunday 12 Jan, Kids Ministry: 312 across 4 occurrences.
(Occurrences on that date only; three groups had no occurrence recorded.)
```

## This data is about real people

- **Keep rosters, check results, and person records in the conversation.**
  Never write any of it into a repository — not a scratch file, not a `.md` you
  are drafting, not temporarily. If someone needs a file, put it outside the
  repo and say where.
- **Background check status is need-to-know.** Report the subject of the
  question and nothing around it: whether their check is current, or which are
  expiring.

## Next

- Finding the data view or group first → `/rock:find`
- How a data view is defined rather than what it returns → `/rock:inspect`
