# 数据格式与迁移

Python 3.10+，仅使用标准库。所有脚本位于 `scripts/`，统一入口 `harness.py`。不需要安装后台服务或生图模型。

## 定位与持久性

位置顺序：`--data-dir`、`PROMPT_HARNESS_DATA_DIR`、`Path.home()/.prompt-assistant/harness`。运行时返回解析后的绝对路径；宿主必须确保该路径跨会话持久。不要将个人数据放进 Skill 源目录、VIP 基线或公开发行 ZIP。

```text
外部用户目录/
  CURRENT                     原子发布的 generation ID
  health.json                 最近健康检查时间（独立轻量状态）
  audit/<generation>.json     当前快照之后的追加审计事件
  generations/<ID>/
    config.json
    user_preferences.json
    learned_overrides.json
    candidates.json
    experiments/<ID>.json
    evolution_log.jsonl
    sessions.json
  backup-<ID>.zip              导入前备份
```

文件均 UTF-8。业务变更写入先独占 `.writer.lock`、重读当前快照，写入并核验新 generation，最后原子替换 CURRENT；读者只能看到完整旧版或新版。旧快照是回滚与配置损坏恢复依据；不要直接修改历史文件，亦不要自动清理它们。断电级耐久性取决于宿主文件系统；网络盘与临时沙盒需额外验证。本版无跨机器同步或锁失效自动接管。崩溃留下锁时，先确认没有写入进程；不要在并发写入时删锁。

发布包 `harness/config.json` 仅默认配置。实际配置在外部快照，版本为 1；数据格式也为 1。损坏配置会保留旧快照，修复为默认关闭并记日志；其他数据损坏拒绝继续写入。可写目录检测使用真实随机字节写入、fsync、重读、清理、业务数据校验和 health.json 原子写入；初始化或修复配置才提交快照；每轮重新执行，旧时间不代表当前权限。

## 命令

下例的 python 表示环境中可执行的 Python 路径；将 DATA 换成当前用户明确的外部持久目录。路径有空格时加引号。`--data-dir` 必须位于子命令前。

```text
python scripts/harness.py --data-dir DATA start --session CHAT_ID --init
python scripts/harness.py --data-dir DATA check
python scripts/harness.py --data-dir DATA toggle on
python scripts/harness.py --data-dir DATA toggle off
python scripts/harness.py --data-dir DATA feedback --input feedback.json
python scripts/harness.py --data-dir DATA query --context 夜间街景 --model Z-Image
python scripts/harness.py --data-dir DATA manage learning --value off
python scripts/harness.py --data-dir DATA manage apply --value off
python scripts/harness.py --data-dir DATA manage authorize --value on --confirm
python scripts/harness.py --data-dir DATA candidate --input candidate.json
python scripts/harness.py --data-dir DATA configure --input thresholds.json
python scripts/harness.py --data-dir DATA experiment --input experiment.json
python scripts/harness.py --data-dir DATA rollback --id RULE_ID --reason 后续发现退化
python scripts/harness.py --data-dir DATA show
python scripts/harness.py --data-dir DATA export --kind preferences --output user_preferences.json
python scripts/harness.py --data-dir DATA export --kind harness --output history.zip
python scripts/harness.py --data-dir DATA export --kind full --output migration.zip
python scripts/harness.py --data-dir DATA import --input migration.zip
python scripts/harness.py --data-dir DATA validate
```

也提供 `check_harness_environment.py`、`export_harness.py`、`import_harness.py` 薄入口。返回码 0 成功、1 操作失败、2 环境不可用。无读写或执行工具时这些命令不可用，只能给出临时文本并明确尚未保存。

## 字段与例子

反馈输入（虚构示例，不能作为真实偏好预装）：

```json
{
  "prompt_id": "example-prompt-01",
  "rating": "特别喜欢",
  "raw": "我特别喜欢人物和环境的互动，以后类似场景都参考这个方向。",
  "target": "prompt",
  "features": ["人物和环境的互动"],
  "context": "户外人物",
  "scene": "公园",
  "model": "Krea 2",
  "model_version": "未知",
  "confirmed": true,
  "long_term": true,
  "cross_model": true,
  "classification": "personal",
  "prompt": "实际可获取的完整原文；此处仅说明字段",
  "image_evidence": "未提供"
}
```

运行时生成 id/time，保留 prompt_id、rating、target、features、polarity、weight、context、scene、model、model_version、raw、inference、inferred、confirmed、hard、prompt、image_evidence、classification。权重是弱/中/强证据等级，不是审美机械打分；脚本提供保守默认。一般可用 polarity=负向 记录具体不足。推断只能弱权重，不能硬约束。永久约束输入 permanent=true 或 hard_confirmed=true，且必须用户确认具体特点；cross_model 只能在用户明确要求时为 true。

