# -*- coding: utf-8 -*-
"""
平台内容自动发布工具（拟人版）

反检测特性：
- 发布间隔平均 3-5 天（脚本内部掷骰子决定是否发布）
- 随 relay 每晚北京 22:23 触发，脚本内部随机等待 1-5 分钟后开始
- 文案从正向励志文案库里随机选取，长短句混合，长句自动折行排进图片
- 图片完全随机生成（背景色、装饰、字体大小、文字位置每次都不同）
- 操作间加入随机延迟，模拟人类行为
- 不发布时静默退出，不发邮件
"""

import json
import random
import sys
import logging
import traceback
import hashlib
import uuid
import re
import time
import math
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("netease-notes")

BASE_URL = "https://music.163.com"
EAPI_KEY = "e82ckenh8dichen8"
NOBODY = "36cd479b6b5"

# ========== 文案库（全正向励志，2026-10-27 重写） ==========
# 口径：只发积极向上的内容，不出现抱怨/丧/负面情绪。
# 单行为正文一句；含 \n 的是两行式金句，图片与正文都按两行呈现。
QUOTES = [
    # ===== 励志奋斗（努力与行动） =====
    "努力的意义，是让未来的自己感谢现在。",
    "把喜欢的事做到极致，就是天赋。",
    "先把自己活成一道光，再谈照亮别人。",
    "今天多流的汗，都会变成明天的底气。",
    "没有白费的努力，也没有碰巧的成功。",
    "你只管努力，时间会给出答案。",
    "所有的好运，都是努力埋下的伏笔。",
    "所有的惊艳，都来自长久的准备。",
    "别怕走得慢，只怕站着不动。",
    "你今天的坚持，是别人明天的羡慕。",
    "天赋决定上限，努力决定下限，先赢在下限。",
    "每一份热爱，都值得全力以赴。",
    "路虽远，行则将至；事虽难，做则必成。",
    "千里之行，始于足下。",
    "不积跬步，无以至千里。",
    "锲而不舍，金石可镂。",
    "心之所向，素履以往。",
    "星光不问赶路人，时光不负有心人。",
    "天道酬勤，力耕不欺。",
    "越努力，越幸运。",
    "所有的坚持，终将美好。",
    "拼搏到无能为力，坚持到感动自己。",
    "别在该奋斗的年纪选择安逸。",
    "今天的努力，是为了明天有更多选择。",
    "你的努力，时间都看得见。",
    "把目标写下来，把行动做出来。",
    "每天进步一点点，一年就是巨大的改变。",
    "与其羡慕，不如开始。",
    "想做的事，今天就迈出第一步。",
    "付出不一定立刻有回报，但一定不会白费。",
    "把力气用在能改变的事情上。",
    "认真做事的人，运气都不会太差。",

    # ===== 坚持与成长 =====
    "慢慢来，比较快。",
    "成长的路上，每一步都算数。",
    "熬过的夜，都会变成照亮你的光。",
    "你比昨天更好，就足够了。",
    "允许自己笨拙地开始，也是一种勇敢。",
    "真正的成长，是安静地变强。",
    "坚持一件小事，也会收获大不同。",
    "每一次复盘，都是下一次的加速。",
    "别急，好的东西都需要时间。",
    "耐心，是天赋的另一种写法。",
    "把每一件小事做好，就是了不起。",
    "你在暗处扎根，终会在明处开花。",
    "重复是通往精通最短的路。",
    "优秀是一种习惯，不是一次表演。",
    "把简单的事做到极致，就不简单。",
    "不慌不忙，稳稳成长。",
    "每天多懂一点，世界就宽一点。",
    "积累的过程很安静，结果会很响。",
    "慢一点没关系，方向对就好。",
    "试错也是前进的一部分。",
    "今天的笨拙，是明天的熟练。",
    "一步一步走，路自然就出来了。",
    "把热爱熬成实力。",
    "你正在成为更好的自己。",
    "每一次重新开始，都值得被鼓励。",
    "日拱一卒，功不唐捐。",
    "成长从来不是突然的，是每天一点点。",

    # ===== 梦想与远方 =====
    "愿你眼里有星辰，心中有山海。",
    "愿你以梦为马，不负韶华。",
    "愿你保持热爱，奔赴山海。",
    "有梦就去追，什么时候都不晚。",
    "心若有光，何惧路长。",
    "把远方装进行囊，从脚下开始。",
    "世界很大，值得你走出去看看。",
    "去见更大的世界，遇见更好的自己。",
    "所谓远方，是一步一步走到的。",
    "愿你所有的努力，都通向想去的地方。",
    "你想去的地方，都在你努力的方向上。",
    "把梦想拆成今天的待办。",
    "愿你披荆斩棘，也愿你途中遇花。",
    "愿你眼里的光，永远不会熄。",
    "愿你走出半生，归来仍是少年。",
    "愿你不负光阴，不负自己。",
    "愿你历尽千帆，得偿所愿。",
    "逐光而行，向阳而生。",
    "向上生长，向下扎根。",
    "把每一个今天，都过成通往梦想的台阶。",
    "梦想不会逃跑，只要你一直在路上。",
    "心有多大，舞台就有多大。",
    "敢想，敢做，敢成为。",
    "远方不远，只要出发。",

    # ===== 自律与时间 =====
    "自律给我自由。",
    "早起的清晨，藏着一天的底气。",
    "把时间花在热爱上，就不算浪费。",
    "管理好今天，就管理好了未来。",
    "时间从不辜负认真生活的人。",
    "每天读点书，走点路，做点事。",
    "好的作息，是最好的自我投资。",
    "把手机放下十分钟，世界会安静很多。",
    "重要的事，先做。",
    "一年之计在于春，一日之计在于晨。",
    "别把时间都用来焦虑，用来行动更好。",
    "你对时间的态度，就是时间对你的态度。",
    "把每天过成值得纪念的一天。",
    "今日事，今日毕，心就轻了。",
    "专注一小时，胜过忙碌一天。",
    "把日子过得有规划，也留一点惊喜。",
    "少一点抱怨，多一点行动。",
    "生活有节奏，心里才有空间。",
    "认真吃饭，好好睡觉，也是一场自律。",
    "把身体养好，是一切的开始。",
    "早睡的人，赢在下一天的清晨。",
    "把每个小时用在值得的地方。",

    # ===== 积极心态 =====
    "今天也要元气满满。",
    "生活明朗，万物可爱。",
    "把每一天都当作新的开始。",
    "心态好，事事顺。",
    "晴天晒太阳，雨天听雨声。",
    "心宽一寸，路宽一丈。",
    "换个角度看，难事也有礼物。",
    "遇到难题，先深呼吸，再想办法。",
    "越简单，越快乐。",
    "把注意力放回自己能做的事上。",
    "日子是自己的，开心最重要。",
    "允许一切发生，然后继续向前。",
    "不为昨天叹息，只为今天努力。",
    "凡事尽力，然后随缘。",
    "心若向阳，无畏悲伤。",
    "积极不是盲目乐观，是相信有解法。",
    "把抱怨的时间，换成行动的时间。",
    "每天给自己一个微笑。",
    "所有的不顺，都是暂时的。",
    "人可以有情绪，但要学会自己走回来。",
    "把困难当练习题，做完就升级了。",
    "从容一点，世界不会塌。",
    "把心放宽，路自然就宽。",
    "好心情，是可以自己给自己的。",
    "今天也值得被好好对待。",

    # ===== 温暖治愈（正向表达） =====
    "你值得被温柔以待。",
    "愿你被这个世界温柔以待。",
    "愿你所有的不安，都是虚惊一场。",
    "总会有人山高路远，为你而来。",
    "你很好，你值得。",
    "愿你心里有光，脚下有路。",
    "愿你眉眼带笑，日子清甜。",
    "你笑起来的样子，真好。",
    "愿你三冬暖，愿你春不寒。",
    "愿你天黑有灯，下雨有伞。",
    "愿你身边有人陪，心里有事做。",
    "愿你的努力都有回应。",
    "愿你所求皆所愿，所行化坦途。",
    "愿你所到之处，遍地阳光。",
    "愿你平安喜乐，万事胜意。",
    "愿你每天都有一点小确幸。",
    "愿你的好心情，不需要理由。",
    "愿你的世界，永远有光。",
    "照顾好自己的情绪，是最重要的事。",
    "好好爱自己，是一生的浪漫。",
    "你现在的样子，就已经很好了。",
    "慢慢来，你已经很努力了。",
    "你不是一个人在努力。",
    "把日子过成喜欢的模样。",
    "今天也有人在默默为你加油。",

    # ===== 早晚问候（正向版） =====
    "早安，新的一天，从好心情开始。",
    "早安，愿你今天一切顺利。",
    "早安，阳光和好运都在路上。",
    "新的一天，值得全力以赴。",
    "醒来的第一缕光，就是新的开始。",
    "今天的风很好，适合做点喜欢的事。",
    "晚安，今天的你已经很棒了。",
    "晚安，把疲惫交给夜晚。",
    "晚安，明天会更好。",
    "晚安，愿你有个好梦。",
    "睡前放下一切，醒来便是新生。",
    "把开心的事留到睡前想一想。",
    "今晚的月亮很圆，愿你心里也圆满。",
    "好好睡一觉，明天继续发光。",
    "一天的忙碌结束，给自己一个赞。",
    "今天的努力，请好好收下。",
    "夜深了，愿你被温柔包裹。",
    "清晨适合出发，夜晚适合感恩。",
    "明天见，更好的自己。",
    "睡前想想今天的小进步，就会很好睡。",

    # ===== 清醒金句 / 自我肯定 =====
    "做自己的太阳，无需借谁的光。",
    "你不需要向任何人证明自己。",
    "你不用活成别人期待的样子。",
    "你的人生，不需要别人打分。",
    "把标准握在自己手里。",
    "你独一无二，这本身就是价值。",
    "先成为自己的光，再去照亮别人。",
    "喜欢的事，就大胆去做。",
    "你的节奏，不需要和别人同步。",
    "允许自己慢一点，也允许自己不一样。",
    "别把自己活成别人的复印件。",
    "你值得拥有更好的。",
    "自信是从一次次做到里长出来的。",
    "你要相信，你比想象中更有力量。",
    "真正的底气，来自你的能力。",
    "把喜欢变成本事，把本事变成底气。",
    "你若盛开，蝴蝶自来。",
    "你有多自律，就有多自由。",
    "把自己经营好，是最好的答案。",
    "你只管发光，自有人看见。",
    "把目光收回自己身上，方向就清楚。",
    "不比较，不内耗，只前进。",
    "你可以温柔，也可以有力量。",

    # ===== 短句 =====
    "今日份的开心。",
    "新的一天，加油。",
    "元气满满。",
    "向光而生。",
    "慢慢来，会好的。",
    "一切都会好起来的。",
    "保持热爱。",
    "向前走，别回头。",
    "每天进步一点点。",
    "早安。",
    "晚安。",
    "今天也要好好生活。",
    "值得期待。",
    "全力以赴。",
    "心之所向。",
    "向阳而行。",
    "步履不停。",
    "笃定前行。",
    "热爱可抵岁月长。",
    "把每一天过好。",
    "日子在变好。",
    "好心情营业中。",
    "万事胜意。",
    "未来可期。",
    "前程似锦。",
    "知足且上进。",
    "温柔且有力量。",
    "清醒且坚定。",
    "在慢慢变好。",
    "加油，你可以的。",

    # ===== 经典（正向励志） =====
    "天行健，君子以自强不息。",
    "有志者，事竟成。",
    "宝剑锋从磨砺出，梅花香自苦寒来。",
    "长风破浪会有时，直挂云帆济沧海。",
    "会当凌绝顶，一览众山小。",
    "沉舟侧畔千帆过，病树前头万木春。",
    "山重水复疑无路，柳暗花明又一村。",
    "千磨万击还坚劲，任尔东西南北风。",
    "苟日新，日日新，又日新。",
    "博观而约取，厚积而薄发。",
    "业精于勤，荒于嬉。",
    "纸上得来终觉浅，绝知此事要躬行。",
    "天生我材必有用，千金散尽还复来。",
    "莫愁前路无知己，天下谁人不识君。",
    "海阔凭鱼跃，天高任鸟飞。",
    "大鹏一日同风起，扶摇直上九万里。",
    "仰天大笑出门去，我辈岂是蓬蒿人。",

    # ===== 两行式金句（正文与图片都分两行） =====
    "把热爱做到极致\n就是对天赋最好的回答。",
    "你只管努力\n剩下的交给时间。",
    "路虽远，行则将至\n事虽难，做则必成。",
    "星光不负赶路人\n时光不负有心人。",
    "心有猛虎\n细嗅蔷薇。",
    "接纳自己的不完美\n才有力量去成长。",
    "今天的坚持\n是明天的底气。",
    "先扎根\n再生长。",
    "慢慢来\n一切都会好。",
    "把日子过成诗\n也把生活过好。",
    "发光不是太阳的专利\n你也可以。",
    "愿你一生温暖纯良\n不舍爱与自由。",
    "所有努力都不会白费\n它们只是延迟兑现。",
    "生活不会亏待\n每一个认真努力的人。",
    "先把自己点亮\n世界就亮了。",
    "你比自己以为的\n更有力量。",
    "今天也要\n好好努力呀。",
    "一步一个脚印\n走向想要的生活。",
]


