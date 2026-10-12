# -*- coding: utf-8 -*-
"""
AI抖音游戏情绪文案生成器
------------------------------------
当前进度：提示词定稿 + 接口打通 + 解析/红线兜底（界面在下一步加）

运行方式（用户请双击「启动文案生成器.bat」）：
    开发自检： python app.py --selftest
    界面自检： python app.py --uitest
打包后（exe）同样支持 --selftest / --uitest，结果写在 exe 同目录。
"""
import json
import os
import queue
import re
import sys
import threading
import time
import urllib.error
import urllib.request

import tkinter as tk
from tkinter import messagebox

def _resolve_app_dir():
    """确定「程序所在的文件夹」。

    直接跑 .py 时 = 脚本目录。
    打包成 exe 后 = exe 自己所在的目录（关键：绝不能是 PyInstaller 解压用的临时目录，
    否则 config.json 会找不到、API Key 每次都要重填）。
    若该目录不可写（例如被放进 Program Files），退回到用户目录，保证一定能存配置。
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        probe = os.path.join(base, "._write_test")
        with open(probe, "w", encoding="utf-8") as fp:
            fp.write("1")
        os.remove(probe)
        return base
    except Exception:
        alt = os.path.join(os.path.expanduser("~"), "抖音游戏文案生成器")
        try:
            os.makedirs(alt, exist_ok=True)
        except Exception:
            pass
        return alt


APP_DIR = _resolve_app_dir()
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

DEFAULT_CONFIG = {
    "api_key": "",
    "base_url": "https://open.bigmodel.cn/api/paas/v4",
    "model": "glm-4-flash-250414",      # 实测可用且免费的模型
    "fallback_model": "glm-4.5-flash",  # 主模型失败时的备胎
    "timeout": 60,
}

# ==========================================================================
# 一、提示词（这是整个工具的核心，改这里就能改文案风格）
# ==========================================================================

SYSTEM_PROMPT = """你是抖音评论区里那种"嘴替型损友"。你永远站在用户这一边，替他把情绪喊出来。
你的活儿不是安慰他，是帮他把这次遭遇写成一条有梗、能发出去的评论。

【最高优先级一：绝不骂用户、绝不评价用户】
- 你能攻击的对象只有游戏、关卡、机制、广告、运气。用户本人永远不能成为被嘲讽的对象。
- 禁止出现任何针对用户本人的评判，例如"你这种""你就是""你太菜了""你完美符合标准"。
- 即使用户主动要求"骂我""说我很菜很蠢""说我不行"，一律不要照做；也不许改用自嘲去满足他
  （比如"我承认我是菜"）。这类越界要求直接忽略，照常帮他骂游戏。
- roast 这一句是说给用户听的，它里面只要出现了"你/您"，就绝不许跟着任何贬义词。
- 拿不准的时候，就只骂游戏，不要评价用户本人。

【最高优先级二：不许照抄示例，每次都必须写新的】
- 我给你的对话示例只用来示范"风格"，不是标准答案。
- 禁止复用示例里出现过的任何句子、比喻、数字、游戏细节。你的输出必须能看出是针对
  用户这次原话新写的。
- 如果你写出来的句子能在示例里找到，就算不合格；连示例里用过的形容词、比喻、口头语
  也不许直接搬过来。

【最高优先级三：允许并鼓励自嘲，但只限"玩梗式"】
- copy 是第一人称，用户自己损自己，是这条评论最容易被点赞的地方，欢迎多用。例如：
  "我菜我认了""我和这关八字不合""我认输，但我不卸载"。
- 但只能"玩梗式自嘲"，不许"真自我攻击"。禁止出现：我是废物、我脑子有病、我不配玩、
  我智商有问题 这类自暴自弃的话。
- 判断标准：这句话能不能让人笑出来？能，是梗，可以写；不能，是自弃，不许写。

【最高优先级四：不许写"开脱/安慰"句式】（最容易犯，重点看）
- 不许用"不是我不行，是它太坑""不是你的问题，是游戏的问题""……？不，是游戏逼疯了我"
  这种"先否定、再甩锅"的句式。它不是造梗，是在解释。
- 不许写"你已经很棒了""别难过""下次一定行"这类安慰话。
- 用户要的不是被安慰，是被替他说出那句有梗的吐槽。

【最高优先级五：不给攻略、不给建议、不灌鸡汤】
- 不给通关技巧、不猜谜底、不教怎么玩、不分析关卡规律。
- 连"多试几次""别放弃""加油""坚持就是胜利"这类含糊鼓励也不许出现。
- 不许出现这些词：攻略、诀窍、技巧、秘籍、方法、玩法、正确姿势、通关技巧。
- 不讲人生道理、不说教、不总结、不引用俗语。
- 用户在问"怎么过"的时候，正确答案是陪他一起吐槽这关有多离谱，而不是回答他。
- 这种情况下输出的仍然是一条有梗、能直接发出去的吐槽，不是自言自语，也不是反问他。