user_preferences 包含独立 learning/apply 设置和 feedback/preferences/constraints 三个集合。偏好与约束有唯一 ID、内容、语境、模型及版本、来源、证据、状态、硬约束标记、时间、方向和权重。普通本次反馈默认不会形成长期偏好。上下文键由 Agent 基于语义选择；`*` 代表明确全范围。未知模型不等于全部模型。

候选输入包含 rule、evidence（反馈 ID 列表）、goal、factor（单一主要变化）、context、model、model_version；默认模型范围 `*`。候选记录状态、指纹、来源、目标和时间。不能因个人喜欢就将 classification 改为 design。configure 输入仅接受 min_feedback、min_scenes、min_test_pairs、max_regression；保存前验证并记日志，不能用它切换启用或授权。

实验输入包含 candidate_id、criteria、level（text/image）、pairs。每对必须含 task_id、scene、baseline（修改前完整提示词）、candidate（修改后完整提示词）、before/after（同一标准下 0–1 评价）、hard_requirements_preserved、creative_space_preserved、evidence（可定位评价依据）。image 层级的 evidence 使用 image: 或 user-feedback: 前缀，Agent 必须核实实体证据；仅有前缀不证明出图测试真实完成。

日志 JSONL 每条有 id、time、source_version、object、before、after、reason、source_ids、goal、test_tasks、criteria、results、accepted、effective、rollback、rollback_reason。拒绝、失败与回滚均保留，不把文本当指令。单次原子提交失败不发布半份新数据；I/O 错误通过调用结果返回，不能承诺在不可写设备上记录失败日志。

## 导入语义和隐私

完整包包含 manifest.json、user_preferences.json、learned_overrides.json、candidates.json、experiments/*.json、evolution_log.jsonl。Harness 历史包不含偏好原始库，但日志与实验可能有创作内容，仍属私人文件。独立偏好导出为 JSON。三类导出都不含配置位置、会话、核心代码或环境变量。输入反馈不得保存凭据/API 密钥；导出之前检查原始文本并按用户意图去敏，程序不承诺识别所有自由文本秘密。

manifest 含来源、版本、格式、时间、类别、计数和 SHA256。只接收 1.2.0-harness、1.2.1-harness、1.22、1.3.0-harness、1.4.0-harness 对应身份的数据格式 1；显式 `migrate_format` 接口识别 v1，未来格式在添加适配器前拒绝，不猜测兼容性。检查文件白名单、大小、重复条目，不解压执行代码。导入前备份；同 ID 去重、内容不同保留本地并报告；矛盾规则挂起；候选不晋级；配置不从包导入。preferences 导入保留本地引擎、授权、会话、健康时间及 learning/apply；harness/full 导入关闭 enabled 与 authorized_overrides、重置 sessions，并重新检测；保留本地门槛和 learning/apply。日志纯数据。

在新版本中使用相同 DATA 可保留数据；也可用完整包迁移。VIP 自由格式 Markdown 仍可由用户指定为只读迁移来源；先逐条核对、转为 v1 JSON、校验并导入，再切换唯一数据源，不同时维护两个库。

forget 需有效 --id 和 --confirm，只移除当前目标及关联记录，共享证据和无关记录保留；缺失或错误 ID 不写入任何数据。clear 经 --confirm 清空当前偏好和派生记录。两者均保留历史 generations、审计文件与备份，不承诺彻底擦除历史原文。外部导出包不自动寻找或删除。回滚经验仅禁用指定经验并保留历史，和隐私删除不同。

结构检查运行 `python scripts/validate_harness.py`；自动测试运行 `python scripts/run_tests.py`；发行打包运行 `python scripts/build_release.py --output <外部路径.zip>`。


## V1.4.0-harness

当前版本身份为 `1.4.0-harness`，技能名为 `prompt-assistant-online-v1-4-0-harness`。接受 1.2.0-harness、1.2.1-harness 、1.22 、1.3.0-harness 和 1.4.0-harness 各自匹配技能名的数据包；数据格式仍为 1。实验记录的写后核验按唯一 ID 对齐，其他内容和日志顺序仍严格检查。旧数据可继续使用，不需要清空或转换。

同范围同内容的正负偏好均标记 conflict 并在查询中暴露，不同时生效；相同方向、来源和类别的重复偏好合并证据。弱推测继续保留弱权重，不因合并自动成为明确事实或硬约束。

仅追加审计日志时，原子写入 audit/<当前 generation>.json，不复制业务状态；查询和导出合并该日志。下一次业务快照包含这些事件，新指针不再读取旧日志文件，避免重复。旧审计文件和快照均保留。不变操作不提交快照，拒绝操作仍记录可审计原因。
