---
name: transmission-torque
description: "Calculate transmitted torque from mechanical power and rotational speed using the project's deterministic Python calculator."
whenToUse: "Use when a task asks for transmitted torque and provides power and rotational speed, or values that can be safely converted to kW and rpm."
user-invocable: true
---

# Transmission Torque

## Purpose

Calculate steady transmitted torque from mechanical power P and rotational speed n. The current engineering formula is T = 9550 × P / n, where P is in kW, n is in rpm (r/min), and T is in N·m. The Python calculator uses the textbook approximation 9550.

## Mandatory deterministic calculation

Never compute the final numerical torque in the language model. From the project root, call the existing Python CLI:

```powershell
python -m mechanical_agent.calculators.torque --power-kw <P> --speed-rpm <n>
```

For example:

```powershell
python -m mechanical_agent.calculators.torque --power-kw 5.5 --speed-rpm 960
```

Parse the CLI's JSON output. Its `torque_nm` field is the sole authority for the numerical result. You may explain the formula, but do not replace the Python result with a number calculated by the model. If the CLI fails, report its error and do not invent a result.

## Units and missing information

The CLI accepts `power_kw` in kW and `speed_rpm` in rpm. Convert only unambiguous units before calling it: 5500 W is 5.5 kW; 16 r/s is 960 rpm. State any conversion used. Never guess units. If power or speed units are missing and context does not establish them, ask for clarification before calculating. Inputs explicitly stated in kW and r/min can be used directly.

## Scope

Use this skill for steady transmitted torque, the power-speed torque relation, and requests for transmitted torque with known kW and rpm. The current calculator does not cover starting or transient torque, acceleration inertia torque, motor stall torque, impact loading, cyclic torque, complex dynamics, shaft strength or diameter, or bearing selection. For those tasks, explain that this calculator does not support the requested analysis.

## Runtime

Start DeepSeek Harness from the repository root after `conda activate mech-agent`, using `npx.cmd @deepseek-ai/dsh web`. Its Shell should inherit the activated Python environment. Do not hard-code a machine-specific Python path.
