import os
import re
import json
import asyncio
import argparse
import requests
from collections import defaultdict
from dotenv import load_dotenv
from playwright.async_api import async_playwright


DEFAULT_URL = "********"
DEFAULT_MAX_DEPTH = 2
DEFAULT_DEEP_ITEM_LIMIT = 20


BAD_NAMES = {
    "تسجيل الدخول",
    "sign in",
    "connexion",
    "error 400",
    "bad request",
    "google drive",
    "drive",
    "name",
    "owner",
    "last modified",
    "file size",
    "more actions",
    "download",
    "preview",
    "open",
    "shared with me",
    "my drive",
    "storage",
    "computers",
    "recent",
    "starred",
    "trash",
    "spam",
    "title",
}


def extract_folder_ids(url):
    ids = []

    for match in re.finditer(r"/folders/([^?#]+)", url):
        segment = match.group(1)

        for part in segment.split("/"):
            part = part.strip()

            if valid_drive_id(part):
                ids.append(part)

    for match in re.finditer(r"[?&]id=([^&#]+)", url):
        folder_id = match.group(1).strip()

        if valid_drive_id(folder_id):
            ids.append(folder_id)

    return ids


def extract_folder_id(url):
    ids = extract_folder_ids(url)
    return ids[-1] if ids else None

def extract_file_id(url):
    m = re.search(r"/file/d/([^/?#&]+)", url)
    return m.group(1) if m else None


def valid_drive_id(value):
    return bool(value and re.fullmatch(r"[A-Za-z0-9_-]{20,}", value))


def desktop_folder_url(folder_id):
    return f"https://drive.google.com/drive/folders/{folder_id}"


def mobile_folder_url(folder_id):
    return f"https://drive.google.com/drive/mobile/folders/{folder_id}"


def embedded_folder_url(folder_id):
    return f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"


def file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\u202a", "").replace("\u202c", "").replace("\u200f", "")
    text = text.replace("\u200e", "").replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" - Google Drive", "")
    return text.strip()


def is_bad_name(name):
    name = clean_text(name)
    low = name.lower()

    if not low or len(low) < 2:
        return True

    if valid_drive_id(name):
        return True

    for bad in BAD_NAMES:
        if bad in low:
            return True

    if "!!1" in low:
        return True

    return False


def best_name_from_text(text):
    text = clean_text(text)

    if not text:
        return ""

    parts = re.split(r"[\n\r\t|•]+", text)
    parts = [clean_text(p) for p in parts]
    parts = [p for p in parts if p and not is_bad_name(p)]

    if not parts:
        return ""

    parts.sort(key=lambda x: (len(x) > 120, len(x)))
    return parts[0][:150]


def load_cookies_from_txt(path):
    cookies = []

    if not path:
        return cookies

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")

            if len(parts) != 7:
                continue

            domain, include_subdomains, cookie_path, secure, expiry, name, value = parts

            if "google" not in domain:
                continue

            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": cookie_path or "/",
                "secure": secure.upper() == "TRUE",
                "httpOnly": False,
            }

            try:
                expiry = int(expiry)
                if expiry > 0:
                    cookie["expires"] = expiry
            except Exception:
                pass

            cookies.append(cookie)

    return cookies


async def wait_drive(page):
    await page.wait_for_timeout(5000)

    for _ in range(5):
        await page.mouse.wheel(0, 2500)
        await page.wait_for_timeout(700)


async def extract_page_title(page, fallback):
    title = clean_text(await page.title())

    candidates = await page.evaluate(
        """
        () => {
            const values = [];

            for (const el of document.querySelectorAll('h1, [role="heading"], [aria-label], [title]')) {
                const txt = el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '';
                if (txt && txt.length < 120) {
                    values.push(txt);
                }
            }

            return values;
        }
        """
    )

    candidates = [clean_text(x) for x in candidates]
    candidates.append(title)

    for c in candidates:
        if c and not is_bad_name(c) and c.lower() not in {"folder", "title"}:
            return c

    return fallback


