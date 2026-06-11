import os
import re
import json
import asyncio
import argparse
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv
from playwright.async_api import async_playwright


DEFAULT_URL = "https://drive.google.com/drive/mobile/folders/1VFsQVw8vAxJt26HUtrJDIdwP7V75P8_K"


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
}


def extract_folder_id(url):
    m = re.search(r"/folders/([^/?#&]+)", url)
    return m.group(1) if m else None


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

    h1 = await page.evaluate(
        """
        () => {
            const candidates = [];

            for (const el of document.querySelectorAll('h1, [role="heading"], [aria-label], [title]')) {
                const txt = el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '';
                if (txt && txt.length < 120) candidates.push(txt);
            }

            return candidates;
        }
        """
    )

    candidates = [clean_text(x) for x in h1]
    candidates.append(title)

    for c in candidates:
        if c and not is_bad_name(c) and c.lower() != "folder":
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

                results.push({
                    id,
                    text,
                    html
                });
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
            or ".ppt" in low
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
                "url": f"https://drive.google.com/file/d/{item_id}/view"
            }
        else:
            files[item_id] = {
                "id": item_id,
                "name": name,
                "url": f"https://drive.google.com/file/d/{item_id}/view"
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


async def crawl_drive(root_url, max_depth, cookies_path=None, headless=False):
    root_id = extract_folder_id(root_url)

    if not root_id:
        raise ValueError("Invalid Google Drive folder URL")

    queue = [(root_id, 0, "Root folder")]
    visited = set()
    collected = []

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

        while queue:
            folder_id, depth, fallback_name = queue.pop(0)

            if folder_id in visited:
                continue

            if depth > max_depth:
                continue

            visited.add(folder_id)

            print(f"\nVisiting depth {depth}: {folder_id}")

            folder_data = await scrape_folder(context, folder_id, fallback_name)
            folder_name = folder_data["folder_name"]

            print(f"  selected folder name: {folder_name}")
            print(f"  selected content: {len(folder_data['folders'])} folders, {len(folder_data['files'])} files")

            collected.append({
                "type": "folder",
                "depth": depth,
                "name": folder_name,
                "url": desktop_folder_url(folder_id),
                "parent": None
            })

            for file in folder_data["files"]:
                collected.append({
                    "type": "file",
                    "depth": depth + 1,
                    "name": file["name"],
                    "url": file["url"],
                    "parent": folder_name
                })

            for subfolder in folder_data["folders"]:
                collected.append({
                    "type": "folder",
                    "depth": depth + 1,
                    "name": subfolder["name"],
                    "url": subfolder["url"],
                    "parent": folder_name
                })

                if depth + 1 <= max_depth:
                    queue.append((subfolder["id"], depth + 1, subfolder["name"]))

        await browser.close()

    unique = []
    seen = set()

    for item in collected:
        key = (item["type"], item["depth"], item["name"], item["url"])

        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def compact_list_for_llm(items):
    lines = []

    for item in items:
        indent = "  " * item["depth"]
        lines.append(f'{indent}- [{item["type"]}] {item["name"]}')

    return "\n".join(lines)


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

    folder_content = compact_list_for_llm(collected_items)

    prompt = f"""
You are helping build a static website of resources for prepa MP / CPGE students.

From this crawled Google Drive structure, predict a good name and a short useful description for the drive.

Return only valid JSON with exactly these keys:
{{
  "predicted_name": "...",
  "predicted_description": "..."
}}

Do not invent details. Use only the folder and file names below.

Crawled content:
{folder_content}
""".strip()

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

    content = response.json()["choices"][0]["message"]["content"]
    return extract_json(content)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cookies", nargs="?", default=None)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    collected_items = await crawl_drive(
        root_url=args.url,
        max_depth=args.depth,
        cookies_path=args.cookies,
        headless=args.headless
    )

    print("\nCollected names:\n")
    print("\n".join([
        f'{"  " * item["depth"]}{item["type"]}: {item["name"]}'
        for item in collected_items
    ]))

    real_items = [x for x in collected_items if x["depth"] > 0]

    if not real_items:
        print("\nNo real files/subfolders were collected.")
        print("This means the page content is still not accessible or Google Drive changed the DOM.")
        print("Try running without --headless and check what the opened browser actually displays.")
        return

    if args.no_llm:
        return

    print("\nLLM result:\n")
    result = ask_openrouter(collected_items)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())