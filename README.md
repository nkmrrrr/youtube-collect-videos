# YouTube Transcript CLI Tool

Python-based CLI tool to extract YouTube channel videos, fetch transcripts, and generate AI-ready summary prompts.

## 🎯 Features

- **Video Data Collection**: Fetch YouTube channel videos sorted by likes
- **Transcript Extraction**: Extract video transcripts using YouTube's official APIs
- **AI Summary Prompts**: Generate structured prompts for ChatGPT/Claude/Gemini
- **Interactive Mode**: User-friendly interactive interface
- **Fallback Support**: Multiple transcript sources for reliability

## 📋 Requirements

Install the necessary Python packages:

```bash
pip install google-api-python-client youtube-transcript-api python-dateutil tqdm python-dotenv
```

## ⚙️ Setup

Create a `.env` file with your credentials:
```
YOUTUBE_API_KEY=YOUR_YOUTUBE_API_KEY
CHANNEL_ID=YOUR_YOUTUBE_CHANNEL_ID
```

## 🚀 Usage

### 1. Collect Video Data

```bash
# Basic video data collection
python main.py

# Skip transcripts (faster)
python main.py --no-transcript

# Custom output file
python main.py -o my_output.json

# Add throttling for API rate limits
python main.py --throttle-ms 1000
```

### 2. Extract Transcripts and Generate Summary Prompts

```bash
# Interactive mode (recommended)
python generate_urls.py --interactive

# Process specific number of videos
python generate_urls.py output.json -n 10 -l ja

# Process with different language
python generate_urls.py output.json -n 5 -l en
```

## 📊 Output Files

- **JSON**: Structured data with transcripts and AI-ready summary prompts

## 💡 AI Integration

Generated summary prompts are optimized for:
- **ChatGPT**: OpenAI's conversational AI
- **Claude**: Anthropic's AI assistant
- **Gemini**: Google's AI model

Simply copy the generated prompts and paste them into your preferred AI tool.

## 🔧 Technical Details

This tool replicates the mechanism used by Chrome extensions like "YouTube Summary with ChatGPT & Claude":

1. **Official Caption API**: Attempts to fetch captions via YouTube's `ytInitialPlayerResponse`
2. **Fallback Method**: Uses `youtube-transcript-api` when official API fails
3. **Multi-language Support**: Supports Japanese, English, and other languages
4. **Structured Output**: Generates AI-friendly prompts with consistent formatting

## 📁 File Structure

```
├── main.py                 # Video data collection
├── generate_urls.py        # Transcript extraction and prompt generation
├── .env                   # API credentials (create this)
├── README.md              # This file
└── .gitignore            # Git ignore rules
```

## 🚨 Troubleshooting

**No transcripts found**: Ensure videos have captions enabled
**API quota exceeded**: Add `--throttle-ms 1000` or higher
**Permission errors**: Check your YouTube API key and channel ID

## 📝 Example Workflow

1. Set up your `.env` file with API credentials
2. Collect video data: `python main.py`
3. Extract transcripts: `python generate_urls.py --interactive`
4. Choose number of videos and language
5. Copy generated prompts from JSON output to your preferred AI tool
6. Generate summaries and save results

## 🏆 Benefits

- **Independent**: No need for Chrome extensions
- **Reliable**: Multiple fallback methods for transcript extraction
- **Flexible**: Support for multiple languages
- **AI-Ready**: Optimized prompts for popular AI tools
- **Fast**: Batch processing for efficiency
