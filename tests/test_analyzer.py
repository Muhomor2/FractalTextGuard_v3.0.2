#!/usr/bin/env python3
"""Basic tests for analyzer"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer_core import (
    analyze_text_full, quick_verdict, dfa_hurst, 
    compressibility_ratio, repetition_metrics
)

def test_human_text():
    text = """The morning fog lifted slowly from the valley, revealing 
    patches of wildflowers that had bloomed overnight. Sarah picked her way 
    carefully along the muddy path, her boots squelching with each step. 
    She had promised her grandmother to collect herbs before noon, 
    and the best ones grew near the old stone bridge."""
    
    result = analyze_text_full(text)
    assert result["verdict"] in ("HEALTHY", "WARNING"), f"Human text misclassified: {result}"
    print(f"✓ Human text: {result['verdict']} (H={result['metrics'].get('H')})")

def test_repetitive_text():
    text = "I apologize. " * 50 + "Let me help. " * 50
    result = analyze_text_full(text)
    assert result["verdict"] in ("WARNING", "CRITICAL"), f"Repetitive text not flagged: {result}"
    print(f"✓ Repetitive text: {result['verdict']}")

def test_dfa_white_noise():
    import random
    random.seed(42)
    # White noise should have H ≈ 0.5
    data = [random.gauss(0, 1) for _ in range(2048)]
    result = dfa_hurst(data, order=2)
    assert result["ok"], "DFA failed on white noise"
    assert 0.4 <= result["H"] <= 0.6, f"White noise H={result['H']} out of range"
    print(f"✓ DFA white noise: H={result['H']:.3f}")

def test_compressibility():
    # Random text should be less compressible than repetitive
    random_text = b"abcdefghijklmnopqrstuvwxyz" * 10
    repetitive = b"aaaaaaaaaa" * 26
    
    r1 = compressibility_ratio(random_text)
    r2 = compressibility_ratio(repetitive)
    assert r2 < r1, "Repetitive text should be more compressible"
    print(f"✓ Compressibility: varied={r1:.3f}, repetitive={r2:.3f}")

def test_quick_verdict():
    text = "Normal human text with varied vocabulary and structure."
    result = quick_verdict(text)
    assert "verdict" in result
    print(f"✓ Quick verdict works: {result['verdict']}")

if __name__ == "__main__":
    print("Running GSL-LRD Analyzer Tests\n" + "="*40)
    test_human_text()
    test_repetitive_text()
    test_dfa_white_noise()
    test_compressibility()
    test_quick_verdict()
    print("="*40 + "\nAll tests passed! ✓")
