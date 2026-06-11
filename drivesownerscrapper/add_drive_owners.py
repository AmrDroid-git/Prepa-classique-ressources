import argparse
import json
import re
from collections import Counter
from pathlib import Path


BAD_VALUES = {
    "",
    "details",
    "activity",
    "general access",
    "google drive",
    "drive",
    "loading",
    "owner",
    "owned by",
    "propriétaire",
    "proprietaire",
    "date",
    "modified",
    "date modified",
    "last modified",
    "file size",
    "size",
    "type",
    "name",
    "source",
    "people",
    "shared with me",
    "my drive",
    "sort",
    "me",
    "you",
    "moi",
    "vous",
    "-",
    "—",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def is_bad_owner(value):
    value = normalize(value).strip(" :-–—")
    low = value.lower()

    if low in BAD_VALUES:
        return True

    if len(value) <= 1:
        return True

    if len(value) > 80:
        return True

    if re.search(r"https?://|@|\.com|\.pdf|\.zip|\.rar|\.doc|\.ppt|\.xls", value, re.I):
        return True

    if re.fullmatch(r"\d+(\.\d+)?\s*(b|kb|mb|gb|tb|bytes?)", low):
        return True

    if re.search(r"\b\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", low):
        return True

    if re.search(r"\b\d{4}\b", low) and re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", low):
        return True

    return False


def clean_owner(value):
    value = normalize(value).strip(" :-–—")
    if is_bad_owner(value):
        return None
    return value


def parse_netscape_cookies(path):
    cookies = []

    if not path:
        return cookies

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()

            if not line or line.startswith("# Netscape"):
                continue

            http_only = False

            if line.startswith("#HttpOnly_"):
                http_only = True
                line = line[len("#HttpOnly_"):]

            if line.startswith("#"):
                continue

            parts = line.split("\t")

            if len(parts) != 7:
                parts = re.split(r"\s+", line, maxsplit=6)

            if len(parts) != 7:
                continue

            domain, _, path_, secure, expires, name, value = parts

            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path_ or "/",
                "httpOnly": http_only,
                "secure": secure.upper() == "TRUE",
                "sameSite": "Lax",
            }

            try:
                exp = int(float(expires))
                if exp > 0:
                    cookie["expires"] = exp
            except Exception:
                pass

            cookies.append(cookie)

    return cookies


def wait_drive_loaded(page):
    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass

    try:
        page.wait_for_function(
            """
            () => {
                const t = document.body.innerText || "";
                return t.includes("Owner") || t.includes("Date modified") || t.includes("Propriétaire");
            }
            """,
            timeout=20000,
        )
    except Exception:
        pass

    page.wait_for_timeout(1500)


def force_list_view(page):
    selectors = [
        'button[aria-label*="List layout"]',
        'button[aria-label*="List view"]',
        'button[aria-label*="Switch to list"]',
        'button[aria-label*="List"]',
        'button[aria-label*="liste"]',
        'button[aria-label*="Vue liste"]',
        'button[aria-label*="Affichage liste"]',
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=800)
                page.wait_for_timeout(800)
                return
        except Exception:
            pass


def extract_owner_from_rows(page):
    candidates = page.evaluate(
        """
        () => {
            function norm(s) {
                return (s || "").replace(/\\s+/g, " ").trim();
            }

            function visible(el) {
                const r = el.getBoundingClientRect();
                const st = window.getComputedStyle(el);

                return (
                    r.width > 0 &&
                    r.height > 0 &&
                    st.display !== "none" &&
                    st.visibility !== "hidden" &&
                    Number(st.opacity || "1") > 0
                );
            }

            function isDateText(t) {
                return /^\\d{1,2}\\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\\s+\\d{4}$/i.test(t)
                    || /^\\d{1,2}\\s+(janv|févr|fevr|mars|avr|mai|juin|juil|août|aout|sept|oct|nov|déc|dec)\\.?\\s+\\d{4}$/i.test(t);
            }

            const elements = Array.from(document.querySelectorAll("div, span, a, button"));

            const items = elements
                .filter(visible)
                .map(el => {
                    const r = el.getBoundingClientRect();

                    let text = norm(el.innerText || el.textContent || el.getAttribute("aria-label") || "");

                    return {
                        text,
                        x: r.x,
                        y: r.y,
                        w: r.width,
                        h: r.height,
                        cx: r.x + r.width / 2,
                        cy: r.y + r.height / 2
                    };
                })
                .filter(item => item.text);

            const dateItems = items.filter(item => isDateText(item.text));
            const results = [];

            for (const dateItem of dateItems) {
                const sameRow = items
                    .filter(item => {
                        if (Math.abs(item.cy - dateItem.cy) > 18) return false;
                        if (item.x >= dateItem.x - 5) return false;
                        if (item.text === dateItem.text) return false;
                        return true;
                    })
                    .sort((a, b) => b.x - a.x);

                for (const item of sameRow) {
                    const t = item.text.trim();
                    const low = t.toLowerCase();

                    if (!t) continue;
                    if (t.length <= 1) continue;

                    if ([
                        "name",
                        "owner",
                        "date",
                        "date modified",
                        "modified",
                        "file size",
                        "sort",
                        "type",
                        "people",
                        "source"
                    ].includes(low)) continue;

                    if (/^\\d{1,2}\\s+[A-Za-zÀ-ÿ]+\\s+\\d{4}$/.test(t)) continue;
                    if (/^\\d+(\\.\\d+)?\\s*(b|kb|mb|gb|tb)$/i.test(t)) continue;

                    results.push(t);
                    break;
                }
            }

            return results;
        }
        """
    )

    owners = []

    for candidate in candidates:
        owner = clean_owner(candidate)
        if owner:
            owners.append(owner)

    if not owners:
        return None

    return Counter(owners).most_common(1)[0][0]


