# 本地工具

命令的 --data-dir 使用源码之外的显式目录。Python 路径按 README，不依赖裸命令。
交互示例：preview --case portrait / environment / correction。
示例是预写合成数据，确认来自终端真实输入；其语义评审是作者预写自审，不是独立在线模型执行。

自由创作由当前宿主 LLM 执行，工具按下列顺序接收 JSON：
new → concepts → select → master → coordinate → show → approve → manifest → submit → deliver。
修改：change → master（新版本）→ coordinate → show → approve → manifest → submit → deliver。
status 显示任务和历史母版。每次业务修改发布新任务快照，CURRENT 原子切换，旧快照不删除。
CLI 完整选项用 --help 和相应子命令 --help。
manifest在当前任务记录所选Adapter；省略--target沿用已选值，首次未指定则为generic。该选择不改变母版，不重置编译次数，也不执行模型调用；之后提交及交付必须与本次选择一致。

coordinate --input：
result、issues、summary、domains。pass 时 issues 必须为空，domains 仅五领域枚举。
画幅相对上次通过协调的母版改变后，另填aspect_ratio_review，键为subject_scale_position、framing_crop、foreground_occlusion、background_information、spatial_relations、visual_hierarchy、negative_space_overall；各值为`{"result":"pass/fail/uncertain","note":"实际复核结论"}`。只有七项均pass才可协调通过；这些是宿主声明，Python仅检查结构与状态，不证明构图质量。无改变也可填写，不强制无关复核。内部连续改版不能绕过未完成的画幅复核。
manifest支持`--target generic/gpt-web/midjourney/krea2/grok-web/qwen-image-2.1/z-image/gemini-image/seedream/moss-image/moss-image-layout`及配置别名。候选JSON的target须与实际目标一致；省略仅为generic兼容。deliver返回prompt、external_settings与完整formatted；宿主展示formatted，不再统一追加块外比例。没有Python时按 [Adapter契约](adapter-contract.md) 执行同一规则。
MOSS Layout仅在明确布局需求且有可靠画布尺寸时使用，候选parameters增加image_size，text为一个完整JSON；具体结构与坐标见[路由说明](model-routes.md)。程序会检查与画幅的关系和坐标边界，失败不得手工绕过后宣称通过。无Python时可以按同一格式组织文本，但须说明未执行确定性校验。
master --authorization：
user_ref、item_ids，仅填写真实修改授权，不能用 Agent 自己的判断冒充。
approve 必须提供当前 revision 和真实 user-ref；方向选择不会自动产生批准。

工具仅提供任务记录与偏好模板，没有旧版的导入导出、迁移包或自动晋级实验入口。
偏好模板由 `scripts/prefs.py` 维护，与任务快照共用同一 `--data-dir`：`init / status / template add|list|show|on|off|stop|resume / query / archive add / infer / set`。模板默认全部关闭；`on` 是唯一让它自动生效的动作。读写规则见[偏好协议](preferences.md)，用户侧说明见[说明书](manual.md)。
工具拒绝把数据目录设在技能源码内；Sandbox只允许写工作区的宿主必须把数据目录放在工作区内且跨会话不变。
快照恢复须在确认无写入进程后，经用户指定选择旧快照，不自动删锁或清理历史。

知识工具 `scripts/knowledge.py` 的 search/show/audit 离线只读；build-index 仅开发维护时更新源码索引。search 返回候选ID，show 每次1–5条，不调用LLM。无Python时按 [知识入口](../knowledge/README.md) 定位条目，核心创作继续。工具不代替专业适配判断和用户确认。

