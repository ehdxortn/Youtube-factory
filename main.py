"""
SOVEREIGN APEX v47 — 100% HANDS-OFF AUTOMATION ENGINE
=====================================
- 텔레그램 의존성 완전 제거 (Pure API Endpoint)
- Google Cloud Run + Cloud Scheduler 구동 최적화
- Cinematic Retention Engine (pydub, Anti-pattern, Hook DB) 탑재
"""

import os, json, asyncio, logging, httpx, re, time, random
from datetime import datetime, timezone
from typing import Optional, List, Literal, TypedDict
from pydantic import BaseModel, Field

from fastapi import FastAPI, BackgroundTasks
from pydub import AudioSegment

import litellm
from litellm import acompletion
from langgraph.graph import StateGraph, END

# --- Langfuse ---
try:
    from langfuse import Langfuse
    from langfuse.decorators import observe, langfuse_context
except ImportError:
    class DummyLangfuseContext:
        def update_current_observation(self, **kwargs): pass
    langfuse_context = DummyLangfuseContext()
    def observe(**kwargs):
        def decorator(func): return func
        return decorator
    Langfuse = None

from openai import AsyncOpenAI
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
import moviepy.audio.fx.all as afx
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ============================================================
# 0. 환경 설정 및 시스템 변수
# ============================================================
LITELLM_GPT        = "openai/gpt-5.4"
LITELLM_CLAUDE     = "claude-sonnet-4-6"  
LITELLM_GEMINI     = "gemini/gemini-3.1-pro"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SSULTUBE-AUTORUN")

def get_env(k, default=""):
    return os.environ.get(k, default)

litellm.set_verbose = False
os.environ["OPENAI_API_KEY"]    = get_env("OPENAI_API_KEY")
os.environ["ANTHROPIC_API_KEY"] = get_env("ANTHROPIC_API_KEY")
os.environ["GEMINI_API_KEY"]    = get_env("GEMINI_API_KEY")

if Langfuse:
    langfuse = Langfuse(public_key=get_env("LANGFUSE_PUBLIC_KEY"), secret_key=get_env("LANGFUSE_SECRET_KEY"), host="https://cloud.langfuse.com")

app = FastAPI()
openai_client = AsyncOpenAI(api_key=get_env("OPENAI_API_KEY"))

# ============================================================
# 1. 훅(Hook) DB & 프롬프트 시스템
# ============================================================
used_hooks = set()
CATEGORIZED_HOOK_DB = {
    "가족_시댁갈등": [
        "시어머니가 내 이름으로 20억 대출을 받은 걸 알게 된 건, 우편함에 꽂힌 압류 통지서를 본 날이었습니다.",
        "치매 걸린 시아버지를 10년 모셨는데, 유산 50억은 얼굴 한 번 안 비친 시누이에게 넘어갔습니다."
    ],
    "배신_불륜": [
        "15년 지기 절친이 내 남편과 나눈 카톡을, 딸아이의 낡은 태블릿에서 발견했습니다.",
        "은퇴 자금을 몽땅 털어 산 아파트, 그 계약서에 찍힌 도장이 가짜라는 걸 입주 전날 알았습니다."
    ],
    "사이다_참교육": [
        "내 재산을 다 빼돌리고 야반도주한 전 남편이, 오늘 내가 운영하는 식당에 일용직 면접을 보러 왔습니다.",
        "가난하다고 날 벌레 보듯 하던 동서가 쫄딱 망해 길거리에 나앉은 날, 나는 그들이 살던 집을 현찰로 매입했습니다."
    ]
}

def get_unique_hook(category: str) -> str:
    global used_hooks
    available = [h for h in CATEGORIZED_HOOK_DB.get(category, CATEGORIZED_HOOK_DB["사이다_참교육"]) if h not in used_hooks]
    if not available:
        used_hooks.clear()
        available = CATEGORIZED_HOOK_DB.get(category, CATEGORIZED_HOOK_DB["사이다_참교육"])
    hook = random.choice(available)
    used_hooks.add(hook)
    return hook

HARNESS_CONTEXT = """[SSUL-TUBE HARNESS SYSTEM CORE RULES]
1. 비식별화 및 검열 우회 100% 적용.
2. 시각적 일관성: image_prompt에 "Korean webtoon style, dramatic shading" 유지.
3. 순수 JSON 포맷 강제 (마크다운 금지)."""

WRITER_SYSTEM_PROMPT = """[WRITER CORE DIRECTIVE: RADIO DOCUMENTARY ENGINE]
당신은 '그것이 알고싶다' 스타일의 베테랑 작가입니다. 4050 타겟 1인칭 사연자 시점 대본을 작성합니다.

[RETENTION & IMMERSION RULES]
1. Humanization (인간화): "그러니까 제 말은...", "참 기가 막히게도..." 처럼 구어체 노이즈 15% 믹싱.
2. Retention Spike: 매 30초 분량마다 '충격 포인트'를 던져 긴장감 유발.
3. Audio Immersion: "그때였습니다.", "순간, 등골이 서늘해졌습니다." 적극 활용.

[구조 설계]
- Hook: 반드시 제시된 '첫 문장'으로 시작.
- 본론: 갈등의 고조 (Information Gap 유지)
- 결말: 선정성/폭력성 없는 합법적이고 통쾌한 참교육. (살인/폭력/성적 묘사 절대 금지)

*주의: 성우가 호흡을 쉴 수 있도록 문단(씬)은 짧게 나누어 [PAUSE] 기호로 구분해 주십시오. 
예시: "믿을 수 없었습니다. [PAUSE] 그 안에는..."
"""

# ============================================================
# 2. Pydantic 스키마 및 State
# ============================================================
class SceneItem(BaseModel):
    scene_no: int
    tts_text: str
    subtitle: str = Field(description="압축 자막 (15자 이내)")
    image_prompt: str
    zoom_mode: Literal["in", "out"]

class SsulBlueprint(BaseModel):
    title: str
    seo_tags: List[str]
    thumbnail_prompt: str
    scenes: List[SceneItem]

class FactoryState(TypedDict):
    category: str
    keyword: Optional[str]
    character: Optional[str]
    raw_script: Optional[str]
    safe_script: Optional[str]
    blueprint: Optional[dict]
    error: Optional[str]

def safe_json_extract(text: str) -> Optional[dict]:
    try:
        text = re.sub(r"```json|```", "", text).strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and start < end:
            return json.loads(text[start:end+1])
    except: pass
    return None

