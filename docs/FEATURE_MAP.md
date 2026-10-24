# PSD Design Inspector 功能地图

> 更新日期：2026-10-24  
> 状态图例：✅ 可用 ｜ ◐ 部分可用（字段或范围受限）｜ ○ 未实现  
> 当前能力与限制以本文和根目录 [`README.md`](../README.md) 为准；初始规划见 [`archive/`](archive/README.md)。

## 1. 定位与边界

**做什么**：把 PSD/PSB 转换为确定性、可校验、可追溯的 Design IR，覆盖图层结构、原生样式、测量几何、Token 候选与可复用资源。

**不做什么**：
- 不生成 Vue/HTML 页面。
- 不修改原始 PSD/PSB。
- 不用 AI 猜测 PSD 中已经存在的属性。
- 不把布局候选、Token 命名或栅格采样描述成 PSD 原生值。

**信任规则**：无法确定时输出 `null`/缺失字段，并在 `extraction.unsupported_properties` 或 `diagnostics` 中说明；禁止伪造高置信度结果。

## 2. 端到端数据流

```text
PSD / PSB
  ↓ adapters/psd_tools_adapter.py
文档元数据 + 原始图层树 + 文字/外观/蒙版/智能对象元数据
  ↓ pipeline._build_design_ir
Design IR（Layer / Typography / Appearance / Geometry / ExtractionInfo）
  ↓ analysis/geometry_engine.py + layout_detector.py
相对坐标、空间关系、对齐/间距组、布局候选
  ↓ analysis/token_extractor.py
颜色 / 排版 / 间距 / 边框 / 阴影 Token 候选
  ↓ exporters/
预览、标注图、非文字图层 PNG、HTML 检查器、报告
  ↓ validation/ir_validator.py + pipeline.manifest
JSON Schema 校验结果 + 运行清单 + 文件哈希
```

## 3. 完整功能地图

### 3.1 文档与坐标空间

| 能力 | 状态 | 实现位置 | 输出字段 | 来源/说明 |
|---|---|---|---|---|
| PSD/PSB 头校验 | ✅ | `adapters/psd_tools_adapter.py` | — | 仅接受 `8BPS` 签名 |
| 画布尺寸、DPI、色彩模式、位深 | ✅ | 同上 | `document.metadata` | `psd_native` |
| 文件大小、SHA256 | ✅ | 同上 | `metadata.file_size_bytes` / `sha256` | 文件内容计算 |
| ICC 配置名称 | ✅ | 同上 | `metadata.icc_profile` | 仅名称，不做色彩转换 |
| 图层/组/可见/隐藏/智能对象计数 | ✅ | 同上 | `metadata.total_*`、`smart_objects` | `psd_native` |
| 画板（Artboard） | ○ | `get_artboards()` | `document.artboards=[]` | psd-tools 1.x 不暴露画板记录，返回空而不是猜测 |
| 坐标空间 | ◐ | `get_coordinate_spaces()` | `document.coordinateSpaces` | 仅文档级；画板/组级未实现 |

### 3.2 图层树与原生属性

| 能力 | 状态 | 输出字段 | 来源/说明 |
|---|---|---|---|
| 稳定内部 ID | ✅ | `id` = `layer-<native>` 或 `layer-path-*` | 原生 ID 缺失时使用确定性路径 |
| 原始图层 ID | ✅ | `source_layer_id` | `psd_native`，无效时为 `null` |
| 父子关系、深度、同级 z 序 | ✅ | `parent_id` / `depth` / `z_index` | 基于图层树 |
| 图层类型 | ✅ | `kind` | pixel / shape / text / group / smart_object / adjustment / fill / stroke |
| 可见性、锁定、不透明度、填充不透明度、混合模式 | ✅ | `visible` / `locked` / `appearance.*` | `psd_native` |
| 剪贴蒙版标记 | ◐ | `extraction.unsupported_properties += clipping_mask` | 只记录存在性，不解析蒙版成员关系 |
| 调整图层参数 | ○ | 仅 `kind=adjustment` | 不提取曲线、色阶等参数 |
| 图层效果存在性 | ✅ | `effects`（类名列表） | `psd_native` |

