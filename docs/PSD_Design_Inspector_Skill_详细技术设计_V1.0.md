# PSD Design Inspector Skill — PSD 设计稿全量解析 Skill 详细技术设计

> 版本：V1.0  
> 目标用户：Codex / Claude Code / AI Agent / 前端开发团队  
> 项目名称：`psd-design-inspector`  
> 目标：将 PSD / PSB 转换为完整、可溯源、可校验的设计信息（Design IR），供 Vue / HTML 页面还原、PSD Normalize Studio 和设计自动化系统使用。

## 1. 项目定位与目标

本项目不是简单的 PSD 图层读取器，而是面向前端还原的**设计信息提取 Skill**。输入 PSD / PSB，全面提取文档、图层、字体、字号、文字样式、颜色、边框、圆角、阴影、尺寸、位置、空间关系、资源及语义组件信息，输出标准化 Design IR。

**原则**：
1. 原生属性优先，不使用 AI 猜测已有的确定信息。
2. 原生数据不足时使用像素测量、几何计算、视觉模型、Photoshop UXP 补全。
3. 每个重要属性记录 `source`、`confidence`、异常与原始值。
4. 保留原始图层树，语义组件树独立生成，不覆盖原始结构。
5. 解析与 Vue/HTML 生成解耦。
6. 默认只读，不修改原始 PSD。
7. 属性无法可靠判断时输出 `unknown/null`，不得伪造精确结果。

### 1.1 工作流程

```text
PSD / PSB
   ↓
文档预检与原生图层解析
   ↓
文字 / 形状 / 样式 / 颜色 / 特效提取
   ↓
像素视觉分析（有必要时）
   ↓
空间关系与布局候选推断
   ↓
语义组件分析（独立于原始图层）
   ↓
Design IR 统一组装及校验
   ↓
设计规格文档、Token、PNG/SVG 资源、可视化标注
   ↓
下游 PSD Normalize Studio / Vue Generation Skill
```

## 2. 技术选型

| 技术 | 用途 | 说明 |
|---|---|---|
| Python | 解析核心与 CLI | 易于组合文件、视觉与 AI 处理能力 |
| `psd-tools` | PSD/PSB 主解析器 | 图层、文本、资源、样式基础解析；非 Photoshop 完整渲染引擎 |
| Pillow | RGBA、图像读写、色彩基础处理 | 配合 ICC 色彩转换 |
| NumPy | 像素和矩阵计算 | 变换与统计 |
| OpenCV | 图层轮廓、边缘、形状、边框分析 | 用于栅格化对象 |
| Pydantic | IR 数据模型、验证 | 明确字段及规范 |
| `ag-psd` | 可选 JS 解析适配器 | 主要为 Web/Node 集成预留，须评估格式覆盖 |
| Photoshop UXP / batchPlay | 可选高级补全 | 当原生解析无法可靠恢复高级属性时使用 |
| 视觉大模型 | 可选语义与复杂图片分析 | 仅处理缺失/歧义，必须保留来源和置信度 |

离线基础解析不得依赖云端 API。外部模型调用默认为禁止上传，需明确配置许可。

## 3. 功能需求

### 3.1 文档级解析

- 文件名、文件尺寸、SHA256、PSD/PSB 版本、解析器版本。
- 画布宽度/高度、DPI、坐标原点、颜色模式、位深、ICC 配置。
- 画板数量、画板范围及其独立坐标空间。
- 图层数、组数、最大层级、可见/隐藏数量、智能对象数量。
- 原始合成预览和独立渲染预览；如不一致须标注。
- 字体依赖列表、缺失资源、未支持属性清单。
- 色彩应记录 `rawColor`、`convertedColor`、`displayColor`；转换到 CSS sRGB 不得丢失源颜色模式。

### 3.2 图层全量解析

每个图层需要：
- `id`、原生 ID、名称、类型、父 ID、图层深度、z-order。
- 可见性、锁定状态、不透明度、填充不透明度、混合模式。
- `sourceBounds` 原生几何边界、`visibleBounds` 可见像素边界、`effectBounds` 包含特效的边界。
- 文档全局坐标、父节点局部坐标、画板坐标与变换矩阵。
- 蒙版、矢量蒙版、剪贴关系、关联智能对象及其资源引用。
- 图层样式、效果、可输出资源路径、异常状态。

