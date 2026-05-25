"""
refresh.py — Fetch video portfolio from Feishu Bitable and generate videos.json

Uses Feishu Open API to:
1. Get tenant access token
2. List records from Bitable
3. Get temporary download URLs for video attachments
4. Generate api/videos.json for the website
"""

import json
import os
import sys
import requests

# Config from environment variables
LARK_APP_ID = os.environ.get("LARK_APP_ID", "")
LARK_APP_SECRET = os.environ.get("LARK_APP_SECRET", "")
LARK_BASE_TOKEN = os.environ.get("LARK_BASE_TOKEN", "XyhFbpdEyahWZJs2LvTcCjwdn8d")
LARK_TABLE_ID = os.environ.get("LARK_TABLE_ID", "tblMmpptHwhuEyUH")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "api")

BASE_URL = "https://open.feishu.cn/open-apis"


def get_tenant_token():
    """Get tenant_access_token using app credentials."""
    url = f"{BASE_URL}/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": LARK_APP_ID,
        "app_secret": LARK_APP_SECRET
    }, timeout=30)
    data = resp.json()
    if data.get("code") != 0:
        print(f"ERROR: Failed to get tenant token: {data}", file=sys.stderr)
        sys.exit(1)
    return data["tenant_access_token"]


def list_records(token):
    """List all records from the Bitable table."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/bitable/v1/apps/{LARK_BASE_TOKEN}/tables/{LARK_TABLE_ID}/records"
    all_records = []
    offset = 0
    limit = 100

    while True:
        resp = requests.get(url, headers=headers, params={
            "page_size": limit,
            "offset": offset
        }, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            print(f"ERROR: Failed to list records: {data}", file=sys.stderr)
            sys.exit(1)

        items = data.get("data", {}).get("items", [])
        if not items:
            break

        all_records.extend(items)
        if not data.get("data", {}).get("has_more", False):
            break
        offset += len(items)

    return all_records


def get_download_urls(token, file_tokens):
    """Get temporary download URLs for file attachments.
    Try each token individually via the drive media download endpoint."""
    headers = {"Authorization": f"Bearer {token}"}
    url_map = {}

    for ft in file_tokens:
        # Try single file download URL
        url = f"{BASE_URL}/drive/v1/medias/{ft}"
        try:
            resp = requests.get(url, headers=headers, params={
                "extra": json.dumps({"bitablePerm": {"tableId": LARK_TABLE_ID, "rev": 1}})
            }, timeout=30)
            # Response might not be JSON (could be redirect or binary)
            content_type = resp.headers.get("Content-Type", "")
            if "json" in content_type:
                data = resp.json()
                tmp_url = data.get("data", {}).get("tmp_download_url", "")
                if tmp_url:
                    url_map[ft] = tmp_url
                    print(f"DEBUG got URL for {ft}", file=sys.stderr)
                    continue
            # If not JSON or no URL, check if response is a redirect
            if resp.status_code == 302 or resp.is_redirect:
                url_map[ft] = resp.headers.get("Location", "")
                print(f"DEBUG got redirect for {ft}", file=sys.stderr)
                continue
            print(f"DEBUG no URL for {ft}: status={resp.status_code} ct={content_type}", file=sys.stderr)
        except Exception as e:
            print(f"DEBUG error for {ft}: {e}", file=sys.stderr)

    return url_map


def parse_records(token, records):
    """Parse raw records into clean video objects."""
    # Collect all file tokens first for batch download URL fetch
    all_tokens = []
    for rec in records:
        fields = rec.get("fields", {})
        for att in fields.get("样本", []):
            ft = att.get("file_token", "")
            if ft:
                all_tokens.append(ft)

    # Batch fetch download URLs
    print(f"Fetching download URLs for {len(all_tokens)} files...")
    url_map = get_download_urls(token, all_tokens) if all_tokens else {}

    videos = []
    for rec in records:
        fields = rec.get("fields", {})
        title = fields.get("内容", "")
        if not title:
            continue

        raw_type = fields.get("类型", [])
        video_type = raw_type[0] if isinstance(raw_type, list) and raw_type else str(raw_type)

        attachments = fields.get("样本", [])
        file_token = attachments[0].get("file_token", "") if attachments else ""
        video_url = url_map.get(file_token, "")

        videos.append({
            "title": title,
            "type": video_type,
            "description": fields.get("描述", ""),
            "date": fields.get("日期", ""),
            "file_name": attachments[0].get("name", "") if attachments else "",
            "file_size": attachments[0].get("size", 0) if attachments else 0,
            "video_url": video_url,
            "file_token": file_token
        })

    return videos


def main():
    if not LARK_APP_ID or not LARK_APP_SECRET:
        print("ERROR: LARK_APP_ID and LARK_APP_SECRET must be set", file=sys.stderr)
        sys.exit(1)

    print("Getting tenant access token...")
    token = get_tenant_token()

    print("Fetching records from Feishu Bitable...")
    records = list_records(token)
    print(f"Found {len(records)} records")

    print("Parsing records and fetching video URLs...")
    videos = parse_records(token, records)
    print(f"Generated {len(videos)} video entries")

    # Write output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "videos.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)

    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