# ========== eapi 加密 ==========

def _generate_key(key_bytes):
    gen = bytearray(16)
    copy_len = min(16, len(key_bytes))
    gen[:copy_len] = key_bytes[:copy_len]
    for i in range(16, len(key_bytes)):
        gen[i % 16] ^= key_bytes[i]
    return bytes(gen)


def eapi_encrypt(plaintext):
    key = _generate_key(EAPI_KEY.encode("utf-8"))
    cipher = AES.new(key, AES.MODE_ECB)
    data = pad(plaintext.encode("utf-8"), AES.block_size)
    encrypted = cipher.encrypt(data)
    return encrypted


def eapi_params(path, json_str):
    msg = f"nobody{path}use{json_str}md5forencrypt"
    md5_hex = hashlib.md5(msg.encode("utf-8")).hexdigest()
    data = f"{path}-{NOBODY}-{json_str}-{NOBODY}-{md5_hex}"
    encrypted = eapi_encrypt(data)
    return {"params": encrypted.hex().upper()}


# ========== 平台客户端 ==========

class NeteaseClient:
    def __init__(self, cookie_str):
        self.s = requests.Session()
        self.cookie_str = cookie_str
        self.cookies = {}
        for item in cookie_str.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                self.cookies[k.strip()] = v.strip()
        self.csrf = self.cookies.get("__csrf", "")
        # 2026-10-22：与 run.py / signin.py 统一——用 md5(cookie) 派生永久稳定的 deviceId。
        # 原来每次随机，同一账号同一天在平台眼里是三个不同设备，正是风控最容易命中的特征。
        self.device_id = "YD-" + hashlib.md5(cookie_str.encode("utf-8")).hexdigest()[:32]
        self.buildver = str(int(time.time()))[:10]
        # 2026-10-23：login_check() 里拿到的昵称要存下来给直邮用。
        # 原来 notes.py 直邮调用的是 client.nickname，但本类从没定义过该属性 →
        # 每次 code=250 都抛 AttributeError，被 except 吞掉，号主一封邮件都收不到。
        self.nickname = ""

    def _build_cookie_header(self, extra=None):
        c = dict(self.cookies)
        c["deviceId"] = self.device_id
        c["appver"] = "9.3.40"
        c["buildver"] = self.buildver
        c["resolution"] = "1920x1080"
        c["os"] = "Android"
        if extra:
            c.update(extra)
        parts = [f"{k}={v}" for k, v in c.items()]
        return "; ".join(parts)

    def _eapi_post(self, path, payload_dict, max_retries=3):
        url = f"{BASE_URL}{path.replace('/api/', '/eapi/')}"
        json_str = json.dumps(payload_dict, separators=(",", ":"))
        params = eapi_params(path, json_str)
        ua_list = [
            "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.4951.41 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 11; Redmi Note 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.73 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 10; HUAWEI P30) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.98 Mobile Safari/537.36",
            "Mozilla/5.0 (Linux; Android 13; Samsung Galaxy S22) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.71 Mobile Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 15_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.5 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Linux; Android 9; MIX 2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Mobile Safari/537.36",
        ]
        headers = {
            "User-Agent": random.choice(ua_list),
            "Referer": "https://music.163.com",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": self._build_cookie_header(),
        }
        body = f"params={params['params']}"
        for attempt in range(max_retries):
            try:
                r = self.s.post(url, data=body, headers=headers, timeout=30)
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"请求失败，已重试 {max_retries} 次: {e}")
                    return {"code": -1, "message": f"请求失败: {e}"}
        try:
            return r.json()
        except Exception:
            try:
                from Crypto.Cipher import AES as _AES
                key = _generate_key(EAPI_KEY.encode("utf-8"))
                cipher = _AES.new(key, _AES.MODE_ECB)
                decrypted = cipher.decrypt(bytes.fromhex(r.text))
                pad_len = decrypted[-1]
                decrypted = decrypted[:-pad_len]
                return json.loads(decrypted.decode("utf-8"))
            except Exception:
                logger.error(f"响应解密失败: {r.text[:300]}")
                return {"code": -1, "message": "响应解密失败"}

    def login_check(self, name=""):
        logger.info(f"[{name}] 验证登录状态...")
        resp = self._eapi_post("/api/w/nuser/account/get", {})
        code = resp.get("code", -1)
        if code == 200:
            profile = resp.get("profile") or resp.get("data", {}).get("profile")
            # 2026-10-19 修复：eapi 通道对失效会话也返回 code=200 但 profile 为空
            # （实测：死号打"登录成功! 用户: 未知"后发布动态 301）。无 profile.userId 一律判过期。
            if not profile or not profile.get("userId"):
                logger.warning(f"[{name}] code=200 但无 profile（会话已失效），判过期")
                return False
            nickname = profile.get("nickname", "未知")
            self.nickname = "" if nickname == "未知" else nickname
            logger.info(f"[{name}] 登录成功! 用户: {nickname}")
            return True
        logger.warning(f"[{name}] Cookie 已过期或无效, code={code}")
        return False

    def upload_image(self, image_bytes):
        logger.info("Step 1: 获取 NOS token...")
        md5_hex = hashlib.md5(image_bytes).hexdigest()
        alloc_payload = {
            "filename": "note.jpg",
            "local": "false",
            "nos_product": 0,
            "fileSize": len(image_bytes),
            "md5": md5_hex,
            "ext": ".jpg",
            "type": "image",
        }
        alloc_resp = self._eapi_post("/api/nos/token/alloc", alloc_payload)
        if alloc_resp.get("code") != 200:
            logger.error(f"获取 NOS token 失败: {alloc_resp}")
            return None

        result = alloc_resp.get("result", {})
        object_key = result.get("objectKey", "")
        token = result.get("token", "")
        doc_id = result.get("docId", "")
        bucket = result.get("bucket", "yyimgs")

        # 模拟人类：上传前随机等待
        time.sleep(random.uniform(0.5, 2.0))

        logger.info("Step 2: 上传图片到 NOS...")
        try:
            lbs_resp = requests.get("https://wanproxy.127.net/lbs?version=1.0&bucketname=cloudmusic", timeout=10).json()
            upload_host = lbs_resp.get("upload", ["https://nosup-hz1.127.net"])[0]
        except Exception:
            upload_host = "https://nosup-hz1.127.net"

        nos_url = f"{upload_host}/{bucket}/{object_key}?version=1.0&offset=0&complete=true"
        nos_headers = {"x-nos-token": token, "Content-Type": "image/jpeg", "User-Agent": "Mozilla/5.0"}
        nos_resp = requests.post(nos_url, headers=nos_headers, data=image_bytes, timeout=60)
        if nos_resp.status_code not in (200, 201):
            logger.error(f"NOS 上传失败: {nos_resp.status_code}")
            return None

        # 模拟人类：上传后随机等待
        time.sleep(random.uniform(0.3, 1.5))

        logger.info("Step 3: 获取动态图片信息...")
        event_img_payload = {"imgid": doc_id, "format": "jpeg"}
        event_resp = self._eapi_post("/api/upload/event/img/v1", event_img_payload)
        if event_resp.get("code") != 200:
            logger.error(f"获取动态图片信息失败: {event_resp}")
            return None

        pic_info = event_resp.get("picInfo", {})
        return {
            "originId": pic_info.get("originId"),
            "squareId": pic_info.get("squareId"),
            "rectangleId": pic_info.get("rectangleId"),
            "format": pic_info.get("format", "jpeg"),
        }

    def publish_event(self, msg, pic_data=None):
        logger.info("发布动态...")
        event_uuid = uuid.uuid4().hex
        payload = {
            "msg": msg,
            "type": "noresource",
            "uuid": event_uuid,
            "addComment": "false",
        }
        if pic_data:
            pics = [{
                "originId": pic_data["originId"],
                "squareId": pic_data["squareId"],
                "rectangleId": pic_data["rectangleId"],
                "format": pic_data["format"],
            }]
            payload["pics"] = json.dumps(pics, separators=(",", ":"))
        else:
            payload["pics"] = "[]"
        return self._eapi_post("/api/share/friends/resource", payload)


