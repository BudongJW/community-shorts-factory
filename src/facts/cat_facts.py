"""큐레이션된 영문 고양이 팩트 풀.

narration(= Edge TTS) + 고양이 영상 합성용 스크립트.
Education 틱(cat fact channel) 지향으로 교육 카테고리 RPM($0.05~0.12) 진입 목표.
각 fact는 TTS로 읽었을 때 15~35초 분량이 되도록 길이 조절됨.
"""

import json
import random
from pathlib import Path

# (title_hook, narration_text) 쌍.
# title_hook: 쇼츠 제목 훅 (질문형/클릭베이트). narration_text: 음성 스크립트.
# 모두 영문. 한국어 채널로 돌리려면 별도 풀 분리.
CAT_FACTS: list[tuple[str, str]] = [
    (
        "Why cats knead you",
        "Cats knead with their paws because it reminds them of nursing from their "
        "mother. When your cat kneads you, they see you as family. It's the highest "
        "compliment a cat can give.",
    ),
    (
        "Cats can jump 6x their height",
        "A house cat can jump up to six times its own body length in a single leap. "
        "That's like a human jumping over a two story building. Their powerful back "
        "legs store and release energy like a spring.",
    ),
    (
        "Why cats stare at you",
        "When your cat stares at you with slow blinks, it's saying I love you in cat "
        "language. A slow blink means they trust you completely. Try slow blinking back. "
        "They will often return the gesture.",
    ),
    (
        "Cats have 32 muscles in each ear",
        "Cats have thirty two muscles in each ear, letting them rotate their ears a full "
        "180 degrees. They can pinpoint the exact location of a sound within three "
        "inches from three feet away.",
    ),
    (
        "Why cats bring you dead things",
        "When your cat brings you a dead mouse or toy, they think you're a bad hunter. "
        "They are literally teaching you how to survive. It's not gross, it's generous.",
    ),
    (
        "Cats purr at a healing frequency",
        "A cat's purr vibrates between 25 and 150 hertz, the exact frequency used in "
        "medical therapy to heal bones and reduce pain. When you pet a purring cat, "
        "you're being medically soothed.",
    ),
    (
        "Why cats knock things off tables",
        "Cats knock things off tables because their paws are hunting tools. They test "
        "if an object is alive, edible, or interesting by swatting it. The fact that "
        "you react just makes it more fun.",
    ),
    (
        "Cats sleep 70% of their lives",
        "Cats spend about 70 percent of their lives sleeping. That's around 16 hours "
        "a day. A 12 year old cat has only been awake for about 3 to 4 years of its "
        "entire life.",
    ),
    (
        "Why cats hate closed doors",
        "Cats hate closed doors because in the wild, any barrier could hide a threat "
        "or an escape route. Closing a door tells them you are controlling territory "
        "they want access to. That's why they meow until you open it.",
    ),
    (
        "Cats see in near darkness",
        "A cat's eyes need only one sixth of the light humans do to see clearly. "
        "Their pupils expand to the width of their eye and a reflective layer called "
        "the tapetum bounces light back through the retina.",
    ),
    (
        "Why cats chatter at birds",
        "When a cat sees a bird through a window and chatters its teeth, it's "
        "practicing the killing bite. The jaw movement mimics the neck snap they'd "
        "use on prey. It's an involuntary hunter reflex.",
    ),
    (
        "Cats have a third eyelid",
        "Cats have a third eyelid called the nictitating membrane. It sweeps "
        "horizontally to clear debris and protect the eye. If you can see it when "
        "they're awake, it often means they're sick.",
    ),
    (
        "Why cats rub their face on you",
        "When your cat rubs its face on your leg, it's marking you as property using "
        "scent glands on its cheeks. Other cats can smell that you belong to someone. "
        "It's a love-claim, not affection alone.",
    ),
    (
        "Cats can't taste sweet",
        "Cats are the only mammals that cannot taste sweetness. A genetic mutation "
        "disabled their sweet receptor. That cake your cat is trying to steal? It "
        "literally tastes like nothing sugary to them.",
    ),
    (
        "Why black cats got unlucky",
        "Black cats became unlucky in medieval Europe when the Pope declared them "
        "servants of the devil in 1233. Thousands were killed. Ironically this caused "
        "the rat population to explode, worsening the bubonic plague.",
    ),
    (
        "Cats recognize your voice",
        "Cats can recognize their owner's voice from a stranger's, but they choose "
        "to ignore you. Studies show they respond with ear and head movement but "
        "rarely vocalize back. That's not rudeness, it's just how they evolved.",
    ),
    (
        "Why cats tuck their paws in",
        "When a cat sits with its paws tucked under its body, it's called the cat "
        "loaf. They do it to conserve body heat and signal safety. A loafing cat "
        "feels no threats nearby.",
    ),
    (
        "Cats have unique nose prints",
        "Every cat has a unique nose print, just like a human fingerprint. No two "
        "cats share the same pattern of ridges and bumps. In theory, cats could be "
        "identified by nose scan alone.",
    ),
    (
        "Why cats hate water",
        "Most cats hate water because their fur isn't waterproof and takes a long "
        "time to dry. Wet fur also loses its insulation, making a wet cat cold and "
        "vulnerable. Exceptions like the Turkish Van actually love swimming.",
    ),
    (
        "Cats have 24 whiskers",
        "Cats have about 24 whiskers, arranged in rows on each side of the face. "
        "Whiskers sense air currents and measure if a gap is too narrow to squeeze "
        "through. Cutting them disables spatial awareness.",
    ),
    (
        "Why cats wag their tails",
        "A cat's wagging tail doesn't mean happy. A twitching tip signals focus or "
        "mild annoyance. A fully thrashing tail means they are angry and about to "
        "lash out. It is the opposite of a dog wag.",
    ),
    (
        "Cats have a dominant paw",
        "Cats are either right or left pawed. Studies show females tend to be right "
        "pawed and males left pawed. Test yours by dropping a treat and seeing which "
        "paw reaches first.",
    ),
    (
        "Why cats meow at humans",
        "Adult cats rarely meow at other cats. They developed meowing specifically "
        "to communicate with humans, mimicking baby cries to trigger our caretaking "
        "instinct. You have been manipulated by evolution.",
    ),
    (
        "Cats were worshipped as gods",
        "In ancient Egypt cats were considered sacred and killing one, even "
        "accidentally, was punishable by death. When a family cat died, the family "
        "would shave their eyebrows in mourning.",
    ),
    (
        "Why cats bury their poop",
        "Cats bury their waste to hide their scent from predators and rival cats. "
        "Dominant cats often leave it uncovered as a territorial statement. If your "
        "cat doesn't bury, they think they own the place.",
    ),
    (
        "Cats can drink seawater",
        "A cat's kidneys are so efficient they can rehydrate from seawater. The "
        "kidneys filter out salt better than human kidneys can. This is why cats "
        "thrive in dry environments where other mammals wouldn't.",
    ),
    (
        "Why orange cats are mostly male",
        "About 80 percent of orange cats are male because the orange color gene is "
        "carried on the X chromosome. A female needs two copies to be orange, a male "
        "needs only one. That explains the ginger boy stereotype.",
    ),
    (
        "Cats walk like camels",
        "Cats walk by moving both legs on one side of the body at once, then "
        "switching to the other side. Only camels and giraffes share this gait. It "
        "lets them walk silently without tangling their legs.",
    ),
    (
        "Why cats go crazy at 3am",
        "The 3am zoomies come from cats being crepuscular. Their bodies evolved to "
        "hunt at dawn and dusk, not day or night. Indoor cats release that hunting "
        "energy by sprinting through your house at the worst hours.",
    ),
    (
        "Cats have over 100 sounds",
        "Cats can make over 100 different vocal sounds. Dogs make only about 10. "
        "Each cat develops a custom vocabulary with its owner. They literally invent "
        "private languages one human at a time.",
    ),
]

HISTORY_PATH = Path(__file__).parent.parent.parent / "output" / "cat_facts_history.json"
HISTORY_MAX = 20  # 최근 20개 피한 후 재사용


def _load_history() -> list[str]:
    if HISTORY_PATH.exists():
        try:
            return list(json.loads(HISTORY_PATH.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return []
    return []


def _record_used(hook: str):
    history = _load_history()
    history = [h for h in history if h != hook]
    history.append(hook)
    if len(history) > HISTORY_MAX:
        history = history[-HISTORY_MAX:]
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False), encoding="utf-8"
    )


def pick_cat_fact() -> tuple[str, str]:
    """(hook, narration) 선택. 최근 사용한 것은 회피."""
    history = set(_load_history())
    fresh = [f for f in CAT_FACTS if f[0] not in history]
    pool = fresh if fresh else CAT_FACTS
    chosen = random.choice(pool)
    _record_used(chosen[0])
    return chosen
