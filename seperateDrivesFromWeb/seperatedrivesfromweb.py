import argparse
import re
from pathlib import Path
from urllib.parse import urlparse


URL_RE = re.compile(r"https?://[^\s]+")


def extract_links(line):
    return URL_RE.findall(line)


def clean_link(link):
    return link.strip().rstrip(".,);]\"'")


def is_google_drive(link):
    parsed = urlparse(link)
    return parsed.netloc.lower() == "drive.google.com"


def unique_keep_order(links):
    seen = set()
    result = []

    for link in links:
        if link not in seen:
            seen.add(link)
            result.append(link)

    return result


def split_links(input_file):
    google_drives = []
    other_websites = []

    with open(input_file, "r", encoding="utf-8") as file:
        for line in file:
            links = extract_links(line)

            for link in links:
                link = clean_link(link)

                if is_google_drive(link):
                    google_drives.append(link)
                else:
                    other_websites.append(link)

    return unique_keep_order(google_drives), unique_keep_order(other_websites)


def save_links(filename, links):
    with open(filename, "w", encoding="utf-8") as file:
        for link in links:
            file.write(link + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Input file containing links")
    args = parser.parse_args()

    google_drives, other_websites = split_links(args.input_file)

    save_links("googledrives.txt", google_drives)
    save_links("otherwebsites.txt", other_websites)

    print(f"Google Drive links: {len(google_drives)}")
    print(f"Other website links: {len(other_websites)}")
    print("Created: googledrives.txt")
    print("Created: otherwebsites.txt")


if __name__ == "__main__":
    main()