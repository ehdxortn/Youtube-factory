"""
SOVEREIGN APEX — SSUL-TUBE FACTORY (v47 DIAGNOSTIC & STABILITY)
=====================================
"""
import os, json, asyncio, logging, httpx, html, re, time, random, uuid, shutil
from datetime import datetime, timezone
from typing import Optional, List, Literal, TypedDict
from pydantic import BaseModel, Field

from fastapi import FastAPI, Request, BackgroundTasks
from telegram import Update, Bot
from telegram.constants import ParseMode

import litellm
from litellm import acompletion
from langgraph.graph import StateGraph, END

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
# 0. 환경 변수 진단 엔진 (서버 즉사 방지)
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SSULTUBE-PROD-v47")

app = FastAPI()
MISSING_KEYS = []

def get_env_safe(k: str) -> str:
    v = os.environ.get(k)
    if not v:
        MISSING_KEYS.append(k)
        return ""
    return v

LITELLM_GPT        = "openai/gpt-5.4"
LITELLM_CLAUDE     = "claude-sonnet-4-6"  
LITELLM_GEMINI     = "gemini/gemini-3.1-pro"
LITELLM_PERPLEXITY = "perplexity/sonar-pro"

litellm.set_verbose = False
os.environ["OPENAI_API_KEY"]     = get_env_safe("OPENAI_API_KEY")
os.environ["ANTHROPIC_API_KEY"]  = get_env_safe("ANTHROPIC_API_KEY")
os.environ["GEMINI_API_KEY"]     = get_env_safe("GEMINI_API_KEY")
os.environ["PERPLEXITY_API_KEY"] = get_env_safe("PERPLEXITY_API_KEY")
TELEGRAM_TOKEN                   = get_env_safe("TELEGRAM_TOKEN")
ALLOWED_IDS_STR                  = get_env_safe("ALLOWED_USER_ID")

try:
    ALLOWED_IDS = [int(x) for x in ALLOWED_IDS_STR.split(",")] if ALLOWED_IDS_STR else []
except:
    ALLOWED_IDS = []
    if "ALLOWED_USER_ID" not in MISSING_KEYS: MISSING_KEYS.append("ALLOWED_USER_ID (숫자 형식이 아닙니다)")

bot = Bot(token=TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None
openai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]) if os.environ["OPENAI_API_KEY"] else None

if Langfuse and os.environ.get("LANGFUSE_PUBLIC_KEY"):
    langfuse = Langfuse(public_key=os.environ["LANGFUSE_PUBLIC_KEY"], secret_key=os.environ["LANGFUSE_SECRET_KEY"], host="https://cloud.langfuse.com")

HARNESS_CONTEXT = """[SSUL-TUBE HARNESS SYSTEM CORE RULES]
1. 비식별화 및 검열 우회 100% 적용.
2. 시각적 일관성: image_prompt에 "Korean webtoon style, dramatic shading" 유지.
3. 훅 강제: 1번 씬은 무조건 가장 자극적인 3초 이내의 결론/반전 스포일러.
4. 순수 JSON 포맷 강제 (마크다운 금지)."""

# ============================================================
# 0-1. 웹 진단 페이지
# ============================================================
@app.get("/")
async def health_check():
    if MISSING_KEYS:
        return {"status": "FAIL", "message": "API 키 누락", "missing_variables": MISSING_KEYS}
    return {"status": "SUCCESS", "message": "모든 세팅이 완벽합니다. 텔레그램에서 /auto 명령어를 내려주십시오."}

# ============================================================
# 1. 스키마 및 State
# ============================================================
class SceneItem(BaseModel):
    scene_no: int
    tts_text: str
    subtitle: str
    image_prompt: str
    zoom_mode: Literal["in", "out"]

class SsulBlueprint(BaseModel):
    title: str
    seo_tags: List[str]
    thumbnail_prompt: str
    scenes: List[SceneItem]

