#!/usr/bin/env python3
"""
YouTube字幕取得・AI要約プロンプト生成CLI
YouTube公式APIと音声認識APIを使用した独立実装
"""

import json
import argparse
import requests
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse
import time
from pathlib import Path

def extract_video_id(url: str) -> str:
    """YouTube URLから動画IDを抽出"""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&\n?#]+)',
        r'v=([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return url if re.match(r'^[a-zA-Z0-9_-]{11}$', url) else None

def get_youtube_captions(video_id: str, lang: str = 'ja') -> dict:
    """
    YouTube公式キャプションを取得
    拡張機能と同じメカニズムを使用
    """
    try:
        # 1. YouTubeページからytInitialPlayerResponseを取得
        youtube_url = f"https://www.youtube.com/watch?v={video_id}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        response = requests.get(youtube_url, headers=headers)
        response.raise_for_status()
        
        # ytInitialPlayerResponseの抽出
        pattern = r'var ytInitialPlayerResponse = ({.*?});'
        match = re.search(pattern, response.text)
        
        if not match:
            print(f"   🔍 ytInitialPlayerResponse not found, trying alternative patterns...")
            # Alternative patterns
            alt_patterns = [
                r'ytInitialPlayerResponse"?:\s*({.*?}),',
                r'ytInitialPlayerResponse\s*=\s*({.*?});',
                r'"ytInitialPlayerResponse":({.*?}),'
            ]
            for alt_pattern in alt_patterns:
                match = re.search(alt_pattern, response.text)
                if match:
                    print(f"   ✅ Found with alternative pattern")
                    break
            
            if not match:
                return {"error": "ytInitialPlayerResponseが見つかりません"}
        
        player_response = json.loads(match.group(1))
        
        # 2. captionTracksの取得
        captions = player_response.get('captions', {})
        caption_tracks = captions.get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
        
        if not caption_tracks:
            return {"error": "字幕が利用できません"}
        
        # 3. 指定言語または利用可能な言語の字幕を取得
        selected_track = None
        for track in caption_tracks:
            if track.get('languageCode') == lang:
                selected_track = track
                break
        
        # 指定言語がない場合は最初の利用可能な字幕を使用
        if not selected_track and caption_tracks:
            selected_track = caption_tracks[0]
        
        if not selected_track:
            return {"error": "利用可能な字幕がありません"}
        
        # 4. 字幕XMLの取得
        base_url = selected_track.get('baseUrl')
        if not base_url:
            return {"error": "字幕URLが取得できません"}
        
        caption_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ja,en-US;q=0.5',
            'Referer': f'https://www.youtube.com/watch?v={video_id}',
            'Origin': 'https://www.youtube.com',
        }
        
        caption_response = requests.get(base_url, headers=caption_headers)
        caption_response.raise_for_status()
        
        # 5. XMLのパース
        transcript_data = parse_caption_xml(caption_response.text)
        
        return {
            "success": True,
            "video_id": video_id,
            "language": selected_track.get('languageCode'),
            "language_name": selected_track.get('name', {}).get('simpleText', ''),
            "transcript": transcript_data['text'],
            "timed_transcript": transcript_data['timed'],
            "available_languages": [
                {
                    "code": track.get('languageCode'),
                    "name": track.get('name', {}).get('simpleText', '')
                }
                for track in caption_tracks
            ]
        }
        
    except Exception as e:
        return {"error": f"字幕取得エラー: {str(e)}"}

def parse_caption_xml(xml_content: str) -> dict:
    """字幕XMLをパースしてテキストとタイムスタンプ付きデータを生成"""
    try:
        if not xml_content.strip():
            return {"text": "", "timed": [], "error": "Empty XML content"}
        
        root = ET.fromstring(xml_content)
        
        timed_transcript = []
        full_text = []
        
        for text_elem in root.findall('text'):
            start_time = float(text_elem.get('start', 0))
            duration = float(text_elem.get('dur', 0))
            text_content = text_elem.text or ''
            
            # HTMLエンティティのデコード
            text_content = text_content.replace('&amp;', '&')
            text_content = text_content.replace('&lt;', '<')
            text_content = text_content.replace('&gt;', '>')
            text_content = text_content.replace('&quot;', '"')
            text_content = text_content.replace('&#39;', "'")
            
            # タイムスタンプ付きデータ
            timed_transcript.append({
                "start": start_time,
                "duration": duration,
                "text": text_content.strip()
            })
            
            full_text.append(text_content.strip())
        
        return {
            "text": ' '.join(full_text),
            "timed": timed_transcript
        }
        
    except ET.ParseError as e:
        return {"text": "", "timed": [], "error": f"XML解析エラー: {str(e)}"}