def click_details(page):
    selectors = [
        'button[aria-label*="View details"]',
        'button[aria-label*="Show details"]',
        'button[aria-label*="Details"]',
        'button[aria-label*="Détails"]',
        'button[aria-label*="details"]',
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=1000)
                page.wait_for_timeout(1000)
                return
        except Exception:
            pass

    try:
        page.keyboard.press("i")
        page.wait_for_timeout(1000)
    except Exception:
        pass


def extract_owner_from_details(page):
    click_details(page)

    try:
        text = page.locator("body").inner_text(timeout=8000)
    except Exception:
        return None

    lines = [normalize(x) for x in text.splitlines()]
    lines = [x for x in lines if x]

    labels = {"owner", "owned by", "propriétaire", "proprietaire"}

    for i, line in enumerate(lines):
        if line.lower().strip(" :") in labels:
            for j in range(i + 1, min(i + 10, len(lines))):
                owner = clean_owner(lines[j])
                if owner:
                    return owner

    return None


def save_debug(page, debug_dir, name):
    if not debug_dir:
        return

    path = Path(debug_dir)
    path.mkdir(parents=True, exist_ok=True)

    try:
        page.screenshot(path=str(path / f"{name}.png"), full_page=True)
    except Exception:
        pass

    try:
        text = page.locator("body").inner_text(timeout=8000)
        with open(path / f"{name}.txt", "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass

    try:
        elements = page.evaluate(
            """
            () => {
                function norm(s) {
                    return (s || "").replace(/\\s+/g, " ").trim();
                }

                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const st = window.getComputedStyle(el);

                    return (
                        r.width > 0 &&
                        r.height > 0 &&
                        st.display !== "none" &&
                        st.visibility !== "hidden"
                    );
                }

                return Array.from(document.querySelectorAll("div, span, a, button"))
                    .filter(visible)
                    .map(el => {
                        const r = el.getBoundingClientRect();

                        return {
                            text: norm(el.innerText || el.textContent || el.getAttribute("aria-label") || ""),
                            x: Math.round(r.x),
                            y: Math.round(r.y),
                            w: Math.round(r.width),
                            h: Math.round(r.height)
                        };
                    })
                    .filter(x => x.text);
            }
            """
        )

        with open(path / f"{name}_elements.json", "w", encoding="utf-8") as f:
            json.dump(elements, f, ensure_ascii=False, indent=2)

    except Exception:
        pass


def get_owner(page, url, debug_dir=None, debug_name=None):
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    wait_drive_loaded(page)
    force_list_view(page)
    page.wait_for_timeout(1000)

    owner = extract_owner_from_rows(page)

    if owner:
        return owner

    owner = extract_owner_from_details(page)

    if owner:
        return owner

    save_debug(page, debug_dir, debug_name or "debug")
    return None


def process_file(page, input_path, output_path, save_each, debug_dir):
    data = load_json(input_path)

    try:
        for idx, obj in enumerate(data, 1):
            url = obj.get("drive_link", "")
            current = obj.get("owner")

            if current and not is_bad_owner(current):
                print(f"[{idx}/{len(data)}] already has owner: {current}")
                continue

            print(f"[{idx}/{len(data)}] {url}")

            try:
                owner = get_owner(
                    page,
                    url,
                    debug_dir=debug_dir,
                    debug_name=f"{input_path.stem}_{idx}",
                )
            except Exception as e:
                owner = None
                print(f"  error: {e}")

            obj["owner"] = owner
            print(f"  owner: {owner}")

            if save_each:
                save_json(output_path, data)

    except KeyboardInterrupt:
        print("\nInterrupted. Saving current progress...")
        save_json(output_path, data)
        raise

    save_json(output_path, data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("json_files", nargs="+")
    parser.add_argument("--cookies", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-save-each", action="store_true")
    parser.add_argument("--debug-dir", default="debug_drive_owner")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    save_each = not args.no_save_each

    with sync_playwright() as p:
        browser = None

        if args.profile:
            context = p.chromium.launch_persistent_context(
                args.profile,
                headless=args.headless,
                locale="en-US",
                viewport={"width": 1600, "height": 950},
            )
        else:
            browser = p.chromium.launch(headless=args.headless)
            context = browser.new_context(
                locale="en-US",
                viewport={"width": 1600, "height": 950},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125 Safari/537.36"
                ),
            )

            cookies = parse_netscape_cookies(args.cookies)

            if cookies:
                context.add_cookies(cookies)
                print(f"Loaded {len(cookies)} cookies")

        page = context.new_page()

        for file_name in args.json_files:
            input_path = Path(file_name)
            output_path = input_path.with_name(input_path.stem + "_with_owner.json")

            process_file(
                page=page,
                input_path=input_path,
                output_path=output_path,
                save_each=save_each,
                debug_dir=args.debug_dir,
            )

            print(f"Saved: {output_path}")

        try:
            context.close()
        except Exception:
            pass

        if browser:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()