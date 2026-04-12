"""
SOVEREIGN APEX — SSUL-TUBE FACTORY (ANTI-PATTERN & MONETIZATION EDITION)
=====================================
통합 적용:
  1. LangGraph 파이프라인 (Sourcing -> Research -> Writer -> CRO -> PD)
  2. Character & Hook Engine: 페르소나 고정 및 첫 3초 훅 강제 설계
  3. Thumbnail Engine: DALL-E 3 CTR 최적화 썸네일 생성 및 API 자동 등록
  4. Anti-Pattern Randomizer: 줌 비율, 자막 크기, 위치 난수화로 대량생산 필터 회피
"""

import os, json, asyncio, logging, httpx, html, re, time, random
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
# 0. 모델 및 환경 설정
# ============================================================
LITELLM_GPT        = "openai/gpt-5.4"
LITELLM_CLAUDE     = "claude-sonnet-4-6"  
LITELLM_GEMINI     = "gemini/gemini-3.1-pro"
LITELLM_PERPLEXITY = "perplexity/sonar-pro"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SSULTUBE-FACTORY-MONEY")

def get_env(k, default=""):
    v = os.environ.get(k, default)
    if not v: logger.warning(f"⚠️ {k} 누락")
    return v

litellm.set_verbose = False
os.environ["OPENAI_API_KEY"]     = get_env("OPENAI_API_KEY")
os.environ["ANTHROPIC_API_KEY"]  = get_env("ANTHROPIC_API_KEY")
os.environ["GEMINI_API_KEY"]     = get_env("GEMINI_API_KEY")
os.environ["PERPLEXITY_API_KEY"] = get_env("PERPLEXITY_API_KEY")

if Langfuse:
    langfuse = Langfuse(public_key=get_env("LANGFUSE_PUBLIC_KEY"), secret_key=get_env("LANGFUSE_SECRET_KEY"), host="https://cloud.langfuse.com")

bot = Bot(token=get_env("TELEGRAM_TOKEN"))
app = FastAPI()
ALLOWED_IDS = [int(x) for x in get_env("ALLOWED_USER_ID", "0").split(",")]
openai_client = AsyncOpenAI(api_key=get_env("OPENAI_API_KEY"))

# 💡 하네스 절대 지침서
HARNESS_CONTEXT = """[SSUL-TUBE HARNESS SYSTEM CORE RULES]
1. 비식별화 및 검열 우회 100% 적용.
2. 시각적 일관성: image_prompt에 "Korean webtoon style, dramatic shading" 유지.
3. 훅(Hook) 강제: 1번 씬은 무조건 가장 자극적인 3초 이내의 결론/반전 스포일러로 배치한다.
4. 순수 JSON 포맷 강제 (마크다운 금지)."""

# ============================================================
# 1. 스키마 및 State
# ============================================================
class SceneItem(BaseModel):
    scene_no: int
    tts_text: str = Field(description="성우 나레이션")
    subtitle: str = Field(description="압축 자막 (15자 이내)")
    image_prompt: str = Field(description="DALL-E 3 배경 프롬프트")
    zoom_mode: Literal["in", "out"]

class SsulBlueprint(BaseModel):
    title: str = Field(description="유튜브 제목")
    seo_tags: List[str]
    thumbnail_prompt: str = Field(description="CTR 극대화 DALL-E 3 썸네일 프롬프트")
    scenes: List[SceneItem]

class FactoryState(TypedDict):
    chat_id: int
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
# 2. 파이프라인 노드
# ============================================================
@observe(name="factory_llm_call")
async def llm_call(model: str, system: str, payload: str, temp: float = 0.7, tokens: int = 2500) -> str:
    res = await acompletion(model=model, messages=[{"role": "system", "content": system}, {"role": "user", "content": payload}], temperature=temp, max_tokens=tokens)
    return res.choices[0].message.content

