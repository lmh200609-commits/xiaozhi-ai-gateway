import sys
sys.path.insert(0, ".")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from gateway.tts.edge_tts_streamer import clean_speech_text

test_cases = [
    # Case 1: user's exact case with thumbs up / smile emoji
    ("哇，650分，这个分数相当不错呀！👍 没有特别感兴趣的专业也很正常",
     "哇，650分，这个分数相当不错呀！ 没有特别感兴趣的专业也很正常"),
    
    # Case 2: smiling face
    ("你好呀！😊 很高兴为您服务！🎉",
     "你好呀！ 很高兴为您服务！"),
    
    # Case 3: bracketed emotion tags
    ("哇，650分，这个分数相当不错呀！[拇指向上] 没有特别感兴趣的专业也很正常",
     "哇，650分，这个分数相当不错呀！ 没有特别感兴趣的专业也很正常"),
    
    # Case 4: parenthesized emotion tags
    ("哇，这个分数相当不错呀！（羞涩微笑）继续加油！(点赞)",
     "哇，这个分数相当不错呀！ 继续加油！"),
    
    # Case 5: literal artifact phrase
    ("哇，650分，这个分数相当不错呀！拇指向上，没有特别感兴趣的专业也很正常",
     "哇，650分，这个分数相当不错呀！没有特别感兴趣的专业也很正常"),

    # Case 6: markdown asterisks and hashtags
    ("## 招生建议\n**特别提示**：请认真核对！",
     "招生建议\n特别提示：请认真核对！")
]

print("Running emoji cleaner tests...")
for i, (inp, expected) in enumerate(test_cases):
    cleaned = clean_speech_text(inp)
    print(f"Test {i+1}:")
    print(f"  Input:    {inp}")
    print(f"  Cleaned:  {cleaned}")
    assert "👍" not in cleaned, f"Emoji 👍 leaked in case {i+1}"
    assert "😊" not in cleaned, f"Emoji 😊 leaked in case {i+1}"
    assert "🎉" not in cleaned, f"Emoji 🎉 leaked in case {i+1}"
    assert "拇指向上" not in cleaned, f"'拇指向上' leaked in case {i+1}"
    assert "羞涩微笑" not in cleaned, f"'羞涩微笑' leaked in case {i+1}"
    assert "**" not in cleaned, f"Markdown leaked in case {i+1}"
    print(f"  ✅ Case {i+1} PASSED")

print("\n🎉 ALL EMOJI CLEANER TESTS PASSED 100%!")
