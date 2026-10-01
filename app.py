from flask import Flask, render_template, request, jsonify, session, redirect
import os
from werkzeug.utils import secure_filename
import assemblyai as aai
import math
import re
import json

try:
    from bertopic import BERTopic
    from sentence_transformers import SentenceTransformer
    BERTOPIC_AVAILABLE = True
except Exception:
    BERTOPIC_AVAILABLE = False

# youtube downloaders
try:
    from yt_dlp import YoutubeDL
    YTDLP_AVAILABLE = True
except Exception:
    YTDLP_AVAILABLE = False

try:
    from pytube import YouTube
    PYTUBE_AVAILABLE = True
except Exception:
    PYTUBE_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'secret123'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300MB if needed

_device_env = os.environ.get('HF_DEVICE')
try:
    device = int(_device_env) if _device_env is not None else 0
except Exception:
    device = 0

_summarizer = None
def get_summarizer():
    global _summarizer
    if _summarizer is not None:
        return _summarizer
    from transformers import pipeline
    try:
        _summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=device)
    except Exception:
        _summarizer = pipeline("summarization", model="facebook/bart-large-cnn", device=-1)
    return _summarizer

# Summarization config - optimized for completeness
SUMMARY_MIN = 100  # Minimum summary length for completeness
SUMMARY_MAX = 400  # Maximum to allow detailed summaries
CHUNK_MAX_WORDS = 300  # Larger chunks for better context preservation
SUMMARY_RATIO = 0.6  # Target 60% of original for more complete summary  

# BERTopic lazy init
_topic_model = None
_embedding_model = None
def get_topic_model():
    global _topic_model, _embedding_model
    if not BERTOPIC_AVAILABLE:
        return None
    if _topic_model is None:
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        _topic_model = BERTopic(embedding_model=_embedding_model, verbose=False)
    return _topic_model

NOISE_PATTERNS = [
    r"\b(okay|alright|so|uh|um|ah|er|hm|hmm|like|you know|right)\b",
    r"\b(shh|quiet|silence|stop talking|be quiet)\b",
    r"\b(open your books|turn to page|look at the board)\b",
    r"\b(any questions|understood|clear|got it)\b"
]

ASSIGNMENT_KEYWORDS = [
    'assignment', 'homework', 'deadline', 'test', 'quiz', 'exam',
    'project', 'submit', 'deliverable', 'practice', 'reading', 'worksheet'
]

# Topic keywords mapping - comprehensive topic detection
TOPIC_KEYWORDS = {
    'Machine Learning': ['machine learning', 'ml', 'neural network', 'algorithm', 'training data', 'feature extraction', 'supervised learning', 'unsupervised learning'],
    'Artificial Intelligence': ['artificial intelligence', 'ai', 'intelligent', 'automation', 'deep learning', 'nlp', 'computer vision'],
    'Data Science': ['data science', 'data analysis', 'statistics', 'data mining', 'big data', 'analytics', 'dataset', 'prediction'],
    'Python': ['python', 'python programming', 'pandas', 'numpy', 'scikit-learn', 'tensorflow', 'pytorch'],
    'Web Development': ['web', 'html', 'css', 'javascript', 'flask', 'django', 'react', 'frontend', 'backend', 'api', 'rest'],
    'Database': ['database', 'sql', 'mongodb', 'postgresql', 'mysql', 'nosql', 'query', 'schema'],
    'Cloud Computing': ['cloud', 'aws', 'azure', 'gcp', 'kubernetes', 'docker', 'microservices', 'serverless'],
    'Security': ['security', 'encryption', 'authentication', 'authorization', 'cybersecurity', 'ssl', 'password', 'firewall'],
    'Mobile Development': ['mobile', 'ios', 'android', 'flutter', 'react native', 'app development'],
    'Natural Language Processing': ['nlp', 'natural language', 'text processing', 'sentiment analysis', 'tokenization', 'embeddings'],
    'Computer Vision': ['computer vision', 'image processing', 'object detection', 'recognition', 'opencv'],
    'Disaster Management': ['disaster management', 'emergency response', 'risk assessment', 'preparedness', 'resilience'],
    'hazards': ['hazards', 'natural hazards', 'man-made hazards', 'risk', 'mitigation', 'vulnerability'],
    'Mathematics': ['mathematics', 'math', 'calculus', 'linear algebra', 'probability', 'geometry', 'equation'],
    'Physics': ['physics', 'quantum', 'mechanics', 'thermodynamics', 'relativity', 'force', 'energy'],
    'Chemistry': ['chemistry', 'chemical', 'molecule', 'compound', 'reaction', 'element', 'periodic table'],
    'Biology': ['biology', 'genetics', 'dna', 'cell', 'organism', 'evolution', 'ecosystem'],
    'Finance': ['finance', 'financial', 'investment', 'stock', 'portfolio', 'trading', 'cryptocurrency', 'bitcoin'],
    'Marketing': ['marketing', 'brand', 'advertising', 'campaign', 'customer', 'sales', 'seo', 'social media'],
    'Business': ['business', 'startup', 'enterprise', 'management', 'strategy', 'revenue', 'profit'],
    'Education': ['education', 'learning', 'teaching', 'student', 'course', 'school', 'university'],
}