**关键约束**：`bounds` 不一定等于视觉边界，阴影和透明区域必须分别处理。

### 3.3 文字解析

| 类别 | 属性 |
|---|---|
| 内容 | 文本内容、换行符、段落分隔、文字方向 |
| 字体 | 字体族、PostScript 名、字重、字形、缺失状态 |
| 字号 | PSD 原始单位、原始 pt、转换依据、最终有效 px |
| 文字外观 | 颜色、渐变、透明度、粗斜体、删除线、下划线 |
| 字符排版 | tracking、kerning、letter spacing |
| 段落排版 | 对齐、缩进、段前后距、行高、文本方向 |
| 文本盒 | 文本框边界、内容边界、自动换行、变换矩阵 |
| 复杂文字 | 同层不同 `characterRuns` 与 `paragraphRuns` |
| 特效 | 描边、阴影、发光等 |

文字必须存储 `sourceFontSize` 和 `effectiveFontSizePx`，不能无条件将 PSD pt 数值等同 CSS px。对混合文字样式需保存起止 offset。Schema 须统一字符 offset 索引规则（推荐 Unicode code point），适配器处理 UTF-16 或其他索引差异。

### 3.4 颜色与填充

- RGB/RGBA/HEX、透明度、原生颜色空间与 ICC 转换。
- 纯色、线性/径向/角度渐变、色标和透明度色标、图案和纹理。
- 文字、描边、阴影、叠加色等多色来源。
- 图片主色、辅助色（属统计推断，不应覆盖原色）。
- 复杂混合造成可见颜色变化时，保持原始值和显示值分离。

### 3.5 边框、圆角、形状与效果

- 描边颜色、宽度、透明度、内/中/外定位。
- 四边独立边框（若可可靠提取）；四角独立圆角。
- 矩形、椭圆、多边形、自定义路径、路径填充规则。
- 矢量 mask、剪裁、旋转、缩放、斜切和仿射变换。
- 阴影、内阴影、内外发光、颜色叠加、渐变叠加等。
- 对栅格化形状的圆角、边框采用轮廓拟合并报告误差。

### 3.6 空间关系与布局分析

计算：
- 文档绝对坐标、相对父容器位置及四边距。
- 最近相邻元素的水平、垂直间距。
- 对齐（上、下、左、右、中线、文本基线）；重叠面积与比例。
- 组内 padding 候选、元素间 gap、重复卡片行列、对称关系。
- Flex、Grid、Absolute 候选布局及对应证据。

**严格区分**：`measuredRelationships` 是实际几何测量；`layoutHypotheses` 是对前端布局方式的推断，不能把候选 CSS 当作 PSD 原生值。

### 3.7 语义组件分析

识别 Button、Input、Card、Dialog、Navigation、Menu、Icon、Image、Table、Tag、Header、Footer 等；结合名称、层级、视觉、几何、重复结构判别。一个由 3 个 PSD 图层组成的按钮，可在语义组件树新增一个 Button 并通过 `sourceLayerIds` 连接原始图层，但**不得修改或合并原始图层树**。

### 3.8 图层资源导出

- PNG（透明）、WebP、SVG（能正确保留矢量时）、单图层预览、智能对象预览。
- 资源需记录原始图层 ID、坐标、宽高、offset、mask、哈希、导出文件路径。
- 通过图像内容哈希去重。
- 对复杂纹理、角标、游戏 UI 装饰优先保留位图资源；不强制转换 CSS。

### 3.9 Design Tokens 提取

聚合颜色、字体、字号、字重、间距、圆角、阴影、常见组件样式，输出 `design-tokens.json`。Token 命名是候选（如 `primary`、`textPrimary`），支持人工修订；颜色出现频率高不等于品牌主色。

## 4. 七层架构

