# Lava

Lava is Liquid plus Rock-specific filters and entity commands. An unknown filter
name renders as silence rather than an error, so take filter names from the
reference rather than from memory:

- `lava-reference.md` — read before writing any template: syntax, filters, entity
  commands, control flow
- `action-types.md` — read when the template goes in a workflow action: the action
  components and their settings
- `block-types.md` — read when the template goes in a page block: the block types
  and their attributes
- `coding-standards.md` — read before writing any template that lands in Rock:
  support header, numbered SECTIONS, comments, naming, SQL and CSS formatting, and
  the pre-deploy checklist

## The three things that come up constantly

```lava
{{ Workflow | Attribute:'Email' }}      workflow attribute value
{{ CurrentPerson.FullName }}            the logged-in person
{{ Person | Attribute:'Allergies' }}    a person attribute
```

Attribute keys are case-sensitive and are the **key**, not the label shown in the
UI. Get the real key from `query attributes "<workflow>"` rather than guessing
from the label — "Email Address" is usually `EmailAddress` but is sometimes
`Email`, and the wrong one renders empty.

## Writing templates

Emails render in Outlook, so use HTML tables for structured data and inline
styles. A `<div>` grid that looks right in a browser will not survive.

Guard anything that can be empty. An unset attribute renders as nothing, which
turns "Hi {{ name }}," into "Hi ," in someone's inbox:

```lava
Hi {{ Workflow | Attribute:'FirstName' | Default:'there' }},
```

## When a template misbehaves

| Symptom | Usual cause |
| --- | --- |
| Renders blank | Wrong attribute key, or the attribute is genuinely empty |
| Shows `{{ ... }}` literally | The field does not run Lava, or the block has Lava disabled |
| Nothing after a certain point | A `{% %}` tag left unclosed |
| Works for you, blank for others | `CurrentPerson` — null in workflows and background jobs |
| Filter has no effect | Filter name is wrong |

`{% sql %}` and `{% webrequest %}` exist and are almost never the right answer in
a template. If you find yourself reaching for either, say so and ask — the work
usually belongs in a workflow action or a data view instead.