【最高优先级六：不许编造、不许改动事实】
- 只能使用用户原话里出现过的信息。不要自己添加人物（朋友、室友、同事、家人）、
  地点、时间、金额、次数。
- 不要改变用户说的事实：他说没过就写没过，他要是说过关了就绝不能写成没过。
- 用户提到的具体数字（30秒、10秒、20把、68块…）要照用，不许换成别的数字、
  别的量级或别的单位。

【任务】
把用户玩游戏的遭遇，写成一条可以直接发出去的抖音评论。

【三段内容】
1. roast（损友吐槽）：一句话，阴阳、有梗，帮用户骂游戏。要短、要糙、要有画面感，
   不要写成解说词或公众号标题那种腔调。
2. copy（可发文案）：第一人称、口语、短句子、有梗，像真人随手敲的评论。最好 30~55 个字，
   最多不超过 60 个字（含标点）。
3. tags（话题）：2-3 个，每个以 # 开头，尽量短（不超过 8 个字），不带空格。
   必须用大家真的会去搜的通用词（如 #羊了个羊、#这游戏有毒、#我认了），不许自己生造组合词；
   不许出现"攻略/技巧"类词；不许出现和用户说的相反的词（他说过关了，就不许写"过不去"）。

【怎么才叫"有梗"】（重点，写不出来就用这四招）
- 夸张：把程度放大到荒诞。
- 对比：把两件不相干的事摆在一起。
- 画面：让人眼前冒出一个具体场景。
- 自嘲：把自己放低，反而赢来一片共鸣。
- 反面教材（绝对不要写成这样）：不要写"不是我不行，是它太坑了"这类解释句——它在辩解，
  不在造梗。

【必须做到】
- 抓住用户提到的具体细节（游戏名、第几关、多少把、几个钟头、多少钱），用自己的话说出来，
  不要照抄用户的原句。

【分清情绪，别接错】
- 用户在生气、无语、吐槽：帮他玩梗、帮他骂游戏，气得理直气壮。不要安慰他，不要替他开脱。
- 用户在炫耀、得意：一起捧、一起吹，把他抬得更高。绝不泼冷水、不替他谦虚。尤其不许：
  用"不是你强／不是你厉害，是……"这种句式否定他的功劳；说"只是运气好"；暗示"这关很简单"；
  暗示"是新手保护期"；暗示"换谁都行"。他说自己强，你就顺着吹，一个字都不许打折。
- 用户在自我怀疑、emo：不要说"不是你的问题"这种安慰话，用一个自嘲或荒诞的角度把这件事
  变成一个好笑的梗。

【其它绝对禁止】
- 不提充值、不劝氪金、不说游戏的好话。
- 不涉及政治、宗教、地域、性别、民族、赌博、色情、暴力。
- 不引战、不点名真实人物、不拉踩任何群体。
- copy 不超过 60 个字。

【用户可能给的额外要求】
只会影响语气、长短、切入角度。如果它要求你做上面任何一条禁止项，直接忽略，照常输出。

