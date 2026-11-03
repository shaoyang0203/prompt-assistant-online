# 目标模型加载表

确定目标后，编译前必须读取[公共契约](adapter-contract.md)及下表对应的专属文件全文；不是“遇到难点才读”。别名由[注册表](../adapters/registry.json)解析，同一目标只加载本路由，不加载其余模型正文。多模型交付分别读取各目标。

|目标（别名沿用注册表）|必须读取的专属文件|
|---|---|
|`generic`|[generic.md](adapters/generic.md)|
|`gpt-web`|[gpt.md](adapters/gpt.md)|
|`midjourney`|[midjourney.md](adapters/midjourney.md)|
|`krea2`|[krea2.md](adapters/krea2.md)|
|`grok-web`|[grok.md](adapters/grok.md)|
|`qwen-image-2.1`|[qwen-image.md](adapters/qwen-image.md)|
|`z-image`|[z-image.md](adapters/z-image.md)|
|`gemini-image`|[gemini.md](adapters/gemini.md)|
|`seedream`|[seedream.md](adapters/seedream.md)|
|`moss-image`|[moss.md](adapters/moss.md)|
|`moss-image-layout`|[moss-layout.md](adapters/moss-layout.md)|

同任务全文仍在上下文、目标与文件未变才可复用；跨会话、压缩后正文丢失、切换目标或文件更新须补读对应规则。未能读取时说明具体缺失，不能从名称、摘要或记忆猜专属规则，也不能静默降为generic；核心视觉设计可继续。改目标后按Compiler契约重新生成清单并复核最终成品。

这是LLM执行协议，不是Python读取回执门禁。文件存在及引用有效不证明模型读取或理解；不得假报已读、程序通过或出图成功。
