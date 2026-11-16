"""
Comprehensive tests for heuristic research summarization (backend/app/summarizer.py).

Verifies all 10 quality, accuracy, and compatibility criteria:
1. Meaningful information is extracted from actual main_text.
2. Relevant headings and page content contribute to findings.
3. Duplicate findings are removed across sections.
4. Source URLs appear alongside page-level findings and key findings.
5. Facts are not fabricated when source content is insufficient.
6. Crawl limitations are disclosed accurately (page counts, boundaries).
7. Short-content websites receive concise summaries rather than artificially expanded sections.
8. The generated summary contains zero decorative emojis or non-standard symbols.
9. Existing heuristic mode works reliably without an LLM API key.
10. Existing summariser callers and return types remain 100% compatible.
"""
from __future__ import annotations

from typing import Any

from app.summarizer import (
    _EMOJI_PATTERN,
    _heuristic_summarize,
    answer_from_data,
    summarize,
    summarize_link_check,
)


class TestHeuristicSummarizer:
    def test_1_meaningful_information_extracted_from_main_text(self) -> None:
        """Meaningful facts, capabilities, and descriptions are extracted from main_text."""
        crawl_data: dict[str, Any] = {
            "site": "https://techcorp.example",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://techcorp.example",
                    "title": "TechCorp Systems",
                    "meta_description": "Enterprise cloud infrastructure provider.",
                    "h1_headings": ["Cloud Infrastructure"],
                    "h2_headings": [],
                    "main_text": (
                        "We deliver automated kubernetes cluster orchestration across distributed datacenters. "
                        "Our architecture guarantees five-nines uptime for mission-critical banking workloads. "
                        "Serving over 500 financial institutions globally."
                    ),
                }
            ],
        }

        summary, takeaways = _heuristic_summarize(crawl_data)
        assert "kubernetes cluster orchestration" in summary
        assert "banking workloads" in summary or "financial institutions" in summary
        assert len(takeaways) >= 2

    def test_2_headings_and_page_content_contribute_to_findings(self) -> None:
        """Headings, company entities, and detail page content combine into coherent findings with description excerpts."""
        crawl_data: dict[str, Any] = {
            "site": "https://jobs.example",
            "stats": {"pages_crawled": 2},
            "pages": [
                {
                    "url": "https://jobs.example",
                    "title": "Jobs Portal",
                    "h1_headings": ["Jobs Portal"],
                    "h2_headings": ["Staff SRE", "Backend Architect"],
                    "main_text": "Staff SRE Acme Cloud Austin, TX 2024-05-10 Apply Backend Architect Acme Cloud Austin, TX 2024-05-10 Apply",
                },
                {
                    "url": "https://jobs.example/staff-sre",
                    "title": "Jobs Portal",
                    "h1_headings": ["Jobs Portal", "Staff SRE"],
                    "h2_headings": ["Acme Cloud"],
                    "main_text": (
                        "Staff SRE Acme Cloud Lead site reliability and incident management. "
                        "Design resilient disaster recovery workflows. Location: Austin, TX Posted: 2024-05-10"
                    ),
                },
            ],
        }

        summary, takeaways = _heuristic_summarize(crawl_data)
        assert "Staff SRE" in summary
        assert "Acme Cloud" in summary
        assert "Austin, TX" in summary
        # Correction 3: Must describe partial content as description excerpt, NOT full specifications
        assert "description excerpt" in summary.lower()
        assert "full specifications" not in summary.lower()
        assert "site reliability" in summary or "incident management" in summary
        assert any("Acme Cloud" in t or "Staff SRE" in t or "Austin" in t for t in takeaways)

    def test_3_duplicate_findings_removed(self) -> None:
        """Findings and sentences are not duplicated across sections."""
        crawl_data: dict[str, Any] = {
            "site": "https://example.com",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "meta_description": "Official documentation domain.",
                    "h1_headings": ["Example Domain"],
                    "h2_headings": [],
                    "main_text": "This domain is for use in illustrative examples in documents. You may use this domain in literature without permission.",
                }
            ],
        }

        summary, _ = _heuristic_summarize(crawl_data)
        lines = [line.strip() for line in summary.splitlines() if line.strip() and not line.startswith("###")]
        # Assert no identical bullet points or lines
        assert len(lines) == len(set(lines)), "Found duplicate lines in summary output"

    def test_4_source_urls_alongside_page_level_findings(self) -> None:
        """Every page-level finding includes a markdown source link to its exact URL."""
        crawl_data: dict[str, Any] = {
            "site": "https://docs.example",
            "stats": {"pages_crawled": 2},
            "pages": [
                {
                    "url": "https://docs.example/page1",
                    "title": "Introduction",
                    "main_text": "Getting started with our distributed developer platform.",
                },
                {
                    "url": "https://docs.example/page2",
                    "title": "API Reference",
                    "main_text": "Full REST API specifications with endpoint schemas.",
                },
            ],
        }

        summary, _ = _heuristic_summarize(crawl_data)
        assert "- **[Introduction](https://docs.example/page1)**:" in summary
        assert "- **[API Reference](https://docs.example/page2)**:" in summary

    def test_5_facts_not_fabricated_when_content_insufficient(self) -> None:
        """Missing entities, dates, or details are never fabricated."""
        crawl_data: dict[str, Any] = {
            "site": "https://minimal.example",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://minimal.example",
                    "title": "Plain Page",
                    "main_text": "Simple informational statement without any names or metrics.",
                }
            ],
        }

        summary, _ = _heuristic_summarize(crawl_data)
        # Assert no fabricated dates or companies
        assert "202" not in summary
        assert "Acme" not in summary
        assert "Google" not in summary
        assert "RFC" not in summary

    def test_6_crawl_limitations_disclosed_accurately(self) -> None:
        """Limitations section honestly states crawled pages, never equates crawled to max_pages, and only reports limits with evidence."""
        # Case A: Configured limit is NOT in crawl data -> report coverage is unverified without guessing max_pages
        crawl_data_no_limit: dict[str, Any] = {
            "site": "https://example.com",
            "stats": {"pages_crawled": 3},
            "errors": ["Connection timeout on /archive"],
            "skipped": ["/private/admin"],
            "pages": [
                {"url": "https://example.com/p1", "main_text": "Sample content page one."},
                {"url": "https://example.com/p2", "main_text": "Sample content page two."},
                {"url": "https://example.com/p3", "main_text": "Sample content page three."},
            ],
        }

        summary_a, takeaways_a = _heuristic_summarize(crawl_data_no_limit)
        assert "### Research Limitations" in summary_a
        assert "3 successfully crawled page(s)" in summary_a
        # Correction 1: Never use pages_crawled as max_pages configuration
        assert "max_pages=3" not in summary_a
        assert "max_pages=" not in summary_a
        assert "The automated inspection crawled 3 page(s); complete website coverage is unverified." in summary_a
        # No automatic claim about unvisited directories without evidence
        assert "unvisited directory levels" not in summary_a
        assert "1 page error(s)" in summary_a
        assert "1 page(s) were bypassed due to robots.txt or network boundaries" in summary_a
        assert any("Complete website-wide coverage has not been established." in t for t in takeaways_a)
        assert not any("unvisited pages remain on the domain" in t for t in takeaways_a)

        # Case B: Configured limit IS in crawl data -> report configured limit accurately
        crawl_data_with_limit: dict[str, Any] = {
            "site": "https://example.com",
            "stats": {"pages_crawled": 5, "pages_limit": 5},
            "pages": [{"url": f"https://example.com/p{i}", "main_text": f"Page {i} content"} for i in range(5)],
        }
        summary_b, _ = _heuristic_summarize(crawl_data_with_limit)
        assert "reached the configured limit of 5 page(s) (max_pages=5)" in summary_b

    def test_7_short_content_websites_receive_concise_summaries(self) -> None:
        """A minimal website with very little content receives an honest 3-section concise summary."""
        sparse_data: dict[str, Any] = {
            "site": "https://under-construction.example",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://under-construction.example",
                    "title": "Under Construction",
                    "meta_description": "",
                    "h1_headings": [],
                    "h2_headings": [],
                    "main_text": "Website is currently under construction. Please check back later.",
                }
            ],
        }

        summary, _ = _heuristic_summarize(sparse_data)
        # Executive Overview, Page-Level Findings, Research Limitations must be present
        assert "### Executive Overview" in summary
        assert "### Page-Level Findings" in summary
        assert "### Research Limitations" in summary
        # Should NOT force artificial Key Findings or Important Information when no facts exist
        assert "### Key Findings" not in summary
        assert "### Important Information" not in summary

    def test_8_zero_decorative_emojis_while_preserving_international_text(self) -> None:
        """Decorative emojis are removed while English, Tamil, Chinese, currencies, and technical symbols remain completely intact."""
        crawl_data: dict[str, Any] = {
            "site": "https://multilingual.example",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://multilingual.example",
                    "title": "Global Portal 🚀",
                    "meta_description": "💡 Innovative international platform for global users ★",
                    "main_text": (
                        "English overview: High performance cloud platform with $29.99 pricing and 99.9% SLA. "
                        "Tamil section: வணக்கம் உலகம்! தமிழ் மொழி ஆராய்ச்சி ₹5000. "
                        "Chinese section: 你好世界！中文技术文档搜索，价格 ¥999。 "
                        "German/French text: Über 50% Rabatt für Café & Naïve résumé: €45.00. "
                        "Math & technical: f(x) = x^2 ± 3 × 4 ≠ 0, 100°C temperature, a/b < c. "
                        "Decorative bullets to strip: • Item 1 ★ Item 2 📌 Item 3."
                    ),
                }
            ],
        }

        summary, takeaways = _heuristic_summarize(crawl_data)

        # 1. Verify emojis and decorative symbols are stripped
        assert not _EMOJI_PATTERN.search(summary), "Found emoji in summary output"
        assert "🚀" not in summary
        assert "💡" not in summary
        assert "★" not in summary
        assert "•" not in summary
        assert "📌" not in summary

        # 2. Verify English ordinary text and punctuation preserved
        assert "High performance cloud platform" in summary
        assert "$29.99" in summary
        assert "99.9%" in summary

        # 3. Verify Tamil text and currency preserved
        assert "வணக்கம்" in summary
        assert "தமிழ்" in summary
        assert "ஆராய்ச்சி" in summary
        assert "₹5000" in summary

        # 4. Verify Chinese text and currency preserved
        assert "你好世界" in summary
        assert "中文技术文档搜索" in summary
        assert "¥999" in summary

        # 5. Verify German/French accented text and Euro currency preserved
        assert "Über" in summary
        assert "Café" in summary
        assert "€45.00" in summary

        # 6. Verify technical math symbols preserved
        assert "f(x)" in summary or "100°C" in summary

        for t in takeaways:
            assert not _EMOJI_PATTERN.search(t), f"Found emoji in takeaway: {t}"

    def test_9_heuristic_mode_works_without_llm_key(self) -> None:
        """summarize() falls back to heuristic summary seamlessly with zero LLM configuration."""
        crawl_data: dict[str, Any] = {
            "site": "https://example.com",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://example.com",
                    "title": "Example Domain",
                    "meta_description": "Documentation example domain.",
                    "h1_headings": ["Example Domain"],
                    "main_text": "This domain is for use in documentation examples without needing permission.",
                }
            ],
        }

        # Call the public summarize entry point
        summary, takeaways = summarize(crawl_data)
        assert "Example Domain" in summary
        assert "### Executive Overview" in summary
        assert len(takeaways) >= 2

    def test_10_compatibility_of_existing_summarizer_functions(self) -> None:
        """Return types and signatures of summarize, summarize_link_check, and answer_from_data are preserved."""
        # 1. summarize return type
        res = summarize({"site": "https://example.com", "pages": [{"url": "https://example.com", "main_text": "Testing"}]})
        assert isinstance(res, tuple)
        assert len(res) == 2
        assert isinstance(res[0], str)
        assert isinstance(res[1], list)

        # 2. summarize_link_check return type
        lc_res = summarize_link_check({
            "site": "https://example.com",
            "links": [{"url": "https://example.com/a", "status": "working", "status_code": 200}],
            "stats": {"checked": 1, "working": 1, "broken": 0},
        })
        assert isinstance(lc_res, tuple)
        assert len(lc_res) == 2
        assert isinstance(lc_res[0], str)
        assert isinstance(lc_res[1], list)

        # 3. answer_from_data return type
        ans, cites = answer_from_data(
            "What is tested?",
            {"pages": [{"url": "https://example.com", "main_text": "We test robust compatibility."}]},
        )
        assert isinstance(ans, str)
        assert isinstance(cites, list)

    def test_11_distinguish_full_content_from_short_excerpts(self) -> None:
        """Excerpts are labeled honestly as excerpts and never exaggerated as full specifications."""
        crawl_data: dict[str, Any] = {
            "site": "https://jobs.example",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://jobs.example/dev-1",
                    "title": "Lead Developer",
                    "h1_headings": ["Jobs", "Lead Developer"],
                    "h2_headings": ["Beta Corp"],
                    "main_text": (
                        "Beta Corp Lead Developer Short description excerpt here. "
                        "Location: New York, NY Posted: 2024-06-01"
                    ),
                }
            ],
        }

        summary, _ = _heuristic_summarize(crawl_data)
        assert "description excerpt" in summary.lower()
        assert "full specifications" not in summary.lower()
        assert "complete specifications" not in summary.lower()
        assert "detailed vacancy requirements" not in summary.lower()

    def test_12_books_to_scrape_catalog_extraction_and_connected_prices(self) -> None:
        """
        Regression test for Books to Scrape catalog pages:
        - Product titles, prices, and stock availability appear in the summary.
        - Prices are connected directly to their respective book titles.
        - Generic boilerplate ('We love being scraped!', 'demo website') and repeated breadcrumbs are filtered out.
        - Source URLs are included alongside findings.
        - No speculative claims or fabricated coverage.
        """
        crawl_data: dict[str, Any] = {
            "site": "https://books.toscrape.com/",
            "stats": {"pages_crawled": 3},
            "pages": [
                {
                    "url": "https://books.toscrape.com/",
                    "title": "All products | Books to Scrape - Sandbox",
                    "meta_description": "",
                    "h1_headings": ["All products"],
                    "h2_headings": [],
                    "main_text": (
                        "Category: Home > All products | Books to Scrape We love being scraped! "
                        "Warning! This is a demo website for web scraping purposes. "
                        "Prices and ratings here were randomly assigned and have no real meaning. "
                        "A Light in the Attic £51.77 In stock Add to basket "
                        "Tipping the Velvet £53.74 In stock Add to basket "
                        "Soumission £50.10 In stock Add to basket"
                    ),
                },
                {
                    "url": "https://books.toscrape.com/catalogue/category/books/travel_2/index.html",
                    "title": "Travel | Books to Scrape - Sandbox",
                    "meta_description": "",
                    "h1_headings": ["Travel"],
                    "h2_headings": [],
                    "main_text": (
                        "Category: Books | Books to Scrape We love being scraped! "
                        "It's Only the Himalayas £45.17 In stock Add to basket "
                        "Ark: An Odyssey to Mount Ararat and Beyond £49.43 In stock Add to basket"
                    ),
                },
                {
                    "url": "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
                    "title": "Mystery | Books to Scrape - Sandbox",
                    "meta_description": "",
                    "h1_headings": ["Mystery"],
                    "h2_headings": [],
                    "main_text": (
                        "Category: Books | Books to Scrape We love being scraped! "
                        "Sharp Objects £47.82 In stock Add to basket "
                        "In a Dark, Dark Wood £19.63 In stock Add to basket"
                    ),
                },
            ],
        }

        summary, takeaways = _heuristic_summarize(crawl_data)

        # 1. Product titles, prices, and stock appear in the summary
        assert "A Light in the Attic" in summary
        assert "Tipping the Velvet" in summary
        assert "It's Only the Himalayas" in summary
        assert "Sharp Objects" in summary

        # 2. Prices are connected to their respective book titles
        assert ("'A Light in the Attic' offered at £51.77 (In stock)" in summary or
                "'A Light in the Attic' (£51.77, In stock)" in summary)
        assert ("'Sharp Objects' offered at £47.82 (In stock)" in summary or
                "'Sharp Objects' (£47.82, In stock)" in summary)

        # 3. Boilerplate and breadcrumbs are eliminated
        assert "We love being scraped!" not in summary
        assert "demo website for web scraping" not in summary.lower()
        assert "prices and ratings here were randomly assigned" not in summary.lower()
        # Key findings must not contain raw breadcrumbs
        for line in summary.splitlines():
            if line.startswith("- Product item:"):
                assert "Category:" not in line
                assert "We love being scraped!" not in line

        # 4. Source URLs accompany findings
        assert "source: https://books.toscrape.com/" in summary
        assert "source: https://books.toscrape.com/catalogue/category/books/travel_2/index.html" in summary
        assert "source: https://books.toscrape.com/catalogue/category/books/mystery_3/index.html" in summary

        # 5. Inventory status is summarized
        assert "in stock across" in summary

        # 6. Takeaways reflect products and unverified full coverage
        assert any("Indexed catalog items:" in t for t in takeaways)
        assert any("Complete website-wide coverage has not been established." in t for t in takeaways)

    def test_13_books_detail_page_extraction(self) -> None:
        """Single product detail page extracts title, price, status, and description excerpt."""
        crawl_data: dict[str, Any] = {
            "site": "https://books.toscrape.com/",
            "stats": {"pages_crawled": 1},
            "pages": [
                {
                    "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
                    "title": "A Light in the Attic | Books to Scrape - Sandbox",
                    "meta_description": "",
                    "h1_headings": ["A Light in the Attic"],
                    "h2_headings": [],
                    "main_text": (
                        "Category: Books > Poetry | A Light in the Attic £51.77 In stock (22 available) "
                        "Warning! This is a demo website for web scraping purposes. "
                        "Product Description It's hard to imagine a world without A Light in the Attic. "
                        "This now-classic collection of poetry celebrates its 20th anniversary."
                    ),
                }
            ],
        }

        summary, takeaways = _heuristic_summarize(crawl_data)
        assert "A Light in the Attic" in summary
        assert "£51.77" in summary
        assert "In stock (22 available)" in summary
        assert "Description excerpt:" in summary
        assert "poetry celebrates its 20th anniversary" in summary
        assert "We love being scraped!" not in summary
