"""LLM-authored synthetic examples, not a free-input image/prompt generator."""
import copy
from contracts import ZONES, digest, require
from compile_checks import AXES, prepare, review_hash

CONCEPTS = {
"portrait": [
 {"id":"A","core":"书店窗边的阅读停顿","focus":"人物、书页和侧窗光相连","feature":"红外套与深色书架形成清楚分离","scene":"成年中国女性穿红外套，站在旧书店侧窗旁，双手托着摊开的书，低头看书页；腰上侧面构图，左侧窗光落在脸和纸页，后方深色书架仍有层次。"},
 {"id":"B","core":"从书架通道观察阅读者","focus":"重复书架围合出人物与纵深","feature":"保留空间身份和头顶暖色阅读灯","scene":"同一成年女性穿红外套，站在两排书架之间阅读；平视全身，人物置于通道远端，书架在两侧重复延伸，暖色阅读灯照亮书页与近侧脸，木地板承接暖光。"},
 {"id":"C","core":"柜台旁的俯视阅读","focus":"摊开的书、手和侧脸组成斜向关系","feature":"柜台大平面让人物与环境同时成立","scene":"成年女性穿红外套坐在旧书店柜台旁，书摊开放在台面，右手压住书页；从斜上方取半身，侧脸与书页清楚，窗光沿木台铺开，后方书架保持可辨认而较柔和。"}
],
"environment": [
 {"id":"A","core":"巨型藏书厅中的微小旅人","focus":"建筑为主体，人物提供尺度","feature":"高耸拱顶、重复柱廊与侧上方天光","scene":"宏伟古代藏书厅占据绝大部分画面，成年男性旅人站在下方柱脚附近，仅为建筑高度的一小部分；平视远景，石柱向深处重复，左上高窗天光落在柱面与石地，远处书架仍可辨认。"},
 {"id":"B","core":"从高处看藏书厅的层叠空间","focus":"回廊、中央大厅与人物的上下关系","feature":"俯视的几何层次和大片可辨认书架","scene":"从上层回廊俯瞰古代藏书厅，成年男性旅人停在下方中央阅读台旁；建筑占主体，弧形回廊和书架沿大厅展开，高窗天光照亮中央石地，回廊下方保持深色层次。"},
 {"id":"C","core":"从侧廊穿看主厅","focus":"近处石柱与远处大厅形成纵深","feature":"旅人位于两层建筑空间的连接处","scene":"从藏书厅侧廊看向宏大主厅，近处石柱占左侧边缘，成年男性旅人站在侧廊尽头；建筑为主体，右侧高窗光横过石地与柱列，主厅远处书架清楚，人物保持微小。"}
],
"correction": [
 {"id":"A","core":"局部调整为全身工作室肖像","focus":"面部与鞋履都进入画面","feature":"放弃面部特写裁切，保留正面和鞋履要求","scene":"经用户选择局部调整，成年男性在工作室正面全身站立，脸部与鞋履同时可见；人物左侧为大面积柔窗光，深灰墙和简洁地面构成空间，镜头保持平视。"},
 {"id":"B","core":"坐姿全身工作室肖像","focus":"脸、双手与鞋履形成连续关系","feature":"椅子提供明确支撑，鞋履前伸进入画面","scene":"经授权调整为全身构图，成年男性坐在工作室木椅上，双手放膝，双脚落地；平视正面，面部和鞋履可辨认，左侧窗光照亮脸与裤腿，背景保留简洁工作台。"},
 {"id":"C","core":"工作台旁的中远景人物","focus":"人物与工作室空间的整体关系","feature":"身体、面部和鞋履完整保留","scene":"经用户同意放宽景别，成年男性正面站在工作台旁，一手轻扶台边，鞋履完整进入下缘；平视中远景，侧窗柔光照亮人物，工作台与深灰墙在后方保留空间深度。"}
]}