def get_fallback_transcript(video_id: str) -> dict:
    """
    フォールバック: youtube-transcript-apiを使用
    （字幕が取得できない場合の代替手段）
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        
        print(f"   🔍 Trying youtube-transcript-api for video {video_id}")
        
        # 利用可能な言語を取得
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        available_transcripts = []
        for transcript in transcript_list:
            available_transcripts.append({
                'language_code': transcript.language_code,
                'language': transcript.language,
                'is_generated': transcript.is_generated,
                'is_translatable': transcript.is_translatable
            })
        
        print(f"   🔍 Available transcripts: {available_transcripts}")
        
        # 日本語を直接取得→翻訳版を試行
        try:
            print(f"   🔍 Trying Japanese transcript...")
            # まず利用可能な transcript をリストアップ
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            
            # 日本語字幕を取得
            ja_transcript = transcript_list.find_transcript(['ja'])
            transcript_data = ja_transcript.fetch()
            
            # 新しいAPIバージョンに対応した処理
            if hasattr(transcript_data, '__iter__') and len(transcript_data) > 0:
                # APIのレスポンスを適切に処理
                full_text_parts = []
                timed_data = []
                
                for item in transcript_data:
                    if hasattr(item, 'text'):
                        # 新しいAPIの FetchedTranscriptSnippet オブジェクト
                        text = item.text
                        start = getattr(item, 'start', 0)
                        duration = getattr(item, 'duration', 0)
                        
                        full_text_parts.append(text)
                        timed_data.append({
                            "text": text,
                            "start": start,
                            "duration": duration
                        })
                    elif isinstance(item, dict):
                        # 従来形式の辞書
                        text = item.get('text', '')
                        full_text_parts.append(text)
                        timed_data.append(item)
                    else:
                        # 予期しない形式
                        text = str(item)
                        full_text_parts.append(text)
                        timed_data.append({"text": text})
                
                full_text = ' '.join(full_text_parts)
            else:
                full_text = str(transcript_data)
                timed_data = [{"text": full_text}]
            
            print(f"   ✅ Japanese transcript success: {len(full_text)} chars, {len(timed_data)} segments")
            
            return {
                "success": True,
                "video_id": video_id,
                "language": 'ja',
                "transcript": full_text,
                "timed_transcript": timed_data,
                "source": "youtube-transcript-api"
            }
            
        except Exception as e:
            print(f"   ❌ Japanese transcript failed: {str(e)}")
            
        # もう一度シンプルなAPIを試行
        try:
            print(f"   🔍 Trying simple get_transcript...")
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja'])
            
            # データ形式を統一
            if transcript_data and isinstance(transcript_data[0], dict):
                # 従来の辞書形式
                full_text = ' '.join([item['text'] for item in transcript_data])
                timed_data = transcript_data
            else:
                # 新しい形式
                full_text_parts = []
                timed_data = []
                
                for item in transcript_data:
                    if hasattr(item, 'text'):
                        text = item.text
                        start = getattr(item, 'start', 0)
                        duration = getattr(item, 'duration', 0)
                        
                        full_text_parts.append(text)
                        timed_data.append({
                            "text": text,
                            "start": start,
                            "duration": duration
                        })
                
                full_text = ' '.join(full_text_parts)
            
            print(f"   ✅ Simple transcript success: {len(full_text)} chars, {len(timed_data)} segments")
            
            return {
                "success": True,
                "video_id": video_id,
                "language": 'ja',
                "transcript": full_text,
                "timed_transcript": timed_data,
                "source": "youtube-transcript-api (simple)"
            }
            
        except Exception as e:
            print(f"   ❌ Simple transcript failed: {str(e)}")
        
        return {"error": "フォールバック字幕取得も失敗"}
        
    except ImportError:
        return {"error": "youtube-transcript-api がインストールされていません"}
    except Exception as e:
        print(f"   ❌ Fallback error: {str(e)}")
        return {"error": f"フォールバック字幕取得エラー: {str(e)}"}

def generate_summary_prompt(transcript: str, title: str = "") -> str:
    """要約用プロンプトを生成（拡張機能と同様の仕組み）"""
    prompt = f"""以下のYouTube動画の内容を要約してください。

