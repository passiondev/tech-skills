# Rock writes use PATCH, and one operation is generic

Every partial update in the Rock runtime now sends `PATCH`. Attribute values go through Rock's query-string route rather than a JSON body. The write side gains six group operations, a skill to reach them, and one `api_request` operation that sends a single request the caller writes. CI fails on either of the two request shapes Rock will not forgive.

> Written when Rock was two plugins. [0023](0023-rock-is-one-plugin-with-one-skill.md) merged them, so the skill names below have collapsed into `/rock:rock` and its `references/writing.md`. Every fix and every guard described here is unchanged; only where they are documented moved.

This is a bug-fix ADR. Three write paths were wrong in ways the code could not see, and one gap sent people to tooling [0004](0004-tech-skills-owns-the-rock-client.md) archived.

## PUT does not mean "change these fields"

`ApiController<T>.Put` calls `Service.SetValues(value, target)`, which is `Entry(target).CurrentValues.SetValues(source)`. Entity Framework copies every mapped column out of the object you posted — including the ones you left out. A body holding two fields therefore says: set these two, and null the other thirty.

Three things follow, and all three were reported:

- **The write fails outright** where one of the nulled columns is `[Required]`. Rock answers 400. Four of the seven repair operations were dead on arrival for this reason, which is why a colleague without a fallback could not update anything at all.
- **The audit trail is destroyed** on the writes that did pass validation. `CreatedDateTime` and `CreatedByPersonAliasId` go null, because `RockPreSave` fills them on insert and never restores them. This is the "filling in the fields like who made the change" report, and it is worse than it sounds: the row now looks like it was created by nobody.
- **The Guid is replaced.** `Entity<T>` initialises its backing field with `Guid.NewGuid()`, so an absent Guid is indistinguishable from a new entity's. Anything referencing the row by Guid — Lava, a saved URL, an integration — points at nothing.

Rock's `PATCH` sets only the keys it is given, by reflection, and refuses `Id`. That is the verb these six sites always wanted: `update_workflow`, `update_activity`, `update_action`, `reorder_actions`, `move_action`, and the schedule step of `create_checkin_area`, plus `person-update` in `rock_query.py`. `client.put` stays on the client, with a docstring explaining what it does, because a genuine whole-entity replace is still a thing a caller may mean.

> *`client.put` now takes `full_replace` as a keyword argument with no default, so a call site that means a whole-entity replace says so in the call. The check is the backstop rather than the guard. The signature refuses a partial `PUT` at runtime, and `rock-write-shapes` catches a new call site before anyone runs it.*

## The attribute-value writes never worked

`set_attribute_values` posted a JSON body to `{Entity}/Attributes/{id}` and then to `{Entity}/{id}/AttributeValues`. Neither route exists. Both 404s were caught, printed as `Warning: could not set X`, and the entity counted as created. `block-set` in `rock_query.py` had the same shape.

Rock's `SetAttributeValue` is convention-routed and binds from the query string: `POST /api/{Entity}/AttributeValue/{id}?attributeKey=K&attributeValue=V`, with no body — a body makes the request match the OData route instead, which is where the 404 came from. Sending the key as a query parameter is not optional; omit it and the route does not bind.

So every workflow this plugin has ever created had unconfigured actions, and the report said `Warning:` and moved on. Two skills had gone further and written the swallowing down as intended behaviour — "an unknown key only prints a `Warning:` and the operation still reports success" — which is how a bug becomes doctrine. An unrecognised key is a 400 and nothing is written; failures now propagate and fail the operation.

## The escape hatch, and what it costs

[0016](0016-the-rock-runtime-lives-at-a-fixed-path.md) put the read/write boundary in code: `ROCK_ALLOW_WRITES=1`, set only by `rock-build`'s `rock.sh`. `api_request` does not touch that boundary — it sits inside `rock_build.py`, behind the same guard, reached through the same entry point. What it loosens is narrower and worth naming: **on the write side, a write no longer has to be one the script anticipated.** Until now the set of possible changes was the operation table. Now it is whatever the Rock account has permission to do.

That is a real loss of a real constraint. It is still the right trade, because the constraint was not holding. Rock has hundreds of entities and this plugin names a couple of dozen; when a request landed outside them, the honest options were to give up or to guess at an operation that does not exist. What actually happened was neither: people with `rock-tools` checked out went and used it — no guard, no plan file, no confirmation — and people without it were stuck. A boundary that pushes work onto an archived repo is not protecting anything.

`api_request` is deliberately thin. No field maps, no name resolution, no conveniences: what you write is what Rock receives. The guards are the whole safety story:

- the method is one of GET, POST, PATCH, PUT, DELETE;
- the endpoint is a path under `/api/` — no scheme, no leading slash, no `..` segment, so an authenticated session cannot be aimed elsewhere or climbed out of. The percent-decoded form is checked too, because `requests` forwards `%2e%2e` untouched and the server is what decodes it;
- `PATCH` and `PUT` both need a non-empty body. An empty `PATCH` would change nothing and report success; an empty `PUT` would null every column in the row, which is the bug at its purest;
- `PUT` is refused without `"full_replace": true`, and refused again if the row could not be read and written to disk first;
- the request is printed before it is sent, and the skill requires the same yes as every other operation.

