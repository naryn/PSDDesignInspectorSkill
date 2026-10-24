"""Command-line interface for PSD Design Inspector."""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .pipeline import DesignIRPipeline, ExtractorProfile


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='psd-inspector',
        description='Analyze Photoshop PSD/PSB files and extract design specifications'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Inspect command
    inspect_parser = subparsers.add_parser(
        'inspect',
        help='Process a PSD file and generate Design IR'
    )
    inspect_parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to input PSD/PSB file'
    )
    inspect_parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output directory for results'
    )
    inspect_parser.add_argument(
        '--profile', '-p',
        choices=[ExtractorProfile.FAST, ExtractorProfile.FULL, ExtractorProfile.DEEP],
        default=ExtractorProfile.FULL,
        help='Extraction profile (default: full)'
    )
    inspect_parser.add_argument(
        '--export-assets',
        action='store_true',
        help='Export layer assets as images'
    )
    inspect_parser.add_argument(
        '--report',
        action='store_true',
        help='Generate detailed report'
    )
    
    # Layer get command
    layer_parser = subparsers.add_parser(
        'layer',
        help='Layer operations'
    )
    layer_subparsers = layer_parser.add_subparsers(dest='layer_command')
    
    # Layer get
    layer_get = layer_subparsers.add_parser(
        'get',
        help='Get details of a specific layer'
    )
    layer_get.add_argument(
        '--ir',
        required=True,
        help='Path to design.json IR file'
    )
    layer_get.add_argument(
        '--id',
        required=True,
        help='Layer ID to retrieve'
    )
    
    # Geometry neighbors command
    geometry_parser = subparsers.add_parser(
        'geometry',
        help='Geometry analysis operations'
    )
    geometry_subparsers = geometry_parser.add_subparsers(dest='geometry_command')
    
    neighbors = geometry_subparsers.add_parser(
        'neighbors',
        help='Find nearby elements and spacing'
    )
    neighbors.add_argument(
        '--ir',
        required=True,
        help='Path to design.json IR file'
    )
    neighbors.add_argument(
        '--id',
        required=True,
        help='Layer ID to find neighbors for'
    )
    neighbors.add_argument(
        '--distance',
        type=float,
        default=100.0,
        help='Maximum distance in pixels'
    )
    
    # Tokens command
    tokens_parser = subparsers.add_parser(
        'tokens',
        help='Design token operations'
    )
    tokens_subparsers = tokens_parser.add_subparsers(dest='tokens_command')
    
    tokens_extract = tokens_subparsers.add_parser(
        'extract',
        help='Extract design tokens from IR'
    )
    tokens_extract.add_argument(
        '--ir',
        required=True,
        help='Path to design.json IR file'
    )
    tokens_extract.add_argument(
        '--types',
        nargs='+',
        default=['colors', 'typography', 'spacing', 'borders', 'shadows'],
        metavar='TYPE',
        help='Token types: colors typography spacing borders shadows (space or comma separated)'
    )
    tokens_extract.add_argument(
        '--output', '-o',
        help='Output file path (default: stdout)'
    )
    
    # Annotate command
    annotate_parser = subparsers.add_parser(
        'annotate',
        help='Create annotated visualization'
    )
    annotate_parser.add_argument(
        '--ir',
        required=True,
        help='Path to design.json IR file'
    )
    annotate_parser.add_argument(
        '--show',
        nargs='+',
        default=['bounds'],
        metavar='ITEM',
        help='What to draw: bounds ids spacing (space or comma separated)'
    )
    annotate_parser.add_argument(
        '--preview',
        help='Existing composite preview image to annotate (default: <ir-dir>/previews/original.png)'
    )
    annotate_parser.add_argument(
        '--psd',
        help='Source PSD/PSB used to render the composite when no preview exists'
    )
    annotate_parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output image path'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Route to appropriate handler
    if args.command == 'inspect':
        _handle_inspect(args)
    elif args.command == 'layer':
        _handle_layer(args)
    elif args.command == 'geometry':
        _handle_geometry(args)
    elif args.command == 'tokens':
        _handle_tokens(args)
    elif args.command == 'annotate':
        _handle_annotate(args)
    else:
        parser.print_help()
        sys.exit(1)