async def node_sourcing(state: FactoryState) -> FactoryState:
    if state.get("keyword"): 
        state["character"] = "익명의 제보자"
        return state
    try:
        res = await llm_call(LITELLM_GPT, HARNESS_CONTEXT, "한국 4050 타겟 자극적 썰 소재 1줄, 페르소나 1줄 작성.", 0.9, 300)
        lines = res.strip().split('\n')
        state["keyword"] = lines[0] if len(lines) > 0 else "믿었던 가족의 배신"
        state["character"] = lines[1] if len(lines) > 1 else "차분하지만 집요한 성격의 인물"
        state["agent_status"]["Sourcing"] = "✅"
    except Exception as e:
        state["keyword"] = "남편의 배신과 20억 빚"
        state["character"] = "복수를 다짐하는 아내"
        state["agent_status"]["Sourcing"] = "❌"
    return state

async def node_research(state: FactoryState) -> FactoryState:
    try:
        state["facts"] = await llm_call(LITELLM_PERPLEXITY, HARNESS_CONTEXT, f"[{state['keyword']}] 갈등과 타임라인 요약.", 0.1, 1500)
        state["agent_status"]["Research"] = "✅"
    except Exception as e:
        state["error"] = f"리서치 에러: {e}"
    return state

async def node_writer(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        payload = f"주제: {state['keyword']}\n주인공: {state['character']}\n팩트: {state['facts']}\n첫 문장은 충격적인 3초 훅(Hook)으로 시작."
        state["raw_script"] = await llm_call(LITELLM_GPT, HARNESS_CONTEXT, payload, 0.7, 2500)
        state["agent_status"]["Writer"] = "✅"
    except Exception as e:
        state["error"] = f"대본 작성 에러: {e}"
    return state

async def node_cro(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        state["safe_script"] = await llm_call(LITELLM_CLAUDE, HARNESS_CONTEXT, f"유튜브 검열 위험 단어 우회.\n대본: {state['raw_script']}", 0.2, 2500)
        state["agent_status"]["CRO"] = "✅"
    except Exception as e:
        state["error"] = f"검열 에러: {e}"
    return state

async def node_pd_harness(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    sys_prompt = f"{HARNESS_CONTEXT}\n총괄 PD로서 대본을 영상 렌더링용 JSON으로 구조화."
    payload = f"대본: {state['safe_script']}"
    
    for _ in range(3):
        try:
            parsed = safe_json_extract(await llm_call(LITELLM_GEMINI, sys_prompt, payload, 0.1, 2000))
            if parsed:
                state["blueprint"] = SsulBlueprint(**parsed).model_dump()
                state["agent_status"]["PD_JSON"] = "✅"
                return state
        except Exception as e:
            payload = f"에러: {e}\n수정된 완벽한 JSON 재출력.\n대본: {state['safe_script']}"
    state["error"] = "PD 교정 루프 실패"
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
async def generate_dalle_image(prompt: str, file_name: str) -> str:
    try:
        res = await openai_client.images.generate(model="dall-e-3", prompt=prompt, size="1024x576", quality="hd", n=1)
        async with httpx.AsyncClient() as c:
            with open(file_name, 'wb') as f: f.write((await c.get(res.data[0].url)).content)
        return file_name
    except: return ""

async def generate_openai_tts(text: str, scene_no: int) -> str:
    path = f"scene_{scene_no}.mp3"
    try:
        (await openai_client.audio.speech.create(model="tts-1", voice="onyx", input=text)).stream_to_file(path)
        return path
    except: return ""

# ============================================================
# 4. 렌더링 엔진 (Anti-Pattern 난수화)
# ============================================================
def create_zoom_effect(clip, duration, mode="in", zoom_ratio=0.05):
    def effect(get_frame, t):
        img = ImageClip(get_frame(t))
        scale = 1.0 + (zoom_ratio * (t / duration)) if mode == "in" else 1.0 + zoom_ratio - (zoom_ratio * (t / duration))
        return img.resize(scale).get_frame(t)
    return clip.fl(effect)

def render_final_video(blueprint: dict, img_paths: list, audio_paths: list, out_name: str) -> str:
    logging.info("🎬 [연출 엔진] 컴포지션 시작")
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
