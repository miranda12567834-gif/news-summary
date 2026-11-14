"""Inspect the same candidate pool as production, without writing a digest."""
import os
import tempfile
from collections import Counter
from pathlib import Path

from src import state
from src.editorial import publication_time, shortlist
from src.runner import fetch_all, load_config


def report(config, live_search):
    sources = config["sources"]
    delivered = state.load()
    items = fetch_all(sources, config["max_entries"], config["max_age_days"],
                      check_only=not live_search)
    usable = [i for i in items if i.link and not i.title.startswith("[")
              and not state.is_seen(delivered, "seenArticles", i.link)]
    selected = shortlist(usable, sources)
    lines = ["## 每日兴趣简报 · 检索验收", "",
             "计数从抓取器返回材料开始。可解析日期来自来源元数据，尚未独立核实。",
             "", "| 来源 | 正文候选 | 有日期 | 写作候选 | 抓取提示 |",
             "|---|---:|---:|---:|---|"]
    for source in sources:
        name = source["name"]
        rows = [i for i in usable if i.source_name == name]
        notices = Counter(i.title for i in items if i.source_name == name and
                          (i.title.startswith("[") or i.title == "暂无更新"))
        notes = "、".join(f"{k} × {v}" for k, v in notices.items())
        lines.append(f"| {name} | {len(rows)} | {sum(bool(publication_time(i.published)) for i in rows)} "
                     f"| {sum(i.source_name == name for i in selected)} | {notes} |")
    lines.extend(["", "### 可抽查的候选原文", ""])
    for i in selected:
        title = " ".join(i.title.split()).replace("[", "［").replace("]", "］")
        lines.append(f"- {i.source_name} · {i.published} · [{title}](<{i.link}>)")
    output = "\n".join(lines)
    print(output)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(path, "a", encoding="utf-8") as stream:
            print(output, file=stream)
    if not selected:
        raise RuntimeError("没有任何材料进入写作候选，请检查逐源记录")


def main():
    original = state._STATE_FILE
    with tempfile.TemporaryDirectory() as folder:
        state._STATE_FILE = Path(folder) / "state.json"
        try:
            if original.exists():
                state._STATE_FILE.write_bytes(original.read_bytes())
            report(load_config(), os.environ.get("LIVE_SEARCH") == "1")
        finally:
            state._STATE_FILE = original


if __name__ == "__main__":
    main()
