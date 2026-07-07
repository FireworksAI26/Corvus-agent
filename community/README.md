# Community skills

Shareable skill packs for Corvus. Import one with:

```bash
corvus skills import community/skills-starter.json
# or straight from a URL
corvus skills import https://example.com/someones-skills.json
```

Share your own:

```bash
corvus skills export my-skills.json
```

Then open a merge request adding your JSON file to this folder so others can
import it. Please keep skills small, general, and dependency-light, and never
include secrets or credentials.