CORRECTION = {
"issue":"正面面部特写与同一单帧完整展示鞋履存在裁切冲突。",
"intent":"conflict",
"options":[
 {"mode":"strict","design":"保留正面面部特写，认真安排脸部和肩部；鞋履仍位于画面外。","changes":"不改变明确要求，保留未解决冲突。","reason":"面部特写的取景无法同时完整覆盖远离面部的鞋履。","expected":"面部要求成立，但鞋履要求不能同时满足；不宣称协调通过。"},
 {"mode":"local","design":"改为正面全身肖像，脸部与鞋履同时可辨认。","changes":"经用户允许，将面部特写改成全身景别。","reason":"扩大取景范围后可以同时纳入头部与鞋履。","expected":"保留正面和鞋履展示，代价是面部占比减小。"},
 {"mode":"reconstruct","design":"建议改为两张独立肖像：一张面部特写，一张全身。","changes":"需用户允许将单帧任务改成两张图。","reason":"两个画面分别承担面部细节和整体造型展示。","expected":"两个目标各自充分表达，但改变单张交付数量，未选中前不实施。"}
]}

def concept_set(case):
    return copy.deepcopy(CONCEPTS[case])

def build(case="portrait", variant=0):
    request = {
        "portrait":"成年中国女性穿红外套在旧书店看书，默认电影叙事摄影，先给三个方向。",
        "environment":"宏伟古代藏书厅作为视觉主体，一位成年男性旅人只作尺度参照，先给三个方向。",
        "correction":"成年男性在工作室，正面面部特写，同时完整展示鞋履。"
    }[case]
    zones = {key: [] for key in ZONES}
    m = {"schema_version":"0.3.0","master_id":"preview-"+case,"revision":1,"parent_revision":None,
         "zones":zones,"globals":{"medium":"di-medium","aspect_ratio":"di-ratio","image_text":[]},
         "items":{},"changes":[]}
    translations = {}
    def add(key, zone, cn, en=None, user=False, kind="visual_fact", facet=None, deps=(), realized=()):
        m["items"][key] = {"kind":kind,"facet":facet or key[3:],"value":cn,
            "design_source":"user_specified" if user else "model_added",
            "source_refs":["synthetic:user-request" if user else "synthetic:host-llm-design"],
            "confirmation_status":"confirmed" if user else "pending",
            "constraint_strength":"hard_constraint" if user else "adjustable_design",
            "depends_on":[{"item_id":x,"relation":"lighting" if "light" in key else "spatial"} for x in deps]}
        if realized:
            m["items"][key]["realized_by"] = list(realized)
        if zone:
            zones[zone].append(key)
        if en:
            translations[key] = en
    add("di-intent","intent_constraints","以具体人物、空间和受光关系完成电影叙事摄影，不预设画面外故事。",kind="intent")
    if case == "portrait":
        add("di-requirement","intent_constraints","成年中国女性、红外套、旧书店和阅读动作保持。",user=True,kind="constraint",realized=("di-character","di-scene","di-action"))
        add("di-moment","creative_direction_moment",
            ["低头阅读书页的一个停顿。","站在通道远端阅读的单一瞬间。","坐在柜台前阅读，右手压住书页。"][variant],
            ["She pauses with her eyes lowered to the open pages.","She stands at the far end of the aisle, reading an open book.","She reads at the counter with her right hand resting on the page."][variant])
        add("di-focus","visual_subject_hierarchy","人物脸部和书页是主要焦点，书架为次要空间信息。",
            "Her face and the open pages form the primary visual focus, with the shelves providing secondary spatial information.")
        add("di-character","character_art","一位成年中国女性，穿红色外套。",
            "A single adult Chinese woman wears a red coat.",True)
        add("di-styling","character_art","黑色短发，外套衣领整齐。",
            "She has short black hair and a neatly arranged coat collar.")
        if variant == 1:
            add("di-lower","character_art","深色长裙垂至脚踝，穿黑色平底鞋。",
                "A dark skirt falls to her ankles above black flat shoes.")
        scene = ["旧书店侧窗、深色木书架与可辨认的书脊。","旧书店两排深色木书架形成狭长通道，木地板向远端延伸。","旧书店木柜台占据近处，后方书架仍可辨认。"][variant]
        scene_en = ["She is inside an old bookstore beside a side window, with dark wooden shelves and discernible book spines behind her.",
                    "Two rows of dark wooden shelves form a narrow aisle in the old bookstore, with wooden floorboards extending into its depth.",
                    "A wooden counter fills the near part of the old bookstore, with recognizable shelves behind it."][variant]
        add("di-scene","scene_art","人物在旧书店内。","She is inside an old bookstore.",True)
        add("di-scene-detail","scene_art",scene,scene_en)
        action = ["她站在窗旁，双手在腰前托着摊开的书，视线落在书页。",
                  "她站在通道远端，双手在腰前托着书，双脚落在木地板上。",
                  "她坐在柜台旁，书摊开放在台面，右手压住书页，左手放松置于台边。"][variant]
        action_en = ["She stands beside the window with both hands holding the open book at waist level, her gaze resting on its pages.",
                     "She stands at the far end of the aisle with both feet on the floor, holding the book at waist level.",
                     "She sits beside the counter with the open book on its surface, her right hand on the page and her left hand relaxed at the counter edge."][variant]
        add("di-action","action_spatial_relations","人物正在看书。","She is reading a book.",True,deps=("di-scene",))
        add("di-pose","action_spatial_relations",action,action_en,deps=("di-scene","di-action"))
        add("di-camera","camera_composition",
            ["平视腰上侧面构图，人物靠右，左侧保留窗和部分书架。","平视全身构图，人物在通道远端，两排书架向她延伸。","斜上方半身取景，人物侧脸与书页构成斜向关系。"][variant],
            ["An eye-level side view frames her from the waist up on the right, leaving the window and part of the shelves on the left.",
             "An eye-level full-length view places her at the far end of the aisle, with shelves extending toward her on both sides.",
             "An oblique view from above frames her upper body, placing her profile and the book along a diagonal."][variant],deps=("di-focus","di-action"))
        add("di-light","lighting_color",
            ["左侧大窗柔光照亮脸颊和书页，书架保持深色，红衣与背景分离。",
             "头顶暖色阅读灯照亮书页和近侧脸，远处书架保持深暖层次，红衣可辨认。",
             "侧窗柔光沿柜台展开，照亮侧脸、手和书页，后方书架较暗。"][variant],
            ["Soft light from the large window on the left illuminates her cheek and the pages; the shelves remain dark enough to separate the red coat.",
             "A warm reading lamp above illuminates the pages and the near side of her face; the shelves recede in deep warm tones while her red coat remains distinct.",
             "Soft side-window light spreads across the counter, illuminating her profile, hands and pages against darker shelves."][variant],deps=("di-character","di-scene"))
        add("di-material","material_visual_expression","外套为哑光织物，纸页形成柔亮受光面，木材保留暗色纹理。",
            "The coat has a matte woven surface, the paper catches a soft brightness, and the wood retains dark grain.",deps=("di-light",))
    elif case == "environment":
        add("di-requirement","intent_constraints","建筑必须为主要视觉主体，成年男性旅人仅作尺度参照。",user=True,kind="constraint",realized=("di-focus","di-character","di-scene"))
        add("di-moment","creative_direction_moment","旅人停步观察藏书厅的静止瞬间。",
            "The traveler has stopped to observe the library hall.")
        add("di-focus","visual_subject_hierarchy","建筑占据画面绝大部分，人物高度仅为近处巨柱的一小部分。",
            "The architecture occupies most of the frame; the traveler is only a small fraction of the height of the nearest monumental column.",True)
        add("di-character","character_art","一位成年男性旅人。","A single adult male traveler is present.",True)
        add("di-styling","character_art","旅人穿灰色长外套，造型以低对比大形呈现。",
            "The traveler wears a gray long coat, its silhouette expressed in broad low-contrast shapes.")
        add("di-scene","scene_art","古代藏书厅。","The scene is an ancient library hall.",True)
        add("di-scene-detail","scene_art",
            ["古代藏书厅有高耸石拱顶、重复石柱、石地和远处多层木书架。",
             "古代藏书厅有上层弧形回廊、下方大厅、中央阅读台和多层木书架。",
             "古代藏书厅侧廊连向主厅，近处石柱位于左边缘，主厅远处有多层书架。"][variant],
            ["The ancient library hall contains a towering stone vault, repeated stone columns, a stone floor and tiers of wooden shelves in the distance.",
             "The ancient library hall has a curved upper gallery above the main floor, a central reading table and tiers of wooden shelves.",
             "A side aisle connects to the main library hall, with a near stone column at the left edge and tiers of shelves in the distance."][variant])
        add("di-action","action_spatial_relations",
            ["旅人站在下方柱脚附近，头部朝大厅深处。",
             "旅人停在下方中央阅读台旁，抬头望向上层回廊。",
             "旅人站在侧廊尽头，身体朝主厅。"][variant],
            ["The traveler stands near the foot of a column at the bottom of the scene, his head turned toward the hall's depth.",
             "The traveler stands beside the central table on the lower floor, looking up toward the gallery.",
             "The traveler stands at the end of the side aisle, facing the main hall."][variant],deps=("di-scene",))
        add("di-camera","camera_composition",
            ["平视远景保留拱顶、柱脚和石地，柱列向深处重复，画面横向展开。",
             "从上层回廊俯视，回廊弧线、中央大厅和小人物组成上下层次。",
             "从侧廊平视远景看入主厅，近处左柱形成局部遮挡，远处大厅清楚。"][variant],
            ["An eye-level wide view includes the vault, column bases and floor, with the columns repeating into the depth of the horizontal frame.",
             "A view downward from the upper gallery organizes its curved edge, the main hall and the small figure into distinct vertical layers.",
             "An eye-level wide view looks from the side aisle into the main hall; the near column partly occludes the left edge while the distant hall remains legible."][variant],deps=("di-focus","di-action"))
        add("di-light","lighting_color",
            ["左上高窗天光落在柱面与石地，深处书架保留较暗层次，主色为暖灰石材和棕木。",
             "高窗天光照亮中央石地，回廊下方保持阴影，灰石和深棕木材形成有限配色。",
             "右侧高窗光横过石地与柱列，侧廊较暗，远处书架仍有棕木色层次。"][variant],
            ["Daylight from high windows at the upper left falls across the columns and stone floor; the distant shelves remain darker, in warm gray stone and brown wood tones.",
             "High-window daylight illuminates the central stone floor while shadows remain beneath the gallery; gray stone and dark brown wood establish a restrained palette.",
             "Light from high windows on the right crosses the floor and columns; the side aisle is darker while the distant shelves retain brown wood tones."][variant],deps=("di-scene","di-character"))
        add("di-material","material_visual_expression","石材表面粗哑，柱面磨损可辨；木书架吸光，石地高光宽缓。",
            "The stone is rough and matte with discernible wear on the columns; the shelves absorb light, and broad soft highlights cross the stone floor.",deps=("di-light",))
    else:
        add("di-requirement","intent_constraints","采用用户选择的局部调整：放宽面部特写，保留正面和完整鞋履。",user=True,kind="constraint",realized=("di-character","di-camera","di-action"))
        add("di-moment","creative_direction_moment","工作室中安静停顿的一个瞬间。","The man pauses quietly in the studio.")
        add("di-focus","visual_subject_hierarchy","人物整体造型为主体，脸部和鞋履同时可辨。","His overall appearance is the visual subject, with both face and footwear discernible.")
        add("di-character","character_art","一位成年男性。","An adult man is present.",True)
        add("di-styling","character_art","灰衬衫、深色长裤和棕色皮鞋。","He wears a gray shirt, dark trousers and brown leather shoes.")
        add("di-scene","scene_art","人物在工作室内。","He is inside a studio.",True)
        add("di-scene-detail","scene_art","深灰墙、木工作台和简洁地面。","The studio has a dark gray wall, a wooden workbench and an uncluttered floor.")
        add("di-action","action_spatial_relations",["正面站立，双脚落地，双手自然垂下。","正面坐在木椅上，双手放膝，双脚落地。","正面站在工作台旁，一手轻扶台边，双脚落地。"][variant],
            ["He stands facing the camera with both feet on the floor and his arms relaxed.","He sits facing the camera on a wooden chair, hands on his knees and both feet on the floor.","He stands facing the camera beside the workbench, one hand lightly resting on its edge and both feet on the floor."][variant],deps=("di-scene",))
        add("di-camera","camera_composition","平视正面全身取景，头部和鞋履完整进入画面，面部占比小于特写。","An eye-level frontal full-length view includes his entire head and shoes; his face occupies less of the frame than in a close-up.",True,deps=("di-action",))
        for key in ("di-requirement", "di-camera"):
            m["items"][key]["source_refs"] = ["synthetic:user-selected-local-frame-adjustment"]
        add("di-light","lighting_color","左侧大面积柔窗光照亮脸部和衣服，背景保持较暗灰色，肤色自然。","Broad soft window light from the left illuminates his face and clothes against a darker gray background, with natural skin color.",deps=("di-character","di-scene"))
        add("di-material","material_visual_expression","棉衬衫吸光，木台有可见木纹，皮鞋有局部柔亮高光。","The cotton shirt is matte, the workbench shows wood grain, and the leather shoes have localized soft highlights.",deps=("di-light",))
    add("di-medium",None,"真人摄影。","Photorealistic photography.",kind="medium")
    # Authored examples choose by each composition; this is not a production ratio selector.
    ratios = {"portrait": [(4,5),(2,3),(4,3)], "environment": [(3,4),(16,9),(3,2)],
              "correction": [(2,3),(4,5),(3,4)]}
    reasons = {"portrait": ["腰上阅读与书页手势需要一定侧向余量，选择较宽竖幅4:5。",
                           "全身与两侧书架通道纵向展开，选择2:3。", "斜俯视台面、书与侧脸需横向并置，选择4:3。"],
               "environment": ["高拱顶到柱脚人物的上下关系为主，选择3:4。",
                               "俯视弧形回廊与书架横向展开，选择16:9。", "侧廊与主厅两层横向并置，选择3:2。"],
               "correction": ["正面全身及鞋履需完整纵向空间，选择2:3。", "坐姿与膝上手部需要较宽竖幅，选择4:5。",
                              "全身和工作台的上下及侧向关系同时保留，选择3:4。"]}
    width, height = ratios[case][variant]
    add("di-ratio",None,{"width":width,"height":height},kind="aspect_ratio")
    for key in m["items"]:
        m["changes"].append({"item_id":key,"operation":"add","reason":"首轮完整设计","source_ref":"synthetic:preview-design"})
    m["changes"][-1]["reason"] = reasons[case][variant]
    return {"request":request,"concepts":concept_set(case),"master":m,"translations":translations}

