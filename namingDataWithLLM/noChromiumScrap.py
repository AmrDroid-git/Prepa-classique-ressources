import os
import re
import json
import argparse
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


DEFAULT_URL = "https://drive.google.com/drive/mobile/folders/1VFsQVw8vAxJt26HUtrJDIdwP7V75P8_K"


def extract_folder_id(url):
    m = re.search(r"/folders/([^/?#&]+)", url)
    if m:
        return m.group(1)

    m = re.search(r"[?&]id=([^&#]+)", url)
    if m:
        return m.group(1)

    return None


def extract_file_id(url):
    m = re.search(r"/file/d/([^/?#&]+)", url)
    return m.group(1) if m else None


def embedded_url(folder_id):
    return f"https://drive.google.com/embeddedfolderview?id={folder_id}#list"


def folder_url(folder_id):
    return f"https://drive.google.com/drive/folders/{folder_id}"


def file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"


def clean_text(text):
    if not text:
        return ""

    text = text.replace("\u202a", "").replace("\u202c", "")
    text = text.replace("\u200f", "").replace("\u200e", "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_cookies_from_txt(path):
    cookies = {}

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

            if "google" in domain:
                cookies[name] = value

    return cookies


def fetch_html(session, folder_id):
    url = embedded_url(folder_id)

    r = session.get(url, timeout=30)
    r.raise_for_status()

    return r.text


def extract_items(html):
    soup = BeautifulSoup(html, "html.parser")

    folders = {}
    files = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = clean_text(a.get_text(" ", strip=True))

        if not text:
            text = clean_text(a.get("aria-label", ""))

        folder_id = extract_folder_id(href)
        file_id = extract_file_id(href)

        if folder_id and "folders" in href:
            folders[folder_id] = {
                "id": folder_id,
                "name": text or f"Folder {folder_id}",
                "url": folder_url(folder_id)
            }

        elif file_id:
            files[file_id] = {
                "id": file_id,
                "name": text or f"File {file_id}",
                "url": file_url(file_id)
            }

    raw = html

    folder_matches = re.findall(
        r'https://drive\.google\.com/drive/folders/([A-Za-z0-9_-]+)[^"\']*["\'][^>]*>(.*?)</a>',
        raw,
        flags=re.DOTALL
    )

    for folder_id, name_html in folder_matches:
        name = clean_text(BeautifulSoup(name_html, "html.parser").get_text(" ", strip=True))

        folders[folder_id] = {
            "id": folder_id,
            "name": name or f"Folder {folder_id}",
            "url": folder_url(folder_id)
        }

    file_matches = re.findall(
        r'https://drive\.google\.com/file/d/([A-Za-z0-9_-]+)[^"\']*["\'][^>]*>(.*?)</a>',
        raw,
        flags=re.DOTALL
    )

    for file_id, name_html in file_matches:
        name = clean_text(BeautifulSoup(name_html, "html.parser").get_text(" ", strip=True))

        files[file_id] = {
            "id": file_id,
            "name": name or f"File {file_id}",
            "url": file_url(file_id)
        }

    return list(folders.values()), list(files.values())


def crawl_drive(root_url, cookies_path, max_depth):
    root_id = extract_folder_id(root_url)

    if not root_id:
        raise ValueError("Invalid Google Drive folder URL")

    session = requests.Session()

    session.headers.update({
        "User-Agent": "Mozilla/5.0"
    })

    cookies = load_cookies_from_txt(cookies_path)

    for name, value in cookies.items():
        session.cookies.set(name, value, domain=".google.com")

    print(f"Loaded {len(cookies)} Google cookies.")

    queue = [(root_id, 0, "Root")]
    visited = set()
    collected = []

    while queue:
        folder_id, depth, folder_name = queue.pop(0)

        if folder_id in visited:
            continue

        if depth > max_depth:
            continue

        visited.add(folder_id)

        print(f"\nVisiting depth {depth}: {folder_name}")
        print(f"  {embedded_url(folder_id)}")

        html = fetch_html(session, folder_id)
        folders, files = extract_items(html)

        print(f"  found: {len(folders)} folders, {len(files)} files")

        collected.append({
            "type": "folder",
            "depth": depth,
            "name": folder_name,
            "url": folder_url(folder_id)
        })

        for file in files:
            collected.append({
                "type": "file",
                "depth": depth + 1,
                "name": file["name"],
                "url": file["url"]
            })

        for folder in folders:
            collected.append({
                "type": "folder",
                "depth": depth + 1,
                "name": folder["name"],
                "url": folder["url"]
            })

            if depth + 1 <= max_depth:
                queue.append((folder["id"], depth + 1, folder["name"]))

    return collected


def compact_list_for_llm(items):
    return "\n".join(
        f'{"  " * item["depth"]}- [{item["type"]}] {item["name"]}'
        for item in items
    )


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


def ask_openrouter(items):
    load_dotenv()

    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing in .env")

    content = compact_list_for_llm(items)

    prompt = f"""
You are helping build a static website of resources for prepa MP / CPGE students.

From this crawled Google Drive structure, predict a good name and a short useful description for the drive.

Return only valid JSON with exactly these keys:
{{
  "predicted_name": "...",
  "predicted_description": "..."
}}

Use only the folder and file names below.

Crawled content:
{content}
""".strip()

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Prepa MP Drive Classifier"
        },
        json={
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
        },
        timeout=60
    )

    r.raise_for_status()

    return extract_json(r.json()["choices"][0]["message"]["content"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cookies")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    items = crawl_drive(args.url, args.cookies, args.depth)

    print("\nCollected names:\n")
    print(compact_list_for_llm(items))

    if args.no_llm:
        return

    print("\nLLM result:\n")
    result = ask_openrouter(items)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()