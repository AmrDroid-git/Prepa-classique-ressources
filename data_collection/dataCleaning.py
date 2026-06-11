import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qs


URL_REGEX = re.compile(r"https?://[^\s<>'\"]+")


def extract_urls_from_line(line):
    return URL_REGEX.findall(line)


def remove_trailing_junk(url):
    return url.strip().rstrip(".,;:)]}…")


def unwrap_facebook_redirect(url):
    parsed = urlsplit(url)

    if parsed.netloc in {"lm.facebook.com", "l.facebook.com"} and parsed.path == "/l.php":
        params = parse_qs(parsed.query)
        if "u" in params:
            return params["u"][0]

    return url


def remove_query_params(url):
    parsed = urlsplit(url)
    return urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        "",              # remove everything after ?
        parsed.fragment  # keep # part, useful for mega.nz links
    ))


def clean_url(url):
    url = remove_trailing_junk(url)
    url = unwrap_facebook_redirect(url)
    url = remove_trailing_junk(url)
    url = remove_query_params(url)
    return url


def read_links(input_file):
    links = []

    with open(input_file, "r", encoding="utf-8") as file:
        for line in file:
            urls = extract_urls_from_line(line)

            for url in urls:
                cleaned = clean_url(url)
                if cleaned:
                    links.append(cleaned)

    return links


def remove_duplicates_keep_order(links):
    seen = set()
    result = []

    for link in links:
        if link not in seen:
            seen.add(link)
            result.append(link)

    return result


def write_links(output_file, links):
    with open(output_file, "w", encoding="utf-8") as file:
        for link in links:
            file.write(link + "\n")


def default_output_name(input_file):
    path = Path(input_file)
    return str(path.with_name(path.stem + "_clean_links.txt"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file")
    parser.add_argument("-o", "--output", default=None)
    parser.add_argument("--keep-duplicates", action="store_true")

    args = parser.parse_args()

    output_file = args.output or default_output_name(args.input_file)

    links = read_links(args.input_file)

    if not args.keep_duplicates:
        links = remove_duplicates_keep_order(links)

    write_links(output_file, links)

    print(f"Done. Saved {len(links)} links to: {output_file}")


if __name__ == "__main__":
    main()