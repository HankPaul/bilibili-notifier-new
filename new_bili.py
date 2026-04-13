import random
import requests, qrcode, time, re, json, os, tempfile, filecmp, shutil, schedule
from pathlib import Path
import requests.utils as ru
from datetime import datetime


# 加载配置文件
def load_config():
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'

    if is_docker:
        config_file = Path('/app/config.json')
        print("🐳 检测到Docker环境，使用容器内配置路径")
    else:
        config_file = Path('./config.json')

    default_config = {
        "followed_dynamic_types": ["DYNAMIC_TYPE_AV", "DYNAMIC_TYPE_DRAW"],
        "feishu_webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx",
        "check_interval_minutes": 1
    }

    if config_file.exists():
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print("✅ 配置文件加载成功")
            return config
        except Exception as e:
            print(f"⚠️ 配置文件读取失败，使用默认配置: {e}")
            return default_config
    else:
        if not is_docker:
            print("⚠️ 配置文件不存在，创建默认配置文件")
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                print("✅ 默认配置文件已创建")
            except Exception as e:
                print(f"❌ 配置文件创建失败: {e}")
        else:
            print("⚠️ Docker环境：配置文件不存在，使用默认配置")
        return default_config


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Connection': 'keep-alive'
}

CONFIG = load_config()

is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_ENV') == 'true'

if is_docker:
    DATA_DIR = Path('/app/bili')
    WWW_DIR = Path('/app/www/wwwroot')
    print("🐳 Docker环境：使用容器内数据路径")
else:
    DATA_DIR = Path('./bili')
    WWW_DIR = Path('./www/wwwroot')

OLD_BVID_FILE = DATA_DIR / 'old_bvid.json'
COOKIE_FILE = DATA_DIR / 'cookie.txt'
JSON_FILE = DATA_DIR / 'jsonAll.json'
SAVE_FILE = WWW_DIR / 'qr.png'
OLD_SELF_COMMENT_FILE = DATA_DIR / 'old_self_comments.json'

FOLLOWED_DYNAMIC_TYPES = CONFIG.get("followed_dynamic_types", ["DYNAMIC_TYPE_AV", "DYNAMIC_TYPE_DRAW"])

# session = requests.Session()


def saveNprint_qr_image(text: str, path) -> None:
    path_str = str(path)
    os.makedirs(os.path.dirname(path_str), exist_ok=True)
    img = qrcode.make(text)
    img.save(path_str)
    qr = qrcode.QRCode(border=1)
    qr.add_data(text)
    qr.print_ascii(invert=True)


def send_feishu_card_error(error_str: str):
    elements = []
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": (
                f"**系统提示：** {error_str}  \n"
                f"**时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n"
            )
        }
    })
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "👉 扫码登录"},
            "type": "primary",
            "url": ""
        }]
    })
    elements.append({"tag": "hr"})

    FEISHU_WEBHOOK = CONFIG.get("feishu_webhook")
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "⚠️ 系统错误通知"},
                "template": "red"
            },
            "elements": elements
        }
    }
    try:
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    except:
        pass


def send_feishu_self_comment(comment_info: dict):
    if not comment_info:
        return

    elements = []
    content = (
        f"**UP：**{comment_info['name']}  \n"
        f"**时间：**{comment_info['comment_time']}  \n"
        f"**类型：**{comment_info['type_text']}  \n"
        f"**内容：**{comment_info['content']}"
    )

    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": content}
    })
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "👉 查看评论"},
            "type": "primary",
            "url": comment_info['jump_url']
        }]
    })
    elements.append({"tag": "hr"})

    FEISHU_WEBHOOK = CONFIG.get("feishu_webhook")
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"💬 {comment_info['name']}发表评论"},
                "template": "green"
            },
            "elements": elements
        }
    }
    try:
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    except:
        pass


