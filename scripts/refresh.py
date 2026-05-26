"""
refresh.py — Fetch video portfolio from Feishu Bitable and generate videos.json

Videos are stored on Tencent COS (permanent URLs).
This script syncs metadata (title, type, description, date) from Feishu Bitable
and generates api/videos.json with COS video URLs.

COS URL mapping is based on file_token → COS filename mapping.
When new videos are added, download them from Feishu and upload to COS manually,
then add the mapping here.
"""

import json
import os
import sys
import requests

LARK_APP_ID = os.environ.get("LARK_APP_ID", "")
LARK_APP_SECRET = os.environ.get("LARK_APP_SECRET", "")
LARK_BASE_TOKEN = os.environ.get("LARK_BASE_TOKEN", "XyhFbpdEyahWZJs2LvTcCjwdn8d")
LARK_TABLE_ID = os.environ.get("LARK_TABLE_ID", "tblMmpptHwhuEyUH")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "api")

COS_BASE = "https://badge-static-1304293304.cos.ap-guangzhou.myqcloud.com/videos"

BASE_URL = "https://open.feishu.cn/open-apis"

# file_token → COS filename mapping
COS_MAP = {
    "FA4rbWQqOoUa8pxD5R3cWznanRb": "shechu_xiuxian.mp4",
    "P5Epbo2HioBsm3xhsujcXo7AnCb": "bazhong_qiyu.mp4",
    "QHVWbSsxIovTNfxeaCkchvXEnqd": "lumos_jianshou.mp4",
    "OaFKb9qLXo5jzMxDXSuc4Dosngg": "shijie_chengshi.mp4",
    "RagEbMr7no8NDlxlJiHcjBN0nNe": "diewu_huyin.mp4",
    "UPQkbcvh6oeIv8x7804c1xYinih": "pingjing_ai.mp4",
    "MMvZbbl9GoSJwrxRx4ScQkT6nXb": "maomao_aosai.mp4",
}


def get_tenant_token():
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
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{BASE_URL}/bitable/v1/apps/{LARK_BASE_TOKEN}/tables/{LARK_TABLE_ID}/records"
    all_records = []
    page_token = None

    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        data = resp.json()
        if data.get("code") != 0:
            print(f"ERROR: Failed to list records: {data}", file=sys.stderr)
            sys.exit(1)

        items = data.get("data", {}).get("items", [])
        if not items:
            break

        all_records.extend(items)
        page_token = data.get("data", {}).get("page_token", "")
        if not page_token or not data.get("data", {}).get("has_more", False):
            break

    return all_records


def parse_records(records):
    videos = []
    for rec in records:
        fields = rec.get("fields", {})
        title = fields.get("内容", "")
        if not title:
            continue

        raw_type = fields.get("类型", [])
        video_type = raw_type[0] if isinstance(raw_type, list) and raw_type else str(raw_type) if raw_type else ""

        attachments = fields.get("样本", [])
        file_token = attachments[0].get("file_token", "") if attachments else ""

        cos_file = COS_MAP.get(file_token, "")
        video_url = f"{COS_BASE}/{cos_file}" if cos_file else ""

        date_val = fields.get("日期", "")
        if isinstance(date_val, (int, float)):
            from datetime import datetime, timezone
            date_val = datetime.fromtimestamp(date_val / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

        videos.append({
            "title": title,
            "type": video_type,
            "description": fields.get("描述", ""),
            "date": date_val,
            "video_url": video_url,
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

    print("Parsing records...")
    videos = parse_records(records)
    print(f"Generated {len(videos)} video entries")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_path = os.path.join(OUTPUT_DIR, "videos.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)

    print(f"Written to {output_path}")


if __name__ == "__main__":
    main()