```text
L7 Agent Skill: SKILL.md / Codex / Claude Code
L6 Workflow: 编排、任务状态、缓存、部分重试、错误恢复
L5 Semantic: 组件、布局、语义命名
L4 Geometry: 相对坐标、矩阵、间距、对齐、空间图
L3 Extractors: 原生属性、像素分析、资源导出
L2 Adapters: psd-tools / ag-psd / Photoshop UXP
L1 Input: PSD/PSB、文件校验、色彩空间、画板
---------------------------------------------
Shared: Design IR / Schema / Provenance / Assets / Diagnostics
```

| 模块 | 输入 | 输出 |
|---|---|---|
| DocumentParser | PSD | 文档元数据 |
| LayerTreeParser | 原生层 | 原始图层树 |
| TextStyleExtractor | 文本引擎信息 | `characterRuns` 等 |
| ShapeStyleExtractor | 矢量与样式描述 | fill/stroke/radius |
| PixelAnalyzer | RGBA | 轮廓、边界、像素统计 |
| GeometryEngine | 边界/矩阵 | 邻居、距离、对齐 |
| ComponentAnalyzer | 图层+视觉+关系 | 独立组件树 |
| TokenExtractor | 全部元素 | Token 候选 |
| AssetExporter | 图层或合成图像 | 位图/矢量资源 |
| IRBuilder | 标准化结果 | 主 `design.json` |
| Validator | IR + 源证据 | 质量诊断 |
| ReportGenerator | IR | Markdown、预览、标注 |

## 5. Design IR 数据协议

### 5.1 设计目标

- Schema 版本化，例如 `1.0.0`，有迁移策略。
- 文档、原生数据、分析数据、Token、诊断分区。
- 主数据存于 `design.json`，分拆文件仅为投影，不能出现多份相互冲突的权威数据。
- 记录 `coordinateSpaceId`、`sourceFingerprint`、`assetRefs`、`maskRefs`、`clippingRef`。
- `raw` 保留必要原生描述符；`extraction` 含状态、来源、置信度与诊断。

### 5.2 推荐总结构

```json
{
  "schemaVersion": "1.0.0",
  "document": {
    "metadata": {},
    "artboards": [],
    "coordinateSpaces": []
  },
  "source": {
    "rawLayers": [],
    "layerHierarchy": [],
    "originalStyles": [],
    "nativeReferences": []
  },
  "analysis": {
    "measurements": [],
    "spatialRelationships": [],
    "layoutHypotheses": [],
    "semanticComponents": []
  },
  "designSystem": {
    "colorTokens": [],
    "typographyTokens": [],
    "spacingTokens": [],
    "componentPatterns": []
  },
  "diagnostics": {
    "unsupportedFeatures": [],
    "warnings": [],
    "validationResults": []
  }
}
```

### 5.3 图层示例

```json
{
  "id": "layer-1038",
  "sourceLayerId": 1038,
  "name": "登录按钮背景",
  "kind": "shape",
  "parentId": "group-100",
  "zIndex": 12,
  "visible": true,
  "coordinateSpaceId": "document",
  "geometry": {
    "sourceBounds": {"x": 420, "y": 580, "width": 240, "height": 48},
    "visibleBounds": {"x": 420, "y": 580, "width": 240, "height": 48},
    "effectBounds": null,
    "relativeToParent": {"x": 20, "y": 180},
    "normalized": {"x": 0.35, "y": 0.725, "width": 0.2, "height": 0.06},
    "rotationDeg": 0,
    "transform": [1, 0, 0, 1, 0, 0]
  },
  "appearance": {
    "opacity": 1,
    "fillOpacity": 1,
    "blendMode": "normal",
    "fills": [{"type": "solid", "color": "#246BFD", "opacity": 1}],
    "strokes": [{"widthPx": 1, "color": "#1851CD", "position": "inside"}],
    "borderRadius": {"topLeft": 8, "topRight": 8, "bottomRight": 8, "bottomLeft": 8},
    "shadows": [{"type": "drop", "offsetX": 0, "offsetY": 4, "blurPx": 12, "spreadPx": 0, "color": "#000000", "opacity": 0.15}]
  },
  "relationships": {
    "parentComponentId": "component-login-button",
    "alignmentGroupIds": ["align-12"],
    "spacingGroupIds": ["spacing-6"]
  },
  "extraction": {
    "status": "complete",
    "properties": {
      "geometry.sourceBounds": {"source": "psd_native", "confidence": 1},
      "appearance.borderRadius": {"source": "psd_native", "confidence": 1},
      "appearance.shadows": {"source": "geometry_computed", "confidence": 0.92}
    }
  }
}
```

