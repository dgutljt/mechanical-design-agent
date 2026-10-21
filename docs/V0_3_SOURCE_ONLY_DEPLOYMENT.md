# v0.3.0 SOURCE-ONLY 源码交付与部署范围

状态日期：2026-10-21；Phase 14D-R2 修订（Experimental 预发布文档准备）。
R1 后独立 Reviewer 裁决：旧 Native 负零 P2 的披露延期已**有条件接受**（见“未关闭缺陷及安全门禁”），
原条件与适用范围保留；C3 / C4 门禁状态不变。
产品源码基线：`76bcad589b17764a7162b85860d68df28580bdbd`。
Python 项目及 Plugin：**0.3.0**；DSH / DSH Tools / Win32 process provider：**0.2.0-rc.2**。
正式发布基线仍为 **v0.2.0**；本说明不构成 Commit、Push、Tag 或 Release 授权。

**当前发布门禁未通过。** C2 仅证明特定已有依赖条件下的源码部署及部分真实运行成功；
C2 整体为 BLOCKED，C3 独立结论仍为 **INSUFFICIENT EVIDENCE / BLOCKED**。
C4-S0 只读取证方案已完成但未获独立技术验收；动态 C4 未执行，虚拟机工作暂停。
不能据此声称 v0.3.0 已具备正式发布资格或独立技术 PASS。

门禁区分（2026-10-21）：C3 PASS 是**正式运行时发布**（含完整安全验收的稳定版本）的前提，
不是任何形式源码公开的统一前提。`v0.3.0-experimental.1` 属**实验性源码快照**：
仅作为开发阶段源码记录，随附未关闭门禁与已知问题披露（见
[KNOWN_ISSUES](../KNOWN_ISSUES.md) 与[发布说明](releases/v0.3.0-experimental.1.md)），
不宣称任何安全验收。实验性源码归档不构成运行时安全验收，
不能据此宣称新增 Supervisor 已具备可靠隔离保证。

## 交付边界与证据等级

本交付范围仅为指定源码基线的**完整 Git checkout / 完整源码归档及本地 Plugin 构建**。
editable source 是必须保留源码树的部署形式，不是普通 wheel 安装。
不将 wheel、sdist 或独立 npm Plugin 包列为完整 Agent 安装交付物。
具体取证与后续批准仍是正式发布前提；任何 v0.3 标签或 Release 都不能替代按 commit ID 核验的来源证明。

本说明中的“已验证”仅指下列 C2 原有证据，本轮未重跑安装、构建或测试。
“静态核查”只说明源码约束；“UNVERIFIED”表示缺少对应部署/运行证据。

| 项目 | C2 已有结果及限制 |
| --- | --- |
| 干净源码归档 | 指定 HEAD 的 132 个受跟踪文件，最终逐字节核对无变化；9 张模型卡、3 条来源记录及配套资源齐全。该数量不含本轮新增说明 |
| Python 源码部署 | 独立 venv，Python 3.12.14；隔离目录的 `src` 与同根 `knowledge`；从归档外使用 `-I`、无 `PYTHONPATH` 验证 |
| Editable 安装 | PEP 660 离线 editable 成功，metadata 为 0.3.0，`direct_url` 指向隔离源码；两条生产探针在旧 Bridge / 新 Runner 实际调用中通过 |
| Plugin 构建 | 0.3.0，Node 24.18.0 / npm 11.16.0；从源码重建全部 15 个 JS 输出，没有复用正式目录的 `dist` |
| 依赖条件 | 使用既有可信本机资源；Node 依赖以 Junction 指向既有缓存树。DSH / Tools / Win32 provider 0.2.0-rc.2，Koffi 3.1.1，Schemastery 3.18.4。不是干净依赖下载验证 |
| 真实运行 | 默认 11 Tool 的三个旧工程操作、显式 12 Tool 的 Supervisor / Workflow / Reviewer / Provenance / Lineage / Handoff；新字符串载体 signed-zero 往返和失败封闭场景；新会话 11 → 12 → 11 |
| Python 完整回归 | 853 passed，0 failed，0 skipped |
| Plugin 回归 | **146 项：136 passed、1 failed、9 skipped**；失败为 `a1-lifecycle`，不属于全绿验收 |
| V1 / Golden、双平面 Demo | 通过；仅对应已执行的源码路径 |
| P1C | 首次 28 项中 19 通过、9 项 Junction EPERM 失败；同源码权限复验 28/28 通过，首次失败记录保留 |
| V1.5 | **未运行**；发现安全相关失败后停止。预先生成的 `v15.json` 是运行规格，不是执行/通过记录 |
| 回收 | 已记录外层 Job 最终为空；不能替代目标运行期间的指定 Job 成员关系证据 |