タイトル: {title}

内容:
{transcript}

以下の形式で要約してください：
## 概要
[動画の主要な内容を2-3文で]

## 主要なポイント
1. [ポイント1]
2. [ポイント2]
3. [ポイント3]

## 詳細
[より詳細な説明]

## キーワード
[重要なキーワードをカンマ区切りで]
"""
    return prompt

def process_video_transcripts(input_file: str, output_file: str = None, top_n: int = 10, lang: str = 'ja'):
    """動画リストから字幕を取得して要約プロンプトを生成"""
    
    # 入力ファイルの読み込み
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # データが配列の場合の処理
    if isinstance(data, list):
        videos = data[:top_n]
    else:
        videos = data.get('videos', [])[:top_n]
    
    results = []
    
    print(f"🎬 {len(videos)} 件の動画から字幕を取得中...")
    
    for i, video in enumerate(videos, 1):
        video_id = video.get('videoId', '')
        title = video.get('title', '')
        
        print(f"\n{i}/{len(videos)}: {title}")
        print(f"   動画ID: {video_id}")
        
        # 字幕取得（メイン）
        caption_result = get_youtube_captions(video_id, lang)
        
        # フォールバック
        if not caption_result.get('success') or caption_result.get('transcript', '') == '':        print(f"   ⚠️ 公式字幕取得失敗: {caption_result.get('error', 'Empty transcript')}")
        print(f"   🔄 フォールバック字幕取得を試行中...")
        caption_result = get_fallback_transcript(video_id)
        
        if caption_result.get('success'):
            transcript = caption_result['transcript']
            print(f"   ✅ 字幕取得成功 ({len(transcript)} 文字)")
            
            # 要約プロンプト生成
            summary_prompt = generate_summary_prompt(transcript, title)
            
            # 結果の構築
            result = {
                **video,  # 元の動画情報
                "caption_data": caption_result,
                "summary_prompt": summary_prompt,
                "transcript_length": len(transcript),
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
        else:
            print(f"   ❌ 字幕取得失敗: {caption_result.get('error')}")
            result = {
                **video,
                "caption_data": caption_result,
                "summary_prompt": None,
                "transcript_length": 0,
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        
        results.append(result)
        
        # レート制限対策
        time.sleep(1)
    
    # 結果の保存
    output_data = {
        "processed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_videos": len(results),
        "successful_transcripts": len([r for r in results if r.get('transcript_length', 0) > 0]),
        "target_language": lang,
        "videos": results
    }
    
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 結果を保存: {output_file}")
    
    # 統計表示
    successful = output_data['successful_transcripts']
    total = output_data['total_videos']
    print(f"\n📊 処理結果:")
    print(f"   総動画数: {total}")
    print(f"   字幕取得成功: {successful}")
    print(f"   成功率: {successful/total*100:.1f}%")
    
    return output_data


def main():
    parser = argparse.ArgumentParser(description="YouTube字幕取得・AI要約プロンプト生成CLI")
    parser.add_argument("input", nargs='?', help="入力JSONファイル (output.json)")
    parser.add_argument("-n", "--top", type=int, default=10, 
                       help="処理する動画数 (デフォルト: 10)")
    parser.add_argument("-o", "--output", default="transcripts_with_prompts.json",
                       help="出力ファイル (デフォルト: transcripts_with_prompts.json)")
    parser.add_argument("-l", "--lang", default="ja",
                       help="字幕言語 (デフォルト: ja)")
    parser.add_argument("--legacy", action="store_true",
                       help="旧版のURL生成モードで実行")
    parser.add_argument("--interactive", action="store_true",
                       help="対話式モードで実行")
    
    args = parser.parse_args()
    
    if args.interactive:
        # 対話式モード
        interactive_mode()
    elif args.input is None:
        print("❌ エラー: 入力ファイルが指定されていません。")
        print("使用方法: python generate_urls.py output.json [オプション]")
        print("または: python generate_urls.py --interactive")
        return
    elif args.legacy:
        # 後方互換性のための旧機能
        generate_legacy_url_list(args.input, args.top, args.output)
    else:
        # 新機能: 字幕取得と要約プロンプト生成
        results = process_video_transcripts(args.input, args.output, args.top, args.lang)
        
        print(f"\n🎉 処理完了！")
        print(f"📁 生成ファイル: {args.output}")
        if Path(args.output).exists():
            size = Path(args.output).stat().st_size
            print(f"   📄 {size:,} bytes")
        
        # 使用方法の案内
        successful = results['successful_transcripts']
        if successful > 0:
            print(f"\n💡 次のステップ:")
            print(f"   1. 生成されたJSONファイルで要約プロンプトを確認")
            print(f"   2. プロンプトをChatGPT/Claude/Geminiにペーストして要約生成")
            print(f"   3. 生成された要約を保存・整理")
        else:
            print(f"\n⚠️ 字幕が取得できませんでした。以下を確認してください:")
            print(f"   - 動画に字幕が存在するか")
            print(f"   - ネットワーク接続が正常か")
            print(f"   - youtube-transcript-api がインストールされているか")

def interactive_mode():
    """対話式モードでユーザーフレンドリーな操作を提供"""
    print("🎬 YouTube字幕・要約自動生成ツール")
    print("Chrome拡張機能のメカニズムを応用した独立実装")
    print("=" * 60)
    
    # 入力ファイルの確認
    default_input = "output.json"
    if not Path(default_input).exists():
        print(f"❌ デフォルト入力ファイル '{default_input}' が見つかりません。")
        print("まず main.py を実行して動画データを生成してください。")
        return
    
    with open(default_input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        total_videos = len(data)
    else:
        total_videos = len(data.get('videos', []))
    
    print(f"📊 利用可能な動画数: {total_videos} 件")
    
    # 処理数の選択
    while True:
        try:
            user_input = input(f"\\n処理する動画数を入力してください (1-{total_videos}, デフォルト: 5): ").strip()
            if not user_input:
                process_count = 5
            else:
                process_count = int(user_input)
                if process_count < 1 or process_count > total_videos:
                    raise ValueError()
            break
        except ValueError:
            print(f"❌ 1から{total_videos}の間の数値を入力してください。")
    
    # 言語の選択
    available_langs = {
        '1': ('ja', '日本語'),
        '2': ('en', '英語'),
        '3': ('ko', '韓国語'),
        '4': ('zh', '中国語'),
        '5': ('es', 'スペイン語'),
        '6': ('fr', 'フランス語')
    }
    
    print("\\n🌐 字幕言語を選択してください:")
    for key, (code, name) in available_langs.items():
        print(f"   {key}. {name} ({code})")
    
    while True:
        lang_choice = input("言語番号を入力 (デフォルト: 1-日本語): ").strip()
        if not lang_choice:
            selected_lang = 'ja'
            break
        elif lang_choice in available_langs:
            selected_lang = available_langs[lang_choice][0]
            break
        else:
            print("❌ 有効な番号を選択してください。")
    
    print(f"✅ 選択: {process_count} 件の動画, 言語: {selected_lang}")
    
    # 確認
    print("\\n📋 処理内容の確認:")
    print(f"   📁 入力ファイル: {default_input}")
    print(f"   🎯 処理動画数: {process_count} 件")
    print(f"   🌐 字幕言語: {selected_lang}")
    print(f"   📄 出力形式: JSON")
    
    confirm = input("\\n処理を開始しますか？ (y/n): ").strip().lower()
    if confirm not in ['y', 'yes', '']:
        print("⏹️ 処理を中止しました。")
        return
    
    # 処理実行
    print("\\n🚀 処理を開始します...")
    
    output_file = f"transcripts_{selected_lang}_{process_count}videos.json"
    results = process_video_transcripts(default_input, output_file, process_count, selected_lang)
    
    # 結果サマリー
    successful = results['successful_transcripts']
    total = results['total_videos']
    
    print("\\n" + "=" * 60)
    print("🎉 処理が完了しました！")
    print("\\n📊 結果サマリー:")
    print(f"   ✅ 字幕取得成功: {successful} / {total} 件 ({successful/total*100:.1f}%)")
    
    if successful > 0:
        print("\\n💡 次のアクション:")
        print("   1. 生成されたJSONファイルで要約プロンプトを確認")
        print("   2. プロンプトをコピーしてChatGPT/Claude/Geminiで要約生成")
        print("   3. 生成された要約を整理・保存")
        
        # 失敗した動画がある場合の案内
        failed = total - successful
        if failed > 0:
            print(f"\\n⚠️ {failed} 件の動画で字幕取得に失敗しました。")
            print("   原因: 字幕が存在しない、プライベート動画、地域制限など")
    else:
        print("\\n❌ すべての動画で字幕取得に失敗しました。")
        print("   対処法:")
        print("   - 別の言語を試す")
        print("   - youtube-transcript-api をインストール: pip install youtube-transcript-api")
        print("   - ネットワーク接続を確認")
    
    print(f"\\n📁 生成ファイル: {output_file}")
    if Path(output_file).exists():
        size = Path(output_file).stat().st_size
        print(f"   📄 {size:,} bytes")

def show_help():
    """ヘルプ情報を表示"""
    help_text = """
