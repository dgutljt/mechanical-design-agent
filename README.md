# Mechanical Design Agent

An experimental mechanical engineering agent built with DeepSeek Harness and deterministic engineering calculation tools.

**Status: V0.2 Prototype — transmitted torque and theoretical pure-torsion shaft sizing workflows validated.**

## Current capabilities

V0.2 supports:

- Deterministic transmitted torque calculation from power and rotational speed.
- Theoretical minimum diameter of a solid circular shaft under pure steady torsion from torque and allowable shear stress.
- Machine-readable JSON calculator outputs.
- DeepSeek Harness project Skills for transmitted torque and pure-torsion solid-shaft sizing.
- Automatic natural-language Skill discovery and multi-Skill chaining: power and speed → torque → theoretical minimum shaft diameter.
- Unambiguous unit conversion before calculation; ambiguous or missing parameters require clarification.
- Scope-boundary protection for unsupported analyses and invalid-input rejection, including zero rotational speed.
- Pytest regression tests.

The shaft result is a theoretical pure-torsion minimum diameter, not a final shaft design diameter. It does not account for bending, fatigue, keyways, stress concentration, shock or dynamic loading, stiffness, or standard preferred diameters. Final shaft sizing, bearing selection, CAD/CAE integration, reviewer agents, and multi-agent workflows are not implemented.

## Architecture

```text
User request
    ↓
DeepSeek Harness
    ↓
transmission-torque Skill → torque calculator → JSON torque_nm
    ↓ (when shaft sizing is requested)
solid-shaft-torsion Skill → shaft_torsion calculator → JSON min_diameter_mm
    ↓
Natural-language explanation
```

The Agent chooses and sequences independent Skills; deterministic Python calculators perform the engineering arithmetic. When chaining, the Agent passes the original `torque_nm` value from the first calculator's JSON to the second calculator without rounding or recomputing it.

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
│  └─ solid-shaft-torsion/SKILL.md
├─ examples/
├─ knowledge/
├─ outputs/
├─ src/mechanical_agent/
│  ├─ __init__.py
│  └─ calculators/
│     ├─ __init__.py
│     ├─ torque.py
│     └─ shaft_torsion.py
├─ tests/
│  ├─ test_torque.py
│  └─ test_shaft_torsion.py
├─ .gitattributes
├─ .gitignore
├─ environment.yml
├─ pyproject.toml
└─ README.md
```