def send_feishu_card(dynamics: list[dict]):
    if not dynamics:
        return

    elements = []
    for dynamic in reversed(dynamics):
        if dynamic['type'] == 'video':
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**UP：**{dynamic['name']}  \n**时间：**{dynamic['pub_ts']}  \n**视频：**{dynamic['title']}"
                }
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "👉 打开视频"},
                    "type": "primary",
                    "url": f"https://www.bilibili.com/video/{dynamic['bvid']}"
                }]
            })
        elif dynamic['type'] == 'text':
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**UP：**{dynamic['name']}  \n**时间：**{dynamic['pub_ts']}  \n**动态：**{dynamic['title']}"
                }
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "👉 查看完整动态"},
                    "type": "primary",
                    "url": f"https://t.bilibili.com/{dynamic['dynamic_id']}"
                }]
            })
        elif dynamic['type'] == 'forward_video':
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**UP：**{dynamic['name']}转发视频  \n**时间：**{dynamic['pub_ts']}  \n**转发评论：**{dynamic['forward_comment']}  \n**原UP：**{dynamic['orig_author']}  \n**视频：**{dynamic['title']}"
                }
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "👉 查看转发动态"},
                    "type": "primary",
                    "url": f"https://t.bilibili.com/{dynamic['dynamic_id']}"
                }]
            })
        elif dynamic['type'] == 'forward_text':
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**UP：**{dynamic['name']}转发动态  \n**时间：**{dynamic['pub_ts']}  \n**转发评论：**{dynamic['forward_comment']}  \n**原UP：**{dynamic['orig_author']}  \n**原动态：**{dynamic['title']}"
                }
            })
            elements.append({
                "tag": "action",
                "actions": [{
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "👉 查看转发动态"},
                    "type": "primary",
                    "url": f"https://t.bilibili.com/{dynamic['dynamic_id']}"
                }]
            })
        elements.append({"tag": "hr"})

    FEISHU_WEBHOOK = CONFIG.get("feishu_webhook")
    has_video = any(d['type'] == 'video' for d in dynamics)
    has_text = any(d['type'] == 'text' for d in dynamics)
    has_forward_video = any(d['type'] == 'forward_video' for d in dynamics)
    has_forward_text = any(d['type'] == 'forward_text' for d in dynamics)

    if has_forward_video or has_forward_text:
        title = "🔄 关注的 UP 有转发动态啦！"
    elif has_video and has_text:
        title = "🎞 关注的 UP 更新啦！"
    elif has_video:
        title = "🎞 关注的 UP 更新视频啦！"
    elif has_text:
        title = "📝 关注的 UP 发动态啦！"
    else:
        title = "📢 关注的 UP 有更新啦！"

    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue"
            },
            "elements": elements
        }
    }
    try:
        resp = requests.post(FEISHU_WEBHOOK, json=card, timeout=10)
    except:
        pass