async def extract_items_from_links(page):
    data = await page.evaluate(
        """
        () => {
            const results = [];

            for (const a of document.querySelectorAll("a[href]")) {
                const href = a.href;
                const txt = [
                    a.innerText,
                    a.getAttribute("aria-label"),
                    a.getAttribute("title"),
                    a.closest('[role="row"]')?.innerText,
                    a.closest('[role="listitem"]')?.innerText
                ].filter(Boolean).join("\\n");

                results.push({ href, text: txt });
            }

            return results;
        }
        """
    )

    folders = {}
    files = {}

    for item in data:
        href = item.get("href", "")
        text = item.get("text", "")
        name = best_name_from_text(text)

        folder_id = extract_folder_id(href)
        file_id = extract_file_id(href)

        if folder_id and valid_drive_id(folder_id) and not is_bad_name(name):
            folders[folder_id] = {
                "id": folder_id,
                "name": name,
                "url": desktop_folder_url(folder_id)
            }

        if file_id and valid_drive_id(file_id) and not is_bad_name(name):
            files[file_id] = {
                "id": file_id,
                "name": name,
                "url": href
            }

    return folders, files


async def extract_items_from_data_id(page):
    data = await page.evaluate(
        """
        () => {
            const results = [];

            function allText(el) {
                const values = [
                    el.innerText,
                    el.getAttribute("aria-label"),
                    el.getAttribute("title")
                ];

                for (const child of el.querySelectorAll("[aria-label], [title]")) {
                    values.push(child.getAttribute("aria-label"));
                    values.push(child.getAttribute("title"));
                    values.push(child.innerText);
                }

                return values.filter(Boolean).join("\\n");
            }

            for (const el of document.querySelectorAll("[data-id]")) {
                const id = el.getAttribute("data-id");
                const text = allText(el);
                const html = el.outerHTML.slice(0, 3000);

                results.push({ id, text, html });
            }

            return results;
        }
        """
    )

    folders = {}
    files = {}

    for item in data:
        item_id = item.get("id", "")

        if not valid_drive_id(item_id):
            continue

        text = item.get("text", "")
        html = item.get("html", "")
        name = best_name_from_text(text)

        if is_bad_name(name):
            continue

        low = (text + " " + html).lower()

        is_folder = (
            "folder" in low
            or "dossier" in low
            or "مجلد" in low
            or "/drive/folders/" in low
            or "application/vnd.google-apps.folder" in low
        )

        is_file = (
            "/file/d/" in low
            or ".pdf" in low
            or ".doc" in low
            or ".docx" in low
            or ".ppt" in low
            or ".pptx" in low
            or ".zip" in low
            or ".rar" in low
            or "application/pdf" in low
        )

        if is_folder:
            folders[item_id] = {
                "id": item_id,
                "name": name,
                "url": desktop_folder_url(item_id)
            }
        elif is_file:
            files[item_id] = {
                "id": item_id,
                "name": name,
                "url": file_url(item_id)
            }
        else:
            files[item_id] = {
                "id": item_id,
                "name": name,
                "url": file_url(item_id)
            }

    return folders, files


async def scrape_variant(context, url, fallback_name):
    page = await context.new_page()

    try:
        print(f"  opening: {url}")

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await wait_drive(page)

        title = await extract_page_title(page, fallback_name)

        link_folders, link_files = await extract_items_from_links(page)
        data_folders, data_files = await extract_items_from_data_id(page)

        folders = {}
        files = {}

        folders.update(link_folders)
        folders.update(data_folders)

        files.update(link_files)
        files.update(data_files)

        print(f"    found: {len(folders)} folders, {len(files)} files")

        return {
            "title": title,
            "folders": folders,
            "files": files
        }

    finally:
        await page.close()