# ============================================================
# 3. LangGraph 노드
# ============================================================
@observe(name="factory_llm_call")
async def llm_call(model: str, system: str, payload: str, temp: float = 0.7, tokens: int = 2500) -> str:
    res = await acompletion(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": payload}], temperature=temp, max_tokens=tokens)
    return res.choices[0].message.content

async def node_sourcing(state: FactoryState) -> FactoryState:
    categories = list(CATEGORIZED_HOOK_DB.keys())
    state["category"] = random.choice(categories)
    try:
        res = await llm_call(LITELLM_GPT, HARNESS_CONTEXT, f"[{state['category']}] 카테고리에 맞는 4050 타겟 자극적 썰 소재 1줄, 주인공 페르소나 1줄 작성.", 0.9, 300)
        lines = res.strip().split('\n')
        state["keyword"] = lines[0] if len(lines) > 0 else "믿었던 가족의 배신"
        state["character"] = lines[1] if len(lines) > 1 else "차분한 40대 가장"
    except Exception as e:
        state["keyword"], state["character"] = "남편의 빚 20억", "복수를 다짐하는 아내"
    return state

async def node_writer(state: FactoryState) -> FactoryState:
    try:
        selected_hook = get_unique_hook(state["category"])
        payload = f"""주제: {state['keyword']}
주인공 페르소나: {state['character']}
[특별 지시사항]
1. 대본의 **첫 번째 문장**은 반드시 다음 문장으로 시작하십시오: "{selected_hook}"
2. 씬(Scene) 분할 시 1개 씬당 내레이션은 60~90초 분량으로 맞추십시오."""
        state["raw_script"] = await llm_call(LITELLM_GPT, WRITER_SYSTEM_PROMPT, payload, 0.7, 3000)
    except Exception as e: state["error"] = f"대본 작성 에러: {e}"
    return state

async def node_cro(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        state["safe_script"] = await llm_call(LITELLM_CLAUDE, HARNESS_CONTEXT, f"유튜브 검열 위험 단어 우회.\n대본: {state['raw_script']}", 0.2, 2500)
    except Exception as e: state["error"] = f"검열 에러: {e}"
    return state

async def node_pd_harness(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    sys_prompt = f"{HARNESS_CONTEXT}\n총괄 PD로서 대본을 영상 렌더링용 JSON으로 구조화.\n스키마: title, seo_tags, thumbnail_prompt, scenes (scene_no, tts_text, subtitle, image_prompt, zoom_mode)"
    payload = f"대본: {state['safe_script']}"
    for _ in range(3):
        try:
            parsed = safe_json_extract(await llm_call(LITELLM_GEMINI, sys_prompt, payload, 0.1, 2000))
            if parsed:
                state["blueprint"] = SsulBlueprint(**parsed).model_dump()
                return state
        except: payload = f"에러 발생. 수정된 완벽한 JSON 재출력.\n대본: {state['safe_script']}"
    state["error"] = "PD 교정 루프 실패"
    return state

PIPELINE = StateGraph(FactoryState)
PIPELINE.add_node("sourcing", node_sourcing)
PIPELINE.add_node("writer",   node_writer)
PIPELINE.add_node("cro",      node_cro)
PIPELINE.add_node("pd",       node_pd_harness)
PIPELINE.set_entry_point("sourcing")
PIPELINE.add_edge("sourcing", "writer")
PIPELINE.add_edge("writer",   "cro")
PIPELINE.add_edge("cro",      "pd")
PIPELINE.add_edge("pd",       END)
PIPELINE = PIPELINE.compile()

# ============================================================
# 4. 시네마틱 렌더링 엔진 (Cinematic TTS & MoviePy)
# ============================================================
async def generate_dalle_image(prompt: str, file_name: str) -> str:
    try:
        res = await openai_client.images.generate(model="dall-e-3", prompt=prompt, size="1024x576", quality="hd", n=1)
        async with httpx.AsyncClient() as c:
            with open(file_name, 'wb') as f: f.write((await c.get(res.data[0].url)).content)
        return file_name
    except: return ""

async def generate_cinematic_tts(text: str, scene_no: int) -> str:
    final_path = f"scene_{scene_no}_final.mp3"
    chunks = [c.strip() for c in text.split("[PAUSE]") if c.strip()]
    chunk_files = []
    try:
        for i, chunk_text in enumerate(chunks):
            c_path = f"temp_scene_{scene_no}_part_{i}.mp3"
            (await openai_client.audio.speech.create(model="tts-1", voice="nova", input=chunk_text)).stream_to_file(c_path)
            chunk_files.append(c_path)
            
        combined = AudioSegment.empty()
        silence = AudioSegment.silent(duration=800)
        for i, f_path in enumerate(chunk_files):
            combined += AudioSegment.from_mp3(f_path)
            if i < len(chunk_files) - 1: combined += silence
                
        combined.export(final_path, format="mp3")
        for f in chunk_files: os.remove(f)
        return final_path
    except Exception as e:
        logger.error(f"TTS 에러: {e}")
        return ""

def create_zoom_effect(clip, duration, mode="in", zoom_ratio=0.05):
    def effect(get_frame, t):
        scale = 1.0 + (zoom_ratio * (t / duration)) if mode == "in" else 1.0 + zoom_ratio - (zoom_ratio * (t / duration))
        return ImageClip(get_frame(t)).resize(scale).get_frame(t)
    return clip.fl(effect)

def render_final_video(blueprint: dict, img_paths: list, audio_paths: list, out_name: str) -> str:
    logger.info("🎬 영상 렌더링 시작...")
    try:
        font_path = "NanumGothic" 
        clips = []
        for i, scene in enumerate(blueprint.get("scenes", [])):
            if i >= len(img_paths) or i >= len(audio_paths): break
            audio_clip = AudioFileClip(audio_paths[i])
            dur = audio_clip.duration
            
            img_clip = ImageClip(img_paths[i]).set_duration(dur)
            img_clip = create_zoom_effect(img_clip, dur, scene.get("zoom_mode", "in"), zoom_ratio=random.uniform(0.03, 0.08))
            img_clip = img_clip.set_position("center").on_color(size=(1920, 1080), color=(0,0,0))
            
            txt_clip = TextClip(scene.get("subtitle", ""), fontsize=random.choice([60, 65, 70]), color='white', font=font_path, stroke_color='black', stroke_width=2)
            txt_clip = txt_clip.set_position(('center', 'bottom')).margin(bottom=random.choice([80, 100, 120]), opacity=0).set_duration(dur)
            
            clips.append(CompositeVideoClip([img_clip, txt_clip], size=(1920, 1080)).set_audio(audio_clip))
            
        final_video = concatenate_videoclips(clips, method="compose")
        
        bgm_path = "bgm_tense.mp3"
        if os.path.exists(bgm_path):
            bgm = AudioFileClip(bgm_path).fx(afx.volumex, random.uniform(0.06, 0.1)).fx(afx.audio_loop, duration=final_video.duration)
            final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm]))

        final_video.write_videofile(out_name, fps=24, codec="libx264", audio_codec="aac", threads=4, logger=None)
        return out_name
    except Exception as e:
        logger.error(f"렌더링 에러: {e}")
        return ""

