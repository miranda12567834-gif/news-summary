"""Select diverse, dated evidence before the single writing call."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit


def publication_time(value):
    try:
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            stamp = parsedate_to_datetime(value)
        return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc).timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        return 0


def shortlist(items, sources, now=None):
    now = now or datetime.now(timezone.utc).timestamp()
    groups = defaultdict(list)
    counts = Counter()
    selected = []
    urls, titles = set(), set()
    paper_sources = {s["name"] for s in sources if s["type"] == "papers"}
    for item in items:
        stamp = publication_time(item.published)
        paper = item.source_name in paper_sources
        if not item.link or not 0 <= now - stamp <= (30 if paper else 7) * 86400:
            continue
        groups[item.source_name].append((stamp, item))
    for group in groups.values():
        group.sort(key=lambda pair: pair[0], reverse=True)
    for rank in range(max(map(len, groups.values()), default=0)):
        for group in groups.values():
            if rank >= len(group):
                continue
            _, item = group[rank]
            paper = item.source_name in paper_sources
            host = item.source_name if paper else urlsplit(item.link).hostname
            title = " ".join(item.title.casefold().split())
            if counts[paper] >= (4 if paper else 9) or counts[(paper, host)] >= 2:
                continue
            if title in titles or item.link in urls:
                continue
            urls.add(item.link)
            titles.add(title)
            counts[paper] += 1
            counts[(paper, host)] += 1
            selected.append(item)
    return selected