C2 的基础解释器来自已有环境，venv 正常复用其标准库；没有启用旧项目 site-packages
或以旧项目 distribution 冒充隔离源码。Python 构建/测试工具亦复用本机已有可信资源；
setuptools 83.0.0、wheel 0.47.0、packaging 26.3 的复用不证明任意机器可离线部署。

## 必须保留的目录及来源条件

保留完整受跟踪源码树及相对位置，包括隐藏的 `.dsh/`；不得只复制 Python 模块或 Plugin `dist`。
下表说明用途，不是可以据此裁剪其余受跟踪文件的最小安装清单。

| 源码资源 | 部署用途 |
| --- | --- |
| `src/mechanical_agent/` 全部内容 | Calculator、Reviewer、Workflow / Verified Handoff、Registry resolver、Adapter 等既有实现 |
| `knowledge/sources.toml`、`knowledge/models/*.toml` 及其余 `knowledge/` 文件 | Registry 来源和模型卡；必须与 Python 源码同根同版本 |
| 根 `pyproject.toml`、`environment.yml` | 项目身份、Python 要求及环境参考；版本探针需要源码根的 pyproject |
| `packages/dsh-mechanical-plugin/` 的受跟踪源码、contracts、Supervisor、构建入口、package.json 和测试夹具 | 本地重建 Plugin 与后续验收；`dist` 从同一源码重新生成 |
| `.dsh/mechanical-engineering.patch.yml`、`.dsh/mechanical-overhung.patch.yml`、`.dsh/mechanical-web.patch.yml`、`.dsh/skills/` | 默认/显式 Profile、Web 限制及编排契约 |
| 两个根 `start-mechanical-*.cmd` | 默认 Web 和显式 overhung headless 入口 |
| `scripts/`、`tests/`、`examples/`、`docs/`、README、LICENSE 及其他受跟踪文件 | 配置策略/指纹、后续回归、示例、边界和许可 |

另行提供并校验可信 Python/Node 运行时和依赖；它们不在源码归档中。
`node_modules`、旧 `dist`、venv、Provider 凭证及本机配置不得被当作归档已包含的资源。
本地 `.dsh/mechanical-plugin.local.json` 若使用，应由部署人员单独审查来源并核对实际配置；
Provider/model 配置和秘密单独安全配置，不写入源码或证据共享包。

部署时必须记录并核对：

1. checkout 的完整 commit ID，或归档来自该 commit 的可追溯证明及内容清单；文档分支新增内容单独说明。
   C2 本地 git archive 的 SHA-256 为
   `4e04693f50118ae1c907b08043bf8c9b9d0ff3d304538dea03ac36850ff2a97f`。
   这只是该份本地归档的指纹，**不保证 GitHub 自动归档或重新打包文件具有相同字节/哈希**。
2. Python 解释器真实路径、metadata、`direct_url`、实际模块路径、Registry 根目录与探针身份。
   metadata 0.3.0 单独不能证明运行来源正确。旧 Bridge 注入 `repositoryRoot/src` 并限制源码来源；
   新 Runner 还核对预期 Adapter 的真实文件和根目录。不得放宽或绕过检查。
3. 项目和 Plugin 为 0.3.0，固定运行时/原生依赖版本正确；所有 `dist` 来自本次源码构建。
   Junction 的实际目标、依赖版本和可信来源需留证；C2 的本机缓存路径不是可移植依赖供应方案。
4. 核对 [P1C 策略](../scripts/p1c-policy.json) / [V1.5 策略](../scripts/v15-policy.json) 中的有效配置、旧 Tool 指纹和禁用项。
   仅有配置文件或 `--config-only` 成功不能证明真实挂载和调用。

## 后续部署人员的复现顺序（当前禁止据此恢复动态验收）

以下是候选操作说明，**本轮均未执行**。C3 BLOCKED 解除、独立 Reviewer 明确允许恢复及用户授权前，
不得据此运行完整回归、Windows Job 实验或危险内存测试；本文件也不授权启动 VM。
优先使用独立目录，保留首次失败及来源证据，发现身份不一致或隔离/回收异常即停止。