async def scrape_folder(context, folder_id, fallback_name):
    variants = [
        embedded_folder_url(folder_id),
        mobile_folder_url(folder_id),
        desktop_folder_url(folder_id),
    ]

    best = {
        "title": fallback_name,
        "folders": {},
        "files": {}
    }

    for url in variants:
        try:
            result = await scrape_variant(context, url, fallback_name)

            result["folders"].pop(folder_id, None)

            current_score = len(result["folders"]) + len(result["files"])
            best_score = len(best["folders"]) + len(best["files"])

            if current_score > best_score:
                best = result

            if current_score > 0:
                break

        except Exception as e:
            print(f"    failed: {e}")

    title = clean_text(best["title"])

    if is_bad_name(title):
        title = fallback_name

    return {
        "folder_id": folder_id,
        "folder_name": title,
        "folders": list(best["folders"].values()),
        "files": list(best["files"].values())
    }


def should_limit_item(item_depth):
    return item_depth >= 2



async def crawl_drive_with_context(context, root_url, max_depth, deep_item_limit):
    root_id = extract_folder_id(root_url)

    if not root_id:
        raise ValueError("Invalid Google Drive folder URL")

    queue = [(root_id, 0, "Root folder", None)]
    visited = set()
    collected = []
    seen_items = set()

    deep_count = 0
    deep_limit_reached = False

    while queue:
        folder_id, depth, fallback_name, parent_name = queue.pop(0)

        if folder_id in visited:
            continue

        if depth > max_depth:
            continue

        if deep_limit_reached and depth >= 2:
            continue

        visited.add(folder_id)

        print(f"\nVisiting depth {depth}: {folder_id}")

        folder_data = await scrape_folder(context, folder_id, fallback_name)
        folder_name = folder_data["folder_name"]

        print(f"  selected folder name: {folder_name}")
        print(f"  selected content: {len(folder_data['folders'])} folders, {len(folder_data['files'])} files")

        folder_key = ("folder", depth, folder_id)

        if folder_key not in seen_items:
            seen_items.add(folder_key)
            collected.append({
                "type": "folder",
                "id": folder_id,
                "depth": depth,
                "name": folder_name,
                "url": desktop_folder_url(folder_id),
                "parent": parent_name
            })

        children = []

        for file in folder_data["files"]:
            children.append({
                "type": "file",
                "id": file["id"],
                "depth": depth + 1,
                "name": file["name"],
                "url": file["url"],
                "parent": folder_name
            })

        for subfolder in folder_data["folders"]:
            children.append({
                "type": "folder",
                "id": subfolder["id"],
                "depth": depth + 1,
                "name": subfolder["name"],
                "url": subfolder["url"],
                "parent": folder_name
            })

        for child in children:
            item_depth = child["depth"]

            if item_depth > max_depth:
                continue

            if should_limit_item(item_depth):
                if deep_count >= deep_item_limit:
                    deep_limit_reached = True
                    break

                deep_count += 1

            item_key = (child["type"], item_depth, child["id"])

            if item_key not in seen_items:
                seen_items.add(item_key)
                collected.append({
                    "type": child["type"],
                    "id": child["id"],
                    "depth": item_depth,
                    "name": child["name"],
                    "url": child["url"],
                    "parent": child["parent"]
                })

            if child["type"] == "folder" and item_depth < max_depth and not deep_limit_reached:
                queue.append((child["id"], item_depth, child["name"], folder_name))

        if deep_limit_reached:
            print(f"\nDeep collection limit reached: {deep_item_limit} items from depth 2 or deeper.")
            print("Depth 1 was collected completely. Deeper crawling has stopped.")

    return collected


async def crawl_drive(root_url, max_depth, deep_item_limit, cookies_path=None, headless=False):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US"
        )

        cookies = load_cookies_from_txt(cookies_path)

        if cookies:
            await context.add_cookies(cookies)
            print(f"Loaded {len(cookies)} Google cookies.")
        else:
            print("No cookies loaded.")

        try:
            return await crawl_drive_with_context(context, root_url, max_depth, deep_item_limit)
        finally:
            await browser.close()


def compact_list_for_console(items):
    lines = []

    for item in items:
        indent = "  " * item["depth"]
        lines.append(f'{indent}{item["type"]}: {item["name"]}')

    return "\n".join(lines)