### 3.3 文字与排版

| 能力 | 状态 | 输出字段 | 来源/说明 |
|---|---|---|---|
| 文本内容与字符数 | ✅ | `typography.content` / `total_characters` | `psd_native` |
| 字符级 run | ✅ | `typography.character_runs` | 每个 run 含内容、起止索引 |
| 字体家族 / PostScript / 样式 / 粗斜体 / 下划线 / 删除线 | ✅ | `character_runs[].font` | `psd_native`；家族由 PostScript 名拆分 |
| 字号（pt + 换算 px） | ✅ | `source_font_size` / `effective_font_size_px` | 换算依据写入 `conversion_basis` |
| 文字颜色与透明度 | ✅ | `character_runs[].color` / `opacity` | `psd_native` |
| 字距、kerning、letter-spacing | ✅ | `tracking` / `kerning` / `letter_spacing_px` | `psd_native` |
| 段落对齐、行高、段前段后、缩进、方向 | ✅ | `typography.paragraph_runs` | `psd_native` |
| 文本框、自动换行、方向、变换矩阵 | ◐ | `typography.text_box` | 文本框与方向可用；内容宽高通常为空 |
| 主导字体与主导字号 | ✅ | `dominant_font_family` / `dominant_font_size_px` | 由 run 统计 |
| 字体缺失检测 | ○ | `font.missing=false` | 未检查本地字体，恒为 `false`，不得据此判断字体可用 |
| 栅格化文字 / OCR | ○ | — | 未集成 OCR |

### 3.4 外观、填充与效果

| 能力 | 状态 | 输出字段 | 来源/说明 |
|---|---|---|---|
| 矢量填充色 | ✅ | `appearance.fills` | `vscg` 原生记录 |
| 矢量描边色、宽度、位置 | ✅ | `appearance.strokes` | `vstk` 原生记录 |
| 圆角 | ✅ | `appearance.border_radius` | live shape 原生半径 |
| 投影 / 内阴影 | ✅ | `drop_shadow` / `inner_shadow` | 颜色、透明度、角度、距离、扩散、choke、启用状态 |
| 外发光 / 内发光 | ✅ | `outer_glow` / `inner_glow` | 颜色、透明度、大小、噪声、启用状态 |
| 颜色叠加 | ✅ | `color_overlay` | 颜色、透明度、混合模式、启用状态 |
| 渐变叠加 | ✅ | `gradient_overlay` | 类型、角度、缩放、色标 |
| 图案叠加 | ✅ | `pattern_overlay` | 记录图案引用存在性；不导出图案资源 |
| 描边效果（实色） | ✅ | `appearance.strokes`（效果来源） | 渐变/图案描边标记为不支持 |
| BevelEmboss / Satin / 其他效果 | ◐ | `extraction.unsupported_properties` | 保留存在性，不伪造参数 |
| 智能滤镜 / 复杂变换 | ○ | `diagnostics.unsupportedFeatures` | psd-tools 限制 |

### 3.5 蒙版与智能对象

| 能力 | 状态 | 输出字段 | 来源/说明 |
|---|---|---|---|
| 像素蒙版元数据 | ✅ | `mask` | 文档坐标边界、禁用、反相、背景灰度、组合标记 |
| 矢量蒙版元数据 | ✅ | `vector_mask` | **归一化 0–1 边界**、禁用、反相、填充规则、路径数 |
| 蒙版像素导出 | ○ | `extraction.unsupported_properties += layer_mask` | 已能读取 `mask.topil()`，但尚未纳入资源导出 |
| 矢量蒙版路径几何 | ○ | `extraction.unsupported_properties += vector_mask` | 不转换为贝塞尔/IR 路径 |
| 智能对象基本元数据 | ✅ | `smart_object_data` | 类型、文件名、扩展名、大小、UUID、分辨率、变换框、是否 PSD、内容 SHA256 |
| 智能对象外部链接 | ✅ | `smart_object_link` | 外部/别名对象读取 fullPath/relPath；失败时回退文件名 |
| 智能对象内部文档解析 | ○ | `contents_extracted=false` | 不解码内部 PSD/PSB，也不生成子图层 |
| 内容导出 | ○ | `extraction.unsupported_properties += smart_object_contents` | 不写出嵌入或外部对象文件 |

