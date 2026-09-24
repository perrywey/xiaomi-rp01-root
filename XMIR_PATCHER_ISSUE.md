**Issue 标题（Title）** —— 复制这一行填到标题栏：

```
[RP01 / 1.0.67] 四个利用入口失效：根因分析与替代方案 | All 4 entry points fail — root cause & working alternative
```

**Issue 正文（Body）** —— 从这里往下全部复制：

---

## 中文

RP01（小米 BE3600 Pro 网线版）固件 1.0.67 上，现有的四个利用入口全部失效。
我把解包固件后定位到的**每一个入口的失效原因**，以及我找到的替代方案整理在下面，
分享给同样卡在这台机器上的人，也供本项目后续支持该机型时参考。

### 环境

- 设备：小米 BE3600 Pro **网线版**
- 型号：`RP01`
- 固件：MiWiFi 稳定版 `1.0.67` —— 该型号**从未发布过其他版本固件**，
  因此"降级到可利用的旧版本"这条路在这里不存在
- 内核：`Linux 5.4.213 armv7l`

### 现象

所有 connect 脚本都无法取得立足点。我没有直接判定这台机器没救，
而是解包固件后逐个入口跟了一遍。

### 各入口的失效原因

| 入口 | 参数 | 在 1.0.67 上为什么失败 |
|---|---|---|
| `arn_switch` | `level` | 不在 `XQSecureUtil.hackCheck` 白名单内 → 元字符被拦 |
| `start_binding` | `uid`、`key` | 同样不在白名单 → 被拦 |
| `set_mac_filter` | `name` | 用 `formvalue("name", nil, "?commonstr")` 读取；该正则拦 `` ` `` `;` `\|` `$` `&` `<` `>` 和换行，拼不出可用载荷 |
| datacenter / `connect6` | 多个 | 未发现可用入口 |

共同点是 `hackCheck` 那份白名单：它包含 `name`、`password`、`ssid`、`pppoeName` 之类，
但**不包含** `level` / `uid` / `key`。

### 可用的替代方案

固件里还注册了**另一个名字很相近的接口 `set_macfilter_rules`** ——
容易和 `set_mac_filter` 混淆，但它们是不同的处理函数。

- 它用两参数形式 `formvalue("name")` 读取 name，**没有正则检查**
- `hackCheck` 把字段名为 `name` 的参数列入白名单，因此原样放行
- `XQFirewall.setMacFilter()` 随后把它拼进
  `os.execute("/usr/sbin/macfilter add black <mac> rulename=" .. name)`，无转义

真机实测确认的约束条件：

- `option` 必须为 `0`（add）；`option=1` 且 MAC 不存在时会提前返回
- `;` 不可用（控制器会用 `;` 切分 `mac` / `name`），但换行、反引号、`$( )`、`|`、`&` 都可用
- `mac` 必须匹配 `^[0-9a-fA-F:;]+$`，且不能已存在于过滤表中

由此可以获得 root 权限的命令执行。之后我启动 `dropbear`，再用 `mkxqimage -I` 的
密码登录 —— 该密码等于 `MD5(SN + <固件中的固定盐>)[:8]`，
我已与路由器自身的输出做过逐字符核对。

完整的调用链、Lua 代码位置我整理成了文档，并发布了一个自包含的小脚本
（仅用标准库，未复制本项目的任何代码）：

https://github.com/perrywey/xiaomi-rp01-root

### 有一点想请其他机型的使用者帮忙确认

在我的机器上，这个利用**需要提供设备的 WEB 管理密码**，因此不构成无认证 RCE。
我想知道这一点在其他机型上是否同样成立 —— 如果某个型号/固件无需认证就能
访问该接口，那性质就完全不同了，应当按真正的漏洞报告流程处理，而不只是当作一种
root 方法。如果有谁测到了，请务必告诉我。

### 补充

以上任何细节我都可以再展开，也可以协助把 `RP01` 支持加进本项目。
另外我没有直接提 PR 合并代码 —— 本仓库当前未声明开源许可证，想先问一下你的意见。

---

## English

First, thanks for this project — it's been the starting point for basically everyone
working on Xiaomi routers, including me.

On one specific model + firmware combination, I found that all four existing exploit
entry points fail. Below is **why each one fails**, based on tracing the unpacked
firmware, plus a working alternative. Hopefully useful for adding support.

### Environment

- Device: Xiaomi BE3600 Pro (wired version / 网线版)
- Model: `RP01`
- Firmware: MiWiFi stable `1.0.67` — the only firmware ever released for this model,
  so downgrading to an older exploitable version is not an option here
- Kernel: `Linux 5.4.213 armv7l`

### What happens

Every connect script fails to get a foothold. Rather than assume the device was
hopeless, I unpacked the firmware and traced each entry point individually.

### Root cause, per entry point

| Entry point | Parameter | Why it fails on 1.0.67 |
|---|---|---|
| `arn_switch` | `level` | not in `XQSecureUtil.hackCheck`'s whitelist → metacharacters blocked |
| `start_binding` | `uid`, `key` | same, not whitelisted |
| `set_mac_filter` | `name` | read via `formvalue("name", nil, "?commonstr")`; the regex blocks `` ` `` `;` `\|` `$` `&` `<` `>` and newline, so no usable payload survives |
| datacenter / `connect6` | multiple | no working entry found |

The common thread is the `hackCheck` whitelist: it contains `name`, `password`,
`ssid`, `pppoeName` and similar — but **not** `level` / `uid` / `key`.

### A working alternative

The firmware registers **another, similarly-named endpoint: `set_macfilter_rules`** —
easy to confuse with `set_mac_filter`, but a different handler.

- It reads `name` with the two-argument `formvalue("name")`, i.e. **no regex check**.
- `hackCheck` whitelists the field name `name`, so the value is passed through unfiltered.
- `XQFirewall.setMacFilter()` then concatenates it into
  `os.execute("/usr/sbin/macfilter add black <mac> rulename=" .. name)` with no escaping.

Constraints confirmed on real hardware:

- `option` must be `0` (add); `option=1` returns early when the MAC is absent
- `;` is unusable (the controller splits `mac` / `name` on `;`), but newline,
  backticks, `$( )`, `|` and `&` all work
- `mac` must match `^[0-9a-fA-F:;]+$` and must not already exist in the filter table

That yields command execution as root. From there I start `dropbear` and log in with
the password from `mkxqimage -I` — notably `MD5(SN + <static salt found in the
firmware>)[:8]`, which I verified byte-for-byte against the router's own output.

I wrote up the full chain with the Lua call sites and released a small self-contained
script (standard library only, no code copied from this project):

https://github.com/perrywey/xiaomi-rp01-root

### One thing worth checking on other models

On my unit the exploit **requires the device's WEB admin password**, so it is not an
unauthenticated RCE. I'd like to know whether that holds elsewhere — if any
model/firmware accepts this endpoint without authentication, the severity changes
considerably and it should be handled as a proper vulnerability report rather than
just a rooting method. If anyone finds such a case, please let me know.

### Offer

Happy to expand on any of the above, or help add `RP01` support here. I deliberately
did not open a PR merging my code, since this repo doesn't currently declare a
license — wanted to check with you first.

Thanks again for the project.