# ============================================================
# 5. 유튜브 API 업로드
# ============================================================
def upload_to_youtube(video_path: str, thumb_path: str, title: str, tags: list) -> bool:
    if not os.path.exists('token.json'): 
        logger.error("token.json이 없습니다.")
        return False
    try:
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        body = {'snippet': {'title': title, 'description': "실화 바탕 썰다큐입니다.\n#사건사고 #썰튜브", 'tags': tags, 'categoryId': '24'}, 'status': {'privacyStatus': 'public'}}
        
        vid_res = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')).execute()
        
        if vid_res.get("id") and os.path.exists(thumb_path):
            youtube.thumbnails().set(videoId=vid_res.get("id"), media_body=MediaFileUpload(thumb_path)).execute()
        return True
    except Exception as e:
        logger.error(f"유튜브 업로드 실패: {e}")
        return False

# ============================================================
# 6. 완전 자동화 API 엔드포인트 (Cloud Scheduler 트리거용)
# ============================================================
async def execute_factory_cycle():
    logger.info("🚀 [무인 공장 사이클 가동]")
    try:
        state = await PIPELINE.ainvoke({"category": "", "keyword": None, "character": None, "raw_script": None, "safe_script": None, "blueprint": None, "error": None})
        if state.get("error"):
            logger.error(f"파이프라인 에러: {state['error']}")
            return

        bp = state["blueprint"]
        logger.info(f"✅ 기획 완료. 렌더링 진입. 제목: {bp.get('title')}")

        thumb_task = generate_dalle_image(bp.get("thumbnail_prompt", ""), "thumbnail.png")
        img_tasks = [generate_dalle_image(s["image_prompt"], f"scene_{s['scene_no']}.png") for s in bp["scenes"]]
        aud_tasks = [generate_cinematic_tts(s["tts_text"], s["scene_no"]) for s in bp["scenes"]]
        
        thumb_path = await thumb_task
        img_paths = [p for p in await asyncio.gather(*img_tasks) if p]
        aud_paths = [p for p in await asyncio.gather(*aud_tasks) if p]
        
        out = render_final_video(bp, img_paths, aud_paths, f"ssul_{int(time.time())}.mp4")
        if out:
            logger.info("🚀 렌더링 완료. 유튜브 업로드 중...")
            if upload_to_youtube(out, thumb_path, bp.get("title"), bp.get("seo_tags", [])):
                logger.info("✅ 영상 및 썸네일 업로드 성공.")
            
            # 가비지 청소
            try:
                os.remove(out)
                if os.path.exists(thumb_path): os.remove(thumb_path)
                for p in img_paths + aud_paths: os.remove(p)
            except: pass

    except Exception as e:
        logger.error(f"공장 셧다운 에러: {e}")

@app.get("/run-factory")
async def trigger_factory(bg_tasks: BackgroundTasks):
    """
    구글 클라우드 스케줄러(Cron)가 매일 호출할 API 주소입니다.
    이 주소로 GET 요청이 들어오면 백그라운드에서 공장 1사이클을 가동합니다.
    """
    bg_tasks.add_task(execute_factory_cycle)
    return {"status": "Factory cycle initiated in background."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