1. 获取指定 commit 的完整源码，核验上节清单和来源；不要以任何 v0.3 Release 或标签替代按 commit ID 的来源核验。
   正常运行不要求归档含 `.git`，但 V1.5 有 Git 状态前置检查。
   归档无 Git 元数据时的验收方案须另行审查；不得伪造“干净 checkout”充当发布证据。
2. 准备可信 Python 环境及兼容依赖。C2 在新 venv 中预置已有可信构建工具后，
   从源码根使用如下离线 editable 形式（下列 `python` 必须是选定的独立环境）：

   ```powershell
   python -I -m pip install --no-index --no-deps --no-build-isolation -e .
   ```

   这要求构建后端已经可用；命令不会获取缺失依赖。普通 `pip install -e .` 的网络依赖解析、
   可信缓存的制作/分发及全新机器完整离线安装均为 **UNVERIFIED**。
   `PYTHONPATH=src` 是现有源码运行形式，不是 editable metadata 的安装证明。
3. 为 Plugin 准备已校验的依赖树，记录其来源和实际版本。缺少依赖时停止；
   README 中的 `npm install --prefix packages/dsh-mechanical-plugin` 是设置指导，
   其全新机器解析/下载结果为 **UNVERIFIED**。没有完整 npm lockfile，不能保证重装得到 C2 的完整依赖树。
4. 从同一源码根选择解释器并构建，不复用其他 checkout 的产物：

   ```powershell
   $env:MECHANICAL_AGENT_PYTHON = (python -c "import sys; print(sys.executable)").Trim()
   $env:MECHANICAL_AGENT_TEST_PYTHON = $env:MECHANICAL_AGENT_PYTHON
   node packages/dsh-mechanical-plugin/scripts/build.mjs
   ```

   使用实际生产探针核验 0.3.0、模块路径、Registry 可达及根目录；同时独立检查 editable metadata
   和来源。探针通过不是 Supervisor 生命周期验收。