### 3.6 几何测量与布局候选

| 能力 | 状态 | 输出字段 | 来源/说明 |
|---|---|---|---|
| 文档全局坐标边界 | ✅ | `geometry.source_bounds` | `psd_native` |
| 相对父级坐标 | ✅ | `geometry.relative_to_parent` | 父级边界差值 |
| 归一化坐标 | ✅ | `geometry.normalized` | 除以画布尺寸 |
| 像素级可见边界 / 效果边界 | ○ | `visible_bounds` 镜像 `source_bounds`；`effect_bounds=null` | 未做栅格分析 |
| 旋转 / 缩放 / 变换矩阵 | ○ | 固定 `rotation_deg=0`、单位矩阵、`has_transform=false` | psd-tools 当前路径未解析复杂变换 |
| 同级可见叶子图层邻近关系 | ✅ | `analysis.spatialRelationships` | 仅同父级、可见、叶子图层；正交投影重叠 ≥ 0.3 |
| 对齐组 | ✅ | `analysis.measurements` | 按边缘/中心线聚类 |
| 间距组与组内 padding | ✅ | `analysis.measurements` | 实测几何值 |
| Flex / Grid / Absolute 候选 | ✅ | `analysis.layoutHypotheses` | 带 `evidence`、`confidence`、`basis: measured_geometry`；置信度按同级覆盖率校准 |
| 组件/卡片模式 | ○ | `designSystem.componentPatterns=[]` | 未实现 |

### 3.7 设计 Token 候选

| 类型 | 状态 | 输出字段 | 来源/说明 |
|---|---|---|---|
| 颜色 | ✅ | `designSystem.colorTokens` | 原生填充/文字/渐变 + 可选栅格采样；采样标记 `pixel_measured` |
| 排版 | ✅ | `typographyTokens` | 按字体/字号/字重聚合，逐值记录来源图层 |
| 间距 | ✅ | `spacingTokens` | 来自测量值聚类 |
| 边框 | ✅ | `borderTokens` | 描边与效果来源 |
| 阴影 | ✅ | `shadowTokens` | 保留颜色 alpha 与效果透明度的合成结果 |
| 命名与推荐 | ◐ | `name` / `is_recommended` | **候选命名**，必须人工复核 |
| 组件模式 | ○ | `componentPatterns` | 未实现 |

### 3.8 产物与可视化

| 能力 | 状态 | 输出 | 说明 |
|---|---|---|---|
| 合成预览 | ✅ | `previews/original.png` | psd-tools `composite(force=True)`；无 ICC 以保证可复现 |
| 标注图 | ✅ | `previews/annotated.png` | 边界、ID、实测间距；隐藏图层默认不绘制 |
| 独立 HTML 检查器 | ✅ | `viewer.html` | 图片与 IR 子集内嵌，无外部请求；显示蒙版/智能对象详情；标签贪心避让碰撞；点击树行或画布边界框显示高对比选中框与名称标签并自动滚动定位；`viewer --names` 在树/标签/属性面板显示语义名、AI 标记与 PSD 原名，不改 IR |
| 非文字图层 PNG | ✅ | `assets/layer-previews/` | 栅格渲染，不是原生矢量导出；按 SHA256 去重；文字层不导出 |
| 资源索引 | ✅ | `assets/asset-index.json` | 图层 ID、坐标、尺寸、mask 标记、哈希、`duplicatedFrom`、`excludedTextLayers` |
| 蒙版 PNG | ○ | — | 见 3.5 |
| SVG / WebP / 原生矢量 | ○ | — | 未实现 |
| 报告 | ✅ | `reports/*` | 摘要每次生成；详细报告需 `--report` |
| AI 辅助命名 | ✅ | `names pack` → `naming-pack.json` + `naming-visuals/`；`names apply` → `names.json` | 宿主 Agent 基于预览/分组裁剪图与语义线索生成建议；CLI 校验合并；独立文件，不修改原生 `name` |
| 运行清单 | ✅ | `manifest.json` | 输入哈希、解析器版本、profile、警告、文件哈希、校验状态 |

