"""
SOVEREIGN APEX — SSUL-TUBE FACTORY (ANTI-PATTERN & MONETIZATION EDITION)
=====================================
통합 적용:
  1. LangGraph 파이프라인 (Sourcing -> Research -> Writer -> CRO -> PD)
  2. Character & Hook Engine: 페르소나 고정 및 첫 3초 훅 강제 설계
  3. Thumbnail Engine: DALL-E 3 CTR 최적화 썸네일 생성 및 API 자동 등록
  4. Anti-Pattern Randomizer: 줌 비율, 자막 크기, 위치 난수화로 대량생산 필터 회피
  5. 방어적 Pydantic 스키마 및 에러 텔레그램 직배송 로직 탑재
  6. 구간별 상태 보고 및 MoviePy 별도 스레드(Executor) 격리
  7. API 네트워크 무한 대기(Hang) 방지 Async Timeout 강제 적용
  8. DALL-E 3 공식 해상도 규격(1792x1024) 강제 적용
  9. [ULTIMATE FIX] DALL-E 안전 정책 우회 프롬프트 및 누락 이미지 '땜빵(Fallback)' 엔진 탑재
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

# 💡 DALL-E 안전 정책 우회를 위한 강력한 프롬프트 지침 추가
HARNESS_CONTEXT = """[SSUL-TUBE HARNESS SYSTEM CORE RULES]
1. 비식별화 및 검열 우회 100% 적용.
2. 시각적 일관성: image_prompt에 "Korean webtoon style, dramatic shading" 유지.
3. 훅(Hook) 강제: 1번 씬은 무조건 가장 자극적인 3초 이내의 결론/반전 스포일러로 배치한다.
4. 순수 JSON 포맷 강제 (마크다운 금지).
5. [중요] DALL-E 안전 정책 우회: image_prompt에는 절대 폭력, 피, 흉기, 범죄, 자해, 극단적 혐오 표현을 넣지 마세요. 갈등과 분노는 '어두운 그림자', '깨진 거울', '비 내리는 창문' 등 은유적이고 추상적으로 묘사하세요."""

# ============================================================
# 1. 스키마 및 State
# ============================================================
class SceneItem(BaseModel):
    scene_no: int = 1
    tts_text: str = "대본 생성 오류"
    subtitle: str = "자막 누락"
    image_prompt: str = "Korean webtoon style, dramatic shading, intense scene"
    zoom_mode: str = "in" 

class SsulBlueprint(BaseModel):
    title: str = "기막힌 인생실화"
    seo_tags: List[str] = ["썰다큐", "사건사고", "충격실화"]
    thumbnail_prompt: str = "Korean webtoon style, high contrast, shocked face close-up"
    scenes: List[SceneItem] = []

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
        return json.loads(text) 
    except:
        try:
            cleaned = text.replace("```json", "").replace("```", "").strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start != -1 and end != -1:
                return json.loads(cleaned[start:end+1])
        except Exception as e:
            logger.warning(f"JSON 파싱 최후 실패: {e}")
    return None

# ============================================================
# 2. 파이프라인 노드
# ============================================================
@observe(name="factory_llm_call")
async def llm_call(model: str, system: str, payload: str, temp: float = 0.7, tokens: int = 2500, response_format: dict = None) -> str:
    kwargs = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": payload}], "temperature": temp, "max_tokens": tokens}
    if response_format: kwargs["response_format"] = response_format
    res = await acompletion(**kwargs)
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
        state["raw_script"] = await llm_call(LITELLM_GPT, HARNESS_CONTEXT, payload, 0.7, 3000)
        state["agent_status"]["Writer"] = "✅"
    except Exception as e:
        state["error"] = f"대본 작성 에러: {e}"
    return state

async def node_cro(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    try:
        state["safe_script"] = await llm_call(LITELLM_CLAUDE, HARNESS_CONTEXT, f"유튜브 검열 위험 단어 우회.\n대본: {state['raw_script']}", 0.2, 3000)
        state["agent_status"]["CRO"] = "✅"
    except Exception as e:
        state["error"] = f"검열 에러: {e}"
    return state

async def node_pd_harness(state: FactoryState) -> FactoryState:
    if state.get("error"): return state
    
    sys_prompt = f"""{HARNESS_CONTEXT}
