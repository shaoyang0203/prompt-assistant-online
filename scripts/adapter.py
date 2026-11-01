"""Existing delivery conventions, driven by the local registry. No visual redesign."""
import json
import re
from math import gcd
from contracts import ROOT, read_json, require


def routes():
    registry = read_json(ROOT / 'adapters/registry.json')
    rows = registry['adapters']
    require(type(rows) is list and bool(rows), 'Adapter配置为空')
    names = []
    for row in rows:
        require(row.get('implemented') is True and row.get('visual_redesign') is False, 'Adapter能力标注无效')
        require(row['aspect_ratio'] in ('inside-prompt', 'outside-prompt'), '未知画幅输出位置')
        require(row['ratio_format'] in ('natural-language', 'midjourney-ar', 'external-setting'), '未知比例表达')
        require((row['aspect_ratio'] == 'outside-prompt') == (row['ratio_format'] == 'external-setting'), '比例格式与输出位置冲突')
        names.extend([row['target'], *row['aliases']])
    require(all(type(name) is str and name for name in names) and len(set(names)) == len(names), '路由名称冲突')
    require(len({row['id'] for row in rows}) == len(rows), 'Adapter ID重复')
    return rows


def route(target='generic'):
    require(type(target) is str, '目标路由类型错误')
    excluded = read_json(ROOT / 'adapters/registry.json').get('excluded_routes', {})
    require(target not in excluded, '该路由已明确不纳入本版: ' + target)
    for row in routes():
        if target in (row['target'], *row['aliases']):
            return row
    require(False, '目标路由未落实或名称不明确，不能静默回退通用路由: ' + target)


def ratio_text(ratio, normalized=False):
    require(type(ratio) is dict and set(ratio) == {'width', 'height'} and
            all(type(v) is int and v > 0 for v in ratio.values()), '画幅必须为正整数宽高，不能填默认值')
    factor = gcd(ratio['width'], ratio['height']) if normalized else 1
    return str(ratio['width'] // factor) + ':' + str(ratio['height'] // factor)


def validate_ratio(selected, ratio):
    text = ratio_text(ratio)
    allowed = selected['supported_aspect_ratios']
    require(allowed is None or ratio_text(ratio, normalized=True) in allowed,
            '已确认画幅' + text + '不在该路由已登记集合中；保留母版，需说明限制并由用户选择替代或其他路由')
    return text


def raw_body(candidate):
    separator = route(candidate.get('target', 'generic')).get('segment_separator', '\n\n')
    return separator.join(segment['text'] for segment in candidate['segments'])


def control_problems(candidate, image_literals=()):
    # Only explicit canvas-control syntax is deterministic. Semantic paraphrases need LLM review.
    if route(candidate.get('target', 'generic'))['prompt'] == 'json-layout':
        from moss_layout import layout
        layout(candidate)
        return []
    text = raw_body(candidate)
    for literal in image_literals:
        text = text.replace(literal, '')
    controls = r'--(?:ar|aspect)\b|(?:aspect\s*ratio|宽高比|画幅比例|画幅|比例)\s*[:：=]?\s*\d+\s*[:：/]\s*\d+'
    return ['正文重复或绕过Adapter写入画幅控制；请把画幅仅留在结构参数，由路由排版'] if re.search(controls, text, re.I) else []


def render(candidate):
    selected = route(candidate.get('target', 'generic'))
    ratio = candidate['parameters']['aspect_ratio']
    text = validate_ratio(selected, ratio)
    prompt = raw_body(candidate)
    is_layout = selected['prompt'] == 'json-layout'
    if is_layout:
        from moss_layout import layout
        prompt = json.dumps(layout(candidate), ensure_ascii=False, separators=(',', ':'))
    external = None
    if selected['ratio_format'] == 'natural-language':
        prompt += '\n\nAspect ratio: ' + text + '.'
    elif selected['ratio_format'] == 'midjourney-ar':
        prompt += ' --ar ' + text
    else:
        external = {'aspect_ratio': text, 'channel': selected['external_channel']}
        if is_layout:
            external['image_size'] = dict(candidate['parameters']['image_size'])
    # A longer Markdown fence also preserves user-authored image text containing backticks.
    runs = re.findall(r'`+', prompt)
    fence = '`' * max(3, 1 + max((len(run) for run in runs), default=0))
    prefix = '' if external is None else '建议画幅：' + text + '；' + external['channel'] + '。\n\n'
    if is_layout:
        size = external['image_size']
        prefix = ('画幅：' + text + '；画布尺寸：' + str(size['width']) + '×' + str(size['height']) +
                  '；请在MOSS-Image本地Layout工作流设置相同尺寸。\n\n')
    return {'prompt': prompt, 'external_settings': external,
            'adapter_id': selected['id'], 'target': selected['target'],
            'aspect_ratio_placement': selected['aspect_ratio'],
            'formatted': prefix + fence + '\n' + prompt + '\n' + fence}