### 3.9 CLI

| 命令 | 状态 | 能力 |
|---|---|---|
| `psd-inspector inspect` | ✅ | 解析、分析、预览、资源、报告；支持 `--profile fast\|full\|deep` |
| `psd-inspector layer get --ir ... --id ...` | ✅ | 支持 `layer-<n>`、裸原生 ID `<n>`、内部 ID；未知 ID 退出码 1 |
| `psd-inspector geometry neighbors --ir ... --id ... --distance ...` | ✅ | 复用同一 ID 解析；范围限定为同父级可见叶子图层 |
| `psd-inspector tokens extract --ir ... --types ...` | ✅ | 从已有 IR 重算指定 Token 类型 |
| `psd-inspector annotate --ir ... --show bounds,ids,spacing` | ✅ | 复用已有预览或指定 PSD 重新渲染 |
| `psd-inspector names pack --ir ...` | ✅ | 命名上下文包：层级、文字、字体、资源、重名、区域候选、语义提示、UI 词表；默认生成分组视觉裁剪图 |
| `psd-inspector names apply --ir ... --names ...` | ✅ | 校验 IR 哈希/ID/置信度；输出独立 `names.json`，重复名称与 slug 自动消歧 |
| `psd-inspector viewer --ir ... [--names ...]` | ✅ | 从 IR + 可选 `names.json` 重建独立检查器；校验哈希与图层 ID；语义名进入树、画布标签、搜索和属性面板；选中图层显示高对比框、名称标签并自动定位 |

### 3.10 确定性、校验与错误处理

| 能力 | 状态 | 说明 |
|---|---|---|
| JSON Schema 运行时校验 | ✅ | 失败写入 `diagnostics.validationResults`、`reports/validation.json`、`manifest.validation`，不中断解析 |
| 可复现输出 | ✅ | 预览、资源、design.json、geometry、tokens、names、viewer 哈希一致；manifest 与 extraction-summary 含运行时间/输出路径，天然不同；`naming-pack.json` 因 `visualEvidence.visualsDir` 为绝对路径，跨输出目录哈希不同 |
| 过期输出清理 | ✅ | 复用输出目录时移除上次运行的受管文件与目录 |
| 部分图层损坏 | ✅ | 单图层提取失败记录警告，继续处理其他图层 |
| 离线运行 | ✅ | 无网络依赖；AI 命名只产出上下文包，由宿主 Agent 提供建议 |
| 大文件流式读取 | ○ | 当前整体读入内存 |
| 缓存 | ○ | 尚未实现基于输入/配置/版本哈希的缓存 |

## 4. Profile 矩阵

| Profile | 实际行为 | 产物 |
|---|---|---|
| `fast` | 仅原生解析与 IR 组装 | `design.json`、`source-layers.json`、`extraction-summary.json`、`manifest.json` |
| `full` | fast + 几何/Token/预览/检查器 | 上述文件 + `geometry.json`、`design-tokens.json`、`previews/`、`viewer.html`、报告 |
| `deep` | **当前等同 `full`**，额外输出一条诊断警告 | 同 full |

## 5. 数据来源与置信度

| 标记 | 含义 | 示例 |
|---|---|---|
| `psd_native` | 直接来自 PSD 记录 | 图层边界、文字 run、矢量填充、蒙版元数据、智能对象元数据 |
| `measured_geometry` | 对原生几何的确定性测量/推断 | 间距、对齐、邻近关系、布局候选 |
| `pixel_measured` | 对栅格像素的统计采样 | 图层主色 |
| `candidate` | 聚类/命名建议，需人工复核 | Token 名称与推荐项 |