def candidate_for(state, translations):
    packet = prepare(state)
    manifest = packet["manifest"]
    master = state["masters"][-1]
    order = ["character_art","scene_art","creative_direction_moment","action_spatial_relations",
             "camera_composition","visual_subject_hierarchy","lighting_color","material_visual_expression"]
    if master["master_id"].endswith("environment"):
        order = ["scene_art","visual_subject_hierarchy","character_art","creative_direction_moment",
                 "action_spatial_relations","camera_composition","lighting_color","material_visual_expression"]
    keys = ["di-medium"] + list(dict.fromkeys(key for zone in order for key in master["zones"][zone]
                                           if key in manifest["facts"]))
    keys += [key for key,item in manifest["facts"].items()
             if key not in keys and item["kind"] not in ("aspect_ratio","medium")]
    # Detailed scene text already expresses the setting; preserve both IDs in one sentence.
    keys = [key for key in keys if key != "di-scene"]
    segments = []
    for i in range(0,len(keys),3):
        group = keys[i:i+3]
        covered = group + (["di-scene"] if "di-scene-detail" in group else [])
        segments.append({"text":" ".join(translations[key] for key in group),"item_ids":covered})
    return {"master_hash":manifest["master_hash"],"segments":segments,
            "target":manifest["aspect_ratio_delivery"]["target"],
            "parameters":{"aspect_ratio":copy.deepcopy(master["items"]["di-ratio"]["value"])}}