def filter_noise(text):
    if not text:
        return text
    paragraphs = re.split(r'\n\s*\n', text)
    out_paras = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        for pattern in NOISE_PATTERNS:
            p = re.sub(pattern, '', p, flags=re.IGNORECASE)
        p = re.sub(r'\s+', ' ', p).strip()
        if p:
            out_paras.append(p)
    return '\n\n'.join(out_paras)

def split_text(text, max_words=CHUNK_MAX_WORDS):
    words = text.split()
    for i in range(0, len(words), max_words):
        yield " ".join(words[i:i + max_words])

def restore_punctuation_and_casing(text):
    if not text:
        return text
    paragraphs = re.split(r'\n\s*\n', text.strip())
    cleaned_paras = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        sentences = re.split(r'(?<=[\.\?\!])\s+', para)
        if len(sentences) == 1:
            sentences = re.split(r'\n+', para)
        cleaned = []
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            s = s[0].upper() + s[1:] if len(s) > 1 else s.upper()
            cleaned.append(s)
        cleaned_paras.append(' '.join(cleaned))
    return '\n\n'.join(cleaned_paras)

def _extract_text_from_segments(segments):
    parts = []
    for seg in segments:
        if not seg:
            continue
        if isinstance(seg, dict):
            txt = seg.get('text') or seg.get('sentence') or seg.get('words')
            if isinstance(txt, list):
                # join words list if present
                parts.append(' '.join([w.get('text', str(w)) if isinstance(w, dict) else str(w) for w in txt]))
            elif isinstance(txt, str):
                parts.append(txt)
            else:
                # try fields
                if 'text' in seg:
                    parts.append(seg['text'])
        else:
            # object with attributes
            txt = getattr(seg, 'text', None) or getattr(seg, 'sentence', None)
            if txt:
                parts.append(txt)
    return '\n\n'.join([p.strip() for p in parts if p and p.strip()])