🎬 YouTube字幕・要約自動生成ツール - ヘルプ

Chrome拡張機能「YouTube Summary with ChatGPT & Claude」のメカニズムを
応用した独立実装です。拡張機能に依存せずに字幕取得と要約プロンプト生成
を行うことができます。

📋 基本的な使用方法:

1. 対話式モード（推奨）:
   python generate_urls.py --interactive

2. コマンドライン指定:
   python generate_urls.py output.json -n 10 -l ja

3. 旧版互換モード:
   python generate_urls.py output.json --legacy

📊 オプション詳細:

  input                 入力JSONファイル（通常は output.json）
  -n, --top            処理する動画数（デフォルト: 10）
  -l, --lang           字幕言語（ja/en/ko/zh など）
  -o, --output         出力ファイル名
  --legacy             旧版のURL生成モード
  --interactive        対話式モード
  --help               このヘルプを表示

🔧 技術的な仕組み:

1. YouTube公式字幕取得:
   - ytInitialPlayerResponse から captionTracks を抽出
   - timedtext API で XML形式の字幕を取得
   - 拡張機能と同じメカニズムを使用

2. フォールバック機能:
   - 公式字幕が取得できない場合は youtube-transcript-api を使用
   - 複数言語での取得を自動試行

3. 要約プロンプト生成:
   - 取得した字幕から構造化された要約プロンプトを生成
   - ChatGPT/Claude/Gemini で使用可能な形式

