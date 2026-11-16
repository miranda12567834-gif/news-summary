"""Discover recent papers and extract evidence from open JATS full text."""
import json
import logging
from datetime import date, timedelta
from urllib.parse import urlencode
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from .base import RawItem

API = "https://www.ebi.ac.uk/europepmc/webservices/rest"


def evidence(xml):
    root = ET.fromstring(xml)
    body = root.find(".//body")
    if body is None:
        return ""
    sections = []
    for sec in body.iter("sec"):
        title = sec.find("title")
        heading = " ".join("".join(title.itertext()).split()) if title is not None else ""
        paragraphs = [" ".join("".join(p.itertext()).split()) for p in sec.findall("p")]
        if not paragraphs and heading.lower() in ("methods", "materials and methods", "results", "findings"):
            paragraphs = [" ".join(p.itertext()) for p in sec.iter("p")]
        if heading and paragraphs:
            sections.append((heading, " ".join(paragraphs)))
    headings = " ".join(h.lower() for h, _ in sections)
    if not any(k in headings for k in ("method", "materials", "experimental")):
        return ""
    if not any(k in headings for k in ("result", "finding")):
        return ""
    excerpts = []
    for keywords, limit in [(("result", "finding"), 3), (("method", "materials", "experimental"), 2),
                            (("discussion", "limitation", "conclusion"), 2), (("introduction",), 1)]:
        matches = [(h, t) for h, t in sections if any(k in h.lower() for k in keywords)]
        excerpts.extend(h + "\n" + t[:2200] for h, t in matches[:limit])
    abstract = root.find(".//article-meta/abstract")
    if abstract is not None:
        excerpts.append("作者摘要（对照结果）\n" + " ".join(abstract.itertext())[:2200])
    return "\n".join(excerpts)


def fetch_papers(config):
    start = date.today() - timedelta(days=30)
    query = f'ISSN:{config["issn"]} AND DOI:10.* AND OPEN_ACCESS:Y AND FIRST_PDATE:[{start} TO {date.today()}]'
    params = urlencode(dict(query=query, format="json", pageSize=12, sort="FIRST_PDATE_D desc", resultType="core"))
    items = []
    try:
        with urlopen(f"{API}/search?{params}", timeout=15) as response:
            records = json.load(response)["resultList"]["result"]
        print(config["name"], "索引返回", len(records), "条")
        for record in records:
            doi, pmc = record.get("doi"), record.get("pmcid")
            if not doi or not pmc or not record.get("firstPublicationDate"):
                print(config["name"], "缺少 DOI、PMC 全文编号或日期", doi)
                continue
            try:
                with urlopen(f"{API}/{pmc}/fullTextXML", timeout=20) as response:
                    content = evidence(response.read(8000000))
            except (OSError, ET.ParseError) as exc:
                print(config["name"], doi, "全文读取失败", type(exc).__name__)
                continue
            if not content:
                print(config["name"], doi, "全文缺可解析的方法或结果分节")
            if content:
                items.append(RawItem(config["name"], "paper", record["title"],
                                     f"开放全文分节摘录（{pmc}）\n" + content,
                                     "https://doi.org/" + doi, record["firstPublicationDate"]))
            if len(items) == 2:
                break
    except (OSError, ValueError, KeyError) as exc:
        logging.warning("%s 检索失败 %s", config["name"], type(exc).__name__)
    print(config["name"], "取得方法和结果摘录", len(items), "篇")
    return items


def journal_html(page):
    sections = []
    for section in page.xpath('//section[h2] | //div[h2 and p]'):
        paragraphs = section.xpath('./p | ./div/p')
        body = " ".join(p.text_content().strip() for p in paragraphs)
        if len(body) >= 250:
            sections.append((section.find("h2").text_content().strip(), body))
    headings = " ".join(h.lower() for h, _ in sections)
    if not any(k in headings for k in ("data", "method", "empirical", "design")):
        return ''
    if not any(k in headings for k in ("results", "findings", "estimates")):
        return ''
    return "\n".join(h + "\n" + b[:1800] for h, b in sections[:10])


