"""Validate the supported MOSS model-input layout, without generating visual facts."""
import json
from contracts import require


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'MOSS Layout包含重复JSON键: ' + key)
        result[key] = value
    return result


def invalid_constant(value):
    require(False, 'MOSS Layout不接受NaN或Infinity: ' + value)


def layout(candidate):
    params = candidate['parameters']
    require(type(params) is dict and set(params) == {'aspect_ratio', 'image_size'},
            'MOSS Layout须提供aspect_ratio和已确定的image_size，不能猜默认尺寸')
    size = params['image_size']
    require(type(size) is dict and set(size) == {'width', 'height'} and
            all(type(v) is int and v > 0 and v % 16 == 0 for v in size.values()),
            'MOSS画布宽高必须为正整数且为16的倍数')
    ratio = params['aspect_ratio']
    require(type(ratio) is dict and set(ratio) == {'width', 'height'} and
            all(type(v) is int and v > 0 for v in ratio.values()), 'MOSS画幅结构无效')
    width, height = size['width'], size['height']
    require(width * ratio['height'] == height * ratio['width'], 'MOSS画布尺寸与已定画幅不一致')
    require(type(candidate['segments']) is list and len(candidate['segments']) == 1,
            'MOSS Layout须用一个segment承载完整JSON；事实ID可以有多项')
    text = candidate['segments'][0]['text']
    require(type(text) is str, 'MOSS Layout须为JSON文本')
    value = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    require(type(value) is dict and set(value) == {'summary', 'items', 'bbox_coord_space', 'bbox_format'},
            'MOSS Layout须为summary/items模型输入，不得混入内部母版、画布元信息或其他坐标格式')
    require(value['bbox_coord_space'] == 'abs_centralized' and value['bbox_format'] == 'yxyx',
            'MOSS Layout使用中心原点绝对像素坐标与yxyx顺序')
    summary = value['summary']
    require(type(summary) is dict and {'meta', 'canvas', 'caption'} <= set(summary) <= {'meta', 'canvas', 'caption', 'palette'},
            'MOSS summary结构无效')
    require(summary['canvas'] == 'single' and type(summary['caption']) is str and summary['caption'].strip(),
            'MOSS须为单画布，summary.caption不能为空')
    for key in ('meta', 'palette'):
        if key in summary:
            require(type(summary[key]) is list and all(type(x) is str for x in summary[key]), 'MOSS summary数组无效')
    require(type(value['items']) is list and bool(value['items']), 'MOSS Layout元素不能为空')
    for item in value['items']:
        require(type(item) is dict and {'label', 'caption', 'bbox'} <= set(item) <= {'label', 'caption', 'bbox', 'text', 'tags', 'palette'},
                'MOSS元素字段无效')
        require(item['label'] in ('object', 'character', 'text') and type(item['caption']) is str and item['caption'].strip(),
                'MOSS元素类别或描述无效')
        if item['label'] == 'text':
            require(type(item.get('text')) is str and bool(item['text']), 'MOSS文字元素必须提供原文text')
        elif 'text' in item:
            require(type(item['text']) is str, 'MOSS text须为字符串')
        for key in ('tags', 'palette'):
            if key in item:
                require(type(item[key]) is list and all(type(x) is str for x in item[key]), 'MOSS元素数组无效')
        box = item['bbox']
        require(type(box) is list and len(box) == 4 and all(type(v) is int for v in box),
                'MOSS bbox须为四个整数像素坐标')
        ymin, xmin, ymax, xmax = box
        require(-height // 2 <= ymin < ymax <= height // 2 and -width // 2 <= xmin < xmax <= width // 2,
                'MOSS边界框越界或次序无效；不得自动裁切或改写')
    return value


def visible_texts(candidate):
    return [item['text'] for item in layout(candidate)['items'] if item['label'] == 'text']