def build_llm_content(items):
    root = next((item for item in items if item["depth"] == 0), None)
    depth1 = [item for item in items if item["depth"] == 1]
    depth2 = [item for item in items if item["depth"] == 2]

    lines = []

    lines.append("ROOT FOLDER:")
    if root:
        lines.append(f'- [folder] {root["name"]}')
    else:
        lines.append("- Unknown root folder")

    lines.append("")
    lines.append("DEPTH 1 ITEMS DIRECTLY INSIDE THE ROOT FOLDER:")
    if depth1:
        for item in depth1:
            lines.append(f'- [{item["type"]}] {item["name"]}')
    else:
        lines.append("- No depth 1 items found")

    lines.append("")
    lines.append("DEPTH 2 ITEMS FOUND INSIDE DEPTH 1 FOLDERS:")
    if depth2:
        grouped = defaultdict(list)

        for item in depth2:
            parent = item.get("parent") or "Unknown parent"
            grouped[parent].append(item)

        for parent, children in grouped.items():
            lines.append(f"Parent folder: {parent}")

            for child in children:
                lines.append(f'  - [{child["type"]}] {child["name"]}')
    else:
        lines.append("- No depth 2 items found")

    return "\n".join(lines)


def build_llm_prompt(items):
    content = build_llm_content(items)

    return f"""
You are helping build a static website of resources for prepa MP / CPGE students.

You will receive the crawled structure of one Google Drive folder.

The structure is separated by depth:
- ROOT FOLDER: the main Drive folder name.
- DEPTH 1 ITEMS: direct files/folders inside the root folder. These are fully collected.
- DEPTH 2 ITEMS: a limited sample of files/folders found inside depth 1 folders.

Your task:
Predict a good short name and a short useful description for this Google Drive resource.

Rules:
- Use only the folder and file names provided.
- Do not invent resources that are not suggested by the names.
- Prefer clear names useful for prepa MP / CPGE students.
- If the content is mainly Informatique, say that.
- If it is mixed, mention the main visible subjects.
- Return only valid JSON.
- Do not add markdown.
- Do not add explanations.
- Avoid generic names like "Prépa MP / CPGE Resources".
- The predicted name must mention the main subject if it is clear, for example Informatique, Mathématiques, Physique, Chimie, Concours, or Mixed.

Required JSON format:
{{
  "predicted_name": "...",
  "predicted_description": "..."
}}

Crawled Drive structure:
{content}
""".strip()


def extract_json(text):
    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}", text, re.DOTALL)

    if not m:
        raise ValueError("No JSON found in LLM response")

    return json.loads(m.group(0))


def ask_openrouter(collected_items):
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing in .env")

    prompt = build_llm_prompt(collected_items)

    print("\nPrompt sent to LLM:\n")
    print(prompt)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return only valid JSON. No markdown. No explanation."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Prepa MP Drive Classifier"
        },
        json=payload,
        timeout=60
    )

    response.raise_for_status()

    raw_content = response.json()["choices"][0]["message"]["content"]

    print("\nRaw LLM output:\n")
    print(raw_content)

    return extract_json(raw_content)




def load_drive_links(path):
    links = []
    seen = set()

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line_number, line in enumerate(f, start=1):
            urls = re.findall(r"https?://[^\s'\"<>]+", line)

            for raw_url in urls:
                url = raw_url.strip().rstrip(",.;)\"]")
                folder_id = extract_folder_id(url)

                if not folder_id:
                    print(f"Skipping non-folder link at line {line_number}: {url}")
                    continue

                normalized_url = desktop_folder_url(folder_id)

                if normalized_url in seen:
                    print(f"Skipping duplicate folder at line {line_number}: {normalized_url}")
                    continue

                seen.add(normalized_url)
                links.append({
                    "input_url": url,
                    "folder_id": folder_id,
                    "normalized_url": normalized_url
                })

    return links