5. 按下一节选择 Profile。详见 [README 部署入口](../README.md#using-with-deepseek-harness)
   和[悬伸工作流](VERIFIED_OVERHUNG_SHAFT_WORKFLOW.md)。
   Provider/model 需单独配置；C2 的真实 ToolRuntime 证据不能扩大为任意提供商、Web UI 或在线会话验收。
6. 只在相关门禁获准后恢复 P1C / V1.5 等验收，保存真实 inventory、Native 结果、完整 TAP、
   跳过名单和回收证据。当前没有“完成上述部署即可发布”的路径。

## 默认 11 Tool 与显式 12 Tool

| 项目 | 默认模式 | Overhung opt-in |
| --- | --- | --- |
| 入口 | `start-mechanical-dsh.cmd` Web；或受限 headless 加 `.dsh/mechanical-engineering.patch.yml` | `start-mechanical-overhung-dsh.cmd`，独立 headless；或显式 overhung patch |
| 工程操作 | `calculate_transmitted_torque`、`analyze_verified_shaft_strength`、`analyze_verified_two_plane_shaft_strength` | 保留旧三个，仅增加 `verified_overhung_two_plane_shaft_strength_chain_v1` |
| Inventory | 11 Tools，另 8 个为既有检索/Skill/计划工具 | 12 Tools，同样保留 16 项禁用配置 |
| 执行边界 | 旧 Bridge / Schema；三个旧 Tool 为 20 秒配置 | 新 Supervisor；15 秒执行预算、至多 3 秒共同恢复窗口，Native 协作超时 18 秒 |
| 传输 | 旧数值契约，仍受下述负零 P2 影响 | 闭合外层 `{request_json: string}` / `{response_json: string}`，内部数值包保真 |
| 启用条件 | 既有默认 patch，Web 另加 web patch | `enableVerifiedOverhung: true`；缺失/无效 opt-in 或加载失败即停止，无降级 |

新 Tool 需显式接受全轴恒定扭矩假设；它不是旧简支双平面工具的自动等价替代。
成功载体还必须检查内部 `ok`、errors、三项 Reviewer、Provenance 和 Lineage。
裸 `headless` 是开发 Profile，不是受限产品入口。
Overhung 启动器使用临时独立 `DSH_HOME`、无 HTTP 监听，不自动复制默认 Provider 凭证；
历史启动/EOF 检查不证明非空模型请求已完成。

停用时先退出显式会话，再开默认入口、不应用 overhung patch，并核验实际 inventory 回到 11。
现有会话需单独结束，Profile 切换不回退源码、Python 或 Plugin 版本。
回到 v0.2.0 需独立 checkout、对应环境、重建 Plugin、核对探针和配置；
见 [README 回退步骤](../README.md#returning-to-released-v020)。
完整跨版本重新安装/运行回退为 **UNVERIFIED**，不能以 Tag 可读取或 Profile 切换代替。

## 安装包缺口与 UNVERIFIED 范围

14D-C 原有安装实验确实构建并安装了 wheel，metadata 为 0.3.0；
简单 Calculator 可运行，完整 Adapter 因 Registry 不可达而 `REVIEW_FAIL`、失败封闭。
不能称作完整 Agent 安装成功。

- wheel 与 sdist 均缺少 `knowledge/sources.toml` 及模型卡；Registry 沿源码模块祖先查找 `knowledge/`。
- wheel 还缺少当前版本探针依赖的根 `pyproject.toml`。
- sdist 不包含完整 Plugin / Profile / 启动器配套，不能替代完整 Git 源码归档。
- Bridge / Runner 的源码布局和来源绑定仍然存在，仅补数据文件不能实现普通 site-packages 安装。
- Plugin 为 `private: true`，没有独立 npm 安装交付的验收证据。

以下均为 **UNVERIFIED**：全新机器环境准备与依赖获取；不依赖现有本机缓存的完整离线安装；
完整依赖锁定及字节级可复现构建；Windows 10、其他 Windows build/edition、Windows Server、
ARM64、非 Windows；Node/Python 的完整版本矩阵及精确最低版本兼容性。
声明的 Python >=3.12 / Node >=24 不等于整个版本范围已测试。
已有 Windows 11 x64 10.0.26200 系列环境记录不能证明其他系统；
C2 的 Python 3.12.14 venv 功能成功也不能抹去同环境生命周期失败。
LF/CRLF 完整矩阵、缓存 Junction 的通用权限可移植性和完整回退部署也为 **UNVERIFIED**。
生产隔离还要求 creation-time Job-list 和 nested Jobs 可用，无弱化回退。

## 未关闭缺陷及安全门禁

**旧 Native 双平面负零 P2：** 已有独立复现中，一个平面为空时 Python 产生 `-0.0`，
DSH rc.2 数值/输出校验拒绝，旧 Bridge 返回 `INTERNAL_ADAPTER_ERROR`，用户无法取得成功工程结果。
已证实路径失败封闭，没有证据显示错误工程结果被释放。其他加权和为零情形也可能触发，属于静态推断，
不能声称触发范围仅限空平面。C2 同一示例的直接 Python Adapter 三项 Reviewer PASS，
只证明该示例源码路径可用；DSH 等价绕行办法为 **UNVERIFIED**。
不得人为改载荷、改用 overhung 模型或改写负零充当已验收解决方案；未修复，修复计划/时间未定。
延期裁决（2026-10-21）：独立 Reviewer 已**有条件接受**该 P2 的延期——保留上述原条件与适用范围：
失败封闭行为不得放宽，触发范围不得缩小为仅空平面，DSH 等价绕行仍为 UNVERIFIED，
并在实验性发布中以已知问题形式披露（KI-NUM-002）。延期不构成修复或技术 PASS；
问题保持未修复状态，直至按原验收标准修复并复验。

**生命周期异常：** C2 的 `a1-lifecycle` 预期 `BREAKAWAY_DENIED`，实际 `ESCAPED`。
C3 确认该文字由父 Python 在 Popen 返回后打印；它既不能证明目标实际逃离指定 Supervisor Job，
也不能证明隔离仍然有效。原目标 PID、保留句柄及运行期指定 Job 成员矩阵缺失。
venv 附加 Job 对假阳性的解释有依据但未证实；不能将失败降为随机波动，也不能宣布安全漏洞已排除。
C3 的独立结论为 **INSUFFICIENT EVIDENCE / BLOCKED**，不允许继续 C2 完整回归。
C4-S0 仅为未独立验收的只读方案；动态 C4 未执行，VM 工作暂停，未取得补证。

**九项危险内存测试为 SKIPPED，不是 PASS：**
`a1-memory`、`memory-counters`、`memory-study-1-parallel`、`memory-study-8-parallel`、
`memory-study-32-parallel`、`memory-study-1-serial`、`memory-study-8-serial`、
`memory-study-32-serial`、`memory-native-attempt`。
V1.5 强制这些跳过并检查入口指纹和真实 TAP；裸 `npm test` 不提供该安全默认值，不可作为替代。
这些压力实验需另外授权和独立保护边界，本说明不要求也不授权恢复它们。

资源契约限于 256 MiB/进程、512 MiB/Job 的 committed memory、16 个关联进程及软件期限；
DSH Host 不在工程 Job 内，无瞬时峰值、硬实时或完整恶意代码沙箱保证。
`REAP_FAILED/BLOCKED` 及显式验证恢复是既有失败封闭契约，
不能替代未取得的生命周期安全证据，不能以外层 Job 最终为空宣称无逃逸。

## 发布前仍须取得的证据和批准

1. 独立 Reviewer 审查 C4-S0 证据规格；后续动态工作必须另获明确授权并满足安全前提，
   查明原异常的运行期归属，裁决是否需产品/测试修复。保持原失败断言和验收标准。
2. C3/C4 收敛并由独立 Reviewer 明确允许后，恢复 C2 剩余非高风险回归及 V1.5；
   核对最终候选的 Python、Plugin、P1C、V1 / Golden、双平面 Demo、真实 11/12 Tool、
   必需 Native 调用、来源和回收证据。保留九项 skip，不以历史通过替代缺项或失败。
3. 独立 Reviewer 核验最终候选及本说明的来源条件、源码交付限制、负零 P2 披露/延期处理、
   UNVERIFIED 边界和文档一致性；取得最终技术验收及 Gatekeeper 发布准入。
4. **Commit、Push、Tag、Release 均须用户另行明确授权。**
   本轮没有执行这些操作，既有授权不能从文档准备或源码运行成功推导出来。

## 证据索引与既有文档关系

证据为既有外部验收目录，**不在源码归档内**；交接时须另提供受控原件位置，
仅转交经审查且不含凭据/敏感主机信息的必要记录。以下是证据目录名及文件名，不是产品安装路径：

| 证据 | 已核对内容 |
| --- | --- |
| `phase14dc2-20261019/archive-audit-final.json` | 132 文件、归档哈希、Registry 数量、无变更及扫描结果；扫描未命中不等于通用无秘密保证 |
| 同目录 `editable-install.log`、`python-facts.json` | editable 0.3.0、实际源码/Registry 路径、探针 |
| 同目录 `plugin-build-hashes.json`、`config.stdout` | 构建记录及有效配置/指纹；真实 11/12 Tool 另见 P1C 日志和 C2 对话结论 |
| 同目录 `restore11.json`、`v15.json`、`source-proof.json` | 仅为运行规格，不能单独证明执行成功；11 → 12 → 11 的结论引用既有 C2 对话报告，不将规格当作原始结果 |
| 同目录 `python.stdout`、`plugin.stdout`、`golden.stdout`、`twoPlane.stdout` | Python 853、Plugin 136/1/9、两项 Demo；不得只摘取绿色汇总 |
| 同目录 `p1c.stdout`、`p1c-recheck.stdout` 及对应 Job 记录 | 首次权限失败和 28/28 复验；外层清空不证明运行期指定成员关系 |
| 同目录 `p2-python.json` | 指定空平面输入的 Python Adapter 成功，不能证明旧 Native P2 已修复 |
| `phase14dc-20261019/installed-facts.json` 及原制品清单 | 普通 wheel 安装事实与 Registry/探针失败；不是源码部署成绩 |
| 既有 C2 / C3 对话结论；本次 R1 用户提供的 C4-S0 基线 | C2 整体 BLOCKED；C3 INSUFFICIENT EVIDENCE / BLOCKED；S0 完成但未独立验收及动态 C4 未执行，S0 状态未在本轮独立复验 |

README 的历史 14D-A 数量和旧“本轮未 reinstall”描述只适用于对应历史轮次；
C2 后来完成的是**隔离源码 editable 安装**，不能扩大为普通发行包安装。
[悬伸工作流](VERIFIED_OVERHUNG_SHAFT_WORKFLOW.md) 和 [P1B](PHASE_14C_P1B_SUPERVISOR_CONTRACT.md) /
[P1C](PHASE_14C_P1C_NATIVE_TRANSPORT_CONTRACT.md) 契约中的历史结果/设计约束不覆盖新的 C2 FAIL。
如旧文档中的“运行验证”“safe acceptance”被理解为当前发布许可，应以本说明列出的
未关闭门禁为准；发现实际证据冲突交独立 Reviewer 裁决，不自动提升为 PASS。