def _handle_inspect(args):
    """Handle inspect command."""
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Check file extension
    if input_path.suffix.lower() not in ['.psd', '.psb']:
        print(f"Error: Unsupported file format: {input_path.suffix}", file=sys.stderr)
        print("Supported formats: .psd, .psb", file=sys.stderr)
        sys.exit(1)
    
    # Create pipeline and process
    pipeline = DesignIRPipeline(profile=args.profile)
    result = pipeline.process_file(
        str(input_path),
        args.output,
        export_assets=args.export_assets,
        report=args.report,
    )
    
    if result['status'] == 'success':
        print("\n✓ Processing complete!")
        print(f"\nOutput directory: {result['output_dir']}")
        print(f"\nLayers: {result['layers_processed']}")
        print(f"Tokens: {result['tokens']}")
        print(f"Layout candidates: {result['layout_hypotheses']}")
        if args.export_assets:
            print(f"Assets exported: {result['assets_exported']}")
        print(f"Schema validation: {result['validation_status']}")
        print(f"\nFiles generated:")
        for f in result['files_generated']:
            print(f"  - {f}")
        sys.exit(0)
    else:
        print(f"\n✗ Error: {result['error']}", file=sys.stderr)
        if 'details' in result:
            import json
            print(json.dumps(result['details'], indent=2), file=sys.stderr)
        sys.exit(1)


def _handle_layer(args):
    """Handle layer commands."""
    if args.layer_command == 'get':
        _layer_get(args)
    else:
        print("Unsupported layer command", file=sys.stderr)
        sys.exit(1)


