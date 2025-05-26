#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tqdm import tqdm
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
    CouldNotRetrieveTranscript,
)

# --------------------------------------------------------------------------- #
#                         YouTube Data API helper class                       #
# --------------------------------------------------------------------------- #
class YouTubeClient:
    def __init__(self, api_key: str, throttle_ms: int = 0):
        self.service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        self.throttle_ms = throttle_ms

    def _sleep_if_needed(self):
        if self.throttle_ms:
            time.sleep(self.throttle_ms / 1000)

    # 1. チャンネルの “uploads” プレイリスト ID を取得
    def get_uploads_playlist_id(self, channel_id: str) -> str:
        self._sleep_if_needed()
        res = (
            self.service.channels()
            .list(part="contentDetails", id=channel_id, maxResults=1)
            .execute()
        )
        try:
            return res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
        except (IndexError, KeyError):
            raise ValueError("Invalid channel ID or no uploads playlist found")

    # 2. playlistItems.list で動画 ID をすべて取得
    def collect_video_ids(self, playlist_id: str) -> List[str]:
        video_ids, page_token = [], None
        pbar = tqdm(desc="Collecting video ids", unit="videos")
        while True:
            self._sleep_if_needed()
            req = self.service.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
            resp = req.execute()
            chunk = [
                item["contentDetails"]["videoId"] for item in resp.get("items", [])
            ]
            video_ids.extend(chunk)
            pbar.update(len(chunk))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        pbar.close()
        return video_ids

    # 3. videos.list で likeCount など統計情報を取得
    def fetch_video_stats(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        stats: List[Dict[str, Any]] = []
        pbar = tqdm(total=len(video_ids), desc="Fetching statistics", unit="videos")
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            self._sleep_if_needed()
            req = self.service.videos().list(
                part="snippet,statistics", id=",".join(chunk), maxResults=50
            )
            resp = req.execute()
            for v in resp["items"]:
                s = v["statistics"]
                stats.append(
                    {
                        "videoId": v["id"],
                        "title": v["snippet"]["title"],
                        "published_at": v["snippet"]["publishedAt"],
                        "likes": int(s.get("likeCount", 0)),
                        "views": int(s.get("viewCount", 0)),
                    }
                )
                pbar.update(1)
        pbar.close()
        # likes 降順 → views 降順 → 公開日昇順
        stats.sort(
            key=lambda x: (-x["likes"], -x["views"], x["published_at"])
        )
        return stats


# --------------------------------------------------------------------------- #
#                          Transcript helper function                         #
# --------------------------------------------------------------------------- #
def fetch_transcript(video_id: str, lang_priority=("ja", "en")) -> List[Dict[str, Any]]:
    """
    Returns:
        [{'start': 1.23, 'duration': 3.4, 'text': '...'}, ...]
        空リストの場合は字幕なし
    """
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        # 1) 手動字幕優先 2) 自動生成
        for lang in lang_priority:
            try:
                return transcripts.find_manually_created_transcript([lang]).fetch()
            except (NoTranscriptFound, TranscriptsDisabled):
                try:
                    return transcripts.find_generated_transcript([lang]).fetch()
                except (NoTranscriptFound, TranscriptsDisabled):
                    continue
    except (TranscriptsDisabled, CouldNotRetrieveTranscript):
        pass
    return []


# --------------------------------------------------------------------------- #
#                                   Main                                      #
# --------------------------------------------------------------------------- #
def main():
    load_dotenv()

    ap = argparse.ArgumentParser(description="Sort channel videos by likes and get transcripts")
    ap.add_argument(
        "-o",
        "--output",
        default="output.json",
        help="Path to write JSON result (default: output.json)",
    )
    ap.add_argument(
        "--no-transcript",
        action="store_true",
        help="Skip fetching transcripts (faster, cheaper)",
    )
    ap.add_argument(
        "--throttle-ms",
        type=int,
        default=0,
        help="Sleep X milliseconds between API calls (stay under quota)",
    )
    args = ap.parse_args()

    api_key = os.getenv("YOUTUBE_API_KEY")
    channel_id = os.getenv("CHANNEL_ID")

    if not api_key:
        sys.exit("ERROR: YOUTUBE_API_KEY environment variable not set or empty. Please set it in your .env file or environment.")
    if not channel_id:
        sys.exit("ERROR: CHANNEL_ID environment variable not set or empty. Please set it in your .env file or environment.")

    yt = YouTubeClient(api_key, throttle_ms=args.throttle_ms)

    try:
        uploads_playlist_id = yt.get_uploads_playlist_id(channel_id)
    except (ValueError, HttpError) as e:
        sys.exit(f"Failed to get uploads playlist: {e}")

    video_ids = yt.collect_video_ids(uploads_playlist_id)
    if not video_ids:
        sys.exit("No videos found.")

    stats = yt.fetch_video_stats(video_ids)

    if not args.no_transcript:
        pbar = tqdm(stats, desc="Fetching transcripts", unit="videos")
        for item in pbar:
            item["transcript"] = fetch_transcript(item["videoId"])
        pbar.close()

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! Saved {len(stats)} records to {args.output}")


if __name__ == "__main__":
    main()