> 示例属性仅用于说明协议，非真实设计图数据。`confidence` 对推断值是评分，不应宣传为经过校准的概率。

### 5.4 文字对象示例

```json
{
  "text": {
    "content": "欢迎使用系统",
    "orientation": "horizontal",
    "textBox": {"x": 120, "y": 80, "width": 320, "height": 60},
    "characterRuns": [
      {
        "start": 0, "end": 2, "content": "欢迎",
        "font": {"family": "PingFang SC", "postScriptName": null, "weight": 600},
        "sourceFontSize": {"value": 24, "unit": "pt"},
        "effectiveFontSizePx": 32, "color": "#FFFFFF", "tracking": 0
      },
      {
        "start": 2, "end": 6, "content": "使用系统",
        "font": {"family": "PingFang SC", "weight": 400},
        "sourceFontSize": {"value": 18, "unit": "pt"},
        "effectiveFontSizePx": 24, "color": "#CCCCCC"
      }
    ],
    "paragraphRuns": [{"start": 0, "end": 6, "alignment": "left", "lineHeightPx": null, "direction": "ltr"}]
  }
}
```

### 5.5 属性来源

| source | 释义 |
|---|---|
| `psd_native` | PSD 原生数据 |
| `photoshop_api` | Photoshop UXP 获得 |
| `pixel_measured` | 图像像素测量 |
| `geometry_computed` | 确定性几何计算 |
| `vision_inferred` | 视觉/AI 推断 |
| `manual_override` | 人工修正 |

## 6. 几何与空间关系算法

### 6.1 坐标转换

- 全局坐标、父局部坐标、画板局部坐标均需明确。
- 无变换时：`localX = globalX - parentX`，`localY = globalY - parentY`。
- 有旋转/缩放/斜切时，应使用父级仿射矩阵逆矩阵映射，不得直接坐标相减。
- 无法逆变换时保留全局坐标、记录 `non_invertible_transform`。

### 6.2 邻接与间距

- 当 B 位于 A 右侧且正交投影有效重叠时，`gapX = B.left - A.right`。
- 当 B 位于 A 下方且正交投影有效重叠时，`gapY = B.top - A.bottom`。
- 必须考虑遮挡、重叠、透明视觉边界、多层覆盖、组内外关系。
- 不应对任意两个空间上不相邻对象定义 CSS gap。

### 6.3 对齐与布局

```yaml
geometry:
  alignment:
    tolerance_px: 2
    relative_tolerance: 0.005
  spacing:
    tolerance_px: 2
    min_overlap_ratio: 0.3
  layout:
    detect_flex: true
    detect_grid: true
    detect_absolute: true
```

分别输出实际测量与候选布局。判断网格时结合元素尺寸接近度、行列中心聚类、重复间距与结构相似性。推荐布局候选必须附证据和冲突情况。

## 7. 分级解析与视觉补全

| 级别 | 场景 | 策略 |
|---|---|---|
| L0 | 原生属性足够 | PSD 原生提取 |
| L1 | 有坐标与形状 | 确定性计算 |
| L2 | 栅格化/边界不明 | 图像轮廓与颜色分析 |
| L3 | 语义不明 | 视觉 AI 判断 |
| L4 | 高级样式不支持且 Photoshop 可用 | UXP 补全 |
| L5 | 冲突仍未解决 | 人工确认 |

这些等级描述能力层次，不要求固定顺序；高精度模式可在视觉推断前先尝试 Photoshop UXP。