def ensure_json_array_file(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write("[\n]\n")


def json_array_has_records(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        first_char_seen = False

        while True:
            ch = f.read(1)

            if not ch:
                return False

            if ch.isspace():
                continue

            if not first_char_seen:
                if ch != "[":
                    raise ValueError(f"Output file is not a JSON array: {path}")

                first_char_seen = True
                continue

            return ch != "]"


def append_record_to_json_array(path, record):
    ensure_json_array_file(path)
    has_records = json_array_has_records(path)
    encoded = json.dumps(record, ensure_ascii=False, indent=2)

    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell() - 1

        while pos >= 0:
            f.seek(pos)
            ch = f.read(1)

            if ch not in b" \t\r\n":
                break

            pos -= 1

        if pos < 0 or ch != b"]":
            raise ValueError(f"Output file must end with a JSON array closing bracket: {path}")

        insert_pos = pos

        if has_records:
            insert_pos = pos - 1

            while insert_pos >= 0:
                f.seek(insert_pos)
                prev = f.read(1)

                if prev not in b" \t\r\n":
                    break

                insert_pos -= 1

            f.seek(insert_pos + 1)
            f.truncate()
            f.write(b",\n")
        else:
            f.seek(insert_pos)
            f.truncate()
            f.write(b"\n")

        f.write(encoded.encode("utf-8"))
        f.write(b"\n]\n")
        f.flush()
        os.fsync(f.fileno())


def load_processed_links(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return set()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return set()

    processed = set()

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and item.get("drive_link"):
                processed.add(item["drive_link"])

    return processed


def build_output_record(drive_link, llm_result):
    return {
        "drive_link": drive_link,
        "predicted_name": llm_result.get("predicted_name", ""),
        "predicted_description": llm_result.get("predicted_description", "")
    }


def build_error_record(drive_link, error):
    return {
        "drive_link": drive_link,
        "predicted_name": "",
        "predicted_description": "",
        "error": str(error)
    }


async def process_all_links(args):
    drive_links = load_drive_links(args.links_txt)

    if not drive_links:
        print("No Google Drive folder links found in the txt file.")
        return

    ensure_json_array_file(args.output)
    processed_links = load_processed_links(args.output) if args.skip_existing else set()

    print(f"Found {len(drive_links)} unique Google Drive folder links.")
    print(f"Output JSON file: {args.output}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=args.headless)
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US"
        )

        cookies = load_cookies_from_txt(args.cookies)

        if cookies:
            await context.add_cookies(cookies)
            print(f"Loaded {len(cookies)} Google cookies.")
        else:
            print("No cookies loaded.")

        try:
            for index, link_info in enumerate(drive_links, start=1):
                input_url = link_info["input_url"]
                normalized_url = link_info["normalized_url"]

                if args.skip_existing and input_url in processed_links:
                    print(f"\n[{index}/{len(drive_links)}] Already processed, skipping: {input_url}")
                    continue

                print(f"\n[{index}/{len(drive_links)}] Processing: {input_url}")

                try:
                    collected_items = await crawl_drive_with_context(
                        context=context,
                        root_url=normalized_url,
                        max_depth=args.depth,
                        deep_item_limit=args.deep_limit
                    )

                    print("\nCollected names:\n")
                    print(compact_list_for_console(collected_items))

                    real_items = [x for x in collected_items if x["depth"] > 0]

                    if not real_items:
                        raise RuntimeError("No real files/subfolders were collected")

                    llm_result = ask_openrouter(collected_items)
                    record = build_output_record(input_url, llm_result)
                    append_record_to_json_array(args.output, record)
                    print(f"Saved result directly to {args.output}")

                except Exception as e:
                    print(f"ERROR for {input_url}: {e}")

                    if args.write_errors:
                        append_record_to_json_array(args.output, build_error_record(input_url, e))
                        print(f"Saved error record to {args.output}")

                if args.pause > 0:
                    await asyncio.sleep(args.pause)

        finally:
            await browser.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("links_txt")
    parser.add_argument("--cookies", default=None)
    parser.add_argument("--output", default="drive_predictions.json")
    parser.add_argument("--depth", type=int, default=DEFAULT_MAX_DEPTH)
    parser.add_argument("--deep-limit", type=int, default=DEFAULT_DEEP_ITEM_LIMIT)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--pause", type=float, default=0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--write-errors", action="store_true")
    args = parser.parse_args()

    await process_all_links(args)


if __name__ == "__main__":
    asyncio.run(main())