def get_speaker_transcript(transcript_obj):
    """
    Robust extraction of plain text and speaker-segmented text from various transcript objects.
    Returns (speaker_segments, plain_text) - speaker_segments may be None.
    """
    if not transcript_obj:
        return None, ""
    
    words = None
    try:
        if isinstance(transcript_obj, dict):
            words = transcript_obj.get('words') or transcript_obj.get('word_level') or transcript_obj.get('word_timestamped')
        else:
            words = getattr(transcript_obj, 'words', None)
    except Exception:
        words = None

    if words:
        # build speaker segments
        segments = []
        current_speaker = None
        current_words = []
        for w in words:
            try:
                speaker = w.get('speaker') if isinstance(w, dict) else getattr(w, 'speaker', None)
                word_text = w.get('text') if isinstance(w, dict) else (getattr(w, 'text', None) or getattr(w, 'word', None) or str(w))
            except Exception:
                speaker = None
                word_text = str(w)
            if speaker != current_speaker:
                if current_words:
                    segments.append({'speaker': current_speaker, 'text': ' '.join(current_words)})
                current_speaker = speaker
                current_words = [word_text]
            else:
                current_words.append(word_text)
        if current_words:
            segments.append({'speaker': current_speaker, 'text': ' '.join(current_words)})
        plain_parts = [seg['text'].strip() for seg in segments if seg.get('text')]
        plain_text = '\n\n'.join(plain_parts)
        return segments, plain_text

    # Try segments field (common in many APIs)
    segments = None
    try:
        if isinstance(transcript_obj, dict):
            segments = transcript_obj.get('segments') or transcript_obj.get('results') or transcript_obj.get('utterances')
        else:
            segments = getattr(transcript_obj, 'segments', None) or getattr(transcript_obj, 'results', None) or getattr(transcript_obj, 'utterances', None)
    except Exception:
        segments = None

    if segments:
        plain_text = _extract_text_from_segments(segments)
        return None, plain_text

    # Try direct text field
    text_val = ""
    try:
        if isinstance(transcript_obj, dict):
            text_val = transcript_obj.get('text') or transcript_obj.get('transcript') or transcript_obj.get('full_text') or ""
        else:
            text_val = getattr(transcript_obj, 'text', None) or getattr(transcript_obj, 'transcript', None) or getattr(transcript_obj, 'full_text', None) or ""
        if text_val and isinstance(text_val, (str,)):
            return None, text_val
    except Exception:
        pass

    # Fallback: try to stringify
    try:
        return None, str(transcript_obj)
    except Exception:
        return None, ""

def extract_topics_and_tasks(text):
    if not text:
        return {'assignments': [], 'topics': []}
    sentences = [s.strip() for s in re.split(r'(?<=[\.\?\!])\s+', text) if s.strip()]
    assignments = []
    topics = []
    for s in sentences:
        lower = s.lower()
        for kw in ASSIGNMENT_KEYWORDS:
            if re.search(r'\b' + re.escape(kw) + r'\b', lower):
                assignments.append(s)
                break
        if re.search(r'\b(topic|today|lecture|we will|cover|discuss|chapter|section|concept|concepts)\b', lower):
            topics.append(s)
    assignments = list(dict.fromkeys(assignments))
    topics = list(dict.fromkeys(topics))
    return {'assignments': assignments, 'topics': topics}

def extract_recognized_topics(text):
    """
    Extract recognized topics from the transcript by matching keywords.
    Returns a list of identified topics like 'Machine Learning', 'Python', etc.
    """
    if not text:
        return []
    
    text_lower = text.lower()
    identified_topics = []
    
    # Check each topic and its keywords
    for topic, keywords in TOPIC_KEYWORDS.items():
        for keyword in keywords:
            # Use word boundary matching to avoid partial matches
            if re.search(r'\b' + re.escape(keyword) + r'\b', text_lower):
                identified_topics.append(topic)
                break  # Found this topic, move to next topic
    
    # Remove duplicates while preserving order
    identified_topics = list(dict.fromkeys(identified_topics))
    
    return identified_topics

def extract_topics_bertopic(text):
    model = get_topic_model()
    if model is None:
        return {'topics': [], 'sentence_topics': []}
    sentences = [s.strip() for s in re.split(r'(?<=[\.\?\!])\s+', text) if s.strip()]
    sentences = [s for s in sentences if len(s.split()) > 2]
    if not sentences:
        return {'topics': [], 'sentence_topics': []}
    topics, probs = model.fit_transform(sentences)
    topic_info = []
    info = model.get_topic_info()
    for row in info[info.Topic != -1].itertuples(index=False):
        tid = int(row.Topic)
        words = model.get_topic(tid)
        top_words = [w for w, _ in (words or [])][:6]
        topic_info.append({'topic_id': tid, 'n_docs': int(row.Count), 'top_words': top_words})
    sentence_topics = [{'sentence': s, 'topic': int(t)} for s, t in zip(sentences, topics)]
    return {'topics': topic_info, 'sentence_topics': sentence_topics}

