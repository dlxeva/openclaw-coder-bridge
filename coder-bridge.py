#!/usr/bin/env python3
"""
openclaw-coder-bridge
A background daemon that bridges OpenClaw agents with AI coding tools
via a file-based task queue (inbox/ -> outbox/).
https://github.com/dlxeva/openclaw-coder-bridge
"""

import os
import json
import time
import hashlib
import shutil
import subprocess
import signal
import sys
import locale
from datetime import datetime
from pathlib import Path

# Warn early if system encoding is not UTF-8 (affects subprocess on Windows)
_enc = locale.getpreferredencoding(False)
if _enc.upper().replace("-", "") not in ("UTF8", "UTF-8"):
    print(f"[WARNING] System encoding is {_enc}, not UTF-8. "
          "If you see path or decode errors, enable 'Beta: Use Unicode UTF-8' "
          "in Windows Region → Administrative → Change system locale, then reboot.")

# 路径配置
BASE_DIR = Path(__file__).parent
INBOX_DIR = BASE_DIR / "inbox"
OUTBOX_DIR = BASE_DIR / "outbox"
ARCHIVE_DIR = BASE_DIR / "archive"
LOG_FILE = BASE_DIR / "bridge.log"
STATE_FILE = BASE_DIR / "bridge-status.json"
PID_FILE = BASE_DIR / "bridge.pid"


def check_single_instance():
    """确保只有一个 bridge 实例在运行"""
    if PID_FILE.exists():
        old_pid = int(PID_FILE.read_text().strip())
        try:
            import psutil
            if psutil.pid_exists(old_pid):
                print(f"Bridge 已在运行 (PID {old_pid})，退出。")
                sys.exit(0)
        except ImportError:
            # psutil 不可用时用 os.kill 检测
            try:
                os.kill(old_pid, 0)
                print(f"Bridge 已在运行 (PID {old_pid})，退出。")
                sys.exit(0)
            except OSError:
                pass  # 进程不存在，继续启动
    PID_FILE.write_text(str(os.getpid()))

# 超时配置（秒）
CODER_TIMEOUT = int(os.environ.get("CODER_TIMEOUT", "600"))

# Telegram 配置
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Git Bash 路径 —— 优先用环境变量，否则自动检测常见安装位置
def _find_bash():
    if env := os.environ.get("BASH_EXE"):
        return env
    candidates = [
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    raise RuntimeError(
        "找不到 Git Bash。请安装 Git for Windows，"
        "或设置环境变量 BASH_EXE 指向 bash.exe 路径。"
    )

BASH_EXE = _find_bash()


def log(msg):
    """日志输出"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {msg}"
    print(log_msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_msg + "\n")


def load_state():
    """加载状态"""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"running": True, "processed": [], "errors": [], "started_at": datetime.now().isoformat()}


def save_state(state):
    """保存状态"""
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def notify_telegram(task_id, status="completed"):
    """发送 Telegram 通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        import urllib.request
        import urllib.parse
        
        text = f"✅ Bridge 任务 {status}: {task_id}"
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
        log(f"Telegram 通知已发出: {task_id}")
    except Exception as e:
        log(f"Telegram 通知失败: {e}")


def compute_file_hash(filepath):
    """计算文件内容 hash"""
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:8]