당신은 총괄 PD입니다. 제공된 대본을 분석하여 반드시 아래의 JSON 형식으로만 출력하세요. 
마크다운 기호 없이 순수 JSON 객체만 반환해야 합니다.

{{
  "title": "유튜브 제목",
  "seo_tags": ["태그1", "태그2", "태그3"],
  "thumbnail_prompt": "DALL-E 3 썸네일 영문 프롬프트 (안전 규정 준수)",
  "scenes": [
    {{
      "scene_no": 1,
      "tts_text": "성우 나레이션",
      "subtitle": "압축 자막",
      "image_prompt": "DALL-E 3 영문 프롬프트 (안전 규정 준수, 은유적 표현)",
      "zoom_mode": "in" 
    }}
  ]
}}"""

    payload = f"대본: {state['safe_script']}"
    last_err = ""
    
    for attempt in range(3):
        try:
            content = await llm_call(LITELLM_GPT, sys_prompt, payload, 0.1, 4000, response_format={"type": "json_object"})
            parsed = safe_json_extract(content)
            
            if parsed:
                blueprint = SsulBlueprint(**parsed) 
                state["blueprint"] = blueprint.model_dump()
                state["agent_status"]["PD_JSON"] = "✅"
                return state
            else:
                raise ValueError("JSON 형식이 아닙니다.")
                
        except Exception as e:
            last_err = str(e)
            logger.warning(f"PD 교정 에러 ({attempt+1}/3): {e}")
            payload = f"이전 에러: {e}\n위의 JSON 뼈대를 정확히 지켜서 다시 출력하세요.\n대본: {state['safe_script']}"
            
    state["error"] = f"PD 노드 파싱 실패. 상세에러: {last_err[:200]}"
    state["agent_status"]["PD_JSON"] = "❌"
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
        res = await asyncio.wait_for(
            openai_client.images.generate(
                model="dall-e-3", prompt=prompt,
                size="1792x1024", quality="hd", n=1 
            ),
            timeout=60.0  
        )
        async with httpx.AsyncClient(timeout=30.0) as c:
            img_data = await c.get(res.data[0].url)
            with open(file_name, 'wb') as f:
                f.write(img_data.content)
        return file_name
    except asyncio.TimeoutError:
        logger.error(f"DALL-E 타임아웃: {file_name}")
        return ""
    except Exception as e:
        logger.error(f"DALL-E 에러: {e}")
        return ""

async def generate_openai_tts(text: str, scene_no: int) -> str:
    path = f"scene_{scene_no}.mp3"
    try:
        response = await asyncio.wait_for(
            openai_client.audio.speech.create(
                model="tts-1", voice="onyx", input=text
            ),
            timeout=45.0  
        )
        response.stream_to_file(path)
        return path
    except asyncio.TimeoutError:
        logger.error(f"TTS 타임아웃: scene {scene_no}")
        return ""
    except Exception as e:
        logger.error(f"TTS 에러: {e}")
        return ""

# ============================================================
# 4. 렌더링 엔진 (💡 누락 이미지 땜빵(Fallback) 로직 추가)
# ============================================================
def create_zoom_effect(clip, duration, mode="in", zoom_ratio=0.05):
    scale_func = lambda t: 1.0 + (zoom_ratio * (t / duration)) if mode == "in" else 1.0 + zoom_ratio - (zoom_ratio * (t / duration))
    return clip.resize(scale_func)

def render_final_video(blueprint: dict, img_paths: list, audio_paths: list, out_name: str) -> str:
    logging.info("🎬 [연출 엔진] 컴포지션 시작")
    try:
        font_path = "Malgun-Gothic" if os.name == 'nt' else "NanumGothic" 
        clips = []
        
        # 💡 땜빵용 예비 이미지 등록 (썸네일이 있으면 최우선, 없으면 None)
        last_valid_img = "thumbnail.png" if os.path.exists("thumbnail.png") else None
        
        for scene in blueprint.get("scenes", []):
            s_no = scene.get("scene_no", 1)
            img_path = f"scene_{s_no}.png"
            aud_path = f"scene_{s_no}.mp3"
            
            # 오디오가 없으면 씬 진행 불가 (이건 스킵해야 함)
            if not os.path.exists(aud_path):
                logging.warning(f"에셋 누락(오디오) 스킵: 씬 {s_no}")
                continue
                
            # 💡 이미지가 DALL-E 검열 등으로 누락되었을 경우 땜빵 처리
            if not os.path.exists(img_path):
                if last_valid_img and os.path.exists(last_valid_img):
                    logging.warning(f"이미지 검열 누락. 땜빵 이미지 사용: 씬 {s_no}")
                    img_path = last_valid_img
                else:
                    logging.warning(f"땜빵용 이미지도 없음. 씬 전체 스킵: 씬 {s_no}")
                    continue
            else:
                last_valid_img = img_path # 정상 생성되었으면 다음 땜빵용으로 업데이트
                
            audio_clip = AudioFileClip(aud_path)
            dur = audio_clip.duration
            if dur <= 0: continue
            
            z_ratio = random.uniform(0.03, 0.08)
            f_size = random.choice([60, 65, 70])
            m_bottom = random.choice([80, 100, 120])

            img_clip = ImageClip(img_path).set_duration(dur)
            img_clip = create_zoom_effect(img_clip, dur, scene.get("zoom_mode", "in"), zoom_ratio=z_ratio)
            img_clip = img_clip.set_position("center").on_color(size=(1920, 1080), color=(0,0,0))
            
            subtitle_text = scene.get("subtitle", "").strip()
            
            if subtitle_text:
                try:
                    txt_clip = TextClip(subtitle_text, fontsize=f_size, color='white', font=font_path, stroke_color='black', stroke_width=2)
                    txt_clip = txt_clip.set_position(('center', 'bottom')).margin(bottom=m_bottom, opacity=0).set_duration(dur)
                    video_comp = CompositeVideoClip([img_clip, txt_clip], size=(1920, 1080)).set_audio(audio_clip)
                except Exception as text_e:
                    logging.error(f"TextClip 에러 (자막 없이 진행): {text_e}")
                    video_comp = CompositeVideoClip([img_clip], size=(1920, 1080)).set_audio(audio_clip)
            else:
                video_comp = CompositeVideoClip([img_clip], size=(1920, 1080)).set_audio(audio_clip)
                
            clips.append(video_comp)
            
        if not clips:
            raise ValueError("합성할 유효한 씬이 없습니다. (오디오 생성 모두 실패)")
            
        final_video = concatenate_videoclips(clips, method="compose")
        
        bgm_path = "bgm_tense.mp3"
        if os.path.exists(bgm_path):
            bgm = AudioFileClip(bgm_path).fx(afx.volumex, random.uniform(0.06, 0.1)).fx(afx.audio_loop, duration=final_video.duration)
            final_video = final_video.set_audio(CompositeAudioClip([final_video.audio, bgm]))

        final_video.write_videofile(out_name, fps=24, codec="libx264", audio_codec="aac", threads=4, logger=None)
        return out_name
        
    except Exception as e:
        logging.error(f"렌더링 에러: {e}", exc_info=True)
        raise e 

# ============================================================
# 5. 유튜브 업로드
# ============================================================
def upload_to_youtube(video_path: str, thumb_path: str, title: str, tags: list) -> bool:
    if not os.path.exists('token.json'): return False
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials
        creds = Credentials.from_authorized_user_file('token.json', ['https://www.googleapis.com/auth/youtube.upload'])
        youtube = build('youtube', 'v3', credentials=creds)
        body = {'snippet': {'title': title, 'description': "실화 바탕 썰다큐입니다.\n#사건사고 #썰튜브", 'tags': tags, 'categoryId': '24'}, 'status': {'privacyStatus': 'public'}}
        
        video_response = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')).execute()
        video_id = video_response.get("id")
        
        if video_id and os.path.exists(thumb_path):
            youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumb_path)).execute()
            
        return True
    except Exception as e:
        logger.error(f"유튜브 업로드 실패: {e}")
        return False

# ============================================================
# 6. 메인 컨트롤러 
# ============================================================
async def run_factory_pipeline(chat_id: int, keyword: Optional[str] = None):
    try:
        await bot.send_message(chat_id, "🎬 <b>[수익 방어 팩토리 가동]</b> Anti-Pattern 엔진 활성화...", parse_mode=ParseMode.HTML)
        state = await PIPELINE.ainvoke({
            "chat_id": chat_id, "keyword": keyword, "character": None,
            "facts": None, "raw_script": None, "safe_script": None,
            "blueprint": None, "error": None, "agent_status": {}
        })
        
        if state.get("error"):
            return await bot.send_message(chat_id, f"⚠️ <b>파이프라인 에러:</b>\n<code>{html.escape(state['error'])}</code>", parse_mode=ParseMode.HTML)
        
        bp = state["blueprint"]
        await bot.send_message(chat_id, f"✅ 기획 완료. 렌더링 진입.\n제목: {bp.get('title')}\n페르소나: {state['character']}")

        # ── 1단계: 썸네일 생성
        await bot.send_message(chat_id, "🖼️ [1/4] 썸네일 생성 중...")
        thumb_path = await generate_dalle_image(bp.get("thumbnail_prompt", ""), "thumbnail.png")
        await bot.send_message(chat_id, f"{'✅ 썸네일 완료' if thumb_path else '⚠️ 썸네일 실패 (스킵)'}")

        # ── 2단계: 씬 이미지 순차적 생성
        await bot.send_message(chat_id, f"🖼️ [2/4] 씬 이미지 생성 중... ({len(bp['scenes'])}컷)")
        img_paths = []
        for s in bp["scenes"]:
            p = await generate_dalle_image(s["image_prompt"], f"scene_{s['scene_no']}.png")
            if p: img_paths.append(p)
            await asyncio.sleep(0.5) 
        await bot.send_message(chat_id, f"✅ 이미지 {len(img_paths)}/{len(bp['scenes'])}컷 완료")

        # ── 3단계: TTS 순차적 생성
        await bot.send_message(chat_id, "🎙️ [3/4] TTS 나레이션 생성 중...")
        aud_paths = []
        for s in bp["scenes"]:
            p = await generate_openai_tts(s["tts_text"], s["scene_no"])
            if p: aud_paths.append(p)
            await asyncio.sleep(0.5) 
        await bot.send_message(chat_id, f"✅ TTS {len(aud_paths)}/{len(bp['scenes'])}개 완료")

        if not aud_paths:
            return await bot.send_message(chat_id, "❌ TTS 전체 실패. 중단.")

        # ── 4단계: 렌더링
        await bot.send_message(chat_id, "🎬 [4/4] 영상 렌더링 중... (수분 소요)")
        out_name = f"ssul_{int(time.time())}.mp4"
        
        try:
            loop = asyncio.get_running_loop()
            out = await loop.run_in_executor(None, render_final_video, bp, img_paths, aud_paths, out_name)
        except Exception as re:
            return await bot.send_message(chat_id, f"❌ 렌더링 에러:\n<code>{html.escape(str(re))}</code>", parse_mode=ParseMode.HTML)

        if not out or not os.path.exists(out):
            return await bot.send_message(chat_id, "❌ 렌더링 결과물 없음. MoviePy 로그 확인 필요.")

        # ── 5단계: 유튜브 업로드
        await bot.send_message(chat_id, "🚀 유튜브 업로드 중...")
        if upload_to_youtube(out, thumb_path, bp.get("title"), bp.get("seo_tags", [])):
            await bot.send_message(chat_id, "✅ 업로드 완료.")
        else:
            await bot.send_message(chat_id, "⚠️ 유튜브 업로드 실패. (token.json 확인)")

        # ── 정리
        try:
            for f in [out, thumb_path] + img_paths + aud_paths:
                if f and os.path.exists(f): os.remove(f)
        except: pass

    except Exception as e:
        await bot.send_message(chat_id, f"⚠️ 공장 셧다운: <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML)

@app.post("/webhook")
async def webhook(request: Request, bg: BackgroundTasks):
    msg = Update.de_json(await request.json(), bot).message
    if msg and (msg.from_user.id in ALLOWED_IDS) and msg.text:
        if msg.text.startswith("/make "): bg.add_task(run_factory_pipeline, msg.chat.id, msg.text.replace("/make ", "").strip())
        elif msg.text == "/auto": bg.add_task(run_factory_pipeline, msg.chat.id)
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
