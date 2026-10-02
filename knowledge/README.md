# Engineering model provenance

`knowledge/` is an engineering model provenance registry, not an LLM memory dump.

```text
User
  ↓
DSH Skill
  ↓
Deterministic Calculator
  ↓
Engineering Model Card
  ↓
Source Registry
```

The calculator determines the numerical result. Each TOML model card records what the model is, its assumptions and units, which source supports it, and what it cannot do. `sources.toml` contains source metadata and public references. The deterministic provenance resolver loads these files at runtime using the calculator's `model_id`; it reports model and source facts without calculating engineering results.