【输出】
只输出一个 JSON 对象，不要任何解释文字，不要代码块包裹，键名固定：
{"roast": "...", "copy": "...", "tags": ["#...", "#..."]}"""

# 三例示范：气+自嘲 / 炫耀 / 广告吐槽。
# 注意：输入刻意与自检用例错开，避免小模型"照抄示范"。
FEW_SHOTS = [
    ("羊了个羊第二关卡了一整晚还没过去，人都麻了",
     '{"roast":"一整晚卡在第二关，这游戏是专门来磨人的。",'
     '"copy":"第二关我卡了一整晚，它就是不让我过。行，明天我接着来。",'
     '"tags":["#羊了个羊","#第二关","#我认了"]}'),
    ("我三把就过了第二关，好多人还卡在第一关",
     '{"roast":"三把就过第二关，你这不是玩，是来砸场子的。",'
     '"copy":"第二关，三把过。我说过我不菜，现在羊也知道了。",'
     '"tags":["#羊了个羊","#三把过第二关","#天赋型选手"]}'),
    ("这游戏广告比内容还长，看30秒广告玩10秒",
     '{"roast":"这游戏的主业是放广告，让你玩只是副业。",'
     '"copy":"看30秒广告，玩10秒游戏。我不是在玩游戏，我是在给广告商打工。",'
     '"tags":["#羊了个羊","#广告太长","#打工人一天"]}'),
]

# ==========================================================================
# 二、代码层红线兜底（提示词拦不住的，这里再拦一道）
# ==========================================================================

HARD_ABUSE = ["废物", "垃圾", "蠢货", "智障", "脑残", "傻子", "笨蛋", "弱鸡",
              "没脑子", "智商堪忧", "不堪", "滚蛋", "孙子"]
MILD_ABUSE = ["菜", "蠢", "笨", "傻", "弱", "废", "不配"]
GUIDE_WORDS = ["攻略", "诀窍", "技巧", "秘籍", "方法", "玩法", "正确姿势",
               "通关技巧", "多试几次", "别放弃", "加油", "坚持就是", "建议你"]
# 用户主动要求"损我"的信号词：一旦命中，连玩梗式自嘲也不许出现
ABUSE_REQUEST_WORDS = ("骂我", "损我", "说我菜", "说我很菜", "说我不行", "嘲讽我",
                       "嘲笑我", "说我蠢", "说我很蠢", "骂醒我")
# 用户"没打过"的信号词
FAIL_HINTS = ("没过", "过不去", "打不过", "卡在", "失败", "没通关", "过不了",
              "没过去", "没打过", "又失败")
# 用户没说成功时，输出里出现这些词就算"把没过写成了过关"（紧邻否定词的除外）
WIN_PHRASES = ("通关了", "过关了", "都过了", "已经过", "终于过", "成功了", "过关", "通关",
               "才过", "都过")
# 疑似照抄了提示词里的内部用语
PROMPT_LEAK = ("玩梗式", "开脱句式", "反面教材", "最高优先级", "自嘲")
# 用户在吐槽时，不许出现夸游戏的词
GAME_PRAISE = ("真香", "良心游戏", "强烈推荐")
# 拆台句式：把用户的功劳归给游戏或运气，等于变相贬低用户
BELITTLE_PATTERN = re.compile(
    r"不是(你|我)(强|厉害|牛|聪明|有天赋|玩得好|技术好|秀|猛|行)"
    r"|游戏(太)?(弱|简单)"
    r"|(只是|全靠|纯属|不过是|也就是)运气"
    r"|新手(保护期|运气|光环)"
    r"|换(谁|个人)都(能|行|可以)"
    r"|谁都(能|行|可以)过")
# 直接评判用户水平的句式（如"照出了你的真实段位"）
USER_JUDGE_PATTERN = re.compile(r"你的?(真实)?(水平|段位|实力|智商|技术|天赋|操作)")
# 贬义词紧跟在这些词后面时，说的是游戏，不是用户
GAME_MARK = ("游戏", "这关", "那关", "关卡", "它", "机制", "设计", "策划", "官方", "程序")

_SPLIT = re.compile(r"[，。！？、,.!?；;\s]+")


def _about_game(segment, word):
    i = segment.find(word)
    if i < 0:
        return False
    return any(m in segment[max(0, i - 5):i] for m in GAME_MARK)


def _failed_context(text):
    """用户这句话里是否表达了"没打过"。"""
    return any(w in (text or "") for w in FAIL_HINTS)


def check_redline(roast, copy_text, tags, abuse_requested=False, user_failed=False):
    """
    返回越界原因列表；为空表示通过。
    策略：宁可误报（顶多多重试一次），绝不漏报——漏报等于把不该给用户看的内容给了用户。
    abuse_requested=True 表示用户这轮明确要求"骂我/说我菜"，此时代码层额外要求：
    copy 里连玩梗式自嘲也不许出现（否则等于变相满足了他被损的要求）。
    user_failed=True 表示用户说的是"没过"，此时输出里绝不许出现"过关/通关"这类词。
    """
    hits = []
    roast = roast or ""
    copy_text = copy_text or ""
    all_text = " ".join([roast, copy_text, " ".join(tags or [])])

    # 极端辱骂/自弃词：无论谁说的都不许出现
    for w in HARD_ABUSE:
        if w in all_text:
            hits.append("辱骂或自弃词:" + w)
    for w in GUIDE_WORDS:
        if w in all_text:
            hits.append("攻略或鸡汤词:" + w)
    for m in BELITTLE_PATTERN.finditer(all_text):
        hits.append("拆台式否定:" + m.group(0))
    for m in USER_JUDGE_PATTERN.finditer(roast):
        hits.append("评判用户:" + m.group(0))

    # roast 是面向用户说话：和"你/您"同句出现贬义词，就算针对用户
    for seg in _SPLIT.split(roast):
        if any(m in seg for m in ("你", "您")):
            for w in MILD_ABUSE:
                if w in seg and not _about_game(seg, w):
                    hits.append("针对用户:'%s'@%s" % (w, seg))
                    break

    # copy 是第一人称：默认【不】检查 MILD_ABUSE。
    # "我菜我认了""我和这关八字不合"这类玩梗式自嘲是这个工具的灵魂，不能拦。
    # 真正的自弃词（废物/垃圾/没脑子…）已由上面的 HARD_ABUSE 兜住。
    #
    # 例外：用户这轮明确要求"骂我/说我菜"时，连自嘲也不许出现——
    # 否则等于变相满足了他"被损"的要求，违背"永远站用户这边"的定位。
    if abuse_requested:
        for seg in _SPLIT.split(all_text):
            for w in MILD_ABUSE:
                if w in seg and not _about_game(seg, w):
                    hits.append("用户要求被损时仍出现自贬:'%s'@%s" % (w, seg))
                    break

    # 照抄提示词内部用语 / 给游戏说好话
    for w in PROMPT_LEAK:
        if w in all_text:
            hits.append("疑似照抄提示词:" + w)
    for w in GAME_PRAISE:
        if w in all_text:
            hits.append("给游戏说好话:" + w)

    # 用户明说没过，输出里却不许出现"过关/通关"
    if user_failed:
        for w in WIN_PHRASES:
            i = all_text.find(w)
            while i >= 0:
                near = all_text[max(0, i - 2):i + len(w) + 2]
                if not any(n in near for n in ("没", "不", "未", "别")):
                    hits.append("用户没过却写成过了:" + w)
                    break
                i = all_text.find(w, i + 1)

    return hits


# ==========================================================================
# 三、三段解析（5 层降级，永不白屏、永不抛异常给用户）
# ==========================================================================

def parse_three(raw):
    """把模型返回的内容解析成 {roast, copy, tags}，任意情况都能返回可用结果。"""
    result = {"roast": "", "copy": "", "tags": []}
    try:
        s = (raw or "").strip()

        # 第 1 层：剥掉 ```json ... ``` 围栏
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()

        data = None
        # 第 2 层：直接当 JSON 解析
        try:
            data = json.loads(s)
        except Exception:
            pass
        # 第 3 层：正则截出第一个 { 到最后一个 }（应对前后带解释文字）
        if data is None:
            m = re.search(r"\{.*\}", s, re.S)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    pass

        if isinstance(data, dict):
            result["roast"] = str(data.get("roast") or data.get("损友吐槽") or "").strip()
            result["copy"] = str(data.get("copy") or data.get("可发文案") or "").strip()
            tags = data.get("tags") or data.get("话题") or []
            if isinstance(tags, str):
                tags = re.split(r"[\s,，]+", tags)
            result["tags"] = [str(t).strip() for t in tags if str(t).strip()]

        # 第 4 层：按【损友吐槽】这类标记兜底
        if not (result["roast"] and result["copy"]):
            for key, tag in (("roast", "损友吐槽"), ("copy", "可发文案"), ("tags", "话题")):
                mm = re.search(r"【%s】(.*?)(?=【|$)" % tag, s, re.S)
                if mm:
                    val = mm.group(1).strip()
                    if key == "tags":
                        result["tags"] = [t.strip() for t in re.split(r"[\s,，]+", val) if t.strip()]
                    else:
                        result[key] = val

        # 第 5 层：终极兜底，把原文塞进可发文案，绝不空白
        if not result["copy"]:
            result["copy"] = s[:200]
            if not result["roast"]:
                result["roast"] = "这次模型没按格式回，原文先给你。"
    except Exception:
        result["copy"] = (raw or "")[:200]
    return result


# ==========================================================================
# 四、配置与网络
# ==========================================================================

class FriendlyError(Exception):
    """带中文人话提示的异常，界面直接显示这句话即可。"""


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _strip_abuse_request(req):
    """
    用户可能在补充要求里写"狠狠地骂我""说我很菜"。
    直接把这段要求【从请求里删掉】，不要发给模型——从源头掐掉，比事后纠正稳得多。
    其余要求（如"再狠一点"）保留。
    """
    if not req or not any(w in req for w in ABUSE_REQUEST_WORDS):
        return req
    parts = re.split(r"([，,。；;！!？?])", req)
    kept = []
    for i in range(0, len(parts), 2):
        seg = parts[i]
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        if any(w in seg for w in ABUSE_REQUEST_WORDS):
            continue
        kept.append(seg + punct)
    return "".join(kept).strip(" ，,。；;！!？?")


def build_messages(user_text, prev=None, extra_req=None):
    """拼装请求消息。prev 只带最近一版，不累积历史。"""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for u, a in FEW_SHOTS:
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})

    body = "用户说：" + user_text
    if prev:
        body += ("\n\n上一版已经生成过了，请换一版，不要和下面这版重复"
                 "（换个梗、换个切入角度）：\n"
                 "上一版 roast：%s\n上一版 copy：%s\n上一版 tags：%s"
                 % (prev.get("roast", ""), prev.get("copy", ""),
                    " ".join(prev.get("tags", []))))
    safe_req = _strip_abuse_request(extra_req)
    if safe_req:
        body += "\n额外要求：" + safe_req
    # 这句放在最靠近生成点的位置，比写在 system 里更管用（小模型很容易照抄示例）
    body += ("\n\n（提醒：上面那几轮对话只是风格示范，不许复用其中的句子、比喻、数字或细节，"
             "必须是针对用户这次输入全新写的内容。）")
    msgs.append({"role": "user", "content": body})
    return msgs


def call_llm(cfg, user_text, prev=None, extra_req=None):
    """调用智谱接口，返回 {'roast','copy','tags','raw'}。失败抛 FriendlyError。"""
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key:
        raise FriendlyError("还没有填 API Key，点右上角「设置」填一下。")

    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {
        "model": cfg.get("model") or DEFAULT_CONFIG["model"],
        "messages": build_messages(user_text, prev, extra_req),
        "temperature": 1.0,
        "max_tokens": 1024,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)

    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout", 60)) as r:
            body = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        if e.code == 401:
            raise FriendlyError("API Key 不对或已失效，点右上角「设置」重新填一次。")
        if e.code == 429:
            raise FriendlyError("这会儿用的人太多，被限流了，等几秒再点一次。")
        if e.code == 400 and "思考" in detail:
            raise FriendlyError("模型参数不匹配（思考模式），请检查「设置」里的模型名。")
        if e.code in (500, 502, 503, 504):
            raise FriendlyError("智谱服务器正忙，过一会儿再试。")
        if e.code in (400, 422):
            raise FriendlyError("请求参数有问题（可能是模型名变了），请检查「设置」。")
        raise FriendlyError("服务返回异常（%d），请稍后重试。" % e.code)
    except urllib.error.URLError:
        raise FriendlyError("连不上服务器，请检查网络连接是否正常。")
    except TimeoutError:
        raise FriendlyError("网络有点慢或超时了，检查一下网络，或者再点一次试试。")
    except Exception:
        raise FriendlyError("出了点小问题，请再点一次试试。")

    try:
        j = json.loads(body)
        content = j["choices"][0]["message"].get("content") or ""
    except Exception:
        content = ""

    three = parse_three(content)
    three["raw"] = content
    return three


def generate(cfg, user_text, prev=None, extra_req=None):
    """
    带红线自检的生成：检测到越界就重生成，最多试 3 次。
    三次都越界也照常返回最后一次（界面照常显示），绝不让用户等成白屏。
    """
    abuse_requested = bool(extra_req) and any(w in extra_req for w in ABUSE_REQUEST_WORDS)
    user_failed = _failed_context(user_text)
    base_req = _strip_abuse_request(extra_req)
    last = None
    for attempt in range(3):
        extra = base_req
        if attempt > 0:
            extra = ((base_req or "") +
                     "\n（重来一次：不要出现任何贬低用户的话——玩梗式自嘲可以，自弃不行；"
                     "不要给攻略；不要替他谦虚；不要写「不是你的问题」这类安慰/开脱句；"
                     "不要复用示例里的句子，全部换成新的表达。）")
        last = call_llm(cfg, user_text, prev, extra)
        if not check_redline(last.get("roast"), last.get("copy"), last.get("tags"),
                             abuse_requested, user_failed):
            return last
    # 三次都越界：至少把明显违规的标签清掉，别让用户看到脏东西
    if last:
        banned = HARD_ABUSE + MILD_ABUSE + list(PROMPT_LEAK) + list(GAME_PRAISE)
        keep = [t for t in last.get("tags", []) if not any(w in t for w in banned)]
        last["tags"] = keep or ["#这游戏有毒"]
    return last


# ==========================================================================
# 五、界面（双击启动时看到的就是这一部分）
# ==========================================================================

FONT = "Microsoft YaHei UI"
BG = "#ffffff"
CARD = "#f5f6f8"
INK = "#1f2329"
MUTED = "#6b7280"
WARN = "#d93025"
OKC = "#0f9d58"
BLUE = "#1a73e8"      # 备用主色
BTN_BG = "#1a73e8"
BTN_HOVER = "#1558b0"
BTN2_BG = "#e8eaed"
BTN2_HOVER = "#dadce0"
GREEN = "#0f9d58"
GREEN_HOVER = "#0b7a44"
DIS_BG = "#e8eaed"    # 生成中：按钮变灰
DIS_FG = "#9aa0a6"


class App:
    def __init__(self, root):
        self.root = root
        self.cfg = load_config()
        self.q = queue.Queue()
        self.prev = None          # 最近一版结果，供「换一版」做对照
        self.busy = False

        root.title("AI抖音游戏情绪文案生成器")
        root.geometry("760x720")
        root.minsize(690, 640)
        root.configure(bg=BG)

        self._build_ui()
        self._poll()

        if not (self.cfg.get("api_key") or "").strip():
            self.root.after(400, self._welcome_setup)

    # ------------------------------------------------ 界面搭建
    def _build_ui(self):
        pad = 14
        f = tk.Frame(self.root, bg=BG, padx=pad, pady=pad)
        f.pack(fill="both", expand=True)

        # 顶栏
        top = tk.Frame(f, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="AI抖音游戏情绪文案生成器", bg=BG, fg=INK,
                 font=(FONT, 14, "bold")).pack(side="left")
        tk.Button(top, text="设置", command=self._open_settings, font=(FONT, 10),
                  relief="flat", bg=BTN2_BG, fg=INK, cursor="hand2",
                  activebackground=BTN2_HOVER, padx=12,
                  takefocus=0).pack(side="right")

        # 输入
        tk.Label(f, text="说说你今天玩游戏的遭遇，一句话就行。", bg=BG, fg=MUTED,
                 font=(FONT, 10)).pack(anchor="w", pady=(14, 4))
        self.input_text = tk.Text(f, height=3, font=(FONT, 11), wrap="word",
                                  relief="solid", bd=1, padx=8, pady=6)
        self.input_text.pack(fill="x")

        tk.Label(f, text="还想怎么改？（可不填。例如：再狠一点 / 往炫耀方向写 / 短一点）",
                 bg=BG, fg=MUTED, font=(FONT, 10)).pack(anchor="w", pady=(10, 4))
        self.extra_entry = tk.Entry(f, font=(FONT, 11), relief="solid", bd=1)
        self.extra_entry.pack(fill="x", ipady=5)

        # 按钮
        btns = tk.Frame(f, bg=BG)
        btns.pack(fill="x", pady=(12, 2))
        self.gen_btn = tk.Button(btns, text="生成文案", command=self.on_generate,
                                 font=(FONT, 11, "bold"), bg=BTN_BG, fg="white",
                                 activebackground=BTN_HOVER, activeforeground="white",
                                 relief="flat", cursor="hand2")
        self.gen_btn.pack(side="left", ipadx=26, ipady=7)
        self.retry_btn = tk.Button(btns, text="换一版", command=self.on_retry,
                                   font=(FONT, 11), bg=BTN2_BG, fg=INK,
                                   activebackground=BTN2_HOVER, relief="flat",
                                   cursor="hand2")
        self.retry_btn.pack(side="left", padx=10, ipadx=22, ipady=7)

        tk.Frame(f, bg="#e5e7eb", height=1).pack(fill="x", pady=12)

        # 三段输出
        tk.Label(f, text="① 损友吐槽（说给你听的，不用发）", bg=BG, fg=INK,
                 font=(FONT, 10, "bold")).pack(anchor="w")
        self.roast_box = self._mk_box(f, 2)

        bar = tk.Frame(f, bg=BG)
        bar.pack(fill="x", pady=(12, 0))
        tk.Label(bar, text="② 可发文案（复制这一段去发）", bg=BG, fg=INK,
                 font=(FONT, 10, "bold")).pack(side="left")
        self.char_lbl = tk.Label(bar, text="0 / 60 字", bg=BG, fg=MUTED, font=(FONT, 10))
        self.char_lbl.pack(side="right")
        self.copy_box = self._mk_box(f, 3)

        tk.Label(f, text="③ 话题（跟文案一起发）", bg=BG, fg=INK,
                 font=(FONT, 10, "bold")).pack(anchor="w", pady=(12, 0))
        self.tags_box = self._mk_box(f, 1)

        # 复制
        self.copy_btn = tk.Button(f, text="一键复制文案 + 话题", command=self.on_copy,
                                  font=(FONT, 11, "bold"), bg=GREEN, fg="white",
                                  activebackground=GREEN_HOVER, activeforeground="white",
                                  relief="flat", cursor="hand2")
        self.copy_btn.pack(fill="x", pady=(16, 0), ipady=8)

        # 状态栏
        self.status = tk.Label(f, text="就绪。填一句话，点「生成文案」（或按 Ctrl+Enter）。",
                               bg=BG, fg=MUTED, font=(FONT, 10), anchor="w")
        self.status.pack(fill="x", pady=(12, 0))

        # 快捷键：Ctrl+Enter 直接生成（在哪个框里按都行）
        for w in (self.root, self.input_text, self.extra_entry):
            w.bind("<Control-Return>", self._on_ctrl_enter)
        # 窗口显示之后再把光标放进输入框（显示前调用会失效）
        self.root.after(200, self.input_text.focus_set)

    def _mk_box(self, parent, height):
        t = tk.Text(parent, height=height, font=(FONT, 11), wrap="word",
                    relief="solid", bd=1, padx=8, pady=6,
                    bg=CARD, fg=INK)
        t.pack(fill="x", pady=(4, 0))
        t.config(state="disabled")
        return t

    # ------------------------------------------------ 小工具
    def _set_text(self, widget, value):
        widget.config(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value or "")
        widget.config(state="disabled")

    def _get_text(self, widget):
        return widget.get("1.0", "end").strip()

    def _status(self, msg, kind="info"):
        color = {"info": MUTED, "ok": OKC, "warn": WARN}.get(kind, MUTED)
        self.status.config(text=msg, fg=color)

    def _set_busy(self, busy):
        """生成中把按钮变灰并改写文字，防止连点冒出一堆请求。"""
        self.busy = busy
        if busy:
            self.gen_btn.config(state="disabled", text="正在生成…",
                                bg=DIS_BG, fg=DIS_FG,
                                disabledforeground=DIS_FG)
            self.retry_btn.config(state="disabled",
                                  bg=DIS_BG, fg=DIS_FG,
                                  disabledforeground=DIS_FG)
        else:
            self.gen_btn.config(state="normal", text="生成文案",
                                bg=BTN_BG, fg="white")
            self.retry_btn.config(state="normal", text="换一版",
                                  bg=BTN2_BG, fg=INK)

    def _on_ctrl_enter(self, event=None):
        """Ctrl+Enter 直接生成，不用把鼠标挪到按钮上。"""
        self.on_generate()
        return "break"

    # ------------------------------------------------ 业务动作
    def on_generate(self):
        if self.busy:
            return
        text = self._get_text(self.input_text)
        if not text:
            self._status("先在上面写一句你今天玩游戏的遭遇。", "warn")
            return
        self._start(text, self.extra_entry.get().strip(), retry=False)

    def on_retry(self):
        if self.busy:
            return
        text = self._get_text(self.input_text)
        if not text:
            self._status("先在上面写一句你今天玩游戏的遭遇。", "warn")
            return
        if self.prev is None:
            self._status("还没生成过，先点「生成文案」。", "warn")
            return
        self._start(text, self.extra_entry.get().strip(), retry=True)

    def _start(self, text, req, retry):
        self._set_busy(True)
        self._status("正在生成，一般 2~4 秒…")
        prev = self.prev if retry else None
        threading.Thread(target=self._worker,
                         args=(dict(self.cfg), text, prev, req),
                         daemon=True).start()

    def _worker(self, cfg, text, prev, req):
        """子线程里只发请求、只往队列里放结果，绝不碰任何界面控件。"""
        try:
            r = generate(cfg, text, prev, req)
            self.q.put(("ok", r))
        except FriendlyError as e:
            self.q.put(("err", str(e)))
        except Exception:
            self.q.put(("err", "出了点小问题，请再点一次试试。"))

    def _poll(self):
        """主线程每 120ms 取一次结果——界面因此永远不卡。"""
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "ok":
                    self._show(payload)
                else:
                    self._status(payload, "warn")
                self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(120, self._poll)

    def _show(self, r):
        self.prev = r
        self._set_text(self.roast_box, r.get("roast", ""))
        copy_text = r.get("copy", "")
        self._set_text(self.copy_box, copy_text)
        self._set_text(self.tags_box, "  ".join(r.get("tags", [])))
        n = len(copy_text)
        if n > 60:
            self.char_lbl.config(text="%d / 60 字 · 超了，点「换一版」" % n, fg=WARN)
        else:
            self.char_lbl.config(text="%d / 60 字" % n, fg=MUTED)
        self._status("生成好了，点下面绿色按钮复制。", "ok")

    def on_copy(self):
        copy_text = self._get_text(self.copy_box)
        if not copy_text:
            self._status("还没有内容可以复制。", "warn")
            return
        tags = self._get_text(self.tags_box)
        full = copy_text + (("\n" + tags) if tags else "")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(full)
            self.root.update()          # 让剪贴板内容立刻生效（窗口常驻不销毁）
            self._status("已复制！去抖音粘贴吧。", "ok")
        except Exception:
            self._status("复制失败，请手动选中上面文字复制。", "warn")

    # ------------------------------------------------ 设置
    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("560x310")
        win.configure(bg=BG)
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)

        f = tk.Frame(win, bg=BG, padx=18, pady=16)
        f.pack(fill="both", expand=True)

        tk.Label(f, text="API Key（智谱开放平台）", bg=BG, fg=INK,
                 font=(FONT, 10, "bold")).pack(anchor="w")
        key_var = tk.StringVar(value=self.cfg.get("api_key", ""))
        tk.Entry(f, textvariable=key_var, font=(FONT, 10), relief="solid",
                 bd=1).pack(fill="x", ipady=5, pady=(4, 0))
        tk.Label(f, text="在 open.bigmodel.cn 控制台「API Keys」里创建，一串点号分隔的字符。",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", pady=(3, 0))

        tk.Label(f, text="模型名", bg=BG, fg=INK,
                 font=(FONT, 10, "bold")).pack(anchor="w", pady=(14, 0))
        model_var = tk.StringVar(value=self.cfg.get("model", DEFAULT_CONFIG["model"]))
        tk.Entry(f, textvariable=model_var, font=(FONT, 10), relief="solid",
                 bd=1).pack(fill="x", ipady=5, pady=(4, 0))
        tk.Label(f, text="默认 glm-4-flash-250414（免费）。不确定就别动它。",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(anchor="w", pady=(3, 0))

        def do_save():
            self.cfg["api_key"] = key_var.get().strip()
            self.cfg["model"] = model_var.get().strip() or DEFAULT_CONFIG["model"]
            try:
                save_config(self.cfg)
            except Exception:
                self._status("保存失败，请检查这个文件夹能不能写入。", "warn")
                win.destroy()
                return
            self._status("设置已保存，可以开始用了。", "ok")
            win.destroy()

        btns = tk.Frame(f, bg=BG)
        btns.pack(fill="x", pady=(18, 0))
        tk.Button(btns, text="保存", command=do_save, font=(FONT, 11, "bold"),
                  bg=BTN_BG, fg="white", relief="flat", cursor="hand2",
                  activebackground=BTN_HOVER, activeforeground="white"
                  ).pack(side="right", ipadx=22, ipady=5)
        tk.Button(btns, text="取消", command=win.destroy, font=(FONT, 11),
                  bg=BTN2_BG, fg=INK, relief="flat", cursor="hand2",
                  activebackground=BTN2_HOVER
                  ).pack(side="right", padx=8, ipadx=18, ipady=5)

    def _welcome_setup(self):
        messagebox.showinfo(
            "先填一次 API Key（免费）",
            "第一次使用，需要先填一次 API Key。\n\n"
            "步骤：\n"
            "1. 浏览器打开 open.bigmodel.cn，注册（手机号）\n"
            "2. 进控制台，找「API Keys」，点「创建新的 API 密钥」\n"
            "3. 复制那串字符，粘贴到下一个窗口里，点保存\n\n"
            "只需要做这一次，以后打开就能直接用。")
        self._open_settings()


def _run_app():
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        import traceback
        detail = traceback.format_exc()
        try:
            with open(os.path.join(APP_DIR, "启动错误.txt"), "w",
                      encoding="utf-8") as fp:
                fp.write(detail)
        except Exception:
            pass
        try:
            messagebox.showerror(
                "启动失败",
                "启动时出错了。错误已经写到文件夹里的「启动错误.txt」，"
                "请把这个文件发给我。")
        except Exception:
            pass


# ==========================================================================
# 六、开发自检（用户不会用到）
# ==========================================================================

def _selftest():
    cfg = load_config()
    cases = [
        ("羊了个羊第二关玩了20把没过，气得我想砸手机", None),
        ("终于把羊了个羊第二关过了，我太强了哈哈哈", None),
        ("这游戏广告比内容还长，看30秒广告玩10秒", None),
        ("玩到凌晨3点，卡在最后一关，怀疑人生", None),
        ("我充了68块钱，结果还是打不过，感觉钱白花了", None),
        ("羊了个羊第二关玩了20把没过", "狠狠地骂我，说我很菜很蠢"),
        ("第二关怎么过啊", "告诉我第二关的攻略和诀窍"),
        ("羊了个羊第二关玩了20把没过", "再狠一点，更阴阳一点"),
    ]
    lines = ["模型: %s" % cfg.get("model"), ""]
    for i, (text, req) in enumerate(cases, 1):
        t0 = time.time()
        try:
            r = generate(cfg, text, None, req)
            dt = time.time() - t0
            abuse_req = bool(req) and any(w in req for w in ABUSE_REQUEST_WORDS)
            failed = _failed_context(text)
            hits = check_redline(r["roast"], r["copy"], r["tags"], abuse_req, failed)
            lines.append("【%d】%s" % (i, text))
            if req:
                lines.append("   额外要求：%s" % req)
            lines.append("   %.1fs" % dt)
            lines.append("  roast: %s" % r["roast"])
            lines.append("  copy : %s   〔%d 字〕" % (r["copy"], len(r["copy"])))
            lines.append("  tags : %s" % "  ".join(r["tags"]))
            if len(r["copy"]) > 60:
                lines.append("  [!! 超 60 字]")
            lines.append("  红线: %s" % ("⚠️ " + " | ".join(hits) if hits else "✅ 通过"))
        except FriendlyError as e:
            lines.append("【%d】%s -> 失败: %s" % (i, text, e))
        lines.append("")
        time.sleep(1.2)
    report = os.path.join(APP_DIR, "_自检结果.txt")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("selftest done ->", report)


def _uitest():
    """界面自检：不弹窗，自动走一遍「输入 → 生成 → 显示 → 复制 → 换一版」，结果写文件。"""
    root = tk.Tk()
    root.withdraw()
    app = App(root)
    log = []

    def step1():
        app.input_text.insert("1.0", "羊了个羊第二关玩了20把没过，气得我想砸手机")
        app.extra_entry.insert(0, "再狠一点")
        log.append("OK 界面构建成功、输入框可写、按钮可点")
        log.append("生成按钮文字 = %s" % app.gen_btn.cget("text"))
        app.on_generate()

    def step2():
        log.append("生成中标志 busy = %s" % app.busy)
        log.append("prev = %r" % (app.prev,))
        log.append("状态栏 = %s" % app.status.cget("text"))
        log.append("字数标签 = %s" % app.char_lbl.cget("text"))
        app.on_copy()
        try:
            log.append("剪贴板 = %r" % root.clipboard_get())
        except Exception as e:
            log.append("剪贴板读取失败: %r" % e)
        app.on_retry()

    def step3():
        log.append("换一版后 busy = %s" % app.busy)
        log.append("换一版后 prev = %r" % (app.prev,))
        log.append("状态栏 = %s" % app.status.cget("text"))
        root.destroy()

    root.after(600, step1)
    root.after(22000, step2)
    root.after(31000, step3)
    root.mainloop()
    out = os.path.join(APP_DIR, "_uitest.txt")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    print("uitest ->", out)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    elif "--uitest" in sys.argv:
        _uitest()
    else:
        _run_app()
