# Mechanical Design Agent

An experimental mechanical engineering agent built with DeepSeek Harness and deterministic engineering calculation tools.

**Status: V0.3 Prototype — deterministic torque, pure-torsion shaft sizing, and combined bending-torsion shaft sizing workflows validated.**

## Current capabilities

V0.3 supports:

- Deterministic transmitted torque calculation from power and rotational speed.
- Theoretical minimum diameter of a solid circular shaft under pure steady torsion from torque and allowable shear stress.
- Combined bending and torsion theoretical sizing using the maximum shear stress criterion.
- Static reaction and maximum bending-moment analysis for a simply supported shaft with one transverse point load (one plane; no distributed or dynamic loading).
- Machine-readable JSON calculator outputs.
- Each calculator output includes a stable `model_id`.
- Machine-readable engineering model provenance registry.
- Runtime model provenance is resolved deterministically from calculator model IDs to Engineering Model Cards and registered sources.
- Deterministic engineering result reviewer with inverse, equilibrium, and consistency checks across four registered engineering models.
- Engineering calculator outputs are gated by the deterministic reviewer before the DSH agent accepts them.
- Registered source attribution distinguishes underlying relations from project derivations and approximations.
- DeepSeek Harness project Skills for transmitted torque, single-point-load statics, pure-torsion solid-shaft sizing, and combined bending-torsion sizing.
- A combined bending and torsion DSH Skill with load-state-aware selection between pure-torsion and combined strength models.
- Automatic natural-language Skill discovery and multi-Skill chaining: power and speed → torque → theoretical minimum shaft diameter.
- Calculator JSON is the sole numerical authority; the Skills prohibit Agent-side recalculation, substitution, and rounding of results.
- Torque → combined shaft sizing chaining when power, speed, and bending moment are provided.
- Load → statics → combined-strength chaining, with every calculator result gated by the deterministic reviewer.
- Unambiguous unit conversion before calculation; ambiguous or missing parameters require clarification.
- Scope-boundary protection for unsupported analyses and invalid-input rejection, including zero rotational speed.
- Pytest regression tests.

The pure-torsion and combined bending-torsion calculators return theoretical minimum diameters for a solid circular shaft under steady loading. The agent now selects between pure-torsion and combined bending-torsion models based on the stated load condition.

This is not a general shaft loading system or a complete shaft-design system. Neither strength model accounts for fatigue, alternating loads, stress concentrations, shoulders, keyways, shock/dynamic effects, stiffness, deflection, critical speed, or standard preferred diameters. Final shaft sizing, bearing selection, CAD/CAE integration, reviewer agents, and multi-agent workflows are not implemented.

## Architecture

```text
User request
    ↓
DeepSeek Harness
    ↓
transmission-torque Skill → torque calculator → JSON torque_nm (when power and speed are given)
shaft-point-load-statics Skill → statics calculator → JSON reactions and max_bending_moment_nm (when one transverse point load is given)
    ↓ (select from the stated load condition)
solid-shaft-torsion Skill → shaft_torsion calculator → JSON min_diameter_mm (pure torsion)
combined-shaft-loading Skill → shaft_combined calculator → JSON min_diameter_mm (bending present)
    ↓
Natural-language explanation
```

The Agent chooses and sequences independent Skills; deterministic Python calculators perform the engineering arithmetic. When chaining, the Agent passes the original `torque_nm` value from the torque calculator's JSON to the selected shaft calculator without rounding or recomputing it. The provenance resolver uses each calculator's `model_id` to load its Engineering Model Card and registered sources; it does not calculate engineering results. The Skills use calculator JSON for numerical results and resolver JSON for model and source facts.

## Setup

From the repository root, create and activate the Conda environment, then install the package:

```powershell
conda env create -f environment.yml
conda activate mech-agent
python -m pip install -e .
```

Start DeepSeek Harness from the repository root so it can discover the project Skill.

## First Example

Run the calculator directly:

```powershell
python -m mechanical_agent.calculators.torque --power-kw 5.5 --speed-rpm 960
```

Example JSON output:

```json
{
  "model_id": "transmitted_torque_v1",
  "power_kw": 5.5,
  "speed_rpm": 960.0,
  "torque_nm": 54.713541666666664,
  "formula": "T = 9550 * P / n",
  "constant": 9550.0
}
```

In DeepSeek Harness, the same workflow can start from a natural-language request:

> 一台机械传动系统输入功率为 5.5 kW，转速为 960 r/min，请求出传递转矩。

The torque calculator uses `T = 9550 × P / n`, with `P` in kW, `n` in r/min, and `T` in N·m. The constant 9550 is the project's engineering approximation.

## Project Structure

```text
mechanical-design-agent/
├─ .dsh/skills/
│  ├─ transmission-torque/SKILL.md
│  ├─ solid-shaft-torsion/SKILL.md
│  ├─ combined-shaft-loading/SKILL.md
│  └─ shaft-point-load-statics/SKILL.md
├─ examples/
├─ knowledge/
│  ├─ README.md
│  ├─ sources.toml
│  └─ models/
│     ├─ transmitted_torque.toml
│     ├─ solid_shaft_pure_torsion.toml
│     ├─ solid_shaft_combined_tresca.toml
│     └─ simply_supported_point_load.toml
├─ outputs/
├─ src/mechanical_agent/
│  ├─ __init__.py
│  ├─ knowledge_registry.py
│  └─ calculators/
│     ├─ __init__.py
│     ├─ torque.py
│     ├─ shaft_torsion.py
│     ├─ shaft_combined.py
│     └─ shaft_statics.py
├─ tests/
│  ├─ test_torque.py
│  ├─ test_shaft_torsion.py
│  ├─ test_shaft_combined.py
│  └─ test_knowledge_registry.py
├─ .gitattributes
├─ .gitignore
├─ environment.yml
├─ pyproject.toml
└─ README.md
```
