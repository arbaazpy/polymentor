"""Tests for corpus sectioning, BM25 retrieval, and the lane system prompt."""

from __future__ import annotations

from apps.experts import grounding
from apps.experts.fleet import get_spec
from apps.experts.prompts import build_system_prompt


def test_split_sections_handles_markdown_and_underlined_headings():
    md = "# Title\nintro\n## A\nalpha text\n### A.1\nsub text\n"
    titles = [s.title for s in grounding.split_sections("x.md", md)]
    assert titles == ["Title", "A", "A.1"]

    txt = "CARD\n====\nhello\n\nBUGS\n----\noff by one\n"
    sections = grounding.split_sections("x.txt", txt)
    assert [s.title for s in sections] == ["CARD", "BUGS"]
    assert sections[1].text == "off by one"


def test_dsa_index_loads_both_corpus_files():
    sources = {s.source for s in grounding.get_index("dsa").sections}
    assert sources == {"corpus.md", "quickref.txt"}


def test_retrieve_finds_failure_modes_for_binary_search_bug():
    sections = grounding.retrieve("dsa", "My binary search with l = mid loops forever. Why?")
    titles = [s.title for s in sections]
    assert any("Failure modes" in t or "COMMON BUGS" in t for t in titles[:3])


def test_retrieve_always_pins_scope_and_abstention():
    titles = [s.title.lower() for s in grounding.retrieve("dsa", "Kadane maximum subarray")]
    assert any("scope" in t for t in titles)
    assert any("abstention" in t for t in titles)


def test_retrieve_respects_char_budget():
    sections = grounding.retrieve("dsa", "two pointer sliding window heap", max_chars=1500)
    retrieved = [
        s
        for s in sections
        if "scope" not in s.title.lower() and "abstention" not in s.title.lower()
    ]
    assert len(retrieved) <= 1


def test_system_prompt_lists_other_lanes_and_notes():
    spec = get_spec("dsa")
    sections = grounding.retrieve("dsa", "two-sum sorted")
    prompt = build_system_prompt(spec, sections)
    assert "expert.dsa" in prompt
    assert "sysdes:" in prompt and "dsa:" not in prompt.split("Specialists:")[1].split("3.")[0]
    assert "[1] " in prompt and "Reference notes:" in prompt
