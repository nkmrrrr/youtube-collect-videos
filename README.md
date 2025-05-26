# YouTube Like Sort and Transcript

Python script to sort YouTube channel videos by likes and optionally fetch their transcripts.

## Usage

```bash
python main.py [-o output.json] [--no-transcript] [--throttle-ms 0]
```

**Environment Variables:**

Before running the script, make sure you have a `.env` file in the same directory as `main.py` with the following variables set:

```
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
CHANNEL_ID=YOUR_YOUTUBE_CHANNEL_ID
```

Replace `YOUR_YOUTUBE_API_KEY` and `YOUR_YOUTUBE_CHANNEL_ID` with your actual YouTube API key and the target channel ID.

**Options:**

*   `-o, --output OUTPUT`: Path to write JSON result (default: `output.json`).
*   `--no-transcript`: Skip fetching transcripts (faster, cheaper).
*   `--throttle-ms THROTTLE_MS`: Sleep X milliseconds between API calls (to stay under quota, default: 0).

## Requirements

Install the necessary Python packages using pip:

```bash
pip install google-api-python-client youtube-transcript-api python-dateutil tqdm python-dotenv
```
