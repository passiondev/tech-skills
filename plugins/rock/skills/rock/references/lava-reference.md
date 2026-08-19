# Lava Reference for Rock RMS

Lava is Rock's template language, based on Liquid (Shopify). It's used in email templates, content blocks, workflow action templates, webhook handlers, and form headers/footers.

## Core Syntax

### Variables
```
{{ variable }}
{{ person.FirstName }}
{{ Workflow | Attribute:'Email' }}
```

### Filters
```
{{ 'hello' | Upcase }}                    → HELLO
{{ 'Hello World' | Downcase }}            → hello world
{{ 'hello-world' | Replace:'-',' ' }}     → hello world
{{ name | Default:'Guest' }}              → Guest (if name is empty)
{{ amount | FormatAsCurrency }}           → $1,234.56
{{ date | Date:'MMMM d, yyyy' }}          → March 13, 2026
{{ items | Size }}                         → 3
{{ text | Truncate:100 }}                 → first 100 chars...
{{ text | StripHtml }}                    → plain text
{{ text | Escape }}                       → HTML-escaped
{{ text | NewlineToBr }}                  → <br> for newlines
{{ number | Plus:5 }}                     → adds 5
{{ number | Times:2 }}                    → multiplies by 2
{{ items | First }}                       → first item
{{ items | Last }}                        → last item
{{ items | Join:', ' }}                   → comma-separated
{{ items | Sort:'Name' }}                 → sorted by Name
{{ items | Where:'IsActive','true' }}     → filtered
```

### Control Flow
```
{% if person.Email != '' %}
  Has email: {{ person.Email }}
{% elsif person.PhoneNumber != '' %}
  Has phone: {{ person.PhoneNumber }}
{% else %}
  No contact info
{% endif %}

{% unless person.IsDeceased %}
  Active member
{% endunless %}

{% case status %}
  {% when 'Active' %}Active{% when 'Inactive' %}Inactive{% else %}Unknown
{% endcase %}
```

### Loops
```
{% for member in group.Members %}
  {{ member.Person.FullName }}
{% endfor %}

{% for item in items limit:10 offset:5 %}
  {{ forloop.index }}. {{ item.Name }}
{% endfor %}
```

## Rock-Specific Tags

### Entity Commands
```
{% person where:'LastName == "Smith"' limit:'10' %}
  {% for p in personItems %}
    {{ p.FullName }}
  {% endfor %}
{% endperson %}

{% group where:'GroupTypeId == 25' %}
  {% for g in groupItems %}
    {{ g.Name }} ({{ g.Members | Size }} members)
  {% endfor %}
{% endgroup %}

{% campus %}
  {% for c in campusItems %}
    {{ c.Name }}
  {% endfor %}
{% endcampus %}
```

### SQL Tag
```
{% sql %}
  SELECT TOP 10 p.FirstName, p.LastName, p.Email
  FROM Person p
  WHERE p.IsDeceased = 0
  ORDER BY p.CreatedDateTime DESC
{% endsql %}

{% for row in results %}
  {{ row.FirstName }} {{ row.LastName }}
{% endfor %}
```

### Workflow Tags
```
{% workflowactivate workflowtypeid:'42' %}
  Workflow activated: {{ Workflow.Id }}
{% endworkflowactivate %}
```

### Web Request
```
{% webrequest url:'https://api.example.com/data' return:'response' %}
{% endwebrequest %}
{{ response }}
```

### Cache
```
{% cache key:'my-data' duration:'3600' %}
  {{ expensive_computation }}
{% endcache %}
```

## Workflow Context Variables

Inside workflow actions, these variables are available:

```
{{ Workflow.Id }}
{{ Workflow.Name }}
{{ Workflow.Status }}
{{ Workflow | Attribute:'AttributeKey' }}
{{ Activity.Name }}
{{ CurrentPerson.FullName }}
{{ CurrentPerson.Email }}
```

## Common Email Template Patterns

### Simple notification
```html
<p>Hi {{ Workflow | Attribute:'FirstName' }},</p>
<p>Thank you for signing up as a volunteer!</p>
<p>We'll be in touch soon with next steps.</p>
```

### With conditional content
```html
{% assign ministry = Workflow | Attribute:'Ministry' %}
<p>You've been assigned to the <strong>{{ ministry }}</strong> team.</p>
{% if ministry == 'Kids' %}
  <p>Please complete the background check at the link below.</p>
{% endif %}
```

### Staff notification with details
```html
<h3>New Volunteer Signup</h3>
<table>
  <tr><td><strong>Name:</strong></td><td>{{ Workflow | Attribute:'Name' }}</td></tr>
  <tr><td><strong>Email:</strong></td><td>{{ Workflow | Attribute:'Email' }}</td></tr>
  <tr><td><strong>Phone:</strong></td><td>{{ Workflow | Attribute:'Phone' }}</td></tr>
  <tr><td><strong>Ministry:</strong></td><td>{{ Workflow | Attribute:'Ministry' }}</td></tr>
</table>
```

## Common Content Block Patterns

### Dynamic list
```html
{% group id:'42' %}
  <ul>
  {% for member in group.Members %}
    <li>{{ member.Person.FullName }}</li>
  {% endfor %}
  </ul>
{% endgroup %}
```

### Conditional visibility
```html
{% if CurrentPerson %}
  <p>Welcome back, {{ CurrentPerson.NickName }}!</p>
{% else %}
  <p>Please <a href="/login">log in</a> to continue.</p>
{% endif %}
```