**示例：单 PNG 图层按钮**：原生只能知道图层大小和位置，视觉分析可推断背景颜色、轮廓圆角和文本位置；文本内容可能通过 OCR 获取，字体名称不可可靠恢复则输出 `unknown`。原始图层仍然是单一 `pixel` 图层，推断出来的 Button 只写入语义树。

## 8. 项目结构

```text
psd-design-inspector/
├── SKILL.md
├── README.md
├── pyproject.toml
├── config/
│   ├── default.yaml
│   ├── extraction-profiles.yaml
│   └── semantic-rules.yaml
├── schemas/
│   ├── design-ir.schema.json
│   ├── layer.schema.json
│   ├── typography.schema.json
│   ├── appearance.schema.json
│   ├── geometry.schema.json
│   └── extraction-report.schema.json
├── src/psd_inspector/
│   ├── cli.py
│   ├── pipeline.py
│   ├── adapters/
│   │   ├── base.py
│   │   ├── psd_tools_adapter.py
│   │   ├── ag_psd_adapter.py
│   │   └── photoshop_adapter.py
│   ├── extractors/
│   │   ├── document.py
│   │   ├── layer.py
│   │   ├── typography.py
│   │   ├── fills.py
│   │   ├── strokes.py
│   │   ├── effects.py
│   │   ├── shapes.py
│   │   └── smart_objects.py
│   ├── analysis/
│   │   ├── pixel_analyzer.py
│   │   ├── geometry_engine.py
│   │   ├── spatial_graph.py
│   │   ├── layout_detector.py
│   │   ├── component_detector.py
│   │   └── token_extractor.py
│   ├── exporters/
│   │   ├── asset_exporter.py
│   │   ├── ir_exporter.py
│   │   └── report_exporter.py
│   ├── models/
│   ├── validation/
│   └── utils/
├── integrations/
│   └── photoshop-uxp/
├── scripts/
│   ├── inspect.py
│   ├── export_assets.py
│   ├── validate_ir.py
│   └── compare_render.py
└── tests/
    ├── fixtures/
    ├── unit/
    ├── integration/
    └── golden/
```

### 8.1 SKILL.md 示例

```markdown
---
name: psd-design-inspector
description: >
  Analyze Photoshop PSD/PSB files and extract layers,
  typography, colors, effects, geometry, spatial
  relationships, design tokens and assets.
---

# PSD Design Inspector

## When to use
- PSD design specification extraction
- Layer and style inspection
- Typography, colors, spacing, borders, geometry
- Design IR conversion and asset extraction
- Preparation for HTML/Vue reconstruction

## Workflow
1. Verify input PSD/PSB.
2. Run preflight inspection.
3. Select extraction profile.
4. Run deterministic PSD parsing.
5. Identify missing/unsupported properties.
6. Run pixel or visual analysis only when needed.
7. Compute spatial relationships.
8. Build and validate Design IR.
9. Export assets and design specs.
10. Report unresolved properties and warnings.

## Rules
- Never overwrite the original PSD.
- Never invent missing design attributes.
- Keep original layer data separate from inferred components.
- Prefer precise native extraction to model guesses.
```

## 9. CLI 设计

### 9.1 全量分析

```bash
psd-inspector inspect \
  --input ./design/home.psd \
  --output ./output/home \
  --profile full \
  --export-assets \
  --report
```

### 9.2 仅文字

```bash
psd-inspector inspect --input ./design/home.psd --profile typography --output ./output/typography
```

### 9.3 指定图层

```bash
psd-inspector layer get --ir ./output/home/design.json --id layer-1038
```

### 9.4 元素邻居与间距

```bash
psd-inspector geometry neighbors --ir ./output/home/design.json --id layer-1038 --distance 100
```

### 9.5 Token 提取

```bash
psd-inspector tokens extract --ir ./output/home/design.json --types colors,typography,spacing
```

### 9.6 图层标注

```bash
psd-inspector annotate --ir ./output/home/design.json --show bounds,ids,spacing --output ./output/home/annotated.png
```

CLI 应使用明确的退出码，输出结构化 JSON 运行摘要；单个图层错误不得导致所有成果丢失。

## 10. 解析配置

提供三档 Profile：

