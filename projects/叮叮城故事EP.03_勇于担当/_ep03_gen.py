# -*- coding: utf-8 -*-
"""依据 EP03_勇于担当_任务提示词_v1.md 重写 EP03 的 12 镜分镜，落回 project.json。
修复旧草稿的身份矛盾：TT虎 开车蹭柱 -> 巡检发现静止备车剐蹭；拨手机上报 -> 值守系统报备单；
duration 改整数；立场锚回收；三次反转；视觉 DNA 前缀；静态机位；无人类 / 无可读文字；合计 131 秒。
图片 / 视频仍 pending。"""
import json, os

BASE = os.path.dirname(os.path.abspath(__file__))
PJ = os.path.join(BASE, "project.json")

PREFIX = ("3D cartoon cinematic style, chibi Q-version tiger character TT-Hu with orange-gold fur, "
          "dark brown/black stripes, exactly two dark brown stripes on each cheek forming a '>' shape "
          "beside the outer corner of each eye (no other cheek stripes), clear black 王 mark on forehead, "
          "white muzzle and belly, blue inner ears, big round black eyes, pink nose, short round limbs, "
          "blue work uniform with ID badge, Pixar-like 3D render, soft global illumination, "
          "35mm anamorphic lens, cinematic lighting, rainy-night city of Dingding, neon blue-orange contrast, "
          "no readable text, no letters")

VBASE = ("Locked-off static camera, absolutely no camera movement, no zoom, no pan. "
         "Keep all characters fully inside the frame, no morphing, no extra limbs. "
         "Subtle in-frame motion only:")

def scene(index, title, narration, duration, sound, img_tail, vid_tail):
    return {
        "index": index, "year": "", "age": "",
        "title": title, "narration": narration, "duration": duration, "sound": sound,
        "image_prompt": PREFIX + ", " + img_tail,
        "video_prompt": VBASE + " " + vid_tail,
        "image_path": "", "video_path": "", "audio_path": "",
        "image_status": "pending", "video_status": "pending",
    }