def authored_review(state, candidate):
    """Example author's review attestation, NEVER an independent live-model test."""
    require(latest_demo(state), "预写复核仅用于合成演示；真实任务必须由宿主实际逐项复核")
    facts = prepare(state)["manifest"]["facts"]
    notes = {
        "omissions":"逐项对照本示例最终英文段落及路由画幅交付；结构比例参数不代替最终输出检查。",
        "additions":"逐句回看母版，未加入母版之外的人物、道具、天气或关系。",
        "relations":"主体尺度、动作支撑、空间位置及光源方向与母版一致。",
        "requirements":"已明确要求在设计项、英文和画幅参数中有对应。"
    }
    return {"master_hash":candidate["master_hash"],"artifact_hash":review_hash(candidate),
            "reviewer":"authoring-host-llm-example-self-review",
            "evidence_ref":"synthetic:authored-example-not-independent-runtime-evaluation",
            "axes":{k:{"result":"pass","note":notes[k]} for k in AXES},
            "item_results":{key:{"result":"pass","note":"对应英文片段保留："+str(item["value"])}
                            for key,item in facts.items()}}


def latest_demo(state):
    master = state["masters"][-1]
    return master["master_id"] in {"preview-portrait", "preview-environment", "preview-correction"} and all(
        item["source_refs"] and all(ref.startswith(("synthetic:", "KB:")) for ref in item["source_refs"])
        for item in master["items"].values())
