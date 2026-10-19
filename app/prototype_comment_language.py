"""PROTOTYPE — throwaway. Not part of the CMS. Delete once the question is settled.

Question: does "a comment containing any Chinese character is Chinese,
otherwise it is English" put each approved comment on the right language page?

Run: python app/prototype_comment_language.py
"""

import re

# CJK Unified Ideographs plus Extension A — the characters a Chinese comment uses.
CHINESE_CHAR = re.compile(r"[㐀-䶿一-鿿]")


def detect_language(text):
    return "zh" if CHINESE_CHAR.search(text) else "en"


# (comment, the page it should appear on, category)
SAMPLES = [
    ("这个攻略写得太好了，谢谢up主！", "zh", "pure Chinese"),
    ("第三天就该卖掉那把剑，不然后面经济跟不上。", "zh", "pure Chinese"),
    ("请问新版本还能这样玩吗？", "zh", "pure Chinese"),
    ("Vanessa 这套 build 真的强，上分很快", "zh", "Chinese + game terms"),
    ("我觉得 Pygmalien 的 economy 流比这个稳", "zh", "Chinese + game terms"),
    ("这个 combo 在 patch 后被 nerf 了吧", "zh", "Chinese + game terms"),
    ("Great guide, this build carried me to Legend.", "en", "pure English"),
    ("Does this still work after the latest patch?", "en", "pure English"),
    ("I think you should skip the shop on day 4.", "en", "pure English"),
    ("666", "zh", "Chinese internet, no Chinese chars"),
    ("yyds", "zh", "Chinese internet, no Chinese chars"),
    ("GG", "zh", "Chinese internet, no Chinese chars"),
    ("6.7??", "zh", "Chinese internet, no Chinese chars"),
    ("xswl", "zh", "Chinese internet, no Chinese chars"),
    ("😂😂😂", "zh", "Chinese internet, no Chinese chars"),
    ("👍👍", "zh", "Chinese internet, no Chinese chars"),
]


def main():
    wrong = []
    print(f"{'comment':<46} {'expected':<9} {'rule':<5} ok")
    print("-" * 66)
    for text, expected, category in SAMPLES:
        got = detect_language(text)
        ok = got == expected
        if not ok:
            wrong.append((text, expected, got, category))
        print(f"{text:<46} {expected:<9} {got:<5} {'✓' if ok else '✗'}")
    right = len(SAMPLES) - len(wrong)
    print(f"\n{right}/{len(SAMPLES)} right, {len(wrong)} wrong\n")
    for text, expected, got, category in wrong:
        print(f"  WRONG  {text!r:<12} should be {expected}, rule says {got}  ({category})")


if __name__ == "__main__":
    main()
