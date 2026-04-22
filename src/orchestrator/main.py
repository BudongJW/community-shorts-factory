"""전체 파이프라인 오케스트레이터.

실행:
  python -m src.orchestrator.main                    # 기존 나레이션 모드
  python -m src.orchestrator.main --mode chat         # 채팅 썰 모드
  python -m src.orchestrator.main --mode chat --json samples/chat_sample.json  # JSON 직접 지정
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.collector.dcinside import run as collect_trending, save_posts, _download_images
from src.collector.cat_videos import collect_cat_clips
from src.collector.ai_cat_images import generate_ai_cat_images
from src.editor.cat_composer import compose_cat_short
from src.editor.anime_cat_composer import compose_anime_cat
from src.editor.cat_facts_composer import compose_cat_facts_short
from src.facts.cat_facts import pick_cat_fact
from src.collector.filter import filter_topics
from src.collector.history import filter_new_topics, record_topic
from src.script_gen.generator import generate
from src.script_gen.chat_generator import generate_chat, format_topics_with_comments
from src.tts.edge_tts_engine import synthesize
from src.video.pexels import fetch_videos
from src.editor.composer import compose
from src.editor.chat_composer import compose_chat
from src.editor.chat_renderer import ChatScript, ChatMessage, load_chat_script
from src.editor.thumbnail import generate_thumbnail
from src.uploader.youtube import upload
from src.utils.logger import setup_logger

log = setup_logger("pipeline")


def pipeline_chat_single(
    posts,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    run_id: str = "",
    json_path: str | None = None,
) -> dict | None:
    """채팅 썰 영상 생성 파이프라인.

    Returns:
        성공 시 결과 dict, 실패 시 None
    """
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    if json_path:
        # JSON 파일에서 직접 로드
        log.info(f"[chat] JSON 대본 로드: {json_path}")
        script_data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    else:
        # ── 중복 필터링 ──
        titles = [p.title for p in posts[:5]]
        new_titles = filter_new_topics(titles)
        if not new_titles:
            log.warning("  모든 토픽이 이전에 사용됨 -- 건너뜀")
            return None

        filtered = [p for p in posts[:5] if p.title in new_titles]

        # ── 제목 + 댓글 기반 LLM 입력 생성 ──
        topics_text = format_topics_with_comments(filtered)

        # ── LLM 채팅 대본 생성 ──
        log.info(f"[chat 2/4] 채팅 대본 생성 중 (provider: {llm_provider})...")
        log.info(f"  -> 댓글 포함 게시글 {len(filtered)}개 입력")
        script_data = generate_chat(topics_text, provider=llm_provider)

    title = script_data.get("title", "커뮤니티 썰")
    log.info(f"  -> 제목: {title}")
    log.info(f"  -> 메시지 수: {len(script_data.get('messages', []))}개")

    # ── 이미지 다운로드 (image_index가 있는 메시지용) ──
    image_paths_map: dict[int, Path] = {}
    has_image_msgs = any(
        "image_index" in m for m in script_data.get("messages", [])
    )
    if has_image_msgs and posts:
        # LLM이 선택한 원본 게시글 찾기
        topic_source = script_data.get("topic_source", "")
        source_post = None
        for p in posts:
            if p.title == topic_source and getattr(p, "image_urls", []):
                source_post = p
                break
        # 못 찾으면 이미지가 있는 첫 번째 게시글 사용
        if not source_post:
            for p in posts:
                if getattr(p, "image_urls", []):
                    source_post = p
                    break

        if source_post and source_post.image_urls:
            log.info(f"  [image] 이미지 {len(source_post.image_urls)}장 다운로드 중...")
            img_dir = Path("output") / "images" / run_id
            try:
                async def _dl():
                    async with aiohttp.ClientSession() as session:
                        return await _download_images(
                            source_post.image_urls, session, img_dir, max_images=20
                        )
                dl_paths = asyncio.run(_dl())
                for i, p in enumerate(dl_paths):
                    image_paths_map[i] = p
                log.info(f"  [image] {len(dl_paths)}장 다운로드 완료")
            except Exception as e:
                log.warning(f"  [image] 다운로드 실패: {e}")

    # ChatScript 객체 생성 (image_index -> image_path 변환)
    raw_messages = script_data.get("messages", [])
    for m in raw_messages:
        idx = m.pop("image_index", None)
        if idx is not None and idx in image_paths_map:
            m["image_path"] = str(image_paths_map[idx])
    messages = [ChatMessage(**m) for m in raw_messages]
    chat_script = ChatScript(
        category=script_data.get("category", "커뮤니티 썰"),
        title=title,
        subtitle=script_data.get("subtitle", ""),
        participants=script_data.get("participants", []),
        messages=messages,
        result_text=script_data.get("result_text", ""),
        source=script_data.get("topic_source", ""),
    )

    # ── 채팅 영상 합성 (BGM + SFX 포함) ──
    log.info("[chat 3/5] 채팅 영상 렌더링 중 (BGM + SFX)...")
    final_path = compose_chat(chat_script, output_name=run_id)
    log.info(f"  -> 최종: {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    # ── 썸네일 생성 ──
    log.info("[chat 4/5] 썸네일 생성 중...")
    thumb_path = generate_thumbnail(
        title=title,
        result_text=script_data.get("result_text", ""),
        output_name=run_id,
    )
    log.info(f"  -> 썸네일: {thumb_path.name}")

    # ── YouTube 업로드 ──
    video_id = ""
    tags = script_data.get("tags", [])
    # #Shorts 태그 필수 포함
    if "#Shorts" not in tags and "Shorts" not in tags:
        tags.insert(0, "Shorts")

    # SEO 최적화된 설명
    description_lines = [
        title,
        "",
        " ".join(f"#{t.lstrip('#')}" for t in tags),
        "",
        "---",
        "커뮤니티 인기글을 채팅 형식으로 재구성한 쇼츠입니다.",
    ]
    description = "\n".join(description_lines)

    if skip_upload:
        log.info("[chat 5/5] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[chat 5/5] YouTube 업로드 중...")
        video_id = upload(final_path, title, description, tags)
        log.info(f"  -> https://www.youtube.com/shorts/{video_id}")

    # ── 토픽 기록 ──
    topic_source = script_data.get("topic_source", title)
    record_topic(topic_source, video_id)

    return {
        "run_id": run_id,
        "title": title,
        "topic_source": topic_source,
        "final_path": str(final_path),
        "thumb_path": str(thumb_path),
        "video_id": video_id,
    }


REAL_CAT_TITLES = [
    "POV: Your cat at 3am",
    "Cats have zero chill",
    "This cat chose violence",
    "Cat.exe has stopped working",
    "Why cats are unhinged",
    "Average day as a cat owner",
    "The audacity of this cat",
    "Cats being absolute menaces",
    "No thoughts, just cat",
    "This is why we love cats",
    "Cat logic makes no sense",
    "Proof cats are liquid",
    "My cat is broken",
    "Normal day in cat world",
    "Cats vs gravity",
    "When your cat judges you",
    "Cat mode: activated",
    "The duality of cats",
    # 확장: retention hook형 제목
    "Wait until you see this cat",
    "I can't stop watching this",
    "This cat is something else",
    "My cat's villain arc",
    "Cats are built different",
    "Tell me this isn't you",
    "Nobody:\nMy cat:",
    "How is this legal",
    "Cats when you're not looking",
    "Send this to a cat person",
    "Cats will never disappoint",
    "Rate this cat out of 10",
    "Which one is you",
    "This cat said nope",
    "Cat therapy session",
    "Why do cats do this",
]

ANIME_CAT_TITLES = [
    "Cat Mecha Evolution",
    "When cats unlock their final form",
    "Cats but they're anime protagonists",
    "Cat power level: OVER 9000",
    "The cat cinematic universe",
    "Anime cats hit different",
    "Cat transformation sequence",
    "If cats had superpowers",
    "Cat fantasy adventure",
    "Legendary cat warriors",
    # 확장
    "Anime cats go hard",
    "Main character cat energy",
    "This cat could beat Goku",
    "POV: You're a cat in an anime",
    "Isekai but you're a cat",
    "Cat's final form revealed",
    "AI imagined anime cats",
    "The chosen cat",
    "Cat cinematic moments",
    "Cats in the multiverse",
]

# 해시태그 풀: 매번 10개 랜덤 선택 (태그 다양화로 알고리즘 노출 확대)
REAL_CAT_HASHTAGS = [
    "Shorts", "shorts", "cat", "cats", "catsoftiktok", "catsofyoutube",
    "funny", "funnycats", "funnyanimals", "kitten", "kittens", "cute",
    "cutecats", "cuteanimals", "meme", "memes", "catmemes", "viral",
    "fyp", "catlover", "catlife", "catvideo", "cats_of_instagram",
    "lofi", "chill", "relaxing", "고양이", "냥냥", "귀여운", "쇼츠",
]
ANIME_CAT_HASHTAGS = [
    "Shorts", "shorts", "cat", "cats", "anime", "animecat", "animeart",
    "aiart", "aianimation", "aigenerated", "stablediffusion", "fantasy",
    "mecha", "cute", "kawaii", "manga", "isekai", "viral", "fyp",
    "catlover", "animefan", "고양이", "애니메이션", "쇼츠",
]
# Cat Facts (education 서브니치) — education RPM 진입 목표로 지식형 태그.
FACTS_CAT_HASHTAGS = [
    "Shorts", "shorts", "cat", "cats", "catfacts", "didyouknow",
    "animalfacts", "learnontiktok", "learnonyoutube", "educational",
    "catlover", "catsoftiktok", "catbehavior", "funfacts", "facts",
    "kitten", "kittens", "cute", "cuteanimals", "science", "biology",
    "nature", "petfacts", "pets", "viral", "fyp",
]

# 감정/훅을 제목에 이모지로 (30% 확률로 prefix)
TITLE_EMOJIS = ["😹", "🙀", "😻", "🐾", "✨", "🔥", "💀", "😭"]

# variant별 "Day N" 시리즈 카운터 — 누적 업로드 수로 연속성 연출.
# 시리즈물 포맷은 알고리즘상 "같은 채널 반복 시청" 신호 강화 + 시청자가 다음 편 기대.
SERIES_COUNTER_PATH = Path("output") / "series_counter.json"

# 듀레이션 버킷 — 채널에 다양한 길이가 섞여야 알고리즘이 세그먼트 다양하게 추천.
# 짧은 영상은 완주율, 긴 영상은 시청 시간 확보. 70% 짧은/30% 긴 비율이 리텐션 상 유리.
DURATION_BUCKETS = [
    ("short", 15, 25, 0.7),   # name, lo, hi, weight
    ("medium", 26, 40, 0.3),
]


def _pick_target_duration() -> tuple[str, float]:
    """(버킷 이름, 목표 초) 반환. 버킷 내 균등 랜덤."""
    import random
    weights = [b[3] for b in DURATION_BUCKETS]
    bucket = random.choices(DURATION_BUCKETS, weights=weights, k=1)[0]
    name, lo, hi, _ = bucket
    return name, random.uniform(lo, hi)


def _load_series_counters() -> dict:
    if SERIES_COUNTER_PATH.exists():
        try:
            return json.loads(SERIES_COUNTER_PATH.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _peek_series_day(variant: str) -> int:
    """variant별 Day N 번호를 미리 본다. 저장은 하지 않음."""
    counters = _load_series_counters()
    return int(counters.get(variant, 0)) + 1


def _commit_series_day(variant: str, day_num: int):
    """업로드 성공 후 카운터를 커밋한다. 중복 호출해도 day_num 유지."""
    counters = _load_series_counters()
    counters[variant] = day_num
    SERIES_COUNTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    SERIES_COUNTER_PATH.write_text(
        json.dumps(counters, ensure_ascii=False), encoding="utf-8"
    )


def _build_title(title_pool: list[str], day_num: int | None = None) -> str:
    """제목 + 이모지 + 옵션 Day N 시리즈 넘버링.

    day_num 있으면 40% 확률로 "Day N | " prefix 추가 (매번 넣으면 스팸 시그널).
    """
    import random
    title = random.choice(title_pool)
    if random.random() < 0.3:
        title = f"{random.choice(TITLE_EMOJIS)} {title}"
    if day_num is not None and random.random() < 0.4:
        title = f"Day {day_num} | {title}"
    return title


def _build_description(title: str, hashtag_pool: list[str], variant_desc: str) -> tuple[str, list[str]]:
    """설명문 + 태그 리스트 생성. 태그 다양화로 알고리즘 분산 노출."""
    import random
    # 해시태그 10개 랜덤 선택 (Shorts/shorts는 항상 포함)
    essential = ["Shorts", "shorts"]
    optional = [t for t in hashtag_pool if t not in essential]
    picked = essential + random.sample(optional, min(10, len(optional)))
    hashtag_line = " ".join(f"#{t}" for t in picked)
    description = (
        f"{title}\n\n"
        f"{variant_desc}\n\n"
        f"{hashtag_line}\n\n"
        "Subscribe for daily cat shorts! 🐾"
    )
    return description, picked


def pipeline_cat_single(
    skip_upload: bool = False,
    run_id: str = "",
) -> dict | None:
    """실사 고양이 쇼츠 생성 파이프라인."""
    import random
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    log.info("[cat 1/3] 고양이 영상 수집 중...")
    clips = collect_cat_clips(count=1)
    if not clips:
        log.error("  고양이 영상을 수집하지 못했습니다")
        return None

    clip = clips[0]
    log.info(f"  -> {clip.name}")

    bucket_name, target_sec = _pick_target_duration()
    log.info(f"[cat 2/3] Lofi Jazz + 세로 크롭 합성 중 (target: {bucket_name} {target_sec:.0f}s)...")
    final_path = compose_cat_short(clip, output_name=run_id, target_duration=target_sec)
    log.info(f"  -> {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    video_id = ""
    day_num = _peek_series_day("real")
    title = _build_title(REAL_CAT_TITLES, day_num=day_num)
    description, tags = _build_description(
        title, REAL_CAT_HASHTAGS,
        f"Daily dose of chaotic cats with lofi jazz beats. Day {day_num} of the series.\n"
        "Because the internet needs more cats.",
    )

    if skip_upload:
        log.info("[cat 3/3] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[cat 3/3] YouTube 업로드 중...")
        video_id = upload(final_path, title, description, tags)
        log.info(f"  -> https://www.youtube.com/shorts/{video_id}")
        _commit_series_day("real", day_num)
        try:
            from src.analytics.stats import record_generation
            record_generation(
                video_id=video_id, variant="real", title=title,
                day_num=day_num, target_duration=target_sec, hook=None,
            )
        except Exception as e:
            log.warning(f"  generation_log 기록 실패: {e}")

    return {
        "run_id": run_id,
        "title": title,
        "topic_source": clip.name,
        "final_path": str(final_path),
        "video_id": video_id,
    }


def pipeline_cat_facts_single(
    skip_upload: bool = False,
    run_id: str = "",
) -> dict | None:
    """Cat Facts 쇼츠 생성 파이프라인 (education 서브니치).

    기존 cat 클립을 재활용하되 TTS 나레이션 + 자막을 얹어 교육 카테고리 진입.
    Target RPM: $0.05~0.12 (entertainment cat의 2~5배).
    """
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    log.info("[cat-facts 1/4] 고양이 팩트 선택 중...")
    hook_text, narration_text = pick_cat_fact()
    log.info(f"  fact: {hook_text}")

    log.info("[cat-facts 2/4] TTS 나레이션 합성 중...")
    try:
        audio_path, srt_path, tts_meta = synthesize(
            narration_text, filename=f"facts_{run_id}", language="en"
        )
    except Exception as e:
        log.error(f"  TTS 실패: {e}")
        return None
    log.info(f"  voice: {tts_meta['voice']} rate: {tts_meta['rate']}")

    log.info("[cat-facts 3/4] 고양이 영상 수집 중...")
    clips = collect_cat_clips(count=1, min_duration=10, max_duration=40)
    if not clips:
        log.error("  고양이 영상 수집 실패")
        return None
    clip = clips[0]

    log.info("[cat-facts 4/4] 나레이션+자막+클립 합성 중...")
    final_path = compose_cat_facts_short(
        video_path=clip,
        narration_audio=audio_path,
        narration_srt=srt_path,
        hook_text=hook_text.upper(),  # 훅은 대문자 통일 (기존 채널 톤)
        output_name=run_id,
    )
    log.info(f"  -> {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    video_id = ""
    day_num = _peek_series_day("facts")
    # Day N prefix는 해당 제목 빌더에 맡기되, facts는 hook_text를 제목 근간으로.
    # 80% 기본 훅 제목, 20% Day N 시리즈형.
    import random
    if random.random() < 0.2:
        title = f"Day {day_num} | {hook_text}"
    else:
        title = hook_text
    description, tags = _build_description(
        title, FACTS_CAT_HASHTAGS,
        f"{narration_text}\n\nDay {day_num} — Daily cat facts with footage.",
    )

    if skip_upload:
        log.info("[cat-facts] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[cat-facts] YouTube 업로드 중...")
        video_id = upload(final_path, title, description, tags)
        log.info(f"  -> https://www.youtube.com/shorts/{video_id}")
        _commit_series_day("facts", day_num)
        try:
            from src.analytics.stats import record_generation
            record_generation(
                video_id=video_id, variant="facts", title=title,
                day_num=day_num,
                target_duration=0.0,  # facts는 나레이션 길이에 따라 결정
                hook=hook_text,
            )
        except Exception as e:
            log.warning(f"  generation_log 기록 실패: {e}")

    return {
        "run_id": run_id,
        "title": title,
        "topic_source": hook_text,
        "final_path": str(final_path),
        "video_id": video_id,
    }


def pipeline_anime_cat_single(
    skip_upload: bool = False,
    run_id: str = "",
) -> dict | None:
    """AI 애니메이션 고양이 쇼츠 생성 파이프라인."""
    import random
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    log.info("[anime-cat 1/3] AI 고양이 이미지 생성 중...")
    img_dir = Path("output") / "ai_cats" / run_id
    images = generate_ai_cat_images(num_images=5, output_dir=img_dir)
    if not images:
        log.error("  AI 이미지 생성 실패")
        return None
    log.info(f"  -> {len(images)}장 생성 완료")

    bucket_name, target_sec = _pick_target_duration()
    log.info(f"[anime-cat 2/3] Ken Burns + Lofi Jazz 합성 중 (target: {bucket_name} {target_sec:.0f}s)...")
    final_path = compose_anime_cat(images, output_name=run_id, target_duration=target_sec)
    log.info(f"  -> {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    video_id = ""
    day_num = _peek_series_day("anime")
    title = _build_title(ANIME_CAT_TITLES, day_num=day_num)
    description, tags = _build_description(
        title, ANIME_CAT_HASHTAGS,
        f"AI-generated anime cats with lofi jazz. Day {day_num} of the series.\n"
        "Fresh fantasy art every day.",
    )

    if skip_upload:
        log.info("[anime-cat 3/3] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[anime-cat 3/3] YouTube 업로드 중...")
        video_id = upload(final_path, title, description, tags)
        log.info(f"  -> https://www.youtube.com/shorts/{video_id}")
        _commit_series_day("anime", day_num)
        try:
            from src.analytics.stats import record_generation
            record_generation(
                video_id=video_id, variant="anime", title=title,
                day_num=day_num, target_duration=target_sec, hook=None,
            )
        except Exception as e:
            log.warning(f"  generation_log 기록 실패: {e}")

    return {
        "run_id": run_id,
        "title": title,
        "topic_source": "ai_anime_cat",
        "final_path": str(final_path),
        "video_id": video_id,
    }


def pipeline_single(
    posts,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    run_id: str = "",
) -> dict | None:
    """단일 영상 생성 파이프라인.

    Returns:
        성공 시 결과 dict, 실패 시 None
    """
    if not run_id:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 중복 필터링 ──
    titles = [p.title for p in posts[:5]]
    new_titles = filter_new_topics(titles)
    if not new_titles:
        log.warning("  모든 토픽이 이전에 사용됨 — 건너뜀")
        return None

    topics_text = "\n".join(
        f"- [{p.voteup_count}추천] {p.title}"
        for p in posts[:5]
        if p.title in new_titles
    )

    # ── LLM 대본 생성 ──
    log.info(f"[2/6] 대본 생성 중 (provider: {llm_provider})...")
    script = generate(topics_text, provider=llm_provider)
    log.info(f"  → 제목: {script.title}")
    log.info(f"  → 대본 길이: {len(script.script)}자")
    log.info(f"  → 원본 토픽: {script.topic_source}")
    log.debug(f"  → 대본: {script.script}")

    # ── TTS 음성 + 자막 ──
    log.info("[3/6] Edge TTS 음성 생성 중...")
    audio_path, srt_path, tts_meta = synthesize(script.script, filename=run_id)
    log.info(f"  → 음성: {tts_meta['voice']} (속도: {tts_meta['rate']})")
    log.info(f"  → 파일: {audio_path.name} ({audio_path.stat().st_size // 1024}KB)")

    # ── 배경 영상 다운로드 ──
    log.info("[4/6] 배경 영상 다운로드 중...")
    video_paths = fetch_videos(script.search_keywords, per_keyword=1)
    log.info(f"  → {len(video_paths)}개 클립 준비 완료")

    # ── 영상 합성 ──
    log.info("[5/6] FFmpeg 영상 합성 중...")
    final_path = compose(video_paths, audio_path, srt_path, output_name=run_id)
    log.info(f"  → 최종: {final_path.name} ({final_path.stat().st_size // 1024}KB)")

    # ── YouTube 업로드 ──
    video_id = ""
    if skip_upload:
        log.info("[6/6] 업로드 건너뜀 (--skip-upload)")
    else:
        log.info("[6/6] YouTube 업로드 중...")
        description = f"{script.script}\n\n#{' #'.join(script.tags)}"
        video_id = upload(final_path, script.title, description, script.tags)
        log.info(f"  → https://www.youtube.com/shorts/{video_id}")

    # ── 토픽 기록 ──
    record_topic(script.topic_source or script.title, video_id)

    return {
        "run_id": run_id,
        "title": script.title,
        "topic_source": script.topic_source,
        "voice": tts_meta["voice"],
        "final_path": str(final_path),
        "video_id": video_id,
    }


def pipeline(
    num_posts: int = 10,
    llm_provider: str = "groq",
    skip_upload: bool = False,
    dry_run: bool = False,
    batch: int = 1,
    mode: str = "narration",
    json_path: str | None = None,
    cat_variant: str = "auto",
):
    """전체 파이프라인.

    Args:
        num_posts: 수집할 트렌딩 게시글 수
        llm_provider: "groq" 또는 "claude"
        skip_upload: True면 업로드 건너뜀
        dry_run: True면 수집+대본까지만
        batch: 생성할 영상 수
        mode: "narration" (기존) 또는 "chat" (채팅 썰)
        json_path: chat 모드에서 직접 JSON 대본 경로 지정
        cat_variant: "auto"(기존, 마지막만 anime) / "real" / "anime" — cat 모드에서 영상 종류 강제
    """
    log.info("")
    log.info("=" * 50)
    log.info(f"  AI Shorts Pipeline ({mode} mode)")
    log.info("=" * 50)
    log.info("")

    # ── cat 모드: 고양이 영상 (실사 + AI 애니메이션 믹스) ──
    if mode == "cat":
        results = []
        failures = []
        # cat_variant: auto(기존 로직) / real / anime / facts
        anime_idx = batch - 1  # auto일 때 마지막 1개만 애니메이션
        for i in range(batch):
            if cat_variant in ("real", "anime", "facts"):
                label = cat_variant
            else:  # auto — 기존 동작 유지 (real 위주, 마지막만 anime)
                label = "anime" if (i == anime_idx and batch > 1) else "real"

            if batch > 1:
                log.info(f"\n{'--' * 20}")
                log.info(f"  영상 {i + 1}/{batch} ({label})")
                log.info(f"{'--' * 20}")

            run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{i}" if batch > 1 else "")

            try:
                if label == "anime":
                    result = pipeline_anime_cat_single(skip_upload, run_id)
                elif label == "facts":
                    result = pipeline_cat_facts_single(skip_upload, run_id)
                else:
                    result = pipeline_cat_single(skip_upload, run_id)
            except Exception as e:
                log.exception(f"  영상 {i + 1}/{batch} ({label}) 실패: {e}")
                failures.append((i, label, str(e)))
                continue

            if result:
                results.append(result)
            else:
                failures.append((i, label, "pipeline returned None"))

        log.info("")
        log.info("=" * 50)
        log.info(f"  Cat Pipeline 완료! ({len(results)}/{batch}편)")
        log.info("=" * 50)
        for r in results:
            log.info(f"  [{r['run_id']}] {r['title']} -> {r['final_path']}")
        if failures:
            log.error(f"  실패 {len(failures)}편:")
            for idx, label, err in failures:
                log.error(f"    #{idx + 1} ({label}): {err}")
        return {"success": len(results), "failures": len(failures), "batch": batch}

    # ── chat 모드: JSON 직접 지정 시 수집 건너뜀 ──
    if mode == "chat" and json_path:
        log.info(f"[chat] JSON 대본으로 직접 영상 생성: {json_path}")
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = pipeline_chat_single(
            [], llm_provider, skip_upload, run_id, json_path=json_path
        )
        if result:
            log.info("")
            log.info("=" * 50)
            log.info(f"  완료! {result['title']}")
            log.info(f"  -> {result['final_path']}")
            log.info("=" * 50)
        return

    # ── Step 1: 커뮤니티 트렌딩 수집 ──
    with_comments = (mode == "chat")
    with_content = (mode == "chat")  # 채팅 모드에서는 본문도 수집 (맥락 파악용)
    log.info(f"[1/6] 디시인사이드 HIT 갤러리 수집 중{'(+본문+댓글)' if with_comments else ''}...")
    posts = collect_trending(num=num_posts, with_content=with_content, with_comments=with_comments)
    save_path = save_posts(posts)
    log.info(f"  -> {len(posts)}개 게시글 수집 완료")

    top_posts = "\n".join(f"  - [{p.voteup_count}추천] {p.title}" for p in posts[:10])
    log.info(f"  -> 상위 토픽:\n{top_posts}")

    # ── Step 1.5: 니치 필터링 ──
    log.info("\n[1.5/6] 니치 필터링 중 (바이럴 가능성 판단)...")
    posts_for_filter = "\n".join(
        f"- [{p.voteup_count}추천 | {p.view_count}조회 | 댓글{p.comment_count}] {p.title}"
        for p in posts[:10]
    )
    filter_result = filter_topics(posts_for_filter, provider=llm_provider)

    selected = filter_result.get("selected", [])
    rejected = filter_result.get("rejected", [])
    log.info(f"  -> 선택: {len(selected)}개 / 제외: {len(rejected)}개")
    for s in selected:
        log.info(f"    [{s.get('score', '?')}점] {s['title']} -- {s.get('angle', '')}")
    for r in rejected:
        log.info(f"    x {r['title']} -- {r.get('reason', '')}")

    if not selected:
        log.warning("  바이럴 가능한 토픽 없음 -- 상위 3개로 대체 진행")
        selected_titles = [p.title for p in posts[:3]]
    else:
        selected_titles = [s["title"] for s in selected]

    # 선택된 토픽에 해당하는 posts만 필터
    filtered_posts = [p for p in posts if p.title in selected_titles] or posts[:3]

    if dry_run:
        log.info(f"\n[dry-run] 대본 생성 테스트...")
        if mode == "chat":
            topics_text = format_topics_with_comments(filtered_posts[:5])
            script_data = generate_chat(topics_text, provider=llm_provider)
            log.info(f"  -> 제목: {script_data.get('title', '')}")
            log.info(f"  -> 메시지 수: {len(script_data.get('messages', []))}개")
            log.info(f"  -> 결과: {script_data.get('result_text', '')}")
        else:
            script = generate(topics_text, provider=llm_provider)
            log.info(f"  -> 제목: {script.title}")
            log.info(f"  -> 대본 ({len(script.script)}자): {script.script}")
            log.info(f"  -> 태그: {script.tags}")
            log.info(f"  -> 키워드: {script.search_keywords}")
        log.info("\n(dry-run 모드 종료)")
        return

    # ── 배치 생성 ──
    results = []
    for i in range(batch):
        if batch > 1:
            log.info(f"\n{'--' * 20}")
            log.info(f"  영상 {i + 1}/{batch}")
            log.info(f"{'--' * 20}")

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{i}" if batch > 1 else "")

        if mode == "chat":
            result = pipeline_chat_single(filtered_posts, llm_provider, skip_upload, run_id)
        else:
            result = pipeline_single(filtered_posts, llm_provider, skip_upload, run_id)

        if result:
            results.append(result)

    # ── 완료 리포트 ──
    log.info("")
    log.info("=" * 50)
    log.info(f"  파이프라인 완료! ({len(results)}/{batch}편 생성)")
    log.info("=" * 50)

    for r in results:
        log.info(f"  [{r['run_id']}] {r['title']} -> {r['final_path']}")

    log.info("")


def main():
    parser = argparse.ArgumentParser(description="AI Shorts Pipeline")
    parser.add_argument("--posts", type=int, default=10, help="수집할 게시글 수")
    parser.add_argument("--provider", choices=["groq", "claude"], default="groq")
    parser.add_argument("--skip-upload", action="store_true", help="YouTube 업로드 건너뜀")
    parser.add_argument("--dry-run", action="store_true", help="수집+대본까지만")
    parser.add_argument("--batch", type=int, default=1, help="생성할 영상 수 (기본 1)")
    parser.add_argument("--mode", choices=["narration", "chat", "cat"], default="narration",
                        help="영상 모드: narration(나레이션) / chat(채팅 썰) / cat(고양이)")
    parser.add_argument("--json", type=str, default=None,
                        help="chat 모드에서 직접 JSON 대본 경로 지정")
    parser.add_argument("--cat-variant", choices=["auto", "real", "anime", "facts"], default="auto",
                        help="cat 모드 영상 종류 강제 (auto=마지막만 anime / facts=교육형 나레이션)")
    args = parser.parse_args()

    result = pipeline(
        num_posts=args.posts,
        llm_provider=args.provider,
        skip_upload=args.skip_upload,
        dry_run=args.dry_run,
        batch=args.batch,
        mode=args.mode,
        json_path=args.json,
        cat_variant=args.cat_variant,
    )

    # cat 모드의 경우 부분 실패를 non-zero exit code로 신호
    if isinstance(result, dict) and result.get("failures", 0) > 0:
        import sys
        # 전부 실패면 2, 일부 실패면 1
        sys.exit(2 if result["success"] == 0 else 1)


if __name__ == "__main__":
    main()