# ========== 随机图片生成（每次完全不同） ==========

def _font_paths():
    """候选字体路径。Windows 本地与 GitHub ubuntu runner（fonts-arphic-uming / fonts-noto-cjk，
    由 run.yml 的 brush job 安装）都列在这里，逐个 try，哪边能用哪边的。"""
    return [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/STKAITI.TTF",
        "C:/Windows/Fonts/STXINWEI.TTF",
        "C:/Windows/Fonts/FZSTK.TTF",
        "C:/Windows/Fonts/FZYBKSJW.TTF",
        "/usr/share/fonts/truetype/arphic/uming.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]


def _load_font(path, size):
    """按路径加载字体，失败返回 None（不抛异常）。"""
    try:
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    return None


def _default_font(size):
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def _pick_font_file():
    """随机挑一个能用的字体文件（同一张图内字号统一，排版才不歪）。"""
    paths = _font_paths()
    random.shuffle(paths)
    for fp in paths:
        if _load_font(fp, 40) is not None:
            return fp
    for fp in ("arial.ttf", "DejaVuSans.ttf"):
        if _load_font(fp, 40) is not None:
            return fp
    return None


def _pick_font(min_size=42, max_size=72, path=None):
    """随机字号 + 指定（或随机）字体。"""
    size = random.randint(min_size, max_size)
    f = _load_font(path, size)
    if f:
        return f
    for fp in _font_paths():
        f = _load_font(fp, size)
        if f:
            return f
    return _default_font(size)


def _line_height(font):
    try:
        ascent, descent = font.getmetrics()
        return ascent + descent
    except Exception:
        return int(getattr(font, "size", 40) * 1.3)


def _text_width(draw, s, font):
    try:
        b = draw.textbbox((0, 0), s, font=font)
        return b[2] - b[0]
    except Exception:
        try:
            return int(draw.textlength(s, font=font))
        except Exception:
            return len(s) * 40


_WRAP_PUNCT = "，。、；！？：,.;!?:）)】」》"


def _wrap_text(draw, text, font, max_w):
    """按宽度折行，尽量在标点处断开；文案里的 \\n 作为强制换行保留。"""
    lines = []
    for para in str(text).split("\n"):
        para = para.strip()
        if not para:
            continue
        cur = ""
        for ch in para:
            cur += ch
            if _text_width(draw, cur, font) <= max_w:
                continue
            cut = 0
            for i in range(len(cur) - 1, max(0, len(cur) - 10), -1):
                if cur[i - 1] in _WRAP_PUNCT:
                    cut = i
                    break
            if cut <= 0:
                cut = len(cur) - 1
            lines.append(cur[:cut])
            cur = cur[cut:]
        if cur:
            lines.append(cur)
    return lines or [""]


def _fit_text(draw, text, font_path, max_w, max_h):
    """从大字号往小试，找到能把整段文案放进画布且不超过 4 行的排版。"""
    best = None
    for size in range(78, 29, -4):
        font = _load_font(font_path, size) or _default_font(size)
        lines = _wrap_text(draw, text, font, max_w)
        lh = _line_height(font)
        spacing = max(6, int(lh * 0.34))
        block_h = lh * len(lines) + spacing * max(0, len(lines) - 1)
        block_w = max(_text_width(draw, ln, font) for ln in lines)
        best = (font, lines, lh, spacing, block_w, block_h)
        if len(lines) <= 4 and block_w <= max_w and block_h <= max_h:
            return best
    return best


def random_local_image(text="今天也要加油呀"):
    """生成高度随机的图片：背景、装饰、字体、布局每次都不同。
    文案支持自动折行（最多 4 行）与 \\n 强制换行，长句不再被画出画布。"""
    w, h = 1080, 1080

    # 随机背景：纯色 / 渐变
    bg_mode = random.choice(["solid", "gradient_v", "gradient_h", "gradient_d"])
    c1 = tuple(random.randint(220, 255) for _ in range(3))
    c2 = tuple(random.randint(200, 255) for _ in range(3))
    img = Image.new("RGB", (w, h), c1)
    draw = ImageDraw.Draw(img)

    if bg_mode == "gradient_v":
        for y in range(h):
            r = int(c1[0] + (c2[0] - c1[0]) * y / h)
            g = int(c1[1] + (c2[1] - c1[1]) * y / h)
            b = int(c1[2] + (c2[2] - c1[2]) * y / h)
            draw.line([(0, y), (w, y)], fill=(r, g, b))
    elif bg_mode == "gradient_h":
        for x in range(w):
            r = int(c1[0] + (c2[0] - c1[0]) * x / w)
            g = int(c1[1] + (c2[1] - c1[1]) * x / w)
            b = int(c1[2] + (c2[2] - c1[2]) * x / w)
            draw.line([(x, 0), (x, h)], fill=(r, g, b))
    elif bg_mode == "gradient_d":
        for y in range(h):
            for x in range(w):
                t = (x + y) / (w + h)
                r = int(c1[0] + (c2[0] - c1[0]) * t)
                g = int(c1[1] + (c2[1] - c1[1]) * t)
                b = int(c1[2] + (c2[2] - c1[2]) * t)
                img.putpixel((x, y), (r, g, b))

    # 随机装饰：线条 / 圆点 / 圆圈 / 无装饰
    deco_count = random.randint(0, 12)
    for _ in range(deco_count):
        deco_type = random.choice(["line", "dot", "circle", "rect"])
        color = tuple(random.randint(180, 240) for _ in range(3))
        if deco_type == "line":
            x1, y1 = random.randint(0, w), random.randint(0, h)
            x2, y2 = random.randint(0, w), random.randint(0, h)
            draw.line([(x1, y1), (x2, y2)], fill=color, width=random.randint(1, 5))
        elif deco_type == "dot":
            x, y = random.randint(0, w), random.randint(0, h)
            r = random.randint(5, 30)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
        elif deco_type == "circle":
            x, y = random.randint(0, w), random.randint(0, h)
            r = random.randint(30, 200)
            draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=random.randint(1, 4))
        elif deco_type == "rect":
            x1, y1 = random.randint(0, w - 100), random.randint(0, h - 100)
            x2, y2 = x1 + random.randint(50, 300), y1 + random.randint(50, 300)
            draw.rectangle([x1, y1, x2, y2], outline=color, width=random.randint(1, 3))

    # 随机文字颜色（深色系）
    text_color = (random.randint(30, 100), random.randint(30, 100), random.randint(30, 100))

    # 文案排版：字体文件随机、字号在能放下的前提下尽量大，最多 4 行
    margin = 100
    max_w = w - margin * 2
    max_h = h - margin * 2
    body = str(text or "").strip() or "今天也要加油呀"
    font_path = _pick_font_file()
    font, lines, lh, spacing, block_w, block_h = _fit_text(draw, body, font_path, max_w, max_h)

    # 随机位置（居中附近随机偏移），保证整块落在安全边距内
    jx = random.randint(-1, 1) * random.randint(0, max(0, (max_w - block_w) // 2))
    jy = random.randint(-1, 1) * random.randint(0, max(0, (max_h - block_h) // 2))
    block_x = (w - block_w) // 2 + jx
    block_y = (h - block_h) // 2 + jy
    block_x = max(margin, min(block_x, w - block_w - margin))
    block_y = max(margin, min(block_y, h - block_h - margin))

    y = block_y
    for ln in lines:
        lw = _text_width(draw, ln, font)
        draw.text((block_x + (block_w - lw) // 2, y), ln, fill=text_color, font=font)
        y += lh + spacing

    bio = BytesIO()
    img.save(bio, format="JPEG", quality=random.randint(85, 95))
    return bio.getvalue()


# ========== 工具函数 ==========

def load_config(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)
    return _strip(raw)


def _strip(obj):
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip(i) for i in obj]
    return obj


# 2026-10-23：删除了 send_email() / notify_fail() 两个群主告警函数（及唯一调用点）。
# 它们读 cfg.json 的 email_config 段，而两个仓库的 cfg.json 里根本没有这一节 →
# enabled 恒为 False，一进来就 return，从来没真正发出过邮件，属于死代码。
# 号主本人的提醒走 notify.py（凭据来自 Secrets）；程序级故障由 Actions 标红负责。
# ========== 主程序 ==========

def main():
    try:
        cfg = load_config("accounts.json")

        accounts = cfg.get("accounts", [])
        if not accounts:
            # 本片没有账号（账号池小、分片多时正常），静默退出
            print("accounts.json 为空，跳过")
            sys.exit(0)

        # 按 roles 过滤账号，只选 roles 包含 "notes" 的账号
        # 2026-10-26 修复：默认值原为 "listen,notes"（缺字段＝发内容），与 signin.py 的 "" 相反；
        # 统一改成 ""（缺字段一律不动）。make_accounts.py 恒定写 roles="signin,notes"，正常流水线行为不变。
        notes_accounts = [a for a in accounts if "notes" in a.get("roles", "")]

        # ===== 核心：每账号错开发布日 =====
        # offset = md5(账号名) % 6，(当年第几天 + offset) % 6 == 0 时该账号发布。
        # → 每号每 6 天一条（一个月约 5 次，满足创作者"30 天内内容天数≥4"），且各号分散在不同日子，不会同天扎堆
        # 第几天按北京时间算（runner 是 UTC，直接用 now() 会差一天，2026-10-13 修复）
        from datetime import datetime, timezone, timedelta
        day_of_year = (datetime.now(timezone.utc) + timedelta(hours=8)).timetuple().tm_yday

        def publish_today(name):
            offset = int(hashlib.md5(str(name).encode("utf-8")).hexdigest(), 16) % 6
            return (day_of_year + offset) % 6 == 0

        todo = [a for a in notes_accounts if publish_today(a.get("name", "未知"))]
        logger.info(f"notes 账号 {len(notes_accounts)} 个，今日应发布 {len(todo)} 个 (第{day_of_year}天)")
        if not todo:
            logger.info("今日没有轮到发布的账号，静默退出")
            print("今日无发布任务")
            sys.exit(0)

        # 触发后随机等待 1-5 分钟再开始
        wait_seconds = random.randint(60, 300)
        logger.info(f"随机等待 {wait_seconds // 60} 分 {wait_seconds % 60} 秒后开始...")
        time.sleep(wait_seconds)
        success_count = 0
        fail_count = 0
        for acc in todo:
            aname = acc.get("name", "未知")
            cookie = acc.get("cookie", "")
            logger.info(f"本次使用账号: {aname}")

            # 模拟人类：登录后随机等待
            client = NeteaseClient(cookie)
            if not client.login_check(aname):
                logger.warning(f"账号 [{aname}] 的 Cookie 已过期，跳过该账号")
                fail_count += 1
                continue
            time.sleep(random.uniform(2, 8))

            # 随机选文案；文案库里已是长短句混合，整句原样发布，
            # 只有超过 52 字的长句才在句读处收敛（避免动态太长被折叠），2026-10-27 调整
            text = random.choice(QUOTES)
            if "\n" not in text and len(text) > 52:
                for i in range(52, 34, -1):
                    if text[i - 1] in "，。、；！？,.!?…":
                        text = text[:i]
                        break
            logger.info(f"[{aname}] 准备发布文案：{text}")

            # 模拟人类：想文案的时间
            time.sleep(random.uniform(3, 15))

            # 生成随机图片
            logger.info(f"[{aname}] 生成随机图片...")
            img_bytes = random_local_image(text)
            logger.info(f"[{aname}] 图片大小：{len(img_bytes)} bytes")

            # 模拟人类：选图的时间
            time.sleep(random.uniform(2, 10))

            # 上传图片
            pic_data = client.upload_image(img_bytes)
            if pic_data:
                logger.info(f"[{aname}] 图片上传成功")
            else:
                logger.warning(f"[{aname}] 图片上传失败，将发布纯文字动态")

            # 模拟人类：编辑的时间
            time.sleep(random.uniform(1, 5))

            # 发布动态
            resp = client.publish_event(text, pic_data)
            code = resp.get("code", -1)
            logger.info(f"[{aname}] 发布响应: code={code}")

            if code == 200:
                event = resp.get("event", {})
                event_id = event.get("id", "")
                user = event.get("user", {})
                nickname = user.get("nickname", "")
                logger.info(f"[{aname}] 发布成功! 动态ID={event_id}, 用户={nickname}")
                success_count += 1
            else:
                logger.error(f"[{aname}] 发布失败: {json.dumps(resp, ensure_ascii=False)[:300]}")
                fail_count += 1
                # 2026-10-17：需安全验证类失败（code=250）直邮号主本人，平和告知"做一次验证即可"；
                # 未登记邮箱的号只记日志。登录失效由 signin.py 负责，这里只管发布环节，不重复发
                if code == 250:
                    try:
                        import notify
                        # 2026-10-23：getattr 兜底 —— 昵称取不到就传空串，_who() 会自动回落到账号名；
                        # 未登记邮箱的号由 notify_verify() 内部直接跳过，不报错。
                        notify.notify_verify(acc.get("email", ""),
                                             getattr(client, "nickname", ""), aname)
                    except Exception as _e:
                        logger.warning(f"[{aname}] 直邮号主失败（不影响主流程）: {_e}")

            # 账号之间随机等待，模拟人类切换账号
            time.sleep(random.uniform(5, 15))

        logger.info(f'全部完成: 成功 {success_count} 个, 失败 {fail_count} 个, 今日应发 {len(todo)} 个账号')
        if success_count == 0 and fail_count > 0:
            # 2026-10-17 修复：个别号被平台风控(code=250 安全验证)或登录失效，属账号级
            # 临时问题，不该让整个 relay run 标红、误发告警邮件。真正的系统故障(程序异常)
            # 由下方 except 分支统一告警并退出；此处仅记 warning，正常退出。
            logger.warning(
                f"今日应发账号全部为账号级失败(风控/登录失效等)，不计为系统故障，"
                f"不发送告警邮件。成功 {success_count} / 失败 {fail_count} / 应发 {len(todo)}"
            )
        print(f"发布完成: {success_count}/{len(todo)} 成功")

    except Exception as e:
        logger.error(f"程序异常: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()