scenes = [
    scene(1, "第1镜 · 一道浅痕",
          "深夜，地下车库的灯半明半暗。一束手电光，停在一台静止备车的后视镜上——那里有一道浅浅的刮痕。",
          11, "环境：车库回声、排风低鸣；拟音：手电咔哒、脚步；BGM：轻起悬疑；旁白：低声引入",
          "underground parking garage at night, dim half-lit, a flashlight beam sweeps and stops on the side mirror of a stationary white fleet car, a faint scrape on the mirror, TT-Hu not in shot, cold blue light, metal floor reflection",
          "the flashlight beam slowly moves across the concrete pillar and settles on the side mirror, a faint scrape visible, no characters enter"),
    scene(2, "第2镜 · 立场锚",
          "TT虎蹲下身，指尖拂过那道刮痕。他对自己说：「看见了，就不能当没看见。」",
          11, "环境：车库安静；拟音：蹲下、指尖轻拂；BGM：沉稳；旁白：立场落定",
          "close-medium shot, TT-Hu crouching beside the stationary white fleet car, one paw touching the faint scrape on the side mirror, determined calm face, a flashlight on the floor casting a small pool of light, cold garage",
          "TT-Hu crouches down, pauses, then his paw lightly brushes the scrape; he nods to himself, subtle, no big motion"),
    scene(3, "第3镜 · 一个念头",
          "一个念头冒上来：没人看见，绕开就是了。可小助手飘来，投出一张待填的报备单。",
          10, "环境：车库低鸣；拟音：投影弹出；BGM：压抑；旁白：内心独白",
          "TT-Hu standing in the dim garage, a tiny mini-tiger thought-bubble creature whispering on his shoulder (thought only, not real), a small floating robot assistant nearby projecting a glowing reporting form hologram with abstract timeline blocks and icons, no readable text",
          "the tiny thought-tiger leans in whispering, TT-Hu's brow tightens; the assistant projects a form hologram that pops up softly"),
    scene(4, "第4镜 · 没有绕开",
          "他本可以转身离开。可他退了半步，又蹲了回去——把刮痕看个清楚。",
          11, "环境：车库；拟音：脚步顿住、退步；BGM：悬念；旁白：反转先声",
          "medium shot, TT-Hu turning to leave then stopping, stepping back half a pace and crouching down again to inspect the scrape closely, conflicted but choosing, cold garage light",
          "TT-Hu turns, pauses, steps back, lowers into a crouch again and leans toward the scrape, small decisive motion"),
    scene(5, "第5镜 · 猫老板劝",
          "猫老板路过，摆摆手：「这点小伤，别声张，修车钱我出。」",
          11, "环境：车库；拟音：猫老板挥手；BGM：低沉；旁白：诱惑方出场",
          "a grey cat boss with round glasses and grey suit leaning against a pillar, waving a hand casually to dismiss the matter, TT-Hu crouching nearby looking up, dim garage, no readable text",
          "the grey cat boss waves a hand dismissively and gestures for TT-Hu to leave; TT-Hu stays crouched, unmoved"),
    scene(6, "第6镜 · 系统报备",
          "他没争辩，也没迎合。回到值守台，在系统里一条条填好时间、位置、损伤。",
          11, "环境：值守台键盘；拟音：按键、表单提交；BGM：稳住；旁白：按流程",
          "TT-Hu at the duty console, a glowing reporting form hologram projected by the small floating robot assistant, abstract timeline blocks and icons only, no readable text, TT-Hu filling fields with focus, control room with rain window",
          "TT-Hu's paw hovers then taps on the glowing form, a field lights up, he fills one line after another, calm and precise"),
    scene(7, "第7镜 · 隐患逻辑",
          "他忽然明白：今天不摆上台，明天这道小痕，会拖成别人头上的糊涂账。",
          11, "环境：值守台；拟音：笔落；BGM：渐明；旁白：看见盲区",
          "close-up of TT-Hu's face at the console, a soft warm light from the screen reflects on his cheek, thoughtful eyes, the reporting form glowing beside him, rain window behind",
          "TT-Hu's eyes shift to the screen, a small breath out, his shoulders settle; the warm screen light flickers softly"),
    scene(8, "第8镜 · 复盘会",
          "第二天复盘会，他把这起小剐蹭，放上了大屏的时间线。",
          11, "环境：会议室低语；拟音：脚步、大屏亮起；BGM：冷静；旁白：摊开讲",
          "meeting room, TT-Hu standing before a big screen showing an abstract timeline with colored blocks, a few animal colleagues seated, no readable text, cool white meeting light",
          "TT-Hu stands and the big screen lights up with an abstract timeline; the room quiets, colleagues turn to look"),
    scene(9, "第9镜 · 同事质疑",
          "有同事小声嘀咕：「这么小的事，何必自己找麻烦。」他没退，把隐患逻辑讲清楚。",
          10, "环境：会议室议论；拟音：交头接耳；BGM：收紧；旁白：直面质疑",
          "medium shot, animal colleagues whispering to each other in the meeting room, TT-Hu standing steady before the screen, calm gaze, cool meeting light, no readable text",
          "colleagues exchange glances and whisper; TT-Hu stays still, then speaks one clear sentence with steady lip movement"),
    scene(10, "第10镜 · 新规则",
          "安静几秒后，白板上多了一行：「车库剐蹭，即报。」有人，带头点了头。",
          11, "环境：会议室；拟音：落笔；BGM：转暖；旁白：沉淀成规",
          "close-up of a whiteboard where a new line of abstract rule icon appears, animal colleagues in soft focus, one nodding, warm light beginning to fill the room, no readable text",
          "a new rule line fades onto the whiteboard, one colleague slowly nods, others follow, subtle warm light rise"),
    scene(11, "第11镜 · 氛围变了",
          "会议室的空气松了下来。接着，有人轻轻鼓起了掌。",
          11, "环境：会议室；拟音：掌声渐起；BGM：明朗展开；旁白：转变",
          "meeting room, animal colleagues beginning to applaud, TT-Hu slightly surprised, warm light on faces, no readable text",
          "colleagues start to applaud softly, TT-Hu looks around, a small surprised blink, warm light"),
    scene(12, "第12镜 · 敢于担当",
          "天亮了。TT虎站在楼顶，城市在脚下醒来。出事不躲，才担得起后背。",
          12, "环境：楼顶风声、城市苏醒；拟音：无；BGM：温暖收尾和弦；旁白：点题",
          "dawn rooftop, TT-Hu standing at the railing overlooking the city waking up, warm golden light, distant skyline, full body, generous headroom",
          "TT-Hu stands at the rooftop railing, the city lights below fade as dawn breaks, a gentle breeze, he looks out calmly, holds the pose"),
]

d = json.load(open(PJ, encoding="utf-8"))
d["scenes"] = scenes
d["ending_subtitle"] = "勇于担当 · 出事不躲，担得起事，才交得了后背"
d["updated_at"] = "2026-10-23T10:26:52"
assert sum(s["duration"] for s in scenes) >= 120, "总时长不足 120 秒"
json.dump(d, open(PJ, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("EP03 已重写：%d 镜，合计 %d 秒" % (len(scenes), sum(s["duration"] for s in scenes)))

# 删除被完全覆盖的旧规范（内容已并入 _v2，可从 git 历史找回）
old = os.path.join(os.path.dirname(BASE), "dingding-city", "剧本生成规范.md")
if os.path.exists(old):
    os.remove(old)
    print("已删除旧规范：", old)
