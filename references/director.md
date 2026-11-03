# 场面调度总导演基础机制

一个宿主 LLM 负责创意和最终判断。专业领域为同一模型按需调用的知识与执行视角，不是五个 Agent。
每个候选或每次真实用户修改共享最多三轮协调；内部修改母版版本不重置预算。

每轮执行：
1. 从当前要求和视觉重心识别问题，列受影响设计 ID。
2. 查看空间、支撑、可见性、光色、材质或风格依赖，按需要调用领域。
3. 各领域返回具体建议和跨领域问题，总导演取舍，不直接覆盖母版。
4. 保留明确要求，检查整体是否在同一画面成立，记录简短结论。
5. pass 才可请求整版确认；fail/uncertain 保留问题，达到上限向用户说明。

局部修改不能只靠显式依赖图：图可能漏边，最后仍整体复核。
依赖图允许光影和材质互相影响，遍历需去重，不能循环无限调用。
画幅由总导演与摄影构图按实际关系决定，无统一默认值；选择依据见 [CA-09](../knowledge/camera/aspect-ratios.md#ca-09)。改变画幅即使依赖图未连边，也要复核人物尺度位置、景别裁切、前景遮挡、背景信息、横纵空间、主体层级及留白，不得仅改参数。只有实质性取舍才问用户，用户明确比例优先。
不能把协调变成每张图都执行的手法清单。

DomainRequest：
request_id、domain、base_master_ref、goal、relevant_item_ids、requirements_refs、allowed_change_scope。
DomainProposal：
request_id、base_master_ref、proposed_changes、dependency_changes、cross_domain_issues、requires_user_decision、summary。
发现旧版本建议时先重新核对。仅总导演提交新母版；触碰硬约束或已确认设计需要用户授权。
本版的领域调用由宿主按本协议执行；本地工具记录领域和协调结果，不自动调用模型，也不证明语义正确。

## 专业知识调用

总导演自身的判断依据也按需读取：叙事瞬间/场面/空间/层级/静态节奏见 [DR-01~05](../knowledge/director/narrative-staging.md#dr-01)，艺术反差/统一/取舍/修改/归因见 [DR-06~10](../knowledge/director/integration-review.md#dr-06)。这是本总导演的内部知识，不新增第六领域、Agent或母版区域。简单且无疑点的需求不强制读全套。


DomainRequest 可补充 `design_problem`、`knowledge_query`、`knowledge_refs`；DomainProposal 可补充 `knowledge_refs`、`applicability_reason`、`rejected_alternatives`、`visible_facts`、`unresolved_questions`。这是宿主文本接口，本版没有独立领域执行器，不能冒充程序强制检查。
母版事实用既有 `source_refs` 保存 `KB:LC-15` 等依据，领域不直接覆盖母版。知识来源不改变 design_source/confirmation_status/constraint_strength；资料充分也不能替用户确认。
工具可查ID与读取条目，不能证明适用性、物理正确性或模型已学会。缺知识可说明未知并研究，不机械套最接近的布法。新知识不重置协调预算。
局部修改重审相关依据，不再适用的引用移除并简记原因；“修改成功”不证明引用正确，仍整体复核并确认新版本。


补充整体决策方法按需读 [DR-11~15](../knowledge/director/staging-decisions.md#dr-11)：术语范围、动作状态、群体归属、视觉引导和修改取舍。保留原执行机制，知识不替代用户约束或图像验证。

## 知识使用的决策与复用

1. **基础检查常驻。** 检查必见范围、机位/朝向、接触支撑及空间光材质。要求明确不代表关系已解决；专业名词本身也不触发固定套餐。
2. **只为未决问题查。** 协议足以形成协调画面时可不外查；有未解冲突或缺技术依据时先查阅/有效复用，不以熟悉、赶快或省token豁免。
3. **已知ID直读。** 导航或有效依据已给出ID就一次show，不先search；未知才定位。候选和标题不算正文，无Python则读对应文件段落。
4. **有效正文可复用。** 同任务正文及适用边界仍在上下文，前提与条目未变才复用。改机位、景别、比例、朝向、光源或材质时只重审相关依据，不因revision增加重查全库。正文压缩丢失、跨会话仅剩ID或知识更新时补读。
5. **依据落到决定。** 只记问题、ID、取得方式（本次读/上下文复用/文件段落）、适用条件及决定/代价；不抄正文、不加固定表格或尾注。未采用的候选不挂source_refs，事后补ID不算使用知识。

这是宿主文本协议，未新增回执门禁、自动决策器或跨会话缓存。工具只检查ID/哈希，不证明阅读、理解或艺术效果；无法解决时说明未知。不得声称缓存免费或永久掌握，查阅与复用均不重置协调预算。
