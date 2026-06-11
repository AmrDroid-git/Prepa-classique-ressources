import re
import argparse
from pathlib import Path


DRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")
URL_RE = re.compile(r"https?://[^\s\"'<>]+")


def clean_url(url):
    return url.strip().rstrip(".,;)")


def valid_id(value):
    return bool(value and DRIVE_ID_RE.fullmatch(value))


def extract_file_id(url):
    m = re.search(r"/file/d/([^/?#\s]+)", url)
    return m.group(1) if m and valid_id(m.group(1)) else None


def extract_folder_id(url):
    m = re.search(r"/folders/([^?#\s]+)", url)
    if not m:
        return None

    parts = [p for p in m.group(1).split("/") if valid_id(p)]
    return parts[-1] if parts else None


def folder_url(folder_id):
    return f"https://drive.google.com/drive/folders/{folder_id}"


def file_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"


def read_urls(input_file):
    text = Path(input_file).read_text(encoding="utf-8", errors="ignore")
    return [clean_url(u) for u in URL_RE.findall(text)]


def split_drive_links(urls):
    folders = {}
    files = {}

    for url in urls:
        folder_id = extract_folder_id(url)
        file_id = extract_file_id(url)

        if folder_id:
            folders[folder_id] = folder_url(folder_id)
        elif file_id:
            files[file_id] = file_url(file_id)

    return list(folders.values()), list(files.values())


def write_lines(path, lines):
    Path(path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_txt")
    parser.add_argument("--folders-output", default="folders.txt")
    parser.add_argument("--files-output", default="files.txt")
    args = parser.parse_args()

    urls = read_urls(args.input_txt)
    folders, files = split_drive_links(urls)

    write_lines(args.folders_output, folders)
    write_lines(args.files_output, files)

    print(f"Total urls found: {len(urls)}")
    print(f"Unique folder links: {len(folders)} -> {args.folders_output}")
    print(f"Unique file links: {len(files)} -> {args.files_output}")


if __name__ == "__main__":
    main()