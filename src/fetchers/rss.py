"""RSS 抓取：支持 Substack、博客、YouTube、播客、Twitter(Nitter/OpenRSS)"""

import re
import calendar
import time as _time
import feedparser
from .base import RawItem
from src import state as _state


def _fetch_fulltext(url: str, max_chars: int = 8000) -> str | None:
    """用 trafilatura 抓取文章正文，失败时返回 None"""
    try:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
        if text and len(text) > max_chars:
            text = text[:max_chars] + "…（正文已截断）"
        return text
    except Exception:
        return None


def fetch_rss(
    url: str,
    source_name: str,
    max_entries: int = 3,
    fetch_fulltext: bool = False,
    fulltext_chars: int = 8000,
    max_age_days: int = 30,
) -> list[RawItem]:
    """抓取 RSS feed，返回 RawItem 列表（跨天自动去重，7 天内不重复推送同一篇文章）

    fetch_fulltext: 是否用 trafilatura 抓取文章正文（默认关闭）
    fulltext_chars: 正文最大字符数，默认 8000
    max_age_days: 超过此天数的文章直接跳过，默认 30 天
    """
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "NewsSummary/1.0"})
    except Exception as e:
        return [RawItem(source_name=source_name, source_type="rss", title="[抓取失败]", content=str(e), link=url)]

    st = _state.load()
    new_items = []
    age_cutoff = _time.time() - max_age_days * 86400

    for entry in feed.entries:
        if len(new_items) >= max_entries:
            break

        title = entry.get("title", "(无标题)")
        link = entry.get("link", "")
        published = entry.get("published", entry.get("updated", ""))

        # 优先取 content:encoded（Substack / WordPress 全文在这里），
        # 再 fallback 到 summary / description（短摘要）
        content_entries = entry.get("content", [])
        if content_entries:
            summary = content_entries[0].get("value", "")
        else:
            summary = entry.get("summary", entry.get("description", ""))

        # 跳过超过 max_age_days 的文章
        published_parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not published_parsed:
            continue
        if published_parsed:
            pub_ts = calendar.timegm(published_parsed)
            if pub_ts < age_cutoff or pub_ts > _time.time():
                continue

        # 用链接去重；无链接的文章不去重
        if link and _state.is_seen(st, "seenArticles", link):
            continue

        # 清理 RSS 内容里的 HTML 标签
        if summary and "<" in summary:
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = " ".join(summary.split())

        # Read the article even when the feed contains a descriptive snippet.
        content = summary
        if fetch_fulltext and link:
            content = _fetch_fulltext(link, max_chars=fulltext_chars)
            if not content or len(content) < 600:
                new_items.append(RawItem(
                    source_name=source_name, source_type="rss",
                    title="[正文不足]", content="原文提取失败或不足600字符，未用于生成。", link=link))
                continue
            content = "[网页正文提取；可能截断，非独立事实核验]\n" + content

        if content and len(content) > fulltext_chars:
            content = content[:fulltext_chars] + "…（正文已截断）"

        if not link or len(content or "") < 100:
            continue

        if link:
            _state.mark_seen(st, "seenArticles", link)

        new_items.append(RawItem(
            source_name=source_name,
            source_type="rss",
            title=title,
            content=content or title,
            link=link,
            published=published,
        ))

    _state.save(st)
    return new_items
