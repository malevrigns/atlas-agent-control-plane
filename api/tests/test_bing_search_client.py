import unittest
from unittest.mock import patch

import httpx

from app.core.exceptions import AppException
from app.infrastructure.search.bing import BingSearchClient


class BingSearchClientTest(unittest.TestCase):
    def test_falls_back_to_bing_page_search_without_api_key(self) -> None:
        html = """
        <html>
          <body>
            <ol>
              <li class="b_algo">
                <h2><a href="https://example.com/agent">AI Agent News</a></h2>
                <p>Latest AI Agent product updates and research notes.</p>
              </li>
            </ol>
          </body>
        </html>
        """
        request = httpx.Request("GET", "https://www.bing.com/search?q=AI")
        response = httpx.Response(200, request=request, text=html)

        with patch("app.infrastructure.search.bing.httpx.get", return_value=response):
            client = BingSearchClient(
                api_key="",
                endpoint="https://api.bing.microsoft.com",
                market="zh-CN",
                timeout_seconds=10,
            )
            result = client.search("AI Agent latest news", 3)

        self.assertEqual(result.provider, "bing-page")
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].title, "AI Agent News")
        self.assertEqual(result.items[0].url, "https://example.com/agent")
        self.assertEqual(
            result.items[0].snippet,
            "Latest AI Agent product updates and research notes.",
        )

    def test_parses_bing_page_result_without_h2_title(self) -> None:
        html = """
        <html>
          <body>
            <ol>
              <li class="b_algo">
                <div class="result-title">
                  <a href="/redirect?target=agent">Enterprise AI Agent research report</a>
                </div>
                <div class="b_caption">
                  <p>Research teams compare planning, tool use, browser automation and memory.</p>
                </div>
              </li>
            </ol>
          </body>
        </html>
        """
        request = httpx.Request("GET", "https://www.bing.com/search?q=AI")
        response = httpx.Response(200, request=request, text=html)

        with patch("app.infrastructure.search.bing.httpx.get", return_value=response):
            client = BingSearchClient(
                api_key="",
                endpoint="https://api.bing.microsoft.com",
                market="zh-CN",
                timeout_seconds=10,
            )
            result = client.search("AI Agent research report", 3)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(
            result.items[0].title,
            "Enterprise AI Agent research report",
        )
        self.assertEqual(
            result.items[0].url,
            "https://www.bing.com/redirect?target=agent",
        )
        self.assertEqual(
            result.items[0].snippet,
            "Research teams compare planning, tool use, browser automation and memory.",
        )

    def test_parses_snippet_from_plain_text_when_caption_is_missing(self) -> None:
        html = """
        <html>
          <body>
            <ol>
              <li class="b_algo">
                <h2><a href="//example.com/agent-tools">AI Agent Tool Systems</a></h2>
                <div>
                  AI Agent Tool Systems
                  This article explains search tools, browser tools and sandbox execution in detail.
                </div>
              </li>
            </ol>
          </body>
        </html>
        """
        request = httpx.Request("GET", "https://www.bing.com/search?q=AI")
        response = httpx.Response(200, request=request, text=html)

        with patch("app.infrastructure.search.bing.httpx.get", return_value=response):
            client = BingSearchClient(
                api_key="",
                endpoint="https://api.bing.microsoft.com",
                market="zh-CN",
                timeout_seconds=10,
            )
            result = client.search("AI Agent Tool Systems", 3)

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].url, "https://example.com/agent-tools")
        self.assertIn("search tools", result.items[0].snippet)

    def test_raises_clear_error_for_bing_verification_page(self) -> None:
        html = """
        <html>
          <body>
            <div class="captcha">Please verify you are a human</div>
          </body>
        </html>
        """
        request = httpx.Request("GET", "https://www.bing.com/search?q=AI")
        response = httpx.Response(200, request=request, text=html)

        with patch("app.infrastructure.search.bing.httpx.get", return_value=response):
            client = BingSearchClient(
                api_key="",
                endpoint="https://api.bing.microsoft.com",
                market="zh-CN",
                timeout_seconds=10,
            )
            with self.assertRaises(AppException) as context:
                client.search("AI Agent latest news", 3)

        self.assertIn("verification page", context.exception.message)


if __name__ == "__main__":
    unittest.main()
