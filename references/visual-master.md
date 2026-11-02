# 权威母版 V1.5.2

Schema 在 [visual-master.schema.json](../schemas/visual-master.schema.json)。
九区域固定为创作意图与用户约束、创意方向与叙事瞬间、视觉主体与层级、人物美术、场景美术、动作与空间关系、摄影与构图、光影与色彩、材质与视觉表现。
区域为设计项引用，可为空；媒介、画幅、画面文字作为 globals。协调状态属于任务，不占区域。

items 以稳定 ID 为键，来源、确认、强度严格独立：
- design_source：user_specified / model_added / jointly_formed
- confirmation_status：pending / confirmed / rejected
- constraint_strength：hard_constraint / confirmed_design / adjustable_design
用户指定项必须 confirmed。用户确认模型补充项不自动把来源改成共同形成，也不自动升级硬约束。
当前有效母版不含 rejected 项，拒绝的旧版保留历史，不继续编译。

kind intent/constraint 不作为画面文字直译。constraint 的 realized_by 指向落实要求的正向事实。
可编译 kind 为 visual_fact、medium、aspect_ratio、image_text。
画面文字 literal 保留原字符和换行；appearance 写可见位置、颜色、字形和相对字号。
比例结构 width/height为正整数，缺省不填3/2；在设计阶段由总导演与摄影构图决定后写入globals.aspect_ratio所引用的事实。没有确定比例时继续设计，不生成可编译母版。用户明确比例的来源为user_specified、确认confirmed、强度hard_constraint；模型初次选择为model_added/pending；用户后续确认允许改为confirmed，来源仍保持model_added，不能强制永远pending；整版仍需具体版本确认。既有事实的facet可写“画幅及构图选择理由”，changes.reason记录具体理由，source_refs保存用户消息或KB:CA-09等依据，不新增混合状态字段。
参考图比例仅在延续其构图的任务中优先考虑，不自动硬化；元素提取任务按新构图判断。变更画幅须检查尺度位置、景别裁切、前景、背景、横纵空间、主体层级、留白与整体关系，更新必要事实、版本、变更记录和确认。比例的最终块内/块外位置由Adapter配置决定，JSON中的width/height不因排版而变化。

JSON 为权威，完整可读文档从它渲染。每次修改新 revision，关联 parent_revision 和准确 changes。未受影响的设计 ID 保留。
整版用户确认保存在独立 ApprovalRecord，绑定完整快照哈希；不回写旧 JSON。渲染及编译按有效凭据解析模型补充项的整版确认。
工具不能证明用户实际阅读或伪造批准；宿主必须展示并引用真实消息。


区域及全局引用变化另用可选 `structure_changes` 数组记录，每项为 `{"path":"zones.character_art","reason":"具体调整理由","source_ref":"真实来源"}`。path限定为zones的九区域或globals的medium/aspect_ratio/image_text。首版不填相对旧版的结构变化；后续版本须逐项准确覆盖变化路径，不接受遗漏、重复、无实际差异或空白理由。纯设计项修改且结构未变时可省略；旧版快照仍可读取。工具从前后快照计算变化值并写入master_revision事件的structural_changes，可读母版同时展示结构变更理由。任何改版均重新整体复核、展示和确认，不把结构记录当作用户批准。
