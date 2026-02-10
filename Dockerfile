FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt upgrade -y && \
    apt install -y --no-install-recommends \
        python3 python3-pip ffmpeg curl unzip ca-certificates tini wget \
        libsndfile1 portaudio19-dev && \
    apt clean && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
        fastapi uvicorn python-multipart soundfile numpy pillow tqdm requests && \
    pip3 install --no-cache-dir "kokoro-onnx" --break-system-packages

WORKDIR /app
RUN mkdir -p /app/tmp /models/kokoro

# Download Kokoro v1.0 models from nazdridoy's reliable mirror
RUN echo "📦 Downloading Kokoro v1.0 models..." && \
    wget -O /models/kokoro/kokoro-v1.0.onnx "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/kokoro-v1.0.onnx" && \
    wget -O /models/kokoro/voices-v1.0.bin "https://github.com/nazdridoy/kokoro-tts/releases/download/v1.0.0/voices-v1.0.bin" && \
    ls -lh /models/kokoro/ && \
    echo "✅ Kokoro models downloaded!"

COPY <<'EOF' /app/api.py
from fastapi import FastAPI, Form, Header, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import subprocess, os, traceback, uuid, threading, re
from datetime import datetime
from typing import Dict, Optional, List
from kokoro_onnx import Kokoro

app = FastAPI(title="FFmpeg + KokoroTTS API", version="4.2.0")

API_KEY = os.getenv("API_KEY", "changeme123")
BASE_URL = os.getenv("BASE_URL", "https://example.com")
TMP_DIR = "/app/tmp"
MODEL_PATH = "/models/kokoro/kokoro-v1.0.onnx"
VOICES_PATH = "/models/kokoro/voices-v1.0.bin"
os.makedirs(TMP_DIR, exist_ok=True)

# Job storage
jobs: Dict[str, dict] = {}
jobs_lock = threading.Lock()

# Concurrent job limiting
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
running_jobs_semaphore = threading.Semaphore(MAX_CONCURRENT_JOBS)

# All available voices from Kokoro v1.0 (54 voices across 9 languages)
AVAILABLE_VOICES = [
    # American English (20 voices)
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", 
    "am_michael", "am_onyx", "am_puck", "am_santa",
    
    # British English (8 voices)
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    
    # Japanese (5 voices)
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    
    # Mandarin Chinese (8 voices)
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
    
    # Spanish (3 voices)
    "ef_dora", "em_alex", "em_santa",
    
    # French (1 voice)
    "ff_siwis",
    
    # Hindi (4 voices)
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi",
    
    # Italian (2 voices)
    "if_sara", "im_nicola",
    
    # Brazilian Portuguese (3 voices)
    "pf_dora", "pm_alex", "pm_santa"
]

kokoro_engine = None
try:
    print(f"🔧 Loading Kokoro from {MODEL_PATH}")
    print(f"🔧 Voices file: {VOICES_PATH}")
    kokoro_engine = Kokoro(model_path=MODEL_PATH, voices_path=VOICES_PATH)
    samples, sample_rate = kokoro_engine.create(text="Init", voice="af_bella")
    print(f"✅ KokoroTTS OK - {len(AVAILABLE_VOICES)} voices loaded")
except Exception as e:
    print(f"⚠️ Kokoro failed: {e}")
    traceback.print_exc()

def check_api_key(x_api_key: str):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

