import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def read_links(input_file):
    with open(input_file, "r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]


def default_output_names(input_file):
    path = Path(input_file)

    working_file = path.with_name(path.stem + "_working_links.txt")
    bad_file = path.with_name(path.stem + "_bad_links.txt")

    return str(working_file), str(bad_file)


def response_has_content(response):
    try:
        for chunk in response.iter_content(chunk_size=1024):
            if chunk:
                return True
        return False
    except requests.RequestException:
        return False


def check_link(url, timeout):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*"
    }

    try:
        response = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers=headers,
            stream=True
        )

        status_code = response.status_code
        has_content = response_has_content(response)
        response.close()

        if status_code == 200 and has_content:
            return {
                "url": url,
                "status": status_code,
                "working": True,
                "reason": "OK"
            }

        if status_code == 200 and not has_content:
            return {
                "url": url,
                "status": status_code,
                "working": False,
                "reason": "200 but empty content"
            }

        return {
            "url": url,
            "status": status_code,
            "working": False,
            "reason": f"HTTP {status_code}"
        }

    except requests.RequestException as error:
        return {
            "url": url,
            "status": None,
            "working": False,
            "reason": f"ERROR: {error}"
        }


def save_working_links(output_file, working_links):
    with open(output_file, "w", encoding="utf-8") as file:
        for link in working_links:
            file.write(link + "\n")


def save_bad_links(output_file, bad_links):
    with open(output_file, "w", encoding="utf-8") as file:
        for item in bad_links:
            file.write(f"{item['url']} | {item['reason']}\n")


def scan_links(input_file, working_output, bad_output, timeout, workers):
    links = read_links(input_file)

    working_links = []
    bad_links = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(check_link, link, timeout)
            for link in links
        ]

        for future in as_completed(futures):
            result = future.result()

            if result["working"]:
                print(f"[OK] {result['url']}")
                working_links.append(result["url"])
            else:
                print(f"[BAD] {result['reason']} -> {result['url']}")
                bad_links.append(result)

    save_working_links(working_output, working_links)
    save_bad_links(bad_output, bad_links)

    print()
    print("Done.")
    print(f"Checked links: {len(links)}")
    print(f"Working links: {len(working_links)}")
    print(f"Bad links: {len(bad_links)}")
    print(f"Working links saved to: {working_output}")
    print(f"Bad links saved to: {bad_output}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("input_file")
    parser.add_argument("--working-output", default=None)
    parser.add_argument("--bad-output", default=None)
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--workers", type=int, default=10)

    args = parser.parse_args()

    default_working, default_bad = default_output_names(args.input_file)

    working_output = args.working_output or default_working
    bad_output = args.bad_output or default_bad

    scan_links(
        input_file=args.input_file,
        working_output=working_output,
        bad_output=bad_output,
        timeout=args.timeout,
        workers=args.workers
    )


if __name__ == "__main__":
    main()