"""Main parsing pipeline for PSD Design Inspector."""

from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
import json
import hashlib
import sys

from .adapters.psd_tools_adapter import PsdToolsAdapter
from .analysis.geometry_engine import GeometryAnalyzer
from .analysis.token_extractor import TokenExtractor
from .exporters.asset_exporter import export_layer_assets
from .exporters.preview_exporter import draw_annotations, render_composite
from .exporters.report_exporter import write_reports
from .exporters.viewer_exporter import build_viewer_html
from .models.document import DocumentMetadata, Artboard, CoordinateSpace
from .models.layer import (
    Appearance,
    ColorOverlay,
    ExtractionInfo,
    Fill,
    Geometry,
    Glow,
    GradientOverlay,
    Layer,
    PatternOverlay,
    Shadow,
    Stroke,
)
from .models.typography import Typography
from .validation import validate_design_ir
from .validation.ir_validator import validation_results


class ExtractorProfile:
    """Extraction profile configurations."""
    
    FAST = "fast"
    FULL = "full"
    DEEP = "deep"


class DesignIRPipeline:
    """Main pipeline for PSD to Design IR conversion."""
    
    SCHEMA_VERSION = "1.0.0"
    
    def __init__(self, profile: str = ExtractorProfile.FULL):
        """Initialize pipeline with extraction profile.
        
        Args:
            profile: Extraction profile (fast/full/deep)
        """
        self.profile = profile
        self.adapter = PsdToolsAdapter({'sample_colors': profile in (ExtractorProfile.FULL, ExtractorProfile.DEEP)})
        self._design_ir: Dict[str, Any] = {}
        self._manifest: Dict[str, Any] = {}
        self._geometry: Dict[str, Any] = {}
        self._tokens: Dict[str, Any] = {}
        self._preview_image = None
        self._generated_files: List[str] = []
        self._assets: Optional[Dict[str, Any]] = None
        self._assets_error: Optional[str] = None
        self._validation: Optional[Dict[str, Any]] = None
        self._export_assets = False
        self._detailed_report = False
    
    def process_file(
        self,
        input_path: str,
        output_dir: str,
        export_assets: bool = False,
        report: bool = False,
    ) -> Dict[str, Any]:
        """Process a single PSD file and generate Design IR.
        
        Args:
            input_path: Path to PSD file
            output_dir: Output directory for results
            export_assets: Render per-layer PNG assets
            report: Write detailed markdown reports and validation.json
            
        Returns:
            Summary of processing results
        """
        input_path_obj = Path(input_path)
        output_dir_obj = Path(output_dir)
        self._export_assets = export_assets
        self._detailed_report = report
        
        # Ensure output directory exists
        output_dir_obj.mkdir(parents=True, exist_ok=True)
        
        try:
            # Step 1: Parse document metadata
            metadata = self.adapter.parse(input_path_obj)
            
            # Step 2: Extract layers
            raw_layers = self.adapter.get_layers(input_path_obj)
            
            # Step 3: Extract artboards
            artboards = self.adapter.get_artboards(input_path_obj)
            
            # Step 4: Extract coordinate spaces
            coordinate_spaces = self.adapter.get_coordinate_spaces(input_path_obj)
            
            # Step 5: Build Design IR
            self._design_ir = self._build_design_ir(
                metadata, 
                raw_layers, 
                artboards, 
                coordinate_spaces
            )
            
            # Step 6: Run P2 analysis (geometry + design tokens + previews)
            if self.profile in (ExtractorProfile.FULL, ExtractorProfile.DEEP):
                self._run_analysis(metadata, raw_layers)
                self._render_preview(input_path_obj)
            
            # Step 7: Export per-layer assets (opt-in)
            if export_assets:
                self._export_layer_assets(input_path_obj, raw_layers, output_dir_obj)

            # Step 8: Validate the Design IR against the bundled schema
            self._validate_ir()

            # Step 9: Create manifest
            self._create_manifest(input_path_obj, metadata)
            
            # Step 10: Export results
            self._generated_files = self._export_results(output_dir_obj)
            
            return {
                'status': 'success',
                'output_dir': str(output_dir_obj),
                'layers_processed': metadata.total_layers,
                'artboards_found': len(artboards),
                'layout_hypotheses': len(self._design_ir['analysis']['layoutHypotheses']),
                'tokens': self._design_ir['designSystem'].get('totalCount', 0),
                'assets_exported': (self._assets or {}).get('summary', {}).get('exportedLayers', 0),
                'validation_status': (self._validation or {}).get('status'),
                'files_generated': self._generated_files
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'details': getattr(e, 'details', {})
            }
    
    def _build_design_ir(
        self,
        metadata: DocumentMetadata,
        raw_layers: List[Dict[str, Any]],
        artboards: List[Artboard],
        coordinate_spaces: List[CoordinateSpace]
    ) -> Dict[str, Any]:
        """Build complete Design IR structure.
        
        Args:
            metadata: Document metadata
            raw_layers: Raw layer data from adapter
            artboards: Artboard definitions
            coordinate_spaces: Coordinate space definitions
            
        Returns:
            Complete Design IR dictionary
        """
        # Convert DocumentMetadata to dict
        doc_dict = {
            'metadata': metadata.model_dump(mode='json'),
            'artboards': [a.model_dump(mode='json') for a in artboards],
            'coordinateSpaces': [c.model_dump(mode='json') for c in coordinate_spaces]
        }
        
        # Convert raw layers to Layer objects
        bounds_by_id = {
            raw['id']: raw.get('bounds', {'x': 0, 'y': 0, 'width': 0, 'height': 0})
            for raw in raw_layers
        }
        processed_layers = []
        for raw in raw_layers:
            layer = self._convert_raw_to_layer(
                raw, metadata.width_px, metadata.height_px, bounds_by_id
            )
            processed_layers.append(layer.model_dump(mode='json'))
        
        hierarchy = [
            {
                'id': layer['id'],
                'parentId': layer['parent_id'],
                'depth': layer['depth'],
                'childIds': [l['id'] for l in processed_layers if l['parent_id'] == layer['id']],
            }
            for layer in processed_layers
        ]
        
        design_ir = {
            'schemaVersion': self.SCHEMA_VERSION,
            'document': doc_dict,
            'source': {
                'rawLayers': processed_layers,
                'layerHierarchy': hierarchy,
                'originalStyles': [],  # Placeholder for future
                'nativeReferences': []  # Placeholder for future
            },
            'analysis': {
                'measurements': [],  # Will be computed in geometry analysis
                'spatialRelationships': [],
                'layoutHypotheses': [],
                'semanticComponents': []
            },
            'designSystem': {
                'colorTokens': [],  # Computed separately
                'typographyTokens': [],
                'spacingTokens': [],
                'componentPatterns': []
            },
            'diagnostics': {
                'unsupportedFeatures': self.adapter.get_unsupported_features(),
                'warnings': [],
                'validationResults': []
            }
        }
        
        return design_ir

    def _run_analysis(
        self, metadata: DocumentMetadata, raw_layers: List[Dict[str, Any]]
    ) -> None:
        """Compute measured geometry and design token candidates."""
        layers = self._design_ir['source']['rawLayers']
        sampled_colors = self._sampled_color_measurements(raw_layers)

        geometry = GeometryAnalyzer().analyze(
            layers, metadata.width_px, metadata.height_px
        )
        geometry['measurements'] = sampled_colors + geometry['measurements']
        geometry['coordinateSpaceId'] = 'document'
        geometry['basis'] = 'source_bounds'

        self._geometry = geometry
        self._design_ir['analysis'] = {
            'measurements': geometry['measurements'],
            'spatialRelationships': geometry['spatialRelationships'],
            'layoutHypotheses': geometry['layoutHypotheses'],
            'semanticComponents': [],
        }

        self._tokens = TokenExtractor().extract(self._design_ir)
        self._design_ir['designSystem'] = {
            'colorTokens': self._tokens['colorTokens'],
            'typographyTokens': self._tokens['typographyTokens'],
            'spacingTokens': self._tokens['spacingTokens'],
            'componentPatterns': self._tokens['componentPatterns'],
            'borderTokens': self._tokens['borderTokens'],
            'shadowTokens': self._tokens['shadowTokens'],
            'recommendedCount': self._tokens['recommendedCount'],
            'totalCount': self._tokens['totalCount'],
        }

        diagnostics = self._design_ir['diagnostics']
        diagnostics['warnings'].append(
            'visibleBounds equals sourceBounds: pixel-level visible bounds analysis is not implemented (P3).'
        )
        if sampled_colors:
            diagnostics['warnings'].append(
                f"{len(sampled_colors)} color sample(s) were measured from raster pixels; "
                "they are statistical, not native PSD values."
            )
        if any(layer.get('typography') for layer in layers):
            diagnostics['warnings'].append(
                "Font availability is not checked against the local system; "
                "typography font.missing stays false unless the PSD itself marks a substitution."
            )

    def _render_preview(self, input_path: Path) -> None:
        """Render the composite preview used by annotations and the HTML viewer."""
        try:
            self._preview_image = render_composite(input_path)
        except Exception as e:
            self._preview_image = None
            self._design_ir['diagnostics']['warnings'].append(
                f"Composite preview rendering failed: {e}"
            )

    @staticmethod
    def _sampled_color_measurements(layers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        measurements: List[Dict[str, Any]] = []
        for layer in layers:
            for index, sample in enumerate(layer.get('sampled_colors') or []):
                measurements.append({
                    'id': f"measurement-color-{layer['id']}-{index}",
                    'type': 'sampled_color',
                    'layerId': layer['id'],
                    'color': sample.get('color'),
                    'coverage': sample.get('coverage', 0.0),
                    'sampleCount': sample.get('sampleCount', 0),
                    'source': 'pixel_measured',
                    'confidence': sample.get('coverage', 0.0),
                })
        return measurements
    
    def _convert_raw_to_layer(
        self,
        raw: Dict[str, Any],
        document_width: int,
        document_height: int,
        bounds_by_id: Optional[Dict[str, Dict[str, int]]] = None,
    ) -> Layer:
        """Convert raw layer dict to Layer object.
        
        Args:
            raw: Raw layer dictionary from adapter
            document_width: Canvas width for normalization
            document_height: Canvas height for normalization
            bounds_by_id: All layer bounds, used to derive parent-relative offsets
            
        Returns:
            Layer object
        """
        bounds_by_id = bounds_by_id or {}
        bounds = raw.get('bounds', {'x': 0, 'y': 0, 'width': 0, 'height': 0})
        
        # PSD bounds are document-global; parent-relative is a plain difference
        # because psd-tools does not expose a parent transform here.
        parent_bounds = bounds_by_id.get(raw.get('parent_id'))
        if parent_bounds is not None:
            relative_to_parent = {
                'x': bounds['x'] - parent_bounds['x'],
                'y': bounds['y'] - parent_bounds['y'],
            }
        else:
            relative_to_parent = {'x': bounds['x'], 'y': bounds['y']}
        
        geometry = Geometry(
            source_bounds=bounds,
            visible_bounds=bounds.copy(),  # visible pixel bounds require raster analysis
            effect_bounds=None,
            relative_to_parent=relative_to_parent,
            normalized={
                'x': bounds['x'] / document_width if document_width else 0.0,
                'y': bounds['y'] / document_height if document_height else 0.0,
                'width': bounds['width'] / document_width if document_width else 0.0,
                'height': bounds['height'] / document_height if document_height else 0.0,
            },
            rotation_deg=0.0,
            scale_x=1.0,
            scale_y=1.0,
            transform_matrix=[1.0, 0.0, 0.0, 1.0, 0.0, 0.0],
            has_transform=False,
            non_invertible_transform=False
        )
        
        # Build appearance from native shape data and layer effects
        raw_appearance = raw.get('appearance') or {}
        appearance = Appearance(
            opacity=raw.get('opacity', 1.0),
            fill_opacity=raw.get('fill_opacity', 1.0),
            blend_mode=self._map_blend_mode(raw.get('blend_mode', 'normal')),
            fills=[Fill(**item) for item in raw_appearance.get('fills', [])],
            strokes=[Stroke(**item) for item in raw_appearance.get('strokes', [])],
            border_radius=raw_appearance.get('border_radius') or {},
            drop_shadow=self._shadow(raw_appearance.get('drop_shadow')),
            inner_shadow=self._shadow(raw_appearance.get('inner_shadow')),
            outer_glow=self._glow(raw_appearance.get('outer_glow')),
            inner_glow=self._glow(raw_appearance.get('inner_glow')),
            color_overlay=self._overlay(ColorOverlay, raw_appearance.get('color_overlay')),
            gradient_overlay=self._overlay(
                GradientOverlay, raw_appearance.get('gradient_overlay')
            ),
            pattern_overlay=self._overlay(
                PatternOverlay, raw_appearance.get('pattern_overlay')
            ),
        )

        typography_raw = raw.get('typography')
        typography = Typography(**typography_raw) if typography_raw else None

        property_sources = {
            'geometry.source_bounds': {'source': 'psd_native', 'confidence': 1.0},
            'appearance.opacity': {'source': 'psd_native', 'confidence': 1.0},
            'appearance.blend_mode': {'source': 'psd_native', 'confidence': 1.0},
        }
        if raw.get('has_mask'):
            property_sources['masks'] = {'source': 'psd_native', 'confidence': 1.0}
        if raw_appearance.get('fills'):
            property_sources['appearance.fills'] = {
                'source': 'psd_native',
                'confidence': 0.9,
            }
        if raw_appearance.get('strokes'):
            property_sources['appearance.strokes'] = {
                'source': 'psd_native',
                'confidence': 0.9,
            }
        if raw_appearance.get('border_radius'):
            property_sources['appearance.border_radius'] = {
                'source': 'psd_native',
                'confidence': 1.0,
            }
        for effect_key in (
            'drop_shadow',
            'inner_shadow',
            'outer_glow',
            'inner_glow',
            'color_overlay',
            'gradient_overlay',
            'pattern_overlay',
        ):
            if getattr(appearance, effect_key) is not None:
                property_sources[f'appearance.{effect_key}'] = {
                    'source': 'psd_native',
                    'confidence': 1.0,
                }
        if typography is not None:
            property_sources['typography.character_runs'] = {
                'source': 'psd_native',
                'confidence': 1.0,
            }

        unsupported = [
            feature
            for feature, present in (
                ('vector_mask', bool(raw.get('has_vector_mask'))),
                ('clipping_mask', bool(raw.get('clipping'))),
                ('smart_object_contents', raw.get('kind') == 'smart_object'),
            )
            if present
        ]
        unsupported.extend(
            f"effect:{name}"
            for name in raw.get('appearance_unsupported_effects') or []
        )

        extraction_warnings = list(raw.get('typography_warnings') or [])
        extraction_warnings.extend(raw.get('appearance_warnings') or [])

        # Build extraction info
        extraction_info = ExtractionInfo(
            status='partial' if unsupported else 'complete',
            source='psd_native',
            confidence=1.0,
            errors=[],
            warnings=extraction_warnings,
            unsupported_properties=unsupported,
            property_sources=property_sources
        )
        
        # Create layer
        layer = Layer(
            id=raw.get('id', f"layer-{hash(str(raw)) % 10000}"),
            source_layer_id=raw.get('source_layer_id'),
            name=raw.get('name', 'Unnamed'),
            kind=self._map_layer_kind(raw.get('kind', 'pixel')),
            parent_id=raw.get('parent_id'),
            z_index=raw.get('z_index', 0),
            depth=raw.get('depth', 0),
            visible=raw.get('visible', True),
            locked=raw.get('locked', False),
            coordinate_space_id='document',
            geometry=geometry,
            appearance=appearance,
            typography=typography,
            masks=[],
            vector_masks=[],
            clipping_groups=[],
            smart_object_link=None,
            smart_object_data=None,
            export_paths=[],
            extraction=extraction_info
        )
        
        return layer
    
    @staticmethod
    def _shadow(payload: Optional[Dict[str, Any]]) -> Optional[Shadow]:
        return Shadow(**payload) if payload else None

    @staticmethod
    def _glow(payload: Optional[Dict[str, Any]]) -> Optional[Glow]:
        return Glow(**payload) if payload else None

    @staticmethod
    def _overlay(model: Any, payload: Optional[Dict[str, Any]]) -> Any:
        return model(**payload) if payload else None

    def _map_blend_mode(self, mode: str) -> str:
        """Map blend mode string."""
        mapping = {
            'pass through': 'pass through',
            'normal': 'normal',
            'multiply': 'multiply',
            'screen': 'screen',
            'overlay': 'overlay',
            'darken': 'darken',
            'lighten': 'lighten',
            'color dodge': 'color dodge',
            'color burn': 'color burn',
            'soft light': 'soft light',
            'hard light': 'hard light',
            'difference': 'difference',
            'exclusion': 'exclusion',
            'hue': 'hue',
            'saturation': 'saturation',
            'color': 'color',
            'luminosity': 'luminosity',
        }
        return mapping.get(mode.lower(), 'normal')
    
    def _map_layer_kind(self, kind: str) -> str:
        """Map layer kind string."""
        mapping = {
            'pixel': 'pixel',
            'shape': 'shape',
            'text': 'text',
            'group': 'group',
            'smart_object': 'smart_object',
            'adjustment': 'adjustment',
            'fill': 'fill',
            'stroke': 'stroke',
        }
        return mapping.get(kind.lower(), 'pixel')
    
    def _export_layer_assets(
        self,
        input_path: Path,
        raw_layers: List[Dict[str, Any]],
        output_dir: Path,
    ) -> None:
        """Render per-layer PNGs and link them from each layer record."""
        try:
            assets = export_layer_assets(input_path, raw_layers, output_dir / 'assets')
            self._assets = assets
            exported = {asset['layerId']: asset['file'] for asset in assets['assets']}
            for layer in self._design_ir['source']['rawLayers']:
                path = exported.get(layer['id'])
                if path:
                    layer['export_paths'] = [f"assets/{path}"]
        except Exception as error:
            self._assets_error = str(error)
            self._design_ir['diagnostics']['warnings'].append(
                f"Asset export failed: {error}"
            )

    def _validate_ir(self) -> None:
        """Validate the IR and record the outcome in diagnostics."""
        report = validate_design_ir(self._design_ir)
        self._validation = report
        self._design_ir['diagnostics']['validationResults'] = validation_results(report)
        if report['status'] == 'invalid':
            self._design_ir['diagnostics']['warnings'].append(
                f"Design IR schema validation failed with {len(report['errors'])} error(s); "
                "see reports/validation.json."
            )
        elif report['status'] == 'unavailable' and report.get('warning'):
            self._design_ir['diagnostics']['warnings'].append(report['warning'])

    def _asset_manifest(self) -> Dict[str, Any]:
        if self._assets is None:
            return {'enabled': self._export_assets, 'error': self._assets_error}
        return {
            'enabled': True,
            'index': 'assets/asset-index.json',
            **self._assets['summary'],
        }

    def _create_manifest(self, input_path: Path, metadata: DocumentMetadata):
        """Create manifest.json with run information."""
        self._manifest = {
            'inputFile': {
                'path': str(input_path),
                'filename': input_path.name,
                'sha256': metadata.sha256,
                'sizeBytes': metadata.file_size_bytes
            },
            'parser': {
                'version': metadata.parser_version,
                'adapter': 'psd-tools',
                'profile': self.profile
            },
            'run': {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'status': 'success',
                'errors': [],
                'warnings': list(self._design_ir.get('diagnostics', {}).get('warnings', []))
            },
            'analysis': {
                'measurements': len(self._design_ir.get('analysis', {}).get('measurements', [])),
                'spatialRelationships': len(self._design_ir.get('analysis', {}).get('spatialRelationships', [])),
                'layoutHypotheses': len(self._design_ir.get('analysis', {}).get('layoutHypotheses', [])),
                'tokenCount': self._design_ir.get('designSystem', {}).get('totalCount', 0),
            },
            'assets': self._asset_manifest(),
            'validation': {
                'status': (self._validation or {}).get('status'),
                'errorCount': len((self._validation or {}).get('errors') or []),
            },
            'output': {
                'directory': '',  # Set when exporting
                'files': []
            }
        }
    
    def _export_results(self, output_dir: Path) -> List[str]:
        """Export all results to JSON files."""
        written: List[str] = []
        if self._assets is not None:
            written.extend(f"assets/{name}" for name in self._assets['files'])

        # Write design.json
        design_path = output_dir / 'design.json'
        with open(design_path, 'w', encoding='utf-8') as f:
            json.dump(self._design_ir, f, indent=2, ensure_ascii=False)
        written.append('design.json')
        
        # Write source-layers.json (separate raw layers)
        raw_layers = self._design_ir['source']['rawLayers']
        sources_path = output_dir / 'source-layers.json'
        with open(sources_path, 'w', encoding='utf-8') as f:
            json.dump(raw_layers, f, indent=2, ensure_ascii=False)
        written.append('source-layers.json')
        
        if self._geometry:
            geometry_path = output_dir / 'geometry.json'
            with open(geometry_path, 'w', encoding='utf-8') as f:
                json.dump(self._geometry, f, indent=2, ensure_ascii=False)
            written.append('geometry.json')
        
        if self._tokens:
            tokens_path = output_dir / 'design-tokens.json'
            with open(tokens_path, 'w', encoding='utf-8') as f:
                json.dump(self._tokens, f, indent=2, ensure_ascii=False)
            written.append('design-tokens.json')

        if self._preview_image is not None:
            try:
                previews_dir = output_dir / 'previews'
                previews_dir.mkdir(parents=True, exist_ok=True)
                metadata = self._design_ir['document']['metadata']
                relationships = self._design_ir['analysis'].get('spatialRelationships', [])

                original_path = previews_dir / 'original.png'
                self._preview_image.save(original_path)
                written.append('previews/original.png')

                annotated = draw_annotations(
                    self._preview_image,
                    raw_layers,
                    show=('bounds', 'ids', 'spacing'),
                    relationships=relationships,
                    document_width=metadata.get('width_px'),
                    document_height=metadata.get('height_px'),
                )
                annotated.save(previews_dir / 'annotated.png')
                written.append('previews/annotated.png')

                viewer_path = output_dir / 'viewer.html'
                viewer_path.write_text(
                    build_viewer_html(self._design_ir, self._preview_image),
                    encoding='utf-8',
                )
                written.append('viewer.html')
            except Exception as e:
                warning = f"Preview/viewer export failed: {e}"
                self._manifest['run']['warnings'].append(warning)
                print(f"Warning: {warning}", file=sys.stderr)

        try:
            written.extend(
                write_reports(
                    output_dir,
                    self._design_ir,
                    self._manifest,
                    assets=self._assets,
                    validation=self._validation,
                    detailed=self._detailed_report,
                )
            )
        except Exception as e:
            warning = f"Report export failed: {e}"
            self._manifest['run']['warnings'].append(warning)
            print(f"Warning: {warning}", file=sys.stderr)
        
        # Update and write manifest
        written.append('manifest.json')
        self._manifest['output']['directory'] = str(output_dir)
        self._manifest['output']['files'] = written
        self._manifest['output']['hashes'] = {
            name: self._sha256_file(output_dir / name)
            for name in written
            if name != 'manifest.json'
        }
        
        manifest_path = output_dir / 'manifest.json'
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(self._manifest, f, indent=2, ensure_ascii=False)
        
        print(f"Results exported to: {output_dir}")
        for name in written:
            print(f"  - {name}: {(output_dir / name).stat().st_size} bytes")
        return written

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(chunk)
        return digest.hexdigest()