def update_job_status(job_id: str, status: str, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = status
            jobs[job_id].update(kwargs)

def extract_output_files(cmd: str) -> List[str]:
    """
    Extract output file names from FFmpeg command.
    Looks for files after common output patterns.
    """
    output_files = []
    
    # Common patterns for output files in FFmpeg commands
    # Pattern 1: Files without input flags (-i, -f, -filter_complex, etc.)
    # Pattern 2: Last file in the command (usually the output)
    
    # Split command into tokens
    tokens = cmd.split()
    
    # Flags that indicate the next token is NOT an output file
    input_flags = {'-i', '-f', '-c', '-codec', '-vcodec', '-acodec', '-b', '-r', 
                   '-ar', '-ac', '-filter', '-filter_complex', '-map', '-ss', '-t',
                   '-vf', '-af', '-s', '-pix_fmt', '-profile', '-level', '-preset',
                   '-crf', '-maxrate', '-bufsize', '-g', '-keyint_min', '-sc_threshold',
                   '-b:v', '-b:a', '-codec:v', '-codec:a', '-filter:v', '-filter:a'}
    
    # Track files that appear after output-indicative positions
    skip_next = False
    for i, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
            
        if token.startswith('-'):
            if token in input_flags:
                skip_next = True
            continue
        
        # Check if token looks like a file (has extension)
        if '.' in token and not token.startswith('-'):
            # Get just the filename without path
            filename = os.path.basename(token.strip('"').strip("'"))
            if filename and not filename.startswith('-'):
                output_files.append(filename)
    
    # Also try to find the last file mentioned (usually output in FFmpeg)
    file_pattern = r'(?:^|\s)([^\s-][^\s]*\.[a-zA-Z0-9]{2,4})(?:\s|$|")'
    matches = re.findall(file_pattern, cmd)
    if matches:
        last_file = os.path.basename(matches[-1].strip('"').strip("'"))
        if last_file not in output_files:
            output_files.append(last_file)
    
    return output_files if output_files else None

def detect_created_files(before_files: List[str], after_files: List[str]) -> List[str]:
    """Detect newly created files by comparing before and after file lists."""
    return [f for f in after_files if f not in before_files]

def run_ffmpeg_job(job_id: str, cmd: str):
    """Execute FFmpeg command in background and detect output files"""
    with running_jobs_semaphore:
        try:
            update_job_status(job_id, "running")
            
            # Get file list before execution
            files_before = set(os.listdir(TMP_DIR))
            
            # Execute FFmpeg
            result = subprocess.run(
                ["bash", "-c", f"ffmpeg {cmd}"],
                capture_output=True,
                text=True,
                cwd=TMP_DIR
            )
            
            # Get file list after execution
            files_after = set(os.listdir(TMP_DIR))
            
            # Detect newly created files
            new_files = list(files_after - files_before)
            
            if result.returncode == 0:
                # Try to extract output files from command
                extracted_outputs = extract_output_files(cmd)
                
                # Prefer extracted outputs, fallback to detected new files
                output_files = []
                if extracted_outputs:
                    # Verify extracted files exist
                    for f in extracted_outputs:
                        if f in new_files:
                            output_files.append(f)
                
                if not output_files:
                    output_files = new_files
                
                # Build response
                response = {
                    "stdout": result.stdout,
                    "output_files": output_files
                }
                
                # If single output file, add convenience fields
                if len(output_files) == 1:
                    response["output_file"] = output_files[0]
                    response["download_url"] = f"{BASE_URL}/download/{output_files[0]}"
                elif len(output_files) > 1:
                    response["download_urls"] = [f"{BASE_URL}/download/{f}" for f in output_files]
                
                update_job_status(job_id, "completed", **response)
            else:
                update_job_status(job_id, "failed", error=result.stderr)
        except Exception as e:
            update_job_status(job_id, "failed", error=str(e))

def run_tts_job(job_id: str, text: str, voice: str, speed: float, volume: float, format: str):
    """Execute TTS generation in background"""
    with running_jobs_semaphore:
        try:
            update_job_status(job_id, "running")
            k = kokoro_engine or Kokoro(model_path=MODEL_PATH, voices_path=VOICES_PATH)
            output_filename = f"tts_{job_id}.{format}"
            output = os.path.join(TMP_DIR, output_filename)
            
            # Generate TTS
            import soundfile as sf
            samples, sample_rate = k.create(text=text, voice=voice, speed=speed)
            sf.write(output, samples, sample_rate)
            
            # Apply volume adjustment if needed
            if volume != 1.0:
                adjusted = output.replace(f".{format}", f"_vol.{format}")
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", output, "-filter:a", f"volume={volume}", adjusted],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    os.remove(output)
                    output = adjusted
                    output_filename = os.path.basename(adjusted)
            
            update_job_status(
                job_id, 
                "completed", 
                output_file=output_filename,
                download_url=f"{BASE_URL}/download/{output_filename}",
                sample_rate=sample_rate
            )
        except Exception as e:
            update_job_status(job_id, "failed", error=str(e))

@app.get("/")
def root():
    return {
        "status": "✅ Ready", 
        "version": "4.2.0", 
        "kokoro_loaded": kokoro_engine is not None,
        "total_voices": len(AVAILABLE_VOICES),
        "ffmpeg_available": subprocess.run(["which", "ffmpeg"], capture_output=True).returncode == 0,
        "active_jobs": len([j for j in jobs.values() if j["status"] == "running"]),
        "max_concurrent_jobs": MAX_CONCURRENT_JOBS,
        "available_slots": MAX_CONCURRENT_JOBS - len([j for j in jobs.values() if j["status"] == "running"])
    }

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/voices")
def list_voices(x_api_key: str = Header(None)):
    check_api_key(x_api_key)
    return {
        "voices": AVAILABLE_VOICES,
        "total": len(AVAILABLE_VOICES),
        "languages": {
            "American English": 20,
            "British English": 8,
            "Japanese": 5,
            "Mandarin Chinese": 8,
            "Spanish": 3,
            "French": 1,
            "Hindi": 4,
            "Italian": 2,
            "Brazilian Portuguese": 3
        }
    }

@app.post("/tts")
def tts(
    background_tasks: BackgroundTasks,
    text: str = Form(...), 
    voice: str = Form("af_bella"), 
    speed: float = Form(1.0), 
    volume: float = Form(1.0), 
    format: str = Form("wav"), 
    x_api_key: str = Header(None)
):
    check_api_key(x_api_key)
    if not text.strip(): 
        raise HTTPException(400, "Empty text")
    if voice not in AVAILABLE_VOICES:
        raise HTTPException(400, f"Invalid voice '{voice}'. Use GET /voices to see all available voices.")
    
    # Create job
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "type": "tts",
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "text": text,
            "voice": voice,
            "speed": speed,
            "volume": volume,
            "format": format
        }
    
    # Start background task
    background_tasks.add_task(run_tts_job, job_id, text, voice, speed, volume, format)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "check_status_url": f"{BASE_URL}/job/{job_id}"
    }

