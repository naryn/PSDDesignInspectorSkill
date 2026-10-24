"""Standalone HTML viewer for Design IR and measured geometry."""

import base64
import json
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image


def _encode_preview(image: Image.Image, max_edge: int = 1600) -> str:
    preview = image.convert("RGBA")
    background = Image.new("RGB", preview.size, (255, 255, 255))
    background.paste(preview, mask=preview.split()[3])

    if max(background.size) > max_edge:
        background.thumbnail((max_edge, max_edge), Image.LANCZOS)

    buffer = BytesIO()
    background.save(buffer, format="JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _ordered_layers(layers: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten the layer tree topmost-first, preserving parent/child grouping."""
    children: Dict[Optional[str], List[Dict[str, Any]]] = {}
    for layer in layers:
        children.setdefault(layer.get("parent_id"), []).append(layer)

    ordered: List[Dict[str, Any]] = []

    def visit(parent_id: Optional[str]) -> None:
        for layer in sorted(
            children.get(parent_id, []), key=lambda item: item.get("z_index", 0), reverse=True
        ):
            ordered.append(layer)
            visit(layer.get("id"))

    visit(None)
    return ordered


def _viewer_payload(design_ir: Dict[str, Any], preview_uri: str) -> Dict[str, Any]:
    metadata = design_ir.get("document", {}).get("metadata", {})
    layers = []
    for layer in design_ir.get("source", {}).get("rawLayers", []):
        geometry = layer.get("geometry", {})
        extraction = layer.get("extraction", {})
        layers.append({
            "id": layer.get("id"),
            "name": layer.get("name"),
            "kind": layer.get("kind"),
            "parent_id": layer.get("parent_id"),
            "depth": layer.get("depth", 0),
            "z_index": layer.get("z_index", 0),
            "visible": layer.get("visible", True),
            "bounds": geometry.get("source_bounds", {}),
            "relative": geometry.get("relative_to_parent", {}),
            "opacity": layer.get("appearance", {}).get("opacity", 1.0),
            "blend_mode": layer.get("appearance", {}).get("blend_mode", "normal"),
            "mask": layer.get("mask"),
            "vector_mask": layer.get("vector_mask"),
            "smart_object_link": layer.get("smart_object_link"),
            "smart_object_data": layer.get("smart_object_data"),
            "extraction": {
                "status": extraction.get("status"),
                "source": extraction.get("source"),
                "property_sources": extraction.get("property_sources", {}),
                "unsupported_properties": extraction.get("unsupported_properties", []),
            },
        })

    analysis = design_ir.get("analysis", {})
    return {
        "document": {
            "filename": metadata.get("filename"),
            "width": metadata.get("width_px"),
            "height": metadata.get("height_px"),
            "colorMode": metadata.get("color_mode"),
        },
        "layers": _ordered_layers(layers),
        "relationships": analysis.get("spatialRelationships", []),
        "hypotheses": analysis.get("layoutHypotheses", []),
        "warnings": design_ir.get("diagnostics", {}).get("warnings", []),
        "preview": preview_uri,
    }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PSD Design Inspector</title>
<style>
  :root {
    --bg: #f4f5f7; --panel: #ffffff; --border: #dfe3e8; --text: #1f2933;
    --muted: #6b7280; --accent: #2f80ed; --gap: #e67e22; --layout: #9b51e0;
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif;
  }
  header {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    padding: 10px 16px; background: var(--panel); border-bottom: 1px solid var(--border);
  }
  header .title { font-weight: 600; font-size: 14px; }
  header .meta { color: var(--muted); }
  header .note {
    margin-left: auto; color: #8a6d3b; background: #fcf8e3;
    border: 1px solid #faebcc; padding: 2px 8px; border-radius: 4px; font-size: 12px;
  }
  main {
    display: flex; height: calc(100% - 49px); min-height: 0;
  }
  aside { background: var(--panel); overflow: auto; flex: 0 0 280px; }
  #sidebar { border-right: 1px solid var(--border); padding: 12px; }
  #inspector { border-left: 1px solid var(--border); padding: 12px; flex-basis: 320px; }
  #viewport { flex: 1 1 auto; overflow: auto; padding: 24px; display: flex; justify-content: center; align-items: flex-start; }
  #search {
    width: 100%; padding: 7px 9px; border: 1px solid var(--border);
    border-radius: 5px; font: inherit; margin-bottom: 10px;
  }
  .toggles { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; margin-bottom: 14px; }
  .toggles label { color: var(--muted); white-space: nowrap; cursor: pointer; user-select: none; }
  .section-title {
    font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
    color: var(--muted); margin: 12px 0 6px; font-weight: 600;
  }
  .section-title span { font-weight: 400; }
  #layerList { display: flex; flex-direction: column; gap: 1px; }
  .layer-row {
    display: flex; align-items: center; gap: 6px; padding: 4px 6px;
    border-radius: 4px; cursor: pointer; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
  }
  .layer-row:hover { background: #eef2f7; }
  .layer-row.selected { background: #e3edfd; }
  .layer-row.hidden-layer { opacity: .45; }
  .layer-row .dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 8px; }
  .layer-row .name { overflow: hidden; text-overflow: ellipsis; }
  .layer-row .id { color: var(--muted); font-size: 11px; margin-left: auto; }
  #stage { position: relative; display: inline-block; max-width: 100%; line-height: 0; box-shadow: 0 2px 14px rgba(0,0,0,.12); }
  #preview { display: block; width: 100%; height: auto; }
  #boxes, #gaps, #layouts, #labels { position: absolute; inset: 0; pointer-events: none; }
  .box {
    position: absolute; border: 1px solid rgba(47,128,237,.85);
    pointer-events: auto; cursor: pointer; transition: background .1s;
  }
  .box.kind-text { border-color: rgba(39,174,96,.9); }
  .box.kind-shape { border-color: rgba(242,153,74,.95); }
  .box.kind-smart_object { border-color: rgba(155,81,224,.9); }
  .box.kind-group { border-style: dashed; border-color: rgba(127,140,141,.9); }
  .box.kind-adjustment { border-color: rgba(192,57,43,.9); }
  .box:hover, .box.hovered { background: rgba(47,128,237,.12); }
  .box.selected { outline: 2px solid #1f2933; outline-offset: 0; background: rgba(47,128,237,.15); }
  .box.dim { opacity: .15; }
  .box.layer-hidden { display: none; }
  .box.hide-bounds { display: none; }
  .label {
    position: absolute; transform: translateY(-100%); white-space: nowrap;
    font-size: 10px; line-height: 14px; padding: 0 4px; border-radius: 3px;
    color: #fff; background: rgba(31,41,51,.82); pointer-events: none;
  }
  .label.kind-text { background: rgba(39,174,96,.85); }
  .label.kind-shape { background: rgba(242,153,74,.9); }
  .label.kind-group { background: rgba(127,140,141,.85); }
  .label.hide-label { display: none; }
  .gap { position: absolute; pointer-events: none; }
  .gap-h { border-top: 2px dashed var(--gap); }
  .gap-v { border-left: 2px dashed var(--gap); }
  .gap-label {
    position: absolute; font-size: 10px; color: #fff; background: var(--gap);
    padding: 0 4px; border-radius: 3px; white-space: nowrap;
  }
  .hypothesis {
    position: absolute; border: 2px dashed var(--layout); pointer-events: none;
    background: rgba(155,81,224,.04);
  }
  .hypothesis-label {
    position: absolute; font-size: 10px; color: #fff; background: var(--layout);
    padding: 0 4px; border-radius: 3px; white-space: nowrap; transform: translateY(-100%);
  }
  #tooltip {
    position: absolute; display: none; z-index: 10; pointer-events: none;
    background: rgba(17,24,39,.92); color: #fff; padding: 5px 7px;
    border-radius: 4px; font-size: 11px; line-height: 1.4; white-space: nowrap;
  }
  #details dl { margin: 0; display: grid; grid-template-columns: 110px 1fr; gap: 5px 8px; }
  #details dt { color: var(--muted); }
  #details dd { margin: 0; word-break: break-word; }
  #details .hint { color: var(--muted); }
  #details .sources { margin: 8px 0 0; padding-left: 16px; color: var(--muted); }
  #warnings ul { margin: 0; padding-left: 16px; color: #8a6d3b; }
  #warnings li { margin-bottom: 4px; }
  .empty { color: var(--muted); font-style: italic; }
</style>
</head>
<body>
<header>
  <div class="title" id="title">PSD Design Inspector</div>
  <div class="meta" id="meta"></div>
  <div class="note">坐标来自 sourceBounds；间距/布局为确定性测量与候选推断，非 PSD 原生值</div>
</header>
<main>
  <aside id="sidebar">
    <input id="search" type="search" placeholder="搜索图层名称或 ID">
    <div class="toggles">
      <label><input type="checkbox" id="toggleBounds" checked> 图层边界</label>
      <label><input type="checkbox" id="toggleLabels" checked> 名称</label>
      <label><input type="checkbox" id="toggleSpacing" checked> 间距</label>
      <label><input type="checkbox" id="toggleLayout" checked> 布局候选</label>
      <label><input type="checkbox" id="toggleHidden"> 隐藏图层</label>
    </div>
    <div class="section-title">图层 <span id="layerCount"></span></div>
    <div id="layerList"></div>
    <div class="section-title">诊断 <span id="warningCount"></span></div>
    <div id="warnings"></div>
  </aside>
  <section id="viewport">
    <div id="stage">
      <img id="preview" alt="PSD composite preview">
      <div id="boxes"></div>
      <div id="gaps"></div>
      <div id="layouts"></div>
      <div id="labels"></div>
      <div id="tooltip"></div>
    </div>
  </section>
  <aside id="inspector">
    <div class="section-title">属性</div>
    <div id="details"><span class="hint">点击图层查看 IR 记录。</span></div>
  </aside>
</main>
<script>
const DATA = /*__DATA__*/;
const W = DATA.document.width || 1;
const H = DATA.document.height || 1;
const byId = new Map(DATA.layers.map(layer => [layer.id, layer]));
const boxesRoot = document.getElementById('boxes');
const labelsRoot = document.getElementById('labels');
const gapsRoot = document.getElementById('gaps');
const layoutsRoot = document.getElementById('layouts');
const listRoot = document.getElementById('layerList');
const detailsRoot = document.getElementById('details');
const tooltip = document.getElementById('tooltip');
const stage = document.getElementById('stage');

const KIND_COLORS = {
  pixel: '#2f80ed', text: '#27ae60', shape: '#f2994a',
  smart_object: '#9b51e0', group: '#7f8c8d', adjustment: '#c0392b'
};

function pct(value, total) { return (value / total * 100) + '%'; }
function boundsOf(layer) { return layer && layer.bounds ? layer.bounds : {x:0,y:0,width:0,height:0}; }
function kindClass(layer) { return 'kind-' + (layer.kind || 'pixel'); }
function isVisible(layer) { return layer.visible !== false; }

document.getElementById('title').textContent = DATA.document.filename || 'PSD Design Inspector';
document.getElementById('meta').textContent =
  W + ' × ' + H + ' · ' + DATA.layers.length + ' layers · ' +
  (DATA.document.colorMode || 'unknown color mode');
document.getElementById('layerCount').textContent = '(' + DATA.layers.length + ')';

const boxById = new Map();
const labelById = new Map();
let labelsCollided = new Set();

function buildOverlays() {
  let index = 0;
  for (const layer of DATA.layers) {
    const b = boundsOf(layer);
    if (b.width > 0 && b.height > 0) {
      const box = document.createElement('div');
      box.className = 'box ' + kindClass(layer) + (isVisible(layer) ? '' : ' layer-hidden');
      box.style.left = pct(b.x, W);
      box.style.top = pct(b.y, H);
      box.style.width = pct(b.width, W);
      box.style.height = pct(b.height, H);
      box.addEventListener('mouseenter', () => showTooltip(layer));
      box.addEventListener('mousemove', moveTooltip);
      box.addEventListener('mouseleave', hideTooltip);
      box.addEventListener('click', (event) => { event.stopPropagation(); selectLayer(layer.id); });
      boxesRoot.appendChild(box);
      boxById.set(layer.id, box);
    }

    const label = document.createElement('div');
    label.className = 'label ' + kindClass(layer);
    label.textContent = layer.name || layer.id;
    label.style.left = pct(b.x, W);
    label.style.top = pct(b.y, H);
    if (index % 2 === 1) label.style.transform = 'translateY(0)';
    labelsRoot.appendChild(label);
    labelById.set(layer.id, label);
    index += 1;
  }
}

function overlaps(a, b) {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

function declutterLabels(candidate) {
  labelsCollided = new Set();
  const placed = [];
  const stageRect = stage.getBoundingClientRect();
  for (const [id, label] of labelById) {
    label.style.display = 'none';
    const layer = byId.get(id);
    if (!layer || !candidate(layer)) continue;
    label.style.display = '';
    const rect = label.getBoundingClientRect();
    if (!rect.width || !rect.height) { label.style.display = 'none'; continue; }
    const box = {
      left: rect.left - stageRect.left, top: rect.top - stageRect.top,
      right: rect.right - stageRect.left, bottom: rect.bottom - stageRect.top
    };
    if (placed.some(other => overlaps(other, box))) {
      labelsCollided.add(id);
      label.style.display = 'none';
    } else {
      placed.push(box);
    }
  }
}

function buildGaps() {
  for (const rel of DATA.relationships || []) {
    if (!rel.projection_overlap || !rel.is_neighbor) continue;
    const source = byId.get(rel.source_layer_id);
    const target = byId.get(rel.target_layer_id);
    if (!source || !target || !isVisible(source) || !isVisible(target)) continue;
    const a = boundsOf(source), b = boundsOf(target);
    const gap = Number(rel.distance_px);
    if (!(gap > 0)) continue;
    const position = rel.relative_position;
    let element = null, label = null;

    if (position === 'right' || position === 'left') {
      const top = Math.max(a.y, b.y);
      const bottom = Math.min(a.y + a.height, b.y + b.height);
      if (bottom <= top) continue;
      const start = position === 'right' ? a.x + a.width : b.x + b.width;
      const end = position === 'right' ? b.x : a.x;
      if (end <= start) continue;
      element = document.createElement('div');
      element.className = 'gap gap-h';
      element.style.left = pct(start, W);
      element.style.width = pct(end - start, W);
      element.style.top = pct((top + bottom) / 2, H);
      label = document.createElement('div');
      label.className = 'gap-label';
      label.textContent = gap + 'px';
      label.style.left = pct(start, W);
      label.style.top = 'calc(' + pct((top + bottom) / 2, H) + ' - 16px)';
    } else if (position === 'below' || position === 'above') {
      const left = Math.max(a.x, b.x);
      const right = Math.min(a.x + a.width, b.x + b.width);
      if (right <= left) continue;
      const start = position === 'below' ? a.y + a.height : b.y + b.height;
      const end = position === 'below' ? b.y : a.y;
      if (end <= start) continue;
      element = document.createElement('div');
      element.className = 'gap gap-v';
      element.style.top = pct(start, H);
      element.style.height = pct(end - start, H);
      element.style.left = pct((left + right) / 2, W);
      label = document.createElement('div');
      label.className = 'gap-label';
      label.textContent = gap + 'px';
      label.style.left = 'calc(' + pct((left + right) / 2, W) + ' + 4px)';
      label.style.top = pct(start, H);
    }
    if (element && label) { gapsRoot.appendChild(element); gapsRoot.appendChild(label); }
  }
}

function buildLayouts() {
  for (const hypothesis of DATA.hypotheses || []) {
    const members = (hypothesis.layers_involved || [])
      .map(id => byId.get(id)).filter(layer => layer && isVisible(layer));
    if (!members.length) continue;
    let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
    for (const layer of members) {
      const b = boundsOf(layer);
      left = Math.min(left, b.x); top = Math.min(top, b.y);
      right = Math.max(right, b.x + b.width); bottom = Math.max(bottom, b.y + b.height);
    }
    if (!isFinite(left) || right <= left || bottom <= top) continue;
    const box = document.createElement('div');
    box.className = 'hypothesis';
    box.style.left = pct(left, W); box.style.top = pct(top, H);
    box.style.width = pct(right - left, W); box.style.height = pct(bottom - top, H);
    const label = document.createElement('div');
    label.className = 'hypothesis-label';
    const detail = hypothesis.flex_direction ? ' ' + hypothesis.flex_direction : '';
    label.textContent = hypothesis.layout_type + detail +
      ' · conf ' + Number(hypothesis.confidence || 0).toFixed(2);
    label.style.left = pct(left, W); label.style.top = pct(top, H);
    layoutsRoot.appendChild(box); layoutsRoot.appendChild(label);
  }
}

function buildLayerList() {
  for (const layer of DATA.layers) {
    const row = document.createElement('div');
    row.className = 'layer-row' + (isVisible(layer) ? '' : ' hidden-layer');
    row.dataset.id = layer.id;
    row.dataset.search = ((layer.name || '') + ' ' + layer.id).toLowerCase();
    row.style.paddingLeft = (6 + (layer.depth || 0) * 12) + 'px';

    const dot = document.createElement('span');
    dot.className = 'dot';
    dot.style.background = KIND_COLORS[layer.kind] || '#34495e';

    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = layer.name || '(unnamed)';

    const id = document.createElement('span');
    id.className = 'id';
    id.textContent = layer.id;

    row.append(dot, name, id);
    row.addEventListener('click', () => selectLayer(layer.id));
    listRoot.appendChild(row);
  }
}

function buildWarnings() {
  const warnings = DATA.warnings || [];
  document.getElementById('warningCount').textContent = '(' + warnings.length + ')';
  if (!warnings.length) {
    const empty = document.createElement('div');
    empty.className = 'empty';
    empty.textContent = '无诊断警告';
    document.getElementById('warnings').appendChild(empty);
    return;
  }
  const list = document.createElement('ul');
  for (const warning of warnings) {
    const item = document.createElement('li');
    item.textContent = warning;
    list.appendChild(item);
  }
  document.getElementById('warnings').appendChild(list);
}

function showTooltip(layer) {
  const b = boundsOf(layer);
  tooltip.textContent = (layer.name || layer.id) + ' · ' + layer.kind +
    ' · ' + b.width + '×' + b.height + ' @ ' + b.x + ',' + b.y;
  tooltip.style.display = 'block';
  const box = boxById.get(layer.id);
  if (box) box.classList.add('hovered');
}

function moveTooltip(event) {
  const rect = stage.getBoundingClientRect();
  tooltip.style.left = (event.clientX - rect.left + 12) + 'px';
  tooltip.style.top = (event.clientY - rect.top + 12) + 'px';
}

function hideTooltip() {
  tooltip.style.display = 'none';
  for (const box of boxById.values()) box.classList.remove('hovered');
}

function selectLayer(id) {
  const layer = byId.get(id);
  if (!layer) return;
  for (const [layerId, box] of boxById) box.classList.toggle('selected', layerId === id);
  for (const row of listRoot.children) row.classList.toggle('selected', row.dataset.id === id);
  renderDetails(layer);
}

function renderDetails(layer) {
  const b = boundsOf(layer);
  const relative = layer.relative || {};
  const extraction = layer.extraction || {};
  detailsRoot.textContent = '';

  const dl = document.createElement('dl');
  const add = (key, value) => {
    const dt = document.createElement('dt'); dt.textContent = key;
    const dd = document.createElement('dd'); dd.textContent = value;
    dl.append(dt, dd);
  };
  add('名称', layer.name || '(unnamed)');
  add('ID', layer.id);
  add('类型', layer.kind);
  add('可见', isVisible(layer) ? '是' : '否');
  add('层级', String(layer.depth));
  add('z-index', String(layer.z_index));
  add('父级', layer.parent_id || '(root)');
  add('边界', b.x + ', ' + b.y + ' · ' + b.width + ' × ' + b.height);
  add('相对父级', (relative.x ?? '-') + ', ' + (relative.y ?? '-'));
  add('不透明度', String(layer.opacity));
  add('混合模式', layer.blend_mode || 'normal');
  if (layer.mask) {
    const mask = layer.mask;
    const bounds = mask.bounds || {};
    add('像素蒙版', (bounds.width ?? 0) + ' × ' + (bounds.height ?? 0) +
      (mask.disabled ? ' · 禁用' : '') + (mask.inverted ? ' · 反相' : ''));
  }
  if (layer.vector_mask) {
    const mask = layer.vector_mask;
    const bounds = mask.normalized_bounds || {};
    const percent = (value) => Number((Number(value || 0) * 100).toFixed(1)) + '%';
    add('矢量蒙版', percent(bounds.width) + ' × ' + percent(bounds.height) +
      ' · ' + (mask.path_count || 0) + ' 路径' + (mask.disabled ? ' · 禁用' : ''));
  }
  if (layer.smart_object_data) {
    const object = layer.smart_object_data;
    add('智能对象', (object.kind || 'unknown') + ' · ' + (object.filename || '(unnamed)'));
    if (object.filesize_bytes != null) add('对象大小', object.filesize_bytes + ' bytes');
    add('内容已解析', object.contents_extracted ? '是' : '否');
  }
  if (layer.smart_object_link) add('外部链接', layer.smart_object_link);
  add('提取状态', extraction.status || 'unknown');
  add('来源', extraction.source || 'unknown');
  detailsRoot.appendChild(dl);

  const unsupported = extraction.unsupported_properties || [];
  if (unsupported.length) {
    const note = document.createElement('div');
    note.className = 'section-title';
    note.textContent = '未支持属性';
    const list = document.createElement('ul');
    list.className = 'sources';
    for (const item of unsupported) {
      const entry = document.createElement('li'); entry.textContent = item; list.appendChild(entry);
    }
    detailsRoot.append(note, list);
  }

  const sources = extraction.property_sources || {};
  const keys = Object.keys(sources);
  if (keys.length) {
    const note = document.createElement('div');
    note.className = 'section-title';
    note.textContent = '属性来源';
    const list = document.createElement('ul');
    list.className = 'sources';
    for (const key of keys) {
      const entry = document.createElement('li');
      entry.textContent = key + ': ' + sources[key].source + ' (' + sources[key].confidence + ')';
      list.appendChild(entry);
    }
    detailsRoot.append(note, list);
  }
}

function applyVisibility() {
  const search = document.getElementById('search').value.trim().toLowerCase();
  const showBounds = document.getElementById('toggleBounds').checked;
  const showLabels = document.getElementById('toggleLabels').checked;
  const showSpacing = document.getElementById('toggleSpacing').checked;
  const showLayout = document.getElementById('toggleLayout').checked;
  const showHidden = document.getElementById('toggleHidden').checked;
  const matchesLayer = (layer) =>
    !search || ((layer.name || '') + ' ' + layer.id).toLowerCase().includes(search);

  for (const layer of DATA.layers) {
    const matches = matchesLayer(layer);
    const visible = showHidden || isVisible(layer);
    const box = boxById.get(layer.id);
    if (box) {
      box.classList.toggle('layer-hidden', !visible);
      box.classList.toggle('hide-bounds', !showBounds);
      box.classList.toggle('dim', search.length > 0 && !matches);
    }
  }

  // Greedy top-most-first placement: a label that would overlap an already
  // visible label is hidden until the user filters or zooms in.
  declutterLabels(layer =>
    showLabels && showBounds && (showHidden || isVisible(layer)) && matchesLayer(layer)
  );
  for (const [id, label] of labelById) {
    if (labelsCollided.has(id)) continue;
    const layer = byId.get(id);
    label.style.opacity = (search && layer && !matchesLayer(layer)) ? '0.2' : '1';
  }

  gapsRoot.style.display = showSpacing ? '' : 'none';
  layoutsRoot.style.display = showLayout ? '' : 'none';
  for (const row of listRoot.children) {
    row.style.display = (!search || row.dataset.search.includes(search)) ? '' : 'none';
  }
}

buildOverlays();
buildGaps();
buildLayouts();
buildLayerList();
buildWarnings();
for (const id of ['search','toggleBounds','toggleLabels','toggleSpacing','toggleLayout','toggleHidden']) {
  document.getElementById(id).addEventListener('input', applyVisibility);
  document.getElementById(id).addEventListener('change', applyVisibility);
}
document.getElementById('preview').addEventListener('load', () => applyVisibility());
window.addEventListener('resize', () => applyVisibility());
document.getElementById('preview').src = DATA.preview;
applyVisibility();
</script>
</body>
</html>
"""


def build_viewer_html(design_ir: Dict[str, Any], image: Image.Image) -> str:
    """Return a standalone HTML viewer with the preview embedded as a data URI."""
    payload = _viewer_payload(design_ir, _encode_preview(image))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return HTML_TEMPLATE.replace("/*__DATA__*/", data)