def calculate_tf_idf_scores(sentences):
    """
    Calculate TF-IDF scores for sentences to identify importance.
    """
    from collections import Counter
    
    # Tokenize sentences
    tokenized = []
    for sent in sentences:
        words = re.findall(r'\b\w+\b', sent.lower())
        # Remove common stop words
        words = [w for w in words if len(w) > 3 and w not in 
                ['that', 'this', 'with', 'from', 'have', 'will', 'just', 'more', 'been', 'were', 'also', 'than', 'they', 'them', 'such', 'into']]
        tokenized.append(words)
    
    # Calculate IDF
    doc_frequency = Counter()
    for words in tokenized:
        doc_frequency.update(set(words))
    
    idf = {}
    total_docs = len(tokenized)
    for word, freq in doc_frequency.items():
        idf[word] = math.log(total_docs / freq)
    
    
    tf_idf_scores = []
    for words in tokenized:
        if not words:
            tf_idf_scores.append(0)
            continue
        score = sum(idf.get(w, 0) for w in words) / len(words)
        tf_idf_scores.append(score)
    
    return tf_idf_scores

def calculate_semantic_similarity(sent1, sent2):
    """
    Simple word overlap-based similarity to filter redundant key points.
    """
    words1 = set(re.findall(r'\b\w+\b', sent1.lower()))
    words2 = set(re.findall(r'\b\w+\b', sent2.lower()))
    
    if not words1 or not words2:
        return 0
    
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0

def extract_key_points(text, num_points=5):
    """
    Extract key points using improved TF-IDF + position + keyword scoring.
    Filters redundant points for better quality.
    """
    if not text:
        return []
    
    sentences = [s.strip() for s in re.split(r'(?<=[\.\?\!])\s+', text) if s.strip()]
    
    
    sentences = [s for s in sentences if 5 < len(s.split()) < 100]
    
    if not sentences:
        return []
    
    
    tf_idf_scores = calculate_tf_idf_scores(sentences)
    
    
    scored_sentences = []
    important_keywords = ['important', 'key', 'remember', 'note', 'must', 'should', 'critical',
                         'essential', 'significant', 'requirement', 'deadline', 'task', 'project',
                         'assignment', 'quiz', 'test', 'exam', 'topic', 'concept', 'define',
                         'explain', 'example', 'however', 'therefore', 'furthermore', 'conclusion',
                         'summary', 'final', 'achieve', 'objective', 'goal']
    
    for i, sent in enumerate(sentences):
        score = 0
        words = sent.lower().split()
        
        
        score += tf_idf_scores[i] * 0.4
        
       
        if i < 2:
            score += 2 * 0.2
        elif i < len(sentences) / 3:
            score += 0.8 * 0.2
        else:
            score += 0.3 * 0.2
        
        keyword_count = sum(1 for kw in important_keywords if kw in sent.lower())
        score += min(keyword_count * 0.1, 0.3)
        
        
        word_count = len(words)
        if 8 <= word_count <= 25:
            score += 0.1
        
        scored_sentences.append((sent, score))
    
    
    scored_sentences.sort(key=lambda x: x[1], reverse=True)
    
    
    selected_points = []
    for sent, score in scored_sentences:
        is_redundant = False
        for selected_sent, _ in selected_points:
            if calculate_semantic_similarity(sent, selected_sent) > 0.6:
                is_redundant = True
                break
        
        if not is_redundant and score > 0:
            selected_points.append((sent, score))
        
        if len(selected_points) >= num_points:
            break
    
    # Restore original order for readability
    selected_points.sort(key=lambda x: sentences.index(x[0]))
    
    return [sent for sent, _ in selected_points]