def public_versions(doi):
    """Look up deposited full-text copies by exact DOI in Semantic Scholar."""
    from urllib.parse import quote
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/DOI:" + quote(doi, safe="/")
    try:
        with urlopen(endpoint + "?fields=openAccessPdf,externalIds", timeout=10) as response:
            record = json.load(response)
        if (record.get("externalIds") or {}).get("DOI", "").casefold() == doi.casefold():
            url = (record.get("openAccessPdf") or {}).get("url", "")
            if url.startswith("https://"):
                yield url
    except (OSError, ValueError, AttributeError):
        return


def fetch_journal(config):
    """Resolve recent Crossref DOI records and read publisher evidence sections."""
    from urllib.request import Request
    from lxml import html
    from lxml.etree import ParserError

    start = date.today() - timedelta(days=30)
    params = urlencode({"filter": f"from-pub-date:{start},until-pub-date:{date.today()},type:journal-article",
                        "sort": "published", "order": "desc", "rows": 4})
    url = f'https://api.crossref.org/journals/{config["issn"]}/works?{params}'
    items = []
    try:
        with urlopen(url, timeout=15) as response:
            records = json.load(response)["message"]["items"]
        print(config["name"], "索引返回", len(records), "条")
        for record in records:
            parts = record.get("published", {}).get("date-parts", [[]])[0]
            if len(parts) != 3 or not record.get("title"):
                print(config["name"], "缺少完整日期或标题")
                continue
            link = "https://doi.org/" + record["DOI"]
            from itertools import chain
            from io import BytesIO
            import re
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError
            seen = set()
            for address in chain([link], public_versions(record["DOI"])):
                if address in seen:
                    continue
                seen.add(address)
                try:
                    with urlopen(Request(address, headers={"User-Agent": "NewsSummary/1.0"}), timeout=15) as response:
                        data = response.read(8000001)
                    if len(data) > 8000000:
                        continue
                    if data.startswith(b"%PDF"):
                        pdf = PdfReader(BytesIO(data))
                        if len(pdf.pages) > 160:
                            continue
                        pages = [(page.extract_text() or "") for page in pdf.pages]
                        title_words = re.findall(r"\w+", record["title"][0].lower())
                        front = " ".join(re.findall(r"\w+", " ".join(pages[:2]).lower()))
                        if " ".join(title_words) not in front:
                            continue
                        parts_text = re.split(r"(?im)^\s*(?:[IVX\d.]+\s+)?((?:data|methodology|methods|empirical strategy|results|findings|conclusion|discussion|limitations)\b[^\n]{0,55})\n", "\n".join(pages))
                        sections = [(h, t) for h, t in zip(parts_text[1::2], parts_text[2::2]) if len(t.strip()) > 250]
                        headings = " ".join(h.lower() for h, _ in sections)
                        if not re.search(r"data|method|strategy", headings) or not re.search(r"result|finding", headings):
                            continue
                        content = "\n".join(h + "\n" + t[:2000] for h, t in sections[:10])
                    else:
                        content = journal_html(html.fromstring(data))
                    if content:
                        items.append(RawItem(config["name"], "paper", record["title"][0],
                                             "原文分节摘录 " + address + "\n" + content,
                                             link, date(*parts).isoformat()))
                        break
                except (OSError, ValueError, ParserError, PdfReadError) as exc:
                    print(config["name"], link, "全文读取失败", getattr(exc, "code", type(exc).__name__))
            if len(items) >= 2:
                break
    except (OSError, ValueError, KeyError) as exc:
        logging.warning("%s 检索失败 %s", config["name"], type(exc).__name__)
    print(config["name"], "取得方法和结果摘录", len(items), "篇")
    return items