| Profile | 特点 | 典型场景 |
|---|---|---|
| `fast` | 仅原生属性，低计算量 | 快速结构检查 |
| `full` | 全量属性、几何、Token、资源、标注 | **默认推荐** |
| `deep` | 增加复杂栅格分析与视觉推断 | 大量合并图层、复杂 UI |

```yaml
ai:
  enabled: true
  provider: openai-compatible
  base_url: ${AI_BASE_URL}
  api_key: ${AI_API_KEY}
  model: ${VISION_MODEL}
  only_for_unsupported_layers: true
  require_structured_output: true
  allow_external_upload: false
```

离线解析默认可用。禁止上传设置下，必须跳过外部 API 或使用本地模型，不得隐式上传设计图。

## 11. 输出文件规范

```text
output/home/
├── design.json
├── source-layers.json
├── components.json
├── geometry.json
├── typography.json
├── colors.json
├── effects.json
├── design-tokens.json
├── assets/
│   ├── images/
│   ├── icons/
│   ├── backgrounds/
│   └── layer-previews/
├── previews/
│   ├── original.png
│   ├── annotated.png
│   ├── typography-map.png
│   ├── spacing-map.png
│   └── component-map.png
├── reports/
│   ├── design-spec.md
│   ├── layer-inventory.md
│   ├── unsupported.md
│   ├── validation.json
│   └── extraction-summary.json
└── manifest.json
```

`manifest.json` 应包含：输入哈希、解析器版本、使用的 Profile、模型版本、作业状态、时间、输出文件哈希、错误列表，用于增量更新和复现。

### 11.1 可视化检查器

建议输出可独立打开的 HTML Viewer：
- 查看原始合成图并叠加图层外框。
- Hover 显示图层 ID、尺寸与坐标；点击展示原生属性和提取来源。
- 可切换文字边界、间距线、组件框、画板、隐藏图层。
- 支持图层树、名称、ID 查询和警告过滤。
- 可以导出带标注 PNG，不需重新绘制画面本身。

## 12. 复杂与异常场景

| 场景 | 策略 |
|---|---|
| 单合并图层 | 仅能恢复有限像素与视觉语义，标明不可恢复的原生属性 |
| 字体缺失 | 保留原始名称并标记缺失 |
| 字体栅格化 | OCR/视觉估计字号，字体名不可靠则未知 |
| 智能对象嵌套 | 可控深度递归，循环引用保护 |
| 智能对象外部引用丢失 | 使用可用预览，记录缺失引用 |
| 多画板混用 | 每个画板具有独立坐标空间 |
| 剪贴组、蒙版、多层叠加 | 保留层顺序与全部引用关系 |
| 特殊滤镜或渐变 | 优先保留原始描述，并导出 raster fallback |
| 渲染与 Photoshop 不一致 | 同时保存原生合成预览和渲染差异 |
| 巨型 PSD/PSB | 延迟读取、限制并行、缓存、中间文件回收 |
| 部分图层损坏 | 局部容错、跳过、记录诊断 |
| ID 缺失或冲突 | 内部稳定 ID + 原始 ID 字段 |
| 重复分析 | 输入、配置、解析器版本哈希决定缓存有效性 |

## 13. 测试与验收

建设 Golden Fixture 测试集：
1. 简单矢量图层、文字、图片。
2. 同一文本图层多种字体、颜色、字号。
3. 导航、卡片、弹窗、网格、列表。
4. 阴影、发光、描边、渐变和图案。
5. 不规则路径、旋转、四角不同半径。
6. 内嵌与外链智能对象。
7. 单层扁平 PSD、隐藏图层、多画板、超大 PSD。

| 验收项 | 目标 |
|---|---|
| 图层树 | 覆盖样例原生结构完整输出，失败有诊断 |
| 源坐标 | 对受支持的未变换图层与基准一致 |
| 文字样式 | 原生文字样例准确提取字号、字体和 style runs |
| 纯色 | 标准 RGB 填充无损获取 |
| 变换 | 局部与全局坐标矩阵转换测试通过 |
| 栅格属性 | 报告精度与误差，不伪称原生精确 |
| 资产 | 尺寸、透明通道、图层 offset 与基准一致 |
| 数据契约 | 全部通过 JSON Schema 验证 |
| 局部故障 | 部分图层错误不阻止其他成功输出 |
| 源文件 | 处理前后 SHA256 一致 |