def process_task(task_file):
    """处理单个任务"""
    task_id = task_file.stem
    log(f"处理任务: {task_id}")
    
    state = load_state()
    
    try:
        # 读取任务内容
        content = task_file.read_text(encoding="utf-8")
        
        # 提取目标 (from -> to)
        lines = content.split("\n")
        from_addr = "main"
        to_addr = "claude-code"
        for line in lines:
            if line.startswith("from:"):
                from_addr = line.split(":", 1)[1].strip()
            elif line.startswith("to:"):
                to_addr = line.split(":", 1)[1].strip()
        
        # 构建 prompt 给 Claude Code
        prompt = f"""请处理以下任务并回复：

{content}

回复格式：
---
task_id: {task_id}
from: {to_addr}
to: {from_addr}
status: ok|error
---

只返回任务结果，不要多余解释。"""
        
        # 调用 Claude Code
        result = run_claude(prompt)
        
        # 写入回复
        reply_file = OUTBOX_DIR / f"reply-{task_id}.md"
        reply_file.write_text(result, encoding="utf-8")
        
        # 更新状态
        state["processed"].append(task_id)
        save_state(state)
        
        # 归档任务
        archive_file = ARCHIVE_DIR / task_file.name
        shutil.move(str(task_file), str(archive_file))
        
        log(f"任务已完成: {task_id}")
        notify_telegram(task_id, "completed")
        
    except Exception as e:
        error_msg = str(e)
        log(f"任务失败: {task_id} - {error_msg}")
        
        # 记录错误
        state["errors"].append({"task": task_id, "error": error_msg})
        save_state(state)
        
        # 写入错误回复
        reply_file = OUTBOX_DIR / f"reply-{task_id}.md"
        reply_file.write_text(f"---\ntask_id: {task_id}\nstatus: error\n---\n\n# 回复\n\n[ERROR] {error_msg}", encoding="utf-8")

        # 归档失败任务，防止无限重试
        archive_file = ARCHIVE_DIR / task_file.name
        if task_file.exists():
            shutil.move(str(task_file), str(archive_file))

        notify_telegram(task_id, "failed")


def run_claude(prompt):
    """调用 Claude Code - 使用 Git Bash 避免中文路径编码问题"""
    # 清理嵌套 session 标记（保留 ANTHROPIC_API_KEY）
    env = os.environ.copy()
    for k in list(env.keys()):
        if "CLAUDE" in k.upper():
            del env[k]

    # 补全 PATH：确保 Git Bash Unix 工具可用（claude wrapper 需要 sed/dirname/uname）
    bash_dir = str(Path(BASH_EXE).parent)          # .../Git/usr/bin
    git_bin  = str(Path(BASH_EXE).parent.parent.parent / "bin")  # .../Git/bin
    current_path = env.get("PATH", "")
    if bash_dir not in current_path:
        env["PATH"] = bash_dir + ";" + git_bin + ";" + current_path

    # claude bash wrapper 用 dirname "$0" 定位 node_modules，
    # 但 $0 为命令名"claude"时 dirname 返回 "."（当前目录）。
    # 将 cwd 设为 npm bin 目录，确保 "." 正确指向含 node_modules 的位置。
    # 优先用 shutil.which 自动定位（兼容 nvm/pnpm/自定义 prefix），找不到再 fallback。
    _claude_which = shutil.which("claude")
    npm_bin = (
        Path(_claude_which).parent
        if _claude_which
        else Path.home() / "AppData" / "Roaming" / "npm"
    )

    # 通过 Git Bash 调用 claude -p，prompt 经由 stdin 传入
    result = subprocess.run(
        [BASH_EXE, "-c", "claude -p --dangerously-skip-permissions"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=str(npm_bin),
        timeout=CODER_TIMEOUT,
    )

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise Exception(f"Claude 调用失败 (exit {result.returncode}): {stderr[:500]}")

    output = (result.stdout or "").strip()
    if not output:
        stderr = (result.stderr or "").strip()
        raise Exception(f"Claude 返回空输出. stderr: {stderr[:300]}")

    return output


def main():
    """主循环"""
    check_single_instance()

    log("=" * 50)
    log("Claude Bridge 启动")
    log("=" * 50)

    # 创建必要目录
    INBOX_DIR.mkdir(exist_ok=True)
    OUTBOX_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    
    # 扫描存量任务
    log("扫描存量任务...")
    for task_file in INBOX_DIR.glob("task-*.md"):
        process_task(task_file)
    
    log(f"监听目录: {INBOX_DIR}")
    log("按 Ctrl+C 停止")
    
    # 主循环
    try:
        while True:
            # 检查新任务
            task_files = list(INBOX_DIR.glob("task-*.md"))
            if task_files:
                for task_file in task_files:
                    process_task(task_file)
            else:
                time.sleep(2)
                
    except KeyboardInterrupt:
        log("Bridge 已停止")
        state = load_state()
        state["running"] = False
        save_state(state)
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


if __name__ == "__main__":
    main()