class FactoryState(TypedDict):
    chat_id: int
    session_id: str
    keyword: Optional[str]
    character: Optional[str]
    facts: Optional[str]
    raw_script: Optional[str]
    safe_script: Optional[str]
    blueprint: Optional[dict]
    error: Optional[str]
    agent_status: dict

def safe_json_extract(text: str) -> Optional[dict]:
    try:
        text = re.sub(r"```json|```", "", text).strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and start < end:
            return json.loads(text[start:end+1])
    except: pass
    return None

# ============================================================
# 2. 노드 파이프라인
# ============================================================
@observe(name="factory_llm_call")
async def llm_call(model: str, system: str, payload: str, temp: float = 0.7, tokens: int = 2500) -> str:
    for attempt in range(3):
        try:
            res = await acompletion(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": payload}], temperature=temp, max_tokens=tokens, request_timeout=60)
            return res.choices[0].message.content
        except Exception as e:
            logger.warning(f"⚠️ {model} 통신 실패 (시도 {attempt+1}/3). 에러: {e}")
            if attempt == 2: raise e
            await asyncio.sleep(2 * (attempt + 1))
    return ""

async def node_sourcing(state: FactoryState) -> FactoryState:
    if state.get("keyword"): 
        state["character"] = "익명의 제보자"
        return state
    try:
        res = await llm_call(LITELLM_GPT, HARNESS_CONTEXT, "한국 4050 타겟 자극적 썰 소재 1줄, 페르소나 1줄 작성.", 0.9, 300)
        lines = res.strip().split('\n')
        state["keyword"] = lines[0] if len(lines) > 0 else "믿었던 가족의 배신"
        state["character"] = lines[1] if len(lines) > 1 else "차분하지만 집요한 인물"
        state["agent_status"]["Sourcing"] = "✅"
    except Exception as e:
        state["error"] = f"기획 에러: {e}"
        state["agent_status"]["Sourcing"] = "❌"
    return state

async def node_research(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        state["facts"] = await llm_call(LITELLM_PERPLEXITY, HARNESS_CONTEXT, f"[{state['keyword']}] 갈등 요약.", 0.1, 1500)
        state["agent_status"]["Research"] = "✅"
    except Exception as e:
        state["error"] = f"리서치 에러: {e}"
    return state

async def node_writer(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        state["raw_script"] = await llm_call(LITELLM_GPT, HARNESS_CONTEXT, f"주제: {state['keyword']}\n주인공: {state['character']}\n팩트: {state['facts']}\n첫 문장은 충격적 3초 훅 시작.", 0.7, 2500)
        state["agent_status"]["Writer"] = "✅"
    except Exception as e:
        state["error"] = f"대본 작성 에러: {e}"
    return state

async def node_cro(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        state["safe_script"] = await llm_call(LITELLM_CLAUDE, HARNESS_CONTEXT, f"유튜브 검열 단어 우회.\n대본: {state['raw_script']}", 0.2, 2500)
        state["agent_status"]["CRO"] = "✅"
    except Exception as e:
        state["error"] = f"검열 에러: {e}"
    return state

async def node_pd_harness(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    sys_prompt = f"{HARNESS_CONTEXT}\n대본을 영상 렌더링용 JSON 구조화.\n스키마: title, seo_tags, thumbnail_prompt, scenes (scene_no, tts_text, subtitle, image_prompt, zoom_mode)"
    payload = f"대본: {state['safe_script']}"
    for _ in range(3):
        try:
            parsed = safe_json_extract(await llm_call(LITELLM_GEMINI, sys_prompt, payload, 0.1, 2000))
            if parsed:
                state["blueprint"] = SsulBlueprint(**parsed).model_dump()
                state["agent_status"]["PD_JSON"] = "✅"
                return state
        except Exception as e:
            payload = f"에러: {e}\n수정된 완벽 JSON 재출력.\n대본: {state['safe_script']}"
    state["error"] = "PD 교정 3회 실패"
    return state

PIPELINE = StateGraph(FactoryState)
PIPELINE.add_node("sourcing", node_sourcing)
PIPELINE.add_node("research", node_research)
PIPELINE.add_node("writer",   node_writer)
PIPELINE.add_node("cro",      node_cro)
PIPELINE.add_node("pd",       node_pd_harness)
PIPELINE.set_entry_point("sourcing")
PIPELINE.add_edge("sourcing", "research")
PIPELINE.add_edge("research", "writer")
PIPELINE.add_edge("writer",   "cro")
PIPELINE.add_edge("cro",      "pd")
PIPELINE.add_edge("pd",       END)
PIPELINE = PIPELINE.compile()

# ============================================================
# 3. 에셋 생성 엔진
# ============================================================
async def generate_dalle_image(prompt: str, file_path: str) -> str:
    for attempt in range(2):
        try:
            res = await openai_client.images.generate(model="dall-e-3", prompt=prompt, size="1024x576", quality="hd", n=1)
            async with httpx.AsyncClient(timeout=30) as c:
                with open(file_path, 'wb') as f: f.write((await c.get(res.data[0].url)).content)
            return file_path
        except Exception as e:
            await asyncio.sleep(2)
    return ""

async def generate_openai_tts(text: str, file_path: str) -> str:
    for attempt in range(2):
        try:
            (await openai_client.audio.speech.create(model="tts-1", voice="onyx", input=text)).stream_to_file(file_path)
            return file_path
        except Exception as e:
            await asyncio.sleep(2)
    return ""

# ============================================================
# 4. 렌더링 엔진 (try-except 완벽 복구)
# ============================================================
def create_zoom_effect(clip, duration, mode="in", zoom_ratio=0.05):
    def effect(get_frame, t):
        img = ImageClip(get_frame(t))
        scale = 1.0 + (zoom_ratio * (t / duration)) if mode == "in" else 1.0 + zoom_ratio - (zoom_ratio * (t / duration))
        return img.resize(scale).get_frame(t)
    return clip.fl(effect)

def render_final_video(blueprint: dict, img_paths: list, audio_paths: list, out_name: str) -> str:
    logging.info(f"🎬 [연출 엔진] 컴포지션 시작: {out_name}")
    try:
        font_path = "Malgun-Gothic" if os.name == 'nt' else "NanumGothic" 
        clips = []
        for i, scene in enumerate(blueprint.get("scenes", [])):
            if i >= len(img_paths) or i >= len(audio_paths): break
            audio_clip = AudioFileClip(audio_paths[i])
            dur = audio_clip.duration
            
            z_ratio = random.uniform(0.03, 0.08)
            f_size = random.choice([60, 65, 70])
            m_bottom = random.choice([80, 100, 120])

            img_clip = ImageClip(img_paths[i]).set_duration(dur)
            img_clip = create_zoom_effect(img_clip, dur, scene.get("zoom_mode", "in"), zoom_ratio=z_ratio)
            img_clip = img_clip.set_position("center").on_color(size=(1920, 1080), color=(0,0,0))
            
            txt_clip = TextClip(scene.get("subtitle", ""), fontsize=f_size, color='white', font=font_path, stroke_color='black', stroke_width=2)
            txt_clip = txt_clip.set_position(('center', 'bottom')).margin(bottom=m_bottom, opacity=0).set_duration(dur)
            
            video_comp = CompositeVideoClip([img_clip, txt_clip], size=(1920, 1080)).set_audio(audio_clip)
            clips.append(video_comp)
            
        final_video = concatenate_videoclips(clips, method="compose")
        bgm_path = "bgm_tense.mp3"
        if os.path.exists(bgm_path):
            bgm = AudioFileClip(bgm_path).fx(afx.volumex, random.uniform(0.06, 0.1)).fx(afx.audio_loop, duration=final_video.duration)
            final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm]))

        final_video.write_videofile(out_name, fps=24, codec="libx264", audio_codec="aac", threads=4, logger=None)
        return out_name
    except Exception as e:
        logging.error(f"❌ 영상 렌더링 실패: {e}")
        return ""

# ============================================================
# 5. 유튜브 직배송
# ============================================================
def upload_to_youtube(video_path: str, thumb_path: str, title: str, tags: list) -> bool:
    if not os.path.exists('client_secrets.json'): return False
    try:
        creds = Credentials.from_authorized_user_file('client_secrets.json', ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        body = {'snippet': {'title': title, 'description': "실화 바탕 썰다큐입니다.\n#사건사고 #썰튜브", 'tags': tags, 'categoryId': '24'}, 'status': {'privacyStatus': 'public'}}
        video_id = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')).execute().get("id")
        if video_id and os.path.exists(thumb_path):
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path)).execute()
        return True
    except Exception as e:
        logger.error(f"업로드 에러: {e}")
        return False

# ============================================================
# 6. 메인 컨트롤러
# ============================================================
async def run_factory_pipeline(chat_id: int, keyword: Optional[str] = None):
    if not bot: return
    session_id = uuid.uuid4().hex[:8]
    work_dir = f"temp_{session_id}"
    os.makedirs(work_dir, exist_ok=True)
    
    try:
        await bot.send_message(chat_id, f"🎬 <b>[방탄 팩토리 가동]</b> 세션: {session_id}", parse_mode=ParseMode.HTML)
        state = await PIPELINE.ainvoke({"chat_id": chat_id, "session_id": session_id, "keyword": keyword, "character": None, "facts": None, "raw_script": None, "safe_script": None, "blueprint": None, "error": None, "agent_status": {}})
        
        if state.get("error"): return await bot.send_message(chat_id, f"⚠️ 에러: {state['error']}")
        bp = state["blueprint"]
        await bot.send_message(chat_id, f"✅ 기획 완료. 렌더링 진입.\n제목: {bp.get('title')}\n페르소나: {state['character']}")

        thumb_task = generate_dalle_image(bp.get("thumbnail_prompt", ""), f"{work_dir}/thumbnail.png")
        img_tasks = [generate_dalle_image(s["image_prompt"], f"{work_dir}/scene_{s['scene_no']}.png") for s in bp["scenes"]]
        aud_tasks = [generate_openai_tts(s["tts_text"], f"{work_dir}/scene_{s['scene_no']}.mp3") for s in bp["scenes"]]
        
        thumb_path = await thumb_task
        img_paths = [p for p in await asyncio.gather(*img_tasks) if p]
        aud_paths = [p for p in await asyncio.gather(*aud_tasks) if p]
        
        out_video = f"{work_dir}/final_ssul_{session_id}.mp4"
        out_path = render_final_video(bp, img_paths, aud_paths, out_video)
        
        if out_path:
            await bot.send_message(chat_id, "🚀 렌더링 완료. 유튜브 서버 배송 및 썸네일 부착 중...")
            if upload_to_youtube(out_path, thumb_path, bp.get("title"), bp.get("seo_tags", [])):
                await bot.send_message(chat_id, f"✅ 영상/썸네일 업로드 완료. (세션: {session_id})")
    except Exception as e:
        if bot: await bot.send_message(chat_id, f"⚠️ 공장 셧다운: {html.escape(str(e))}")
    finally:
        try:
            if os.path.exists(work_dir): shutil.rmtree(work_dir)
        except: pass

@app.post("/webhook")
async def webhook(request: Request, bg: BackgroundTasks):
    msg = Update.de_json(await request.json(), bot).message
    if bot and msg and (msg.from_user.id in ALLOWED_IDS) and msg.text:
        if msg.text.startswith("/make "): bg.add_task(run_factory_pipeline, msg.chat.id, msg.text.replace("/make ", "").strip())
        elif msg.text == "/auto": bg.add_task(run_factory_pipeline, msg.chat.id)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
