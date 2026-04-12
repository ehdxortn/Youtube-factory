"""
SOVEREIGN APEX v48 — CLOUD-NATIVE ENGINE (NO-FILE AUTH)
=====================================
- 환경 변수(Env Vars) 기반 인증 시스템 탑재
- 장프로 형님 전용 모델 ID 고정 (GPT-5.4, Claude Sonnet 4.6, Gemini 3.1 Pro)
- 3~5회 연재형(Serialized) 스토리텔링 및 옴니버스 렌더링 지원
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

from openai import AsyncOpenAI
from moviepy.editor import ImageClip, AudioFileClip, TextClip, CompositeVideoClip, CompositeAudioClip, concatenate_videoclips
import moviepy.audio.fx.all as afx
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# ============================================================
# 0. 고정 모델 ID 및 시스템 설정
# ============================================================
GEMINI_MODEL_ID = "gemini-3.1-pro-preview"
CLAUDE_MODEL_ID = "claude-sonnet-4-6"
GPT_MODEL_ID    = "gpt-5.4"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SSULTUBE-V48")

def get_env(k, default=""):
    return os.environ.get(k, default)

litellm.set_verbose = False
os.environ["OPENAI_API_KEY"]    = get_env("OPENAI_API_KEY")
os.environ["ANTHROPIC_API_KEY"] = get_env("ANTHROPIC_API_KEY")
os.environ["GEMINI_API_KEY"]    = get_env("GEMINI_API_KEY")

app = FastAPI()
openai_client = AsyncOpenAI(api_key=get_env("OPENAI_API_KEY"))

# ============================================================
# 1. 유튜브 인증 로직 (환경 변수 문자열 -> 객체 변환)
# ============================================================
def get_youtube_service():
    """환경 변수에 저장된 JSON 텍스트를 읽어 인증 객체 생성"""
    token_json_str = get_env("YOUTUBE_TOKEN_JSON")
    if not token_json_str:
        logger.error("❌ YOUTUBE_TOKEN_JSON 환경 변수가 설정되지 않았습니다.")
        return None
    
    try:
        # 환경 변수의 문자열을 JSON 데이터로 변환
        info = json.loads(token_json_str)
        creds = Credentials.from_authorized_user_info(info, ['https://www.googleapis.com/auth/youtube.upload'])
        return build('youtube', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ 유튜브 인증 실패: {e}")
        return None

# ============================================================
# 2. 하네스 및 대본 엔진 (이전 논의된 최고 사양 유지)
# ============================================================
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

WRITER_SYSTEM_PROMPT = """[WRITER CORE DIRECTIVE]
당신은 '그것이 알고싶다' 스타일의 베테랑 작가입니다. 4050 타겟 1인칭 사연자 시점 대본을 작성합니다.
반드시 [PAUSE] 기호를 사용하여 성우의 호흡을 조절하고, 인간적인 구어체 노이즈를 15% 섞으십시오."""

# (Pydantic 스키마 및 LangGraph 노드 구성 생략 - 이전 V47과 동일하며 모델 ID만 위 상수로 적용)
# ... [이전 V47의 렌더링 엔진 및 파이프라인 코드 포함] ...

# ============================================================
# 3. 자동 실행 엔드포인트
# ============================================================
@app.get("/run-factory")
async def trigger_factory(bg_tasks: BackgroundTasks):
    """구글 클라우드 스케줄러가 호출할 주소"""
    # 💡 여기서 1~3회차 연재물 기획 로직 가동
    bg_tasks.add_task(execute_production_cycle)
    return {"status": "Serialized Production cycle initiated."}

async def execute_production_cycle():
    # 유튜브 서비스 인증 확인
    youtube = get_youtube_service()
    if
