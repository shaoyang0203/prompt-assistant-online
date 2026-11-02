# Gemini／Nano Banana、Seedream与MOSS编译规则

本文件由[交付契约](adapter-contract.md)按目标模型加载。承接用户批准的三组旧版文生图规则；不包含API调用、图像编辑或模型安装。只有已展示并获用户确认的完整母版版本可编译，所有设计事实及关系继续受Compiler完整性契约约束。

## Gemini Image／Nano Banana

- 选择`gemini-image`，可使用`gemini`、`nano-banana`、`nanobanana`及配置登记的产品名别名；这些名称共享文本编译协议，不代表本地工具选择或调用了具体型号。
- 以中文自然语言说明主体、动作、环境、构图、光线、色彩及需要保留的内容；用户要求其他语言时优先。复杂画面可以充分描述，不为缩短而删除有效设计，不强制Tags或固定段落模板。
- 画面文字用引号界定并逐字保留原语言，说明母版已定的位置与字形视觉要求，不自行编写额外文案。
- 保留旧版消费端交付：单个代码块内为Prompt，末尾自然语言表达已定比例；不在块外重复比例，不给无依据的像素尺寸。该行是文字建议，不保证界面实际按文字设置画布。
- 分辨率档位及比例可选项因产品型号和界面而异；不将旧型号列表视为全系列能力，不把接口字段或搜索、编辑、多图能力写成提示词正文。本版不输出API请求格式。

官方核实：2026-11-01，[Google图像生成指南](https://ai.google.dev/gemini-api/docs/image-generation)。官方提供自然语言、画面文字和比例描述示例，支持语言包含zh-CN；型号参数能力不作本地实测保证。

## Seedream

- 选择`seedream`或`doubao-seedream`。以中文简洁连贯地写清主体、行为和环境，再按已确认设计补充风格、色彩、光影、构图及材质；用户可要求其他语言。
- 官方建议中文不超过300字、英文不超过600词，作为压缩参考而非程序硬截断、必须写满的目标或语义通过标准。优先删除重复、空泛修饰和解释；保留人物服装、道具、空间、光线、文字等明确要求。若仍过长并需减少设计，先回到母版提出取舍，不擅删事实。
- 画面文字用双引号界定并逐字保留原文；多语文字按母版已有内容表达，不随正文翻译。
- 保留旧版文字交付：一个代码块，已定画幅在Prompt末尾自然语言表达，不给具体像素尺寸；比例行不是API字段，也不保证消费端画布受文字控制。界面提供外部尺寸设置时应与母版一致，不把程序调用参数混入正文。
- 不自动加入组图、联网搜索、图层拆分或编辑协议，不假定这些能力全系列通用。本版无API路由。

官方核实：2026-11-01，[火山引擎生成指南](https://docs.volcengine.com/docs/ark/image-generation-tutorial?redirect=1&lang=zh)、[提示词语言与长度说明](https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh&redirect=1)。所引接口文档仅用于核实模型与提示词能力，不引入API调用。

## MOSS-Image：自然语言

- 默认选择`moss-image`或`moss`。采用中文连贯描述，按用户指定切换语言；普通人像、生活场景、摄影或时尚画面按已确认设计描述人物、动作、场景、空间、光色、材质与媒介。
- 可详细描述，但不因长上下文而加入无关解释或重复形容词，不自动加入模型名、内部编号或创作步骤。保留文字原文、位置和显式换行。
- 单个代码块内只放Prompt；建议比例在块外，普通自然语言成品当前不承载具体像素尺寸。采样参数仅用户明确要求且有依据时说明。现有不输出Negative Prompt的产品规则继续适用。

## MOSS-Image：JSON Layout

仅在用户明确需要位置、群像关系或文字排版的布局控制时选择`moss-image-layout`（别名`moss-layout`）；不能仅因画面细节多就自动切换。Layout本身仍须来自已确认母版，不在编译时重新布局。

支持的模型输入结构：

```json
{"summary":{"meta":["poster"],"canvas":"single","caption":"母版已有的整体画面与风格"},"items":[{"label":"text","caption":"母版已有的标题样式与位置","text":"原始画面文字","bbox":[-416,-384,-288,384]},{"label":"object","caption":"母版已有的主体","bbox":[-192,-288,384,288]}],"bbox_coord_space":"abs_centralized","bbox_format":"yxyx"}
```

以上坐标仅为1024×1024画布的格式示例，不是其他画面的默认布局。

- `summary`描述整体画面；`items`为平面元素列表，使用`label`、`caption`、`bbox`，文字元素另含逐字保真的`text`。支持`object`、`character`、`text`类别；可选的`tags`、`palette`只承载母版已定信息。
- 坐标为中心原点绝对像素，顺序为`[y_min,x_min,y_max,x_max]`。x向右、y向下；宽W高H的范围分别为±W/2、±H/2。不可混用归一化坐标、左上原点或其他bbox顺序。
- Layout必须有可靠、明确的画布尺寸。候选`parameters`为`{"aspect_ratio":{"width":1,"height":1},"image_size":{"width":1024,"height":1024}}`，示例中的比例和尺寸必须替换为实际设计。宽高为正整数且为16倍数，尺寸比必须等于母版画幅；缺失时不得猜默认值或宣称Layout可交付，应说明还缺什么。
- 一个segment的`text`存完整JSON，`item_ids`覆盖所有相应设计事实；内部事实ID不进入模型JSON。坐标、文字位置或画幅的实质变化仍须回到母版重新展示确认。
- Python检查JSON结构、重复键、有限整数坐标、边界及画幅与尺寸关系，不自动裁切或改写。文字在解码后的文字元素中检查，允许原文换行被JSON转义；是否语义遗漏、擅加或关系改变仍由宿主LLM复核。结构正确不证明模型会精确落实坐标。
- 最终代码块为紧凑单行模型JSON，比例与必需尺寸在块外，只交付一份。工作流必须设置相同尺寸；九区域视觉母版JSON和MOSS模型输入JSON是两种不同对象，不能直接互换。

官方核实：2026-11-01，[MOSS官方README](https://github.com/OpenMOSS/MOSS-Image/blob/main/README.md)、[USERGUIDE](https://github.com/OpenMOSS/MOSS-Image/blob/main/USERGUIDE.md)。Layout在官方指南中属于实验能力；本次程序检查不代表真实生图或所有checkpoint已经验证。
