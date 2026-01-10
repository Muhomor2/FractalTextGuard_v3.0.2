#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GSL-LRD Text Analyzer - Simple Interface
========================================

Designed for:
- Professors checking student papers for AI-generated content
- Researchers analyzing text authenticity
- Anyone detecting AI text degradation/collapse

Usage:
  python analyze.py --file essay.txt              # Quick check
  python analyze.py --file essay.txt --detailed   # Full report
  python analyze.py --folder papers/ --output results.json  # Batch

Results:
  HEALTHY - No strong structural risk signals
  WARNING - Mixed/ambiguous signals; review recommended  
  CRITICAL - Strong structural signal; treat as high-risk

Author: Igor Sikorsky (ORCID: 0009-0007-4607-1946)
License: MIT
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

# Import core analyzer
try:
    from src.analyzer_core import analyze_text_full, quick_verdict
except ImportError:
    # Running from package root
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from src.analyzer_core import analyze_text_full, quick_verdict


def format_result_simple(result: Dict, filename: str) -> str:
    """Format result for human reading"""
    verdict = result.get("verdict", "UNKNOWN")
    confidence = result.get("confidence", 0)
    
    icons = {
    "HEALTHY": "✅",
    "WARNING": "⚠️",
    "CRITICAL": "🚨",
}
    icon = icons.get(verdict, "❓")
    
    lines = [
        f"\n{'='*60}",
        f"File: {filename}",
        f"{'='*60}",
        f"",
        f"  Result: {icon} {verdict}",
        f"  Confidence: {confidence:.0%}",
    ]
    
    if result.get("warnings"):
        lines.append(f"\n  ⚠️  Warnings:")
        for w in result["warnings"][:3]:
            lines.append(f"      - {w}")
    
    lines.append(f"\n{'='*60}\n")
    return "\n".join(lines)


def format_result_detailed(result: Dict, filename: str) -> str:
    """Format detailed result"""
    lines = [format_result_simple(result, filename)]
    
    metrics = result.get("metrics", {})
    if metrics:
        lines.append("  📊 Detailed Metrics:")
        lines.append(f"      Hurst exponent (H): {metrics.get('H', 'N/A')}")
        lines.append(f"      Compression ratio: {metrics.get('compress_ratio', 'N/A')}")
        lines.append(f"      Repetition rate: {metrics.get('repeat_rate', 'N/A')}")
        lines.append(f"      Entropy: {metrics.get('entropy', 'N/A')}")
        lines.append("")
    
    interpretation = result.get("interpretation", {})
    if interpretation:
        lines.append("  📝 Interpretation:")
        for key, value in interpretation.items():
            lines.append(f"      {key}: {value}")
        lines.append("")
    
    return "\n".join(lines)


def analyze_single_file(filepath: str, detailed: bool = False, offline: bool = True) -> Dict:
    """Analyze a single file"""
    if not os.path.exists(filepath):
        return {"error": f"File not found: {filepath}", "verdict": "ERROR"}
    
    try:
        with open(filepath, "rb") as f:
            content = f.read()
        
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")
        
        if detailed:
            result = analyze_text_full(text, offline=offline)
        else:
            result = quick_verdict(text, offline=offline)
        
        result["filename"] = os.path.basename(filepath)
        return result
        
    except Exception as e:
        return {"error": str(e), "verdict": "ERROR", "filename": os.path.basename(filepath)}


def analyze_folder(folder: str, detailed: bool = False, offline: bool = True) -> List[Dict]:
    """Analyze all text files in folder"""
    results = []
    
    text_extensions = {".txt", ".md", ".rst", ".tex", ".html", ".htm"}
    
    for root, _, files in os.walk(folder):
        for filename in sorted(files):
            ext = os.path.splitext(filename)[1].lower()
            if ext in text_extensions:
                filepath = os.path.join(root, filename)
                result = analyze_single_file(filepath, detailed, offline)
                results.append(result)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="GSL-LRD Text Analyzer - Detect AI-generated content",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python analyze.py --file essay.txt
  python analyze.py --file paper.txt --detailed
  python analyze.py --folder submissions/ --output results.json
  python analyze.py --file doc.txt --json

Results explanation:
  HEALTHY     - No strong structural risk signals
  WARNING     - Mixed/ambiguous signals; manual review recommended
  CRITICAL    - Strong structural signal (repetition/collapse etc.)
        """
    )
    
    parser.add_argument("--file", "-f", help="Single file to analyze")
    parser.add_argument("--folder", "-d", help="Folder with files to analyze")
    parser.add_argument("--output", "-o", help="Save results to JSON file")
    parser.add_argument("--detailed", action="store_true", help="Show detailed metrics")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--online", action="store_true", help="Enable online verification (default: offline)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    
    args = parser.parse_args()
    
    if not args.file and not args.folder:
        parser.print_help()
        print("\n❌ Error: Please specify --file or --folder")
        return 1
    
    offline = not args.online
    results = []
    
    if args.file:
        result = analyze_single_file(args.file, args.detailed, offline)
        results.append(result)
        
        if not args.quiet:
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            elif args.detailed:
                print(format_result_detailed(result, args.file))
            else:
                print(format_result_simple(result, args.file))
    
    if args.folder:
        folder_results = analyze_folder(args.folder, args.detailed, offline)
        results.extend(folder_results)
        
        if not args.quiet:
            print(f"\n📁 Analyzed {len(folder_results)} files from {args.folder}\n")
            
            # Summary
            verdicts = {"HEALTHY": 0, "WARNING": 0, "CRITICAL": 0, "ERROR": 0, "UNKNOWN": 0}
            for r in folder_results:
                v = r.get("verdict", "UNKNOWN")
                verdicts[v] = verdicts.get(v, 0) + 1
            
            print("Summary:")
            print(f"  ✅ HEALTHY:   {verdicts.get('HEALTHY', 0)}")
            print(f"  ⚠️  WARNING:  {verdicts.get('WARNING', 0)}")
            print(f"  🚨 CRITICAL: {verdicts.get('CRITICAL', 0)}")
            if verdicts.get("ERROR", 0):
                print(f"  ❌ ERRORS:      {verdicts.get('ERROR', 0)}")
            print()
            
            if args.json:
                print(json.dumps(folder_results, indent=2, ensure_ascii=False))
            else:
                # Show suspicious/AI files
                flagged = [r for r in folder_results if r.get("verdict") in ("WARNING", "CRITICAL")]
                if flagged:
                    print("⚠️  Files requiring attention:")
                    for r in flagged:
                        icon = "🤖" if r.get("verdict") == "CRITICAL" else "⚠️"
                        print(f"    {icon} {r.get('filename', 'unknown')}: {r.get('verdict')}")
    
    if args.output:
        output_data = {
            "analyzer": "GSL-LRD Text Analyzer",
            "version": "3.0",
            "files_analyzed": len(results),
            "results": results
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Results saved to: {args.output}")
    
    # Exit code based on results
    ai_count = sum(1 for r in results if r.get("verdict") == "CRITICAL")
    return 1 if ai_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