def _layer_get(args):
    """Get details of specific layer."""
    ir_path = Path(args.ir)
    if not ir_path.exists():
        print(f"Error: IR file not found: {args.ir}", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(ir_path, 'r', encoding='utf-8') as f:
            ir_data = json.load(f)
        
        layers = ir_data.get('source', {}).get('rawLayers', [])
        target_id = args.id
        
        # Find matching layer
        for layer in layers:
            if layer.get('id') == target_id or layer.get('source_layer_id') == int(target_id.replace('layer-', '')):
                print(json.dumps(layer, indent=2, ensure_ascii=False))
                return
        
        print(f"Layer not found: {target_id}", file=sys.stderr)
        sys.exit(1)
        
    except json.JSONDecodeError as e:
        print(f"Error parsing IR file: {e}", file=sys.stderr)
        sys.exit(1)


def _handle_geometry(args):
    """Handle geometry commands."""
    if args.geometry_command == 'neighbors':
        _geometry_neighbors(args)
    else:
        print("Unsupported geometry command", file=sys.stderr)
        sys.exit(1)


def _geometry_neighbors(args):
    """Find neighbor layers and spacing for a given layer."""
    ir_path = Path(args.ir)
    if not ir_path.exists():
        print(f"Error: IR file not found: {args.ir}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(ir_path, 'r', encoding='utf-8') as f:
            ir_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing IR file: {e}", file=sys.stderr)
        sys.exit(1)

    from .analysis.geometry_engine import GeometryAnalyzer, is_visible_leaf

    layers = ir_data.get('source', {}).get('rawLayers', [])
    target = next((layer for layer in layers if layer.get('id') == args.id), None)
    if target is None:
        print(f"Layer not found: {args.id}", file=sys.stderr)
        sys.exit(1)
    if not is_visible_leaf(target):
        print(
            f"Layer {args.id} is a hidden/group layer; neighbor analysis requires a visible leaf layer.",
            file=sys.stderr,
        )
        sys.exit(1)

    neighbors = GeometryAnalyzer().relationships_for(layers, args.id, args.distance)
    print(json.dumps({
        'layer': {
            'id': target.get('id'),
            'name': target.get('name'),
            'bounds': target.get('geometry', {}).get('source_bounds'),
        },
        'maxDistancePx': args.distance,
        'basis': 'measured_geometry',
        'neighbors': neighbors,
    }, indent=2, ensure_ascii=False))


def _handle_tokens(args):
    """Handle token extraction commands."""
    if args.tokens_command == 'extract':
        _tokens_extract(args)
    else:
        print("Unsupported tokens command", file=sys.stderr)
        sys.exit(1)


def _tokens_extract(args):
    """Extract design token candidates from an existing IR file."""
    ir_path = Path(args.ir)
    if not ir_path.exists():
        print(f"Error: IR file not found: {args.ir}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(ir_path, 'r', encoding='utf-8') as f:
            ir_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing IR file: {e}", file=sys.stderr)
        sys.exit(1)

    from .analysis.token_extractor import TokenExtractor

    token_types = _split_values(args.types)
    invalid = set(token_types) - {'colors', 'typography', 'spacing', 'borders', 'shadows'}
    if invalid:
        print(f"Error: unknown token types: {', '.join(sorted(invalid))}", file=sys.stderr)
        sys.exit(2)

    tokens = TokenExtractor().extract(ir_data, types=token_types)
    payload = json.dumps(tokens, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload, encoding='utf-8')
        print(f"Tokens written to: {output_path}")
    else:
        print(payload)


def _split_values(values):
    """Accept both space-separated and comma-separated CLI values."""
    result = []
    for value in values or []:
        result.extend(part.strip() for part in value.split(',') if part.strip())
    return result


def _handle_annotate(args):
    """Draw measured bounds, IDs and spacing over the composite preview."""
    ir_path = Path(args.ir)
    if not ir_path.exists():
        print(f"Error: IR file not found: {args.ir}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(ir_path, 'r', encoding='utf-8') as f:
            ir_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error parsing IR file: {e}", file=sys.stderr)
        sys.exit(1)

    show = _split_values(args.show) or ['bounds']
    invalid = set(show) - {'bounds', 'ids', 'spacing'}
    if invalid:
        print(f"Error: unknown annotation items: {', '.join(sorted(invalid))}", file=sys.stderr)
        sys.exit(2)

    from PIL import Image

    from .exporters.preview_exporter import draw_annotations, render_composite

    layers = ir_data.get('source', {}).get('rawLayers', [])
    metadata = ir_data.get('document', {}).get('metadata', {})
    width = metadata.get('width_px')
    height = metadata.get('height_px')

    preview_path = Path(args.preview) if args.preview else ir_path.parent / 'previews' / 'original.png'
    if preview_path.exists():
        base = Image.open(preview_path)
        base.load()
    else:
        psd_path = Path(args.psd) if args.psd else None
        if psd_path is None:
            manifest_path = ir_path.parent / 'manifest.json'
            if manifest_path.exists():
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        psd_path = Path(json.load(f)['inputFile']['path'])
                except (OSError, ValueError, KeyError):
                    psd_path = None
        if psd_path is not None and psd_path.exists():
            try:
                base = render_composite(psd_path)
            except Exception as e:
                print(f"Error rendering composite preview: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            print(
                "Warning: no preview image found; drawing on a blank canvas.",
                file=sys.stderr,
            )
            base = Image.new('RGB', (width or 1, height or 1), (255, 255, 255))

    annotated = draw_annotations(
        base,
        layers,
        show=show,
        relationships=ir_data.get('analysis', {}).get('spatialRelationships', []),
        document_width=width,
        document_height=height,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(output_path)
    print(f"Annotated preview written to: {output_path}")
    print(f"  - layers drawn: {len(layers)}")
    print(f"  - annotation items: {', '.join(show)}")


if __name__ == '__main__':
    main()