def summarize_text(cleaned):
    """
    Improved summarization that creates more complete summaries.
    Uses multi-chunk summarization to preserve all key information.
    """
    if not cleaned or len(cleaned.split()) < 50:
        return cleaned[:500] if cleaned else ""
    
    summaries = []
    total_words = len(cleaned.split())
    summarizer = get_summarizer()
    
    # Calculate dynamic summary length based on input
    target_summary_words = max(int(total_words * SUMMARY_RATIO), SUMMARY_MIN)
    target_summary_words = min(target_summary_words, SUMMARY_MAX)
    
    for chunk in split_text(cleaned, max_words=CHUNK_MAX_WORDS):
        if not chunk.strip() or len(chunk.split()) < 15:  # Lower threshold
            continue
        
        try:
            # Dynamically adjust summary length per chunk
            chunk_words = len(chunk.split())
            chunk_target_min = max(int(chunk_words * 0.35), 50)  # Increased from 0.25
            chunk_target_max = min(int(chunk_words * 0.60), 200)  # Increased from 0.45
            
            out = summarizer(
                chunk,
                max_length=chunk_target_max,
                min_length=chunk_target_min,
                do_sample=False,
                truncation=True
            )
            stext = out[0].get('summary_text', '') if isinstance(out, list) else str(out)
            summaries.append(stext.strip())
        except Exception as e:
            print("Summarizer error:", e)
            # Fallback: extract important sentences from chunk
            sentences = re.split(r'(?<=[\.\?\!])\s+', chunk)
            # Get first and potentially middle sentences for better coverage
            num_sents = min(4, len(sentences))
            fallback = ' '.join(sentences[:num_sents])
            if fallback.strip():
                summaries.append(fallback.strip())
    
    final_summary = " ".join(summaries).strip()
    
    # Only trim if significantly longer than target (30% over)
    if len(final_summary.split()) > target_summary_words * 1.3:
        # Use extractive summarization to trim intelligently
        key_sents = extract_key_points(final_summary, num_points=min(6, int(target_summary_words / 20)))
        if key_sents:
            final_summary = " ".join(key_sents)
    
    return final_summary

