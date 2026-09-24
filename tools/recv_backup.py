#!/usr/bin/env python3
"""
小米 RP01 flash 备份接收端 —— 在【Mac】上跑。

用法:
    python3 recv_backup.py ~/rp01_backup 8001

为什么需要它:
  busybox 的 `wget --post-file` 走 C 字符串, 遇到 0x00 就截断, 二进制分区直接传会残缺。
  所以路由器侧先 base64, 本脚本收到后自动解码回 .bin, 并按分区表校验大小。

路由器侧配合:
  dd if=/dev/mtdblock21 of=/tmp/m.bin bs=65536 2>/dev/null
  base64 /tmp/m.bin > /tmp/m.b64
  wget -q --post-file=/tmp/m.b64 -O /dev/null http://<MacIP>:8001/mtd21.b64
"""
import base64
import http.server
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "./rp01_backup"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 8001

# /proc/mtd 里的分区大小（字节），用于校验备份是否完整
EXPECT = {
    0: 0x00180000, 1: 0x00180000, 2: 0x00100000, 3: 0x00080000,
    4: 0x00080000, 5: 0x00380000, 13: 0x00080000, 14: 0x00180000,
    15: 0x00180000, 16: 0x00200000, 17: 0x00080000, 18: 0x00040000,
    19: 0x02D00000, 20: 0x02D00000, 21: 0x00080000, 23: 0x02F40000,
}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _safe(self, name):
        keep = [c for c in name if c.isalnum() or c in "._-"]
        return "".join(keep) or "upload.bin"

    def do_POST(self):
        total = int(self.headers.get("Content-Length") or 0)
        buf = bytearray()
        while len(buf) < total:
            chunk = self.rfile.read(min(65536, total - len(buf)))
            if not chunk:
                break
            buf += chunk

        fn = self._safe(os.path.basename(self.path.strip("/")))
        data = bytes(buf)

        if fn.endswith(".b64"):
            try:
                data = base64.b64decode(data)
            except Exception as e:
                print(f"[!] {fn} base64 解码失败: {e}", flush=True)
                self._reply(b"bad")
                return
            fn = fn[:-4] + ".bin"

        path = os.path.join(OUT, fn)
        with open(path, "wb") as f:
            f.write(data)

        # 大小校验
        mark, note = " ", ""
        num = "".join(c for c in fn if c.isdigit())
        if num and fn.startswith("mtd"):
            idx = int(num)
            if idx in EXPECT:
                if len(data) == EXPECT[idx]:
                    mark = "OK"
                else:
                    mark = "NG"
                    note = f"  <-- 应为 {EXPECT[idx]:,}"

        print(f"[{mark}] {path}  {len(data):,} bytes{note}", flush=True)
        self._reply(b"ok")

    def _reply(self, body):
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(b"recv_backup ready\n")

    def log_message(self, *args):
        pass


os.makedirs(OUT, exist_ok=True)
print(f"[*] 接收目录: {os.path.abspath(OUT)}")
print(f"[*] 监听 0.0.0.0:{PORT}  —— 等路由器 wget 过来（[OK]=大小正确 [NG]=残缺）")
http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