💡 使用例:

# 日本語字幕で上位5件を処理
python generate_urls.py output.json -n 5 -l ja

# 英語字幕で上位20件を処理
python generate_urls.py output.json -n 20 -l en

# 対話式でユーザーフレンドリーに実行
python generate_urls.py --interactive

📄 出力ファイル:

- JSON: 字幕データと要約プロンプトの構造化データ

🆘 トラブルシューティング:

Q: 字幕が取得できない
A: 1) 動画に字幕が存在するか確認
   2) 別の言語（en など）を試す
   3) youtube-transcript-api をインストール

Q: 処理が遅い
A: 動画数を減らすか、-n オプションで件数を制限

"""

    print(help_text)



def generate_legacy_url_list(input_file: str, top_n: int, output_file: str):
    """レガシー機能: URLリストの生成（後方互換性のため）"""
    print("⚠️  レガシーモードで実行中...")
    print("新機能を使用するには --interactive または通常モードを使用してください。")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list):
        videos = data[:top_n]
    else:
        videos = data.get('videos', [])[:top_n]
    
    url_list = []
    for video in videos:
        video_id = video.get('videoId', '')
        title = video.get('title', '')
        url = f"https://www.youtube.com/watch?v={video_id}"
        
        url_list.append({
            "title": title,
            "url": url,
            "video_id": video_id
        })
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(url_list, f, ensure_ascii=False, indent=2)
    
    print(f"✅ URLリスト生成完了: {output_file}")
    print(f"📊 {len(url_list)} 件のURLを出力")

if __name__ == "__main__":
    import sys
    
    # ヘルプ要求の場合
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h', 'help']:
        show_help()
    else:
        main()