@app.post("/ffmpeg")
def ffmpeg_async(
    background_tasks: BackgroundTasks,
    cmd: str = Form(...), 
    x_api_key: str = Header(None)
):
    """Execute FFmpeg command asynchronously"""
    check_api_key(x_api_key)
    
    # Create job
    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "job_id": job_id,
            "type": "ffmpeg",
            "status": "queued",
            "created_at": datetime.now().isoformat(),
            "command": cmd
        }
    
    # Start background task
    background_tasks.add_task(run_ffmpeg_job, job_id, cmd)
    
    return {
        "status": "queued",
        "job_id": job_id,
        "check_status_url": f"{BASE_URL}/job/{job_id}"
    }

@app.get("/job/{job_id}")
def get_job_status(job_id: str, x_api_key: str = Header(None)):
    """Check job status"""
    check_api_key(x_api_key)
    
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(404, "Job not found")
        return jobs[job_id]

@app.get("/jobs")
def list_jobs(x_api_key: str = Header(None)):
    """List all jobs"""
    check_api_key(x_api_key)
    
    with jobs_lock:
        return {
            "jobs": list(jobs.values()),
            "total": len(jobs)
        }

@app.delete("/job/{job_id}")
def delete_job(job_id: str, x_api_key: str = Header(None)):
    """Delete a job from history"""
    check_api_key(x_api_key)
    
    with jobs_lock:
        if job_id in jobs:
            del jobs[job_id]
            return {"deleted": job_id}
        raise HTTPException(404, "Job not found")

@app.post("/run")
def run_ffmpeg(cmd: str = Form(...), x_api_key: str = Header(None)):
    """Execute FFmpeg command synchronously (legacy endpoint)"""
    check_api_key(x_api_key)
    result = subprocess.run(["bash", "-c", f"ffmpeg {cmd}"], capture_output=True, text=True, cwd=TMP_DIR)
    if result.returncode != 0: 
        raise HTTPException(500, result.stderr)
    return {"status": "ok", "stdout": result.stdout}

@app.get("/list-files")
def list_files(x_api_key: str = Header(None)):
    check_api_key(x_api_key)
    return {"files": os.listdir(TMP_DIR)}

@app.get("/download/{filename}")
def download(filename: str):
    path = os.path.join(TMP_DIR, filename)
    if not os.path.exists(path): 
        raise HTTPException(404, "Not found")
    return FileResponse(path, filename=filename)

@app.delete("/delete/{filename}")
def delete(filename: str, x_api_key: str = Header(None)):
    check_api_key(x_api_key)
    path = os.path.join(TMP_DIR, filename)
    if os.path.exists(path): 
        os.remove(path)
    return {"deleted": filename}
EOF

ENV API_KEY=changeme123
ENV BASE_URL=https://example.com
ENV SERVER_PORT=8088
ENV MAX_CONCURRENT_JOBS=2

EXPOSE 8088
VOLUME ["/models/kokoro", "/app/tmp"]

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8088", "--log-level", "info"]