- 所有候选布局必须携带 `evidence` 与 `confidence`，不得当作 PSD 原生布局。
- `confidence=1.0` 仅用于可直接读取且语义明确的原生字段。
- `names.json` 的 `ai_inferred` / `rule_based` 是命名来源，不属于 Design IR 属性来源；AI 名称不得写回 `design.json`。
- 未能提取的内容写入 `unsupported_properties`，不计入“已完成”。

## 6. 未完成待办

### P1 — 数据完整性

| 待办 | 当前状态 | 验收标准 | 涉及模块 |
|---|---|---|---|
| 智能对象内部文档解析 | 仅元数据 | 可递归读取内部 PSD/PSB 图层并受深度/循环引用保护 | `adapters/`, `pipeline.py` |
| 蒙版像素导出 | 仅元数据 | `--export-assets` 输出蒙版 PNG 并写入资源索引 | `exporters/asset_exporter.py` |
| 矢量蒙版路径几何 | 仅归一化边界 | 输出可用的贝塞尔/多边形路径与文档坐标 | `adapters/`, `models/layer.py` |
| 剪贴蒙版成员关系 | 仅标志位 | 输出 base layer 与被剪贴图层列表 | `pipeline.py`, `geometry_engine.py` |
| 像素级 `visibleBounds` / `effectBounds` | 镜像/空值 | 基于 alpha 与效果扩散计算边界 | `analysis/`, `pipeline.py` |
| 本地字体缺失检测 | 恒为 false | 按字体家族/PostScript 名检查系统字体并标记缺失 | `extractors/typography.py` |

### P2 — 分析与可视化

| 待办 | 当前状态 | 验收标准 | 涉及模块 |
|---|---|---|---|
| 重复组件/卡片模式 | 空数组 | 输出可解释的重复结构及证据 | `analysis/`, `models/component.py` |
| 语义组件树 | 未实现 | 生成 `components.json` 且与原始图层树分离 | 新增 analysis 模块 |
| `deep` 真实像素测量 | 等同 full | 增加颜色分布、边界、阴影扩散等测量并有测试 | `analysis/`, `pipeline.py` |
| 调整图层参数 | 仅类型 | 提取至少曲线/色阶/色相饱和度等常用参数 | `adapters/` |

### P3 — 性能与互操作

| 待办 | 当前状态 | 验收标准 | 涉及模块 |
|---|---|---|---|
| 大文件流式读取 | 整体读入 | 限制峰值内存并回收中间文件 | `adapters/` |
| 缓存 | 未实现 | 输入/配置/解析器版本哈希命中缓存 | `pipeline.py` |
| 命名包跨目录可复现 | 绝对路径入包 | 不同输出目录生成相同 `naming-pack.json` 字节（相对 `visualsDir` 或规范化哈希输入） | `naming.py` |
| SVG/WebP/原生矢量资源 | 仅 PNG | 输出可复现的矢量或 WebP 资源 | `exporters/asset_exporter.py` |
| 下游系统对接 | 未实现 | 与 PSD Normalize Studio / Vue Generation Skill 的稳定接口 | 集成层 |
| UXP 高级补全 / 批量处理 | 未实现 | 可选补全路径与批量任务 | 新增适配器 |

## 7. 验证基线

- 测试：`pytest -q`，当前 93 项单元/集成测试。
- 真实文件基线：68.7 MB（68,663,039 字节）、3840×3621、470 图层（117 组 / 112 文字 / 184 形状 / 32 智能对象 / 25 像素；446 可见 / 24 隐藏）。
- 真实文件验证结果：32/32 智能对象元数据、14 个像素蒙版元数据、184 个矢量蒙版元数据；重复运行核心产物哈希一致；检查器 470 个标签中可见标签无重叠。
- AI 命名验证：255 个重名图层、24 个隐藏图层、235 张视觉裁剪图（307 层带视觉证据）；67 个 AI 语义名 / 403 个规则名，470 个名称与 slug 全部唯一，`names apply` 无警告。
- 检查器交互：树行与画布边界框均可选中，显示高对比框、名称标签并自动滚动定位；零尺寸图层以 12px 标记定位。
- PSD 测试夹具在测试运行时由 psd-tools 生成，仓库不保存二进制文件。