def download_youtube_audio(url, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    if YTDLP_AVAILABLE:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(out_dir, '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                if os.path.exists(filename):
                    return filename
                for ext in ('m4a','mp3','webm','mkv','wav','aac','opus'):
                    candidate = os.path.splitext(filename)[0] + '.' + ext
                    if os.path.exists(candidate):
                        return candidate
                raise Exception("yt-dlp downloaded file not found")
        except Exception as e:
            raise Exception(f"yt-dlp error: {e}")
    if PYTUBE_AVAILABLE:
        try:
            yt = YouTube(url)
            audio_stream = yt.streams.filter(only_audio=True).order_by('abr').desc().first()
            out_file = audio_stream.download(output_path=out_dir)
            return out_file
        except Exception as e:
            raise Exception(f"pytube error: {e}")
    raise Exception("No downloader available (install yt-dlp or pytube)")

@app.route('/')
def index():
    if session.get('loggedIn'):
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('loggedIn'):
        return redirect('/')
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    # Simple demo authentication
    if username == 'demo' and password == 'password123':
        session['loggedIn'] = True
        session['username'] = username
        return jsonify({'success': True, 'message': 'Login successful'})
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    filename = secure_filename(file.filename)
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    api_key = os.environ.get('ASSEMBLYAI_API_KEY', "9bbfc833b5ea4628acc1fa5f289d6b77")
    if not api_key:
        return jsonify({'error': 'Server missing ASSEMBLYAI_API_KEY environment variable'}), 500
    aai.settings.api_key = api_key

    try:
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(filepath)
    except Exception as e:
        # make sure file is removed and return error
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': f'Transcription failed: {e}'}), 500

    if transcript is None:
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': 'Transcription returned no result'}), 500

    # defensive: check error status
    try:
        if getattr(transcript, 'status', None) == aai.TranscriptStatus.error or (isinstance(transcript, dict) and transcript.get('status') == 'error'):
            err = getattr(transcript, 'error', None) or (transcript.get('error') if isinstance(transcript, dict) else None)
            try:
                os.remove(filepath)
            except Exception:
                pass
            return jsonify({'error': str(err) or 'Transcription service returned error'}), 500
    except Exception:
        pass

    _, plain_text = get_speaker_transcript(transcript)
    if not plain_text:
        # try to pull text attribute explicitly
        try:
            if isinstance(transcript, dict):
                plain_text = transcript.get('text') or transcript.get('transcript') or ''
            else:
                plain_text = getattr(transcript, 'text', '') or getattr(transcript, 'transcript', '') or ''
        except Exception:
            plain_text = ''

    cleaned = filter_noise(plain_text or "")
    cleaned = restore_punctuation_and_casing(cleaned or "")

    final_summary = summarize_text(cleaned or "")
    key_points = extract_key_points(cleaned or "")
    topic_info = extract_topics_and_tasks(cleaned or "")
    recognized_topics = extract_recognized_topics(cleaned or "")
    bert_info = extract_topics_bertopic(cleaned or "") if BERTOPIC_AVAILABLE else {'topics': [], 'sentence_topics': []}

    # remove uploaded file
    try:
        os.remove(filepath)
    except Exception:
        pass

    return jsonify({
        'transcript': cleaned or "",
        'summary': final_summary or "",
        'key_points': key_points or [],
        'recognized_topics': recognized_topics or [],
        'assignments': topic_info['assignments'],
        'topics': bert_info['topics'] or topic_info['topics'],
        'sentence_topics': bert_info.get('sentence_topics', [])
    })

@app.route('/youtube', methods=['POST'])
def youtube_summarize():
    data = request.get_json() or {}
    # accept either 'youtube_url' or 'url' for compatibility
    url = data.get('youtube_url') or data.get('url') or data.get('youtube') or data.get('link')
    if not url:
        return jsonify({'error': 'No YouTube URL provided'}), 400
    try:
        filepath = download_youtube_audio(url, app.config['UPLOAD_FOLDER'])
    except Exception as e:
        return jsonify({'error': f'Error downloading YouTube audio: {e}'}), 500

    api_key = os.environ.get('ASSEMBLYAI_API_KEY', "9bbfc833b5ea4628acc1fa5f289d6b77")
    if not api_key:
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': 'Server missing ASSEMBLYAI_API_KEY environment variable'}), 500
    aai.settings.api_key = api_key

    try:
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(filepath)
    except Exception as e:
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': f'Transcription failed: {e}'}), 500

    if transcript is None:
        try:
            os.remove(filepath)
        except Exception:
            pass
        return jsonify({'error': 'Transcription returned no result'}), 500

    try:
        if getattr(transcript, 'status', None) == aai.TranscriptStatus.error or (isinstance(transcript, dict) and transcript.get('status') == 'error'):
            err = getattr(transcript, 'error', None) or (transcript.get('error') if isinstance(transcript, dict) else None)
            try:
                os.remove(filepath)
            except Exception:
                pass
            return jsonify({'error': str(err) or 'Transcription service returned error'}), 500
    except Exception:
        pass

    _, plain_text = get_speaker_transcript(transcript)
    if not plain_text:
        try:
            if isinstance(transcript, dict):
                plain_text = transcript.get('text') or transcript.get('transcript') or ''
            else:
                plain_text = getattr(transcript, 'text', '') or getattr(transcript, 'transcript', '') or ''
        except Exception:
            plain_text = ''

    cleaned = filter_noise(plain_text or "")
    cleaned = restore_punctuation_and_casing(cleaned or "")

    final_summary = summarize_text(cleaned or "")
    key_points = extract_key_points(cleaned or "")
    topic_info = extract_topics_and_tasks(cleaned or "")
    recognized_topics = extract_recognized_topics(cleaned or "")
    bert_info = extract_topics_bertopic(cleaned or "") if BERTOPIC_AVAILABLE else {'topics': [], 'sentence_topics': []}

    try:
        os.remove(filepath)
    except Exception:
        pass

    return jsonify({
        'transcript': cleaned or "",
        'summary': final_summary or "",
        'key_points': key_points or [],
        'recognized_topics': recognized_topics or [],
        'assignments': topic_info['assignments'],
        'topics': bert_info['topics'] or topic_info['topics'],
        'sentence_topics': bert_info.get('sentence_topics', [])
    })

if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
