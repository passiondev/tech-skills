# Two plugin layers: capabilities hold skills, departments bundle them

Plugins come in two kinds. **Capability plugins** contain the skills. **Department bundles** contain no skills at all — only a `dependencies` array naming the capability plugins that department needs, plus `general`. Installing `local-engineering` therefore installs everything a local engineer needs in one command.

The goal was that a person installs their department and is done. The obstacle is that most skills serve more than one department, and a single flat layer forces a bad trade: either duplicate the skill into every department that needs it, or push it into `general` where the departments that don't need it carry it anyway. Claude Code's plugin `dependencies` resolve this directly — a shared dependency is installed once, auto-installed with its parent, auto-enabled with its parent, and refuses to be disabled while another enabled plugin still needs it.

The layers also have opposite naming pressures, which is a reason to keep them apart rather than an accident of the design. A skill's namespace comes from the plugin that *contains* it, so capability plugin names get typed constantly and must be short: `/rock:workflow`, `/dev:tdd`. Department bundle names are never typed, only installed, so they can be as long and unambiguous as the org chart needs: `service-and-support`.

## Consequences

Re-organising the tech team means editing dependency arrays, not moving skill files. But renaming or removing a department bundle after people have installed it needs a `renames` entry in `marketplace.json`, or their installs break.

Both layers appear in the `/plugin` Discover list — there is no way to hide the capability plugins from someone browsing. `category` on each marketplace entry is what keeps the list legible.