class session_cookie:
    def dict_cookie_to_header(self, dict_cookie_str: str) -> str:
        try:
            m = re.search(r'\{.*?\}', dict_cookie_str, flags=re.S)
            if not m:
                return ""
            cookie_dict = eval(m.group())
            template = (
                "buvid3=xxxx; "
                "b_nut=xxxx; "
                "_uuid=xxxx; "
                "header_theme_version=OPEN; "
                "DedeUserID={DedeUserID}; "
                "DedeUserID__ckMd5={DedeUserID__ckMd5}; "
                "SESSDATA={SESSDATA}; "
                "bili_jct={bili_jct}; "
                "sid={sid};"
            )
            header_cookie = template.format(**cookie_dict)
            return f"Cookie: {header_cookie}"
        except:
            return ""

    def __init__(self):
        self.sess = requests.Session()
        self.sess.headers.update(HEADERS)
        self.load_cookies()
        self.load_self_comment_history()

    def load_cookies(self):
        if COOKIE_FILE.exists() and COOKIE_FILE.stat().st_size > 0:
            try:
                with open(COOKIE_FILE, 'r', encoding='utf-8') as f:
                    cookie_str = f.read().strip()
                    cookie_header = self.dict_cookie_to_header(cookie_str)
                    if cookie_header:
                        self.sess.headers['Cookie'] = cookie_header
                print("✅ 已加载本地 Cookie")
            except Exception as e:
                print("Cookie 文件损坏，已删除，准备重新登录")
                COOKIE_FILE.unlink(missing_ok=True)
        else:
            print("ℹ️ 本地无 Cookie，准备登录")

    def load_self_comment_history(self):
        try:
            with open(OLD_SELF_COMMENT_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                self.old_self_comments = set(json.loads(content)) if content else set()
        except:
            self.old_self_comments = set()

    def save_self_comment_history(self):
        try:
            os.makedirs(os.path.dirname(OLD_SELF_COMMENT_FILE), exist_ok=True)
            with open(OLD_SELF_COMMENT_FILE, 'w', encoding='utf-8') as f:
                json.dump(list(self.old_self_comments), f, ensure_ascii=False)
        except:
            pass

    def cookie_valid(self) -> bool:
        try:
            url = "https://api.bilibili.com/x/space/myinfo"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://space.bilibili.com/'
            }
            r = self.sess.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                return False
            data = r.json()
            if data.get("code") == 0 and data.get("data", {}).get("mid"):
                return True
        except:
            pass

        try:
            self._notify_and_save_qr("Cookie 已失效，需重新扫码登录")
        except:
            pass
        return False

    def _notify_and_save_qr(self, msg: str):
        time.sleep(1)
        send_feishu_card_error(msg)
        gen_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
        resp = self.sess.get(gen_url).json()
        login_url = re.search(r'(https?://[^\s<]+)', resp['data']['url']).group(0)
        print(login_url)
        saveNprint_qr_image(login_url, SAVE_FILE)

    def save_cookies(self):
        try:
            os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
            with open(COOKIE_FILE, 'w', encoding='utf-8') as f:
                json.dump(ru.dict_from_cookiejar(self.sess.cookies), f, ensure_ascii=False)
            print("✅ Cookie 已保存")
        except:
            pass

    def getQrCode(self):
        gen_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
        resp = self.sess.get(gen_url).json()
        self.qrcode_key = resp['data']['qrcode_key']
        login_url = re.search(r'(https?://[^\s<]+)', resp['data']['url']).group(0)
        # print("二维码URL：", login_url)
        # print("qrcode_key：", self.qrcode_key)
        # self._notify_and_save_qr(login_url)
        time.sleep(1)
        send_feishu_card_error(login_url)
        saveNprint_qr_image(login_url, SAVE_FILE)

    def ensure_login(self):
        if self.cookie_valid():
            print("✅ Cookie 有效，已登录")
            return True
        print("❌ Cookie 无效，开始扫码登录")
        return self._wait_for_qr_login()

    def _wait_for_qr_login(self) -> bool:
        self.getQrCode()
        poll_url = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
        while True:
            time.sleep(5)
            try:
                poll_resp = self.sess.get(poll_url, params={'qrcode_key': self.qrcode_key}, timeout=10).json()
                code = poll_resp['data']['code']
                print(code)
                if code == 0:
                    print("🎉 扫码成功")
                    self.save_cookies()
                    return True
                elif code == 86101:
                    print("⌛ 等待扫码...")
                elif code == 86090:
                    print("⌛ 已扫描，等待确认...")
                else:
                    print("❌ 二维码失效")
                    return False
            except:
                return False

    def compare_and_run(self, resp: dict) -> bool:
        try:
            with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8') as tmp:
                json.dump(resp, tmp, ensure_ascii=False, indent=2, sort_keys=True)
                tmp_path = tmp.name

            if JSON_FILE.exists() and filecmp.cmp(tmp_path, JSON_FILE, shallow=False):
                os.unlink(tmp_path)
                return False
            else:
                shutil.move(tmp_path, JSON_FILE)
                return True
        except:
            return True

    # 视频自评论检测（每页约20条，不翻页）
    def check_video_self_comment(self, bvid: str, up_mid: str, up_name: str):
        try:
            url = (
                f"https://api.bilibili.com/x/v2/reply/main?"
                f"mode=2&type=1&oid={bvid}&next=0&plat=1&web_location=1315875"
            )
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': f'https://www.bilibili.com/video/{bvid}'
            }
            response = self.sess.get(url, headers=headers, timeout=10)
            if response.status_code != 200 or not response.content:
                return

            resp = response.json()
            if resp.get('code') != 0:
                return
            #一般评论
            replies = resp.get('data', {}).get('replies', [])
            for reply in replies:
                try:
                    rpid = reply.get('rpid')
                    comment_mid = str(reply.get('member', {}).get('mid', ''))
                    content = reply.get('content', {}).get('message', '')
                    ctime = reply.get('ctime', 0)
                    comment_time = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M:%S')

                    if comment_mid == up_mid:
                        comment_id = f"v_{bvid}_{rpid}"
                        if comment_id not in self.old_self_comments:
                            self.old_self_comments.add(comment_id)
                            info = {
                                'name': up_name,
                                'comment_time': comment_time,
                                'type_text': '视频评论',
                                # 'content': content[:150] + ("..." if len(content) > 150 else ""),
                                'content': content,
                                'jump_url': f'https://www.bilibili.com/video/{bvid}#reply{rpid}'
                            }
                            send_feishu_self_comment(info)
                            print(f"💬 视频自评论: {up_name} | {content[:30]}...")
                except:
                    continue
            #置顶评论
            top_replies = resp.get('data', {}).get('top_replies', [])
            for top_reply in top_replies:
                try:
                    rpid = top_reply.get('rpid')
                    comment_mid = str(top_reply.get('member', {}).get('mid', ''))
                    content = top_reply.get('content', {}).get('message', '')
                    ctime = top_reply.get('ctime', 0)
                    comment_time = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M:%S')

                    if comment_mid == up_mid:
                        comment_id = f"vtop_{bvid}_{rpid}"
                        if comment_id not in self.old_self_comments:
                            self.old_self_comments.add(comment_id)
                            info = {
                                'name': up_name,
                                'comment_time': comment_time,
                                'type_text': '视频置顶评论',
                                # 'content': content[:150] + ("..." if len(content) > 150 else ""),
                                'content': content,
                                'jump_url': f'https://www.bilibili.com/video/{bvid}#reply{rpid}'
                            }
                            send_feishu_self_comment(info)
                            print(f"💬 视频自评论: {up_name} | {content[:30]}...")
                except:
                    continue
        except:
            return

    # 动态自评论检测（每页约20条，不翻页）
    def check_dynamic_self_comment(self, dynamic_id: str, up_mid: str, up_name: str):
        try:
            url = (
                f"https://api.bilibili.com/x/v2/reply/main?"
                f"mode=3&type=11&oid={dynamic_id}&next=0&plat=1&web_location=1315875"
            )
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': f'https://t.bilibili.com/{dynamic_id}'
            }
            response = self.sess.get(url, headers=headers, timeout=10)
            if response.status_code != 200 or not response.content:
                return

            resp = response.json()
            if resp.get('code') != 0:
                return
            # 一般评论
            replies = resp.get('data', {}).get('replies', [])
            for reply in replies:
                try:
                    rpid = reply.get('rpid')
                    comment_mid = str(reply.get('member', {}).get('mid', ''))
                    content = reply.get('content', {}).get('message', '')
                    ctime = reply.get('ctime', 0)
                    comment_time = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M:%S')

                    if comment_mid == up_mid:
                        comment_id = f"d_{dynamic_id}_{rpid}"
                        if comment_id not in self.old_self_comments:
                            self.old_self_comments.add(comment_id)
                            info = {
                                'name': up_name,
                                'comment_time': comment_time,
                                'type_text': '动态评论',
                                # 'content': content[:150] + ("..." if len(content) > 150 else ""),
                                'content': content,
                                'jump_url': f'https://t.bilibili.com/{dynamic_id}#reply{rpid}'
                            }
                            send_feishu_self_comment(info)
                            print(f"💬 动态自评论: {up_name} | {content[:30]}...")
                except:
                    continue
            #置顶评论
            top_replies = resp.get('data', {}).get('top_replies', [])
            for top_reply in top_replies:
                try:
                    rpid = top_reply.get('rpid')
                    comment_mid = str(top_reply.get('member', {}).get('mid', ''))
                    content = top_reply.get('content', {}).get('message', '')
                    ctime = top_reply.get('ctime', 0)
                    comment_time = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M:%S')

                    if comment_mid == up_mid:
                        comment_id = f"dtop_{dynamic_id}_{rpid}"
                        if comment_id not in self.old_self_comments:
                            self.old_self_comments.add(comment_id)
                            info = {
                                'name': up_name,
                                'comment_time': comment_time,
                                'type_text': '动态置顶评论',
                                'content': content,
                                'jump_url': f'https://t.bilibili.com/{dynamic_id}#reply{rpid}'
                            }
                            send_feishu_self_comment(info)
                            print(f"💬 动态自评论: {up_name} | {content[:30]}...")
                except:
                    continue
        except:
            return
    # ========================================================================

    def get_followed_dynamic(self):
        try:
            Url_followed_dynamics = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all?type=all&page=1&features=itemOpusStyle'
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://www.bilibili.com/'
            }
            resp = self.sess.get(Url_followed_dynamics, headers=headers, timeout=15).json()
            self.compare_and_run(resp)

            os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)
            with open(JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump(resp, f, ensure_ascii=False)
            time.sleep(1)

            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)

            items = data.get('data', {}).get('items', [])
            dynamics = []
            followed_mids = CONFIG.get("followed_mids", [])

            for item in items:
                try:
                    dynamic_type = item.get('type')
                    if dynamic_type not in FOLLOWED_DYNAMIC_TYPES:
                        continue

                    author_name = item['modules']['module_author']['name']
                    author_mid = str(item['modules']['module_author']['mid'])
                    pub_ts = datetime.fromtimestamp(item['modules']['module_author']['pub_ts']).strftime(
                        '%Y-%m-%d %H:%M:%S')

                    if followed_mids and author_mid not in followed_mids:
                        continue

                    if dynamic_type == 'DYNAMIC_TYPE_AV':
                        archive = item.get('modules', {}).get('module_dynamic', {}).get('major', {}).get('archive', {})
                        bvid = archive.get('bvid')
                        if not bvid:
                            continue
                        dynamics.append({
                            'type': 'video', 'name': author_name, 'pub_ts': pub_ts,
                            'title': archive['title'], 'bvid': bvid, 'mid': author_mid
                        })
                    elif dynamic_type == 'DYNAMIC_TYPE_DRAW':
                        opus = item.get('modules', {}).get('module_dynamic', {}).get('major', {}).get('opus', {})
                        text = opus.get('summary', {}).get('text', '')
                        if not text:
                            continue
                        dynamics.append({
                            'type': 'text', 'name': author_name, 'pub_ts': pub_ts,
                            'title': text[:100] + '...' if len(text) > 100 else text,
                            'dynamic_id': item.get('id_str', ''), 'mid': author_mid
                            # 'dynamic_id': item.get('basic', {}).get('rid_str', ''), 'mid': author_mid
                        })
                    elif dynamic_type == 'DYNAMIC_TYPE_FORWARD':
                        orig = item.get('orig', {})
                        if not orig:
                            continue
                        forward_text = item.get('modules', {}).get('module_dynamic', {}).get('desc', {}).get('text', '')
                        orig_type = orig.get('type')
                        orig_name = orig.get('modules', {}).get('module_author', {}).get('name', '未知')

                        if orig_type == 'DYNAMIC_TYPE_AV':
                            arc = orig.get('modules', {}).get('module_dynamic', {}).get('major', {}).get('archive', {})
                            if arc.get('bvid'):
                                dynamics.append({
                                    'type': 'forward_video', 'name': author_name, 'pub_ts': pub_ts,
                                    'title': arc['title'], 'forward_comment': forward_text[:100] + '...' if len(
                                        forward_text) > 100 else forward_text,
                                    'orig_author': orig_name, 'bvid': arc['bvid'],
                                    'dynamic_id': item.get('id_str', ''), 'mid': author_mid
                                })
                        elif orig_type == 'DYNAMIC_TYPE_DRAW':
                            orig_text = orig.get('modules', {}).get('module_dynamic', {}).get('major', {}).get('opus',
                                                                                                               {}).get(
                                'summary', {}).get('text', '')
                            if orig_text:
                                dynamics.append({
                                    'type': 'forward_text', 'name': author_name, 'pub_ts': pub_ts,
                                    'title': orig_text[:100] + '...' if len(orig_text) > 100 else orig_text,
                                    'forward_comment': forward_text[:100] + '...' if len(
                                        forward_text) > 100 else forward_text,
                                    'orig_author': orig_name,
                                    'dynamic_id': item.get('id_str', ''), 'mid': author_mid
                                })
                except:
                    continue

            # 去重逻辑
            try:
                with open(OLD_BVID_FILE, encoding='utf-8') as f:
                    old_ids = set(json.loads(f.read().strip() or '[]'))
            except:
                old_ids = set()

            new_dynamics = []
            current_ids = []
            for d in dynamics:
                if d['type'] == 'video':
                    did = f'v_{d["bvid"]}'
                elif d['type'] == 'text':
                    did = f't_{d["dynamic_id"]}'
                elif d['type'] == 'forward_video':
                    did = f'fv_{d["bvid"]}'
                elif d['type'] == 'forward_text':
                    did = f'ft_{d["dynamic_id"]}'
                else:
                    continue

                current_ids.append(did)
                if did not in old_ids:
                    new_dynamics.append(d)

            # 保存
            os.makedirs(os.path.dirname(OLD_BVID_FILE), exist_ok=True)
            with open(OLD_BVID_FILE, 'w', encoding='utf-8') as f:
                json.dump(current_ids, f, ensure_ascii=False)

            if new_dynamics:
                send_feishu_card(new_dynamics)
                print(f"📤 推送 {len(new_dynamics)} 条动态")

            # 自评论检测
            for d in dynamics:
                print(dynamics)
                try:
                    if d['type'] == 'video':
                        self.check_video_self_comment(d['bvid'], d['mid'], d['name'])
                    elif d['type'] == 'text':
                        self.check_dynamic_self_comment(d['dynamic_id'], d['mid'], d['name'])
                except:
                    continue

            self.save_self_comment_history()
            print("✅ 本轮完成")
        except Exception as e:
            print(f"❌ 抓取异常: {e}")


def job():
    try:
        bililogin = session_cookie()
        if bililogin.ensure_login():
            time.sleep(random.randint(1, 6))
            print(f"[{datetime.now():%H:%M:%S}] 开始抓取")
            bililogin.get_followed_dynamic()
        else:
            print("❌ 登录失败")
    except:
        pass

interval_seconds = CONFIG.get("check_interval_seconds", 30)
print(f"⏰ 检查间隔: {interval_seconds} 秒")
schedule.every(interval_seconds).seconds.do(job)


# interval_minutes = CONFIG.get("check_interval_minutes", 1)
# print(f"⏰ 检查间隔: {interval_minutes} 分钟")
# schedule.every(interval_minutes).minutes.do(job)

while True:
    try:
        schedule.run_pending()
    except:
        pass
    time.sleep(1)