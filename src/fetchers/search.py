"""Bounded domain-scoped web search; snippets are never treated as article bodies."""
import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
import json
from urllib.request import Request, urlopen
from .base import RawItem
from .rss import _fetch_fulltext
from src import state

def fetch_search(config, check_only=False):
    name = config["name"]
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        return [RawItem(source_name=name, source_type="rss", title="[搜索未配置]", content="缺少TAVILY_API_KEY，未执行主动搜索；不是无新闻", link=None)]
    if check_only:
        return [RawItem(source_name=name, source_type="rss", title="[搜索检查]", content="已配置密钥；免费检查不调用搜索API", link=None)]
    domains = config["domains"]
    try:
        payload = {"query": config["query"], "include_domains": domains,
                   "time_range": config.get("time_range", "week"),
                   "search_depth": "basic", "max_results": 3,
                   "include_answer": False, "include_raw_content": "text"}
        request = Request("https://api.tavily.com/search",
            data=json.dumps(payload).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
        with urlopen(request, timeout=40) as response:
            results = json.load(response).get("results", [])
    except Exception:
        return [RawItem(source_name=name, source_type="rss", title="[搜索失败]", content="搜索服务请求失败；详查服务账户及额度，不代表没有更新", link=None)]
    print(name, "搜索返回", len(results), "条结果")
    items = []
    st = state.load()
    for result in results:
        url = result.get("url", "")
        host = (urlparse(url).hostname or "").lower()
        if not any(host == d or host.endswith("." + d) for d in domains):
            continue
        if state.is_seen(st, "seenArticles", url):
            continue
        body = _fetch_fulltext(url, max_chars=16000)
        if not body or len(body) < 1000:
            raw = result.get("raw_content")
            if isinstance(raw, str) and len(raw.strip()) >= 1000:
                body = raw[:16000] + "\n[搜索服务提取正文；可能不完整，不能视作独立核验]"
        if not body or len(body) < 1000:
            print(name, "原文不足，剔除", host)
            continue
        # Search dates are not independently verified publication dates.
        published = result.get("published_date", "")
        items.append(RawItem(source_name=name, source_type="rss",
            title=result.get("title", "未命名"),
            content="[主动搜索所得网页正文；日期未经独立核实；可能截断]\n" + body,
            link=url, published=published))
        state.mark_seen(st, "seenArticles", url)
        if len(items) >= 2:
            break
    print(name, "取得正文", len(items), "篇")
    state.save(st)
    if not items:
        return [RawItem(source_name=name, source_type="rss", title="[搜索无可用正文]", content="本次搜索没有取得合格正文，不代表该领域没有重要内容", link=None)]
    return items
