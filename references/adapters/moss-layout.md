# moss-image-layout 专属编译规则

目标确定为本路由后必须读取本文全文，并同时遵守[公共Adapter契约](../adapter-contract.md)。完整正文仍在本任务上下文且文件未变时可复用；只有名称、摘要或旧记忆不算已读。本文件整理既有规则，未重新核实官网或扩大模型能力。

|目标/别名|比例位置|表达与设置|
|---|---|---|
|moss-image-layout / moss-layout|块外、代码块上方|模型Layout JSON，块外显示明确且相符的画布尺寸|

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
