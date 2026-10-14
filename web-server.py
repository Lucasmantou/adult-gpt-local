# -*- coding: utf-8 -*-
"""网页服务器：静态文件 + Ollama / 本地生图 API 反向代理 + Basic Auth 访问密码。

- 监听 0.0.0.0:9090，网页根目录 = 同级 chatgpt-clone 文件夹
- /api/* 转发到本机 Ollama (127.0.0.1:11434)；/img/* 转发到本地生图服务 (127.0.0.1:7860)
- 所有请求需 Basic Auth（浏览器首次访问弹窗输入一次）
- 账号密码从 auth.json（或环境变量 ADULTGPT_AUTH_USER / ADULTGPT_AUTH_PASS）读取，
  不写死在代码里。首次运行会自动生成 auth.json 并在里面打印随机密码。
"""
import base64
import hmac
import json
import os
import secrets
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

PORT = 9090
WEBROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chatgpt-clone")
OLLAMA = "http://127.0.0.1:11434"
QWEN_IMAGE = "http://127.0.0.1:7860"   # Qwen-Image-2.1 本地生图服务
AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auth.json")


def load_auth():
    """读取账号密码：环境变量优先，其次 auth.json；都没有就生成随机密码写入 auth.json。"""
    user = os.environ.get("ADULTGPT_AUTH_USER", "").strip()
    pwd = os.environ.get("ADULTGPT_AUTH_PASS", "").strip()
    if user and pwd:
        return user, pwd
    try:
        with open(AUTH_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("user") and d.get("pass"):
            return str(d["user"]), str(d["pass"])
    except (OSError, ValueError):
        pass
    user = "admin"
    pwd = secrets.token_urlsafe(12)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump({"user": user, "pass": pwd}, f, ensure_ascii=False, indent=2)
    print("已生成 %s，登录账号：%s 密码：%s（请自行保存或修改此文件）" % (AUTH_FILE, user, pwd))
    return user, pwd


AUTH_USER, AUTH_PASS = load_auth()


class Handler(SimpleHTTPRequestHandler):
    # HTTP/1.0 + 连接关闭：流式响应无需 chunked 编码，逐行 flush 即可
    protocol_version = "HTTP/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEBROOT, **kwargs)

    def log_message(self, fmt, *args):
        try:
            print("%s %s" % (self.address_string(), fmt % args))
        except Exception:
            pass

    # ---- Basic Auth ----
    def _authed(self):
        header = self.headers.get("Authorization", "")
        try:
            scheme, cred = header.split(None, 1)
            user, pwd = base64.b64decode(cred).decode("utf-8", "replace").split(":", 1)
        except Exception:
            return False
        return (scheme.lower() == "basic"
                and hmac.compare_digest(user, AUTH_USER)
                and hmac.compare_digest(pwd, AUTH_PASS))

    def _check_auth(self):
        if self._authed():
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="AdultGPT"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    # ---- 请求入口 ----
    def _target(self):
        # /img/* → 本地生图服务 Qwen-Image-2.1（去掉 /img 前缀）；其余 /api/* → Ollama
        if self.path == "/img" or self.path.startswith("/img/"):
            return QWEN_IMAGE, self.path[4:] or "/"
        if self.path.startswith("/api/"):
            return OLLAMA, self.path
        return None, None

    def do_GET(self):
        if not self._check_auth():
            return
        base, path = self._target()
        if base:
            self._proxy(base, path)
        else:
            super().do_GET()

    def do_POST(self):
        if not self._check_auth():
            return
        base, path = self._target()
        if base:
            self._proxy(base, path)
        else:
            self.send_error(404)

    def do_HEAD(self):
        # 不许 HEAD 绕过鉴权（SimpleHTTPRequestHandler 默认的 do_HEAD 不经过认证）
        if not self._check_auth():
            return
        base, path = self._target()
        if base:
            self._proxy(base, path)
        else:
            super().do_HEAD()

    def do_OPTIONS(self):
        # 同源部署下基本用不到，保险起见放行预检
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- 反向代理（流式）：/api/* → Ollama，/img/* → 生图服务 ----
    def _proxy(self, base, path):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(base + path, data=body, method=self.command)
        if body is not None:
            req.add_header("Content-Type",
                           self.headers.get("Content-Type", "application/json"))
        try:
            resp = urllib.request.urlopen(req, timeout=620)
            status = resp.status
        except urllib.error.HTTPError as e:
            resp, status = e, e.code
        except Exception:
            self.send_response(502)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self.send_response(status)
        ctype = resp.headers.get("Content-Type")
        if ctype:
            self.send_header("Content-Type", ctype)
        self.end_headers()
        try:
            while True:                 # 按块转发：NDJSON 流和二进制图片都适用
                chunk = resp.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception:
            pass                        # 客户端提前断开（用户停止生成）属正常


if __name__ == "__main__":
    os.chdir(WEBROOT)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("AdultGPT web server on 0.0.0.0:%d, root=%s" % (PORT, WEBROOT))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
