# LLM Compiler 与最终检查

Compiler 是宿主 LLM，不是 Python 翻译器。仅从当前已展示且获用户版本确认的母版编译。
通用自然语言使用连贯描述；覆盖媒介、主体、瞬间、动作、空间、镜头、光色和可见材质，信息以画面需要决定。
所有已确认可编译设计都应保留；只可等义合并重复表达。发现缺失设计退回总导演。

工具manifest包含master_hash、facts、constraints、adapter_id及aspect_ratio_delivery（配置路由）。命令`manifest --target <已登记路由>`只选择表达方式，不选择或改变画幅。未指定目标仍可明确交付generic，不把未实现模型静默当generic。
候选格式：
- master_hash
- segments：每段 text、item_ids
- parameters：aspect_ratio 的 width/height
- target：已选路由名；省略仅为兼容既有generic候选，不代表自动识别模型

Gemini／Nano Banana、Seedream及MOSS按[专用编译说明](model-routes.md)处理。只有显式MOSS Layout候选在parameters中另提供image_size的width/height，作为已确定的实际画布尺寸；其他路由不接收该字段。Layout的一个segment承载完整模型JSON及其覆盖ID，不把九区域母版原样传给模型。尺寸和JSON均绑定成品哈希，修改后必须重新复核。没有可靠尺寸时不能编造Layout，核心自然语言创作仍可继续并明确未完成Layout交付。

段落可覆盖多项；覆盖 ID 只是声明，不证明真实等义。
segments不预写比例控制，由Adapter从parameters生成路由规定的块内比例行/参数或块外设置。参数在结构对象中保留是校验依据，不是要求对用户重复显示。未确认比例、比例与母版不同、路由不支持或语义uncertain均不得放行。

宿主对 Adapter 后的实际最终成品重新逐项检查：
omissions（遗漏）、additions（擅加）、relations（关系改变）、requirements（明确要求）。
另给每个可编译 ID 的 result 和可审查 note。结果 pass/fail/uncertain。
review绑定master_hash和artifact_hash，写reviewer与evidence_ref。显式target的哈希同时绑定路由配置和最终排版；改变目标或路由后必须重新复核，不能沿用旧pass。禁止在没有复核时批量填写pass。
Python 检查字段、哈希、版本、覆盖 ID、文字原文、比例和预算；无法证明语义。
最终任一必要项 fail 或 uncertain 不放行。失败最多自动修复一次；不可通过重新准备 manifest 重置预算。

文本宿主没有 Python 时仍按同一事实清单和语义合同检查；不能宣称程序强制或已永久保存。