`GET` is in that list on purpose. Building an honest `full_replace` body means reading the entity first, and a caller that cannot read has to guess at field names.

### The snapshot is a precondition, not a courtesy

`rock-tools` had a `safe_put` that backed the row up before replacing it, and its own instructions said to use it and never a bare `put`. That did not come across in the split, and it is the better half of the idea — an instruction saying *always use the safe one* is an instruction someone eventually does not follow.

So the snapshot is not advice here. Before a `PUT`, `api_request` reads the entity and writes it to `$ROCK_HOME/snapshots/`, and if that read fails for any reason — a 404, a permission, a typo in the endpoint — the `PUT` does not go. Whatever stopped the read would also have stopped anyone undoing the write. It is the one write in this runtime that earns a file on disk, and the only place the old `safe_put` habit is enforced rather than requested.

## Six group operations, and a skill to reach them

Group, GroupMember and GroupSync were never covered, which is the gap the reports came from. `create_group`, `update_group`, `add_group_member`, `update_group_member`, `remove_group_member` and `create_group_sync` cover it.

They got their own skill rather than a row in the repair table. Adding an operation to the script does not make it reachable: the router matches a request against skill descriptions, and "add her to the serving team" matches nothing in a skill that describes itself as repairing workflows. Unreachable-because-undescribed is the exact failure mode being fixed here — `rock_client.py` was in the runtime the whole time, and the reason nobody used it as a fallback is that no skill named it. `create_checkin_area` stays with the create operations: it builds a check-in structure with locations and schedules, not a roster.

## Considered options

- **Keep `PUT` and send the entity back whole.** Read, merge, write. Correct, and what a caller who truly means to replace an entity must do. Rejected as the default because it doubles the request count, and because a read-modify-write with no concurrency control turns a partial update into a last-writer-wins overwrite of fields nobody in the conversation mentioned.
- **Leave the attribute-value warnings alone and document them.** Rejected: the warning said "could not set X" while the report said the entity was created, and a plugin that reports success for a write that never happened is worse than one that fails. There is no wording that fixes that.
- **No escape hatch — extend the operation table instead.** The safer-looking option, and the one that has been failing quietly. Every extension is a guess at which entity comes up next, each one is a schema this plugin has to keep, and the request that falls outside still falls outside. Rejected on the evidence: the fallback people actually reached for was an archived repo with no guard at all.
- **Put `api_request` in `rock` rather than `rock-build`.** Rejected outright. It writes, so it belongs on the write side of [0013](0013-rock-splits-into-read-and-write.md), and putting a generic writer in the read-only plugin would undo the split. *[0023](0023-rock-is-one-plugin-with-one-skill.md) undid the split for other reasons, so this now reads as an argument for keeping `api_request` behind `rock.sh`'s guard — which it is.*
- **Add the group operations to the repair table.** Fewer skills, and the operations would be there. Rejected: nothing would route to them. A group has different entities, a different confirmation — removing a member is not archiving a group — and different ways to get it wrong.

## Consequences

CI now carries a check for this bug class ([0010](0010-curator-merges-ci-guards.md)): `rock-write-shapes` fails on `client.put(` in any function or method except `api_request`, and on `/AttributeValues` in any string the code actually sends. The second half reads the parse tree rather than the text of each line, because a comment or a docstring naming the dead route is documentation and no pattern over raw lines tells the two apart — this ADR's own explanation of the bug would have failed the check that forbids it. What it catches is the shape and not the intent, so a new whole-entity replace that genuinely needs `PUT` has to be added to the allow-list by name, which is the review conversation we want. The test suite runs in CI too, which it did not before.

`api_request` has no shape a reader can check. The named operations can be read against the table in the skill; this one is method, URL and body, and the only check is the person answering yes. The skill says so, and says to read the entity before changing it. If that turns out not to be enough, the fix is a narrower allow-list of endpoints, not another paragraph of instructions.

The rows already damaged are not repaired by any of this. Entities updated through the old path have a null `CreatedDateTime`, a null creator, and a Guid that is not the one they were created with. The Guid churn is the part that cannot be reconstructed — `/api/Audits` records what changed, but nothing records what the Guid used to be. A fingerprint query (null `CreatedDateTime` with a 2026 `ModifiedDateTime`) puts an upper bound on the affected rows in each table; it is an upper bound rather than a count because some of Rock's own seeded entities legitimately have null audit fields.

The repair and create skills both stated the swallowed-warning behaviour as if it were designed. Both were corrected. The general point is that a skill describing a bug in confident prose is harder to find than the bug, and skills should not explain why a failure is acceptable.

> *That pass missed two more of them, both in `create_workflow`: a category that resolved to nothing, and a form field naming an attribute the plan never defined. Each printed `Warning:`, carried on, and let the report say created — a workflow filed nowhere, and a form collecting less than the plan asked for. The reference describing the output said both were expected and told the reader to note what is missing, which is the same doctrine one section further down from the sentence above. Both are recorded failures now, and CI carries `rock-build-reports`: no handler in `rock_build.py` may print, because printing is how these two got past a reader twice.*
