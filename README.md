# Mechanical Design Agent

An experimental mechanical engineering agent built with DeepSeek Harness and deterministic engineering calculation tools.

**Status: V0.1 Prototype — first end-to-end mechanical calculation workflow validated.**

## Current Capability

V0.1 supports:

- Transmitted torque calculation from power and rotational speed.
- Deterministic Python engineering calculation with JSON machine-readable output.
- A DeepSeek Harness project Skill at `.dsh/skills/transmission-torque/SKILL.md`.
- Automatic Skill discovery from natural-language requests.
- Unit conversion for unambiguous power and speed units before calculation.
- Invalid-input rejection, including zero rotational speed.
- Pytest regression tests.

It does not yet support shaft sizing, bending analysis, fatigue analysis, bearing selection, CAD/CAE integration, reviewer agents, or multi-agent workflows.

## Architecture

```text
User request
    ↓
DeepSeek Harness
    ↓
transmission-torque Skill
    ↓
Shell tool
    ↓
Python deterministic calculator
    ↓
JSON result
    ↓
Natural-language explanation
```

The LLM decides what calculation is required; deterministic Python code performs the engineering arithmetic. The Skill requires the Agent to use the calculator's `torque_nm` JSON field for the final numerical result.

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

The engineering formula used by this V0.1 calculator is `T = 9550 × P / n`, with `P` in kW, `n` in r/min, and `T` in N·m. The constant 9550 is the project's engineering approximation.

## Project Structure

```text
mechanical-design-agent/
├─ .dsh/skills/transmission-torque/SKILL.md
├─ examples/
├─ knowledge/
├─ outputs/
├─ src/mechanical_agent/
│  ├─ __init__.py
│  └─ calculators/
│     ├─ __init__.py
│     └─ torque.py
├─ tests/test_torque.py
├─ .gitattributes
├─ .gitignore
├─ environment.yml
├─ pyproject.toml
└─ README.md
```
