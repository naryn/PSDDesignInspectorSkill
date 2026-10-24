# 项目总结

> 基线日期：2026-10-24 ｜ Schema：`1.0.0` ｜ 状态：可用，P1 数据补全进行中  
> 完整能力矩阵与验收标准见 [功能地图](FEATURE_MAP.md)。

## 1. 项目定位

PSD Design Inspector 是一个**确定性、离线优先**的 PSD/PSB 解析 Skill。它把设计稿转换为可校验、可追溯的 Design IR，为前端还原、设计系统与自动化流程提供结构化输入。

**不做**：不生成页面、不修改原始 PSD、不使用 AI 猜测已有属性、不把测量值或候选值描述成原生值。

## 2. 架构与模块

| 模块 | 职责 |
|---|---|
| `adapters/psd_tools_adapter.py` | 读取 PSD/PSB，输出文档元数据与原始图层树 |
| `extractors/` | 文字 run、填充/描边、圆角与图层效果 |
| `analysis/geometry_engine.py` | 相对坐标、邻近关系、对齐/间距组、组内 padding |
| `analysis/layout_detector.py` | Flex / Grid / Absolute 候选与置信度 |
| `analysis/token_extractor.py` | 颜色/排版/间距/边框/阴影 Token 候选 |
| `exporters/` | 预览、标注图、逐层 PNG、HTML 检查器、报告 |
| `validation/ir_validator.py` | Design IR JSON Schema 校验 |
| `pipeline.py` | 编排解析、分析、导出、校验与 manifest |

## 3. 已交付能力

- **文档**：PSD/PSB 校验、尺寸、DPI、色彩模式、位深、ICC 名称、SHA256、图层统计。
- **图层**：完整图层树、稳定 ID、父级/深度/z 序、可见性、锁定、不透明度、填充不透明度、混合模式。
- **文字**：字符 run、字体家族/PostScript/样式、字号 pt + px 换算、颜色、字距、段落对齐、行高、缩进、方向。
- **外观**：矢量填充/描边/圆角；投影、内阴影、内外发光、颜色/渐变/图案叠加、描边效果。
- **智能对象**：类型、文件名、大小、UUID、分辨率、变换框、是否 PSD、嵌入内容 SHA256、外部链接。
- **蒙版**：像素蒙版边界/禁用/反相/背景色；矢量蒙版归一化边界/填充规则/路径数。
- **几何**：相对坐标、归一化坐标、同父级邻近关系、对齐组、间距组、Flex/Grid/Absolute 候选。
- **Token**：颜色、排版、间距、边框、阴影候选，逐值记录来源图层；命名需人工复核。
- **产物**：Design IR、几何/Token JSON、预览与标注图、逐层 PNG（哈希去重）、独立 HTML 检查器、报告、manifest。
- **CLI**：`inspect`、`layer get`、`geometry neighbors`、`tokens extract`、`annotate`。

## 4. 当前产物

```text
output/
├── design.json
├── source-layers.json
├── geometry.json
├── design-tokens.json
├── previews/{original,annotated}.png
├── viewer.html
├── assets/{layer-previews/,asset-index.json}
├── reports/{extraction-summary.json,...}
└── manifest.json
```

`fast` 仅输出 IR、源图层、摘要与 manifest；`full` 增加几何、Token、预览与检查器；`deep` 当前等同 `full`。

## 5. 质量基线

- 测试：**65 项**单元/集成测试，覆盖率 **83%**。
- 真实文件：68.7 MB（68,663,039 字节）/ 3840×3621 / 470 图层（117 组、112 文字、184 形状、32 智能对象、25 像素；446 可见 / 24 隐藏）。
- 真实文件验证：32/32 智能对象元数据、14 个像素蒙版、184 个矢量蒙版；核心产物重复运行哈希一致。
- 检查器：470 个标签中可见标签 0 重叠，支持蒙版与智能对象详情。
- 校验失败不中断解析，错误写入 `diagnostics`、`reports/validation.json` 与 `manifest.validation`。

## 6. 数据可信度

| 来源 | 含义 |
|---|---|
| `psd_native` | 直接读取的 PSD 记录 |
| `measured_geometry` | 对原生几何的确定性测量或推断 |
| `pixel_measured` | 栅格像素统计采样 |
| `candidate` | 聚类/命名建议，必须人工复核 |

`confidence=1.0` 仅用于语义明确的原生字段；布局候选必须携带证据与置信度，不得当作 PSD 原生布局。

## 7. 未完成待办

### P1 — 数据完整性

- 解析智能对象内部文档与嵌套图层
- 导出蒙版像素与矢量蒙版路径
- 建立剪贴蒙版成员关系
- 像素级 `visibleBounds` / `effectBounds`
- 本地字体可用性检测

### P2 — 分析与可视化

- 重复组件/卡片模式与 `componentPatterns`
- 语义组件树 `components.json`
- `deep` profile 的真实像素测量
- 调整图层参数提取

### P3 — 性能与互操作

- 大文件流式读取、并行限制与中间文件回收
- 基于输入/配置/解析器版本哈希的缓存
- SVG/WebP/原生矢量资源导出
- 下游系统对接、UXP 高级补全与批量处理

## 8. 入口

```bash
pip install -e .
psd-inspector inspect --input ./design.psd --output ./out --profile full --report
pytest -q
```

- [完整功能地图](FEATURE_MAP.md)
- [文档索引](README.md)
- [归档的 V1.0 设计](archive/README.md)