视觉比对使用 Photoshop 正确渲染图作为可用时的基准，输出差异图和误差指标。但视觉相似度不能证明所有样式值准确。

## 14. 迭代开发

### P1：原生解析核心（必须先完成）

完成文档/画板、图层树、原生文字样式、颜色、位置、尺寸、边框、圆角、效果、导出及 Schema。交付 `psd-inspector inspect` CLI、`design.json`、样例和单测。

### P2：几何与设计系统

完成相对位置、间距、对齐、父子关系、重复模式、布局候选、Token 和 HTML 检查器。交付 `geometry.json`、`design-tokens.json`、标注预览。

### P3：视觉与语义补全

接入 OpenCV、可选本地/云端视觉模型、栅格化元素候选拆分、组件识别、可信度和诊断。交付 `components.json` 和推断证据。

### P4：Photoshop 与 Agent 集成

UXP 高级属性补全、批处理、增量缓存、Skill 编排、对接 PSD Normalize Studio 和 Vue Generator。交付集成测试与执行文档。

**优先级**：P1 + P2 实现可用的设计稿数值解析；P3/P4 用于扩充复杂 PSD 的准确性与覆盖。

## 15. 与 PSD → Vue 系统集成

```text
PSD 文件
   ↓
PSD Design Inspector Skill
   ↓
Design IR（原生属性 + 几何关系）
   ├─────────────┐
   ↓             ↓
PSD Normalize   语义/布局分析
Studio          │
   └──────┬──────┘
          ↓
Enhanced Design IR
          ↓
Vue Generation Skill
          ↓
Vue3 / HTML / CSS
          ↓
渲染对比 → 定位误差 → 修复
```

PSD Normalize Studio 修改图层或变换后，必须更新对应 source fingerprint、重新解析受影响部分并重建相关空间关系；不能假定旧坐标和 ID 继续有效。

## 16. Codex 开发执行要求

1. 首先创建完整目录、Pydantic Schema、单测基建、CLI 骨架和可重复测试 Fixture。
2. 先实现 `psd-tools` 适配器，禁止因高级样式不支持而产生假的属性。
3. 原生图层与语义图层的数据模型严格分离。
4. 所有像素坐标字段必须声明坐标空间、单位和变换依据。
5. 属性提取附带来源、失败原因和兼容状态。
6. 对不可支持的 Photoshop 特性生成 `unsupported.md`，并保留 raster fallback。
7. 每次 CLI 运行至少产生 `manifest.json` 和 `reports/extraction-summary.json`。
8. 通过 Golden Fixture 对图层、颜色、文字、几何建立准确性回归。
9. 所有运行必须默认只读，不修改原始 PSD/PSB。
10. P1、P2 完成后再进行 P3/P4，避免早期视觉 AI 过度参与确定性属性解析。

## 17. 最终验收场景

输入一个典型业务 UI 的 `home.psd` 后，应能：

1. 查到所有图层的 ID、名称、类型、层级与可见性。
2. 查到原生文字的内容、字体、字号、字重、行高、字符/段落样式。
3. 查到图形和文本的颜色、边框、圆角、透明度、阴影及可提取效果。
4. 查到各元素的尺寸、绝对坐标、相对父坐标与相邻间距。
5. 自动发现重复的卡片、按钮以及布局候选，但不会与原生图层混淆。
6. 输出可供后续 Vue Agent 使用的 `design.json`、`design-tokens.json`、`assets/`。
7. 提供标注图片及 HTML 检查器，开发者无需反复打开 Photoshop 量尺寸。
8. 对所有不可可靠恢复的数据生成诊断和待人工确认清单。

**总体目标**：建设一个独立、可测试、可追溯、可复用的 PSD → Design IR 内核，后续所有 PSD → Vue/HTML/Figma/图层优化 Skill 均可共享本解析能力。
