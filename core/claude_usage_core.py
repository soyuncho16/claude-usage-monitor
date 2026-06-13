#!/usr/bin/env python3
"""Claude 구독 사용량 폴러 — 응답 헤더의 unified 사용량을 state.json에 쓴다.

크로스플랫폼 공유 코어. 프론트엔드(GNOME/macOS/Windows)는 이 스크립트를 spawn하고
state.json을 읽는다 — 인터페이스는 state.json 파일 하나뿐.
"""
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime

# 자격증명 경로는 expanduser가 세 OS 모두에서 올바른 홈을 잡는다
# (Windows는 %USERPROFILE%\.claude\.credentials.json, 슬래시도 동작).
CRED_PATH = os.path.expanduser("~/.claude/.credentials.json")


def _cache_dir():
    """OS 관례에 맞는 사용자 캐시 디렉토리 + claude-usage 하위."""
    if os.name == "nt":  # Windows
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(
            r"~\AppData\Local")
    elif sys.platform == "darwin":  # macOS
        base = os.path.expanduser("~/Library/Caches")
    else:  # Linux/기타
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "claude-usage")


STATE_DIR = _cache_dir()
STATE_PATH = os.path.join(STATE_DIR, "state.json")

# Task 1 실측 결과: count_tokens는 unified 헤더를 반환하지 않음(HTTP 200이나 헤더 없음).
# 따라서 messages 엔드포인트로 전환. max_tokens=1로 출력 최소화.
API_URL = "https://api.anthropic.com/v1/messages"
API_BODY = {
    "model": "claude-haiku-4-5",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "ping"}],
}
TIMEOUT_S = 7


class PollerError(Exception):
    """etype ∈ no_creds | auth_expired | network | parse
    (rate_limited는 state error 분류용으로만 존재; 현재 코드에서 raise되지 않음)
    """

    def __init__(self, etype, message):
        super().__init__(message)
        self.etype = etype


def read_token(now):
    """~/.claude/.credentials.json에서 Bearer 토큰을 읽어 반환한다.

    Args:
        now: 현재 unix epoch (초). 만료 시각 비교에 사용.

    Returns:
        accessToken 문자열.

    Raises:
        PollerError(etype="no_creds"): 파일 없음·파싱 실패·토큰 없음.
        PollerError(etype="auth_expired"): 토큰 만료.
    """
    try:
        with open(CRED_PATH) as f:
            oauth = json.load(f)["claudeAiOauth"]
    except (OSError, KeyError, ValueError):
        raise PollerError("no_creds", f"cannot read {CRED_PATH}")
    exp = oauth.get("expiresAt")
    if exp:
        exp_s = exp / 1000 if exp > 10**12 else exp  # ms epoch if > 10^12, else seconds
        if exp_s < now:
            raise PollerError("auth_expired", "accessToken expired")
    token = oauth.get("accessToken")
    if not token:
        raise PollerError("no_creds", "no accessToken in credentials")
    return token


PREFIX = "anthropic-ratelimit-unified-"


def _pct(raw):
    try:
        v = float(raw)
    except ValueError:
        raise PollerError("parse", f"bad utilization value: {raw!r}")
    # 1.5 초과는 퍼센트로 간주 (실측: 분수 0.0-1.0 형식만 관찰됨)
    if "." in raw and v <= 1.5:  # 분수 형식(0.47) → 퍼센트
        v *= 100
    return max(0, min(100, round(v)))


def _epoch(raw, now):
    raw = raw.strip()
    if raw.isdigit():
        n = int(raw)
        return n if n > 10**9 else now + n  # epoch초(> 10^9) vs 남은초
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def parse_state(headers, now):
    """응답 헤더 dict에서 사용량 상태를 파싱해 반환한다.

    Args:
        headers: lowercase 헤더 dict (fetch_headers 반환값).
        now: 현재 unix epoch (초).

    Returns:
        {"ok": True, "fetched_at": now, "five_h": {...}, "seven_d": {...},
         "status": str|None, "error": None}
        (참고: main이 429 응답일 때 반환값의 error에 rate_limited를 주입한다 —
         호출자는 error가 항상 None이라고 가정하면 안 됨)

    Raises:
        PollerError(etype="parse"): 5h utilization 헤더가 없을 때.
    """
    uni = {k[len(PREFIX):]: v for k, v in headers.items() if k.startswith(PREFIX)}

    def window(tag):
        out = {"utilization": None, "resets_at": None}
        for k, v in uni.items():
            if tag in k and "utilization" in k:
                out["utilization"] = _pct(v)
            elif tag in k and "reset" in k:
                out["resets_at"] = _epoch(v, now)
        return out

    five, seven = window("5h"), window("7d")
    if five["utilization"] is None:
        raise PollerError("parse", f"no 5h utilization (unified keys: {sorted(uni)})")
    return {
        "ok": True,
        "fetched_at": now,
        "five_h": five,
        "seven_d": seven,
        "status": uni.get("status"),
        "error": None,
    }


def load_prev():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_PATH)  # 원자적 교체
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def error_state(err, prev, now):
    base = prev or {}
    return {
        "ok": False,
        "fetched_at": now,
        "five_h": base.get("five_h"),
        "seven_d": base.get("seven_d"),
        "status": base.get("status"),
        "error": {"type": err.etype, "message": str(err)},
    }


def fetch_headers(token):
    """(lowercase header dict, http status) 반환. 200/429 둘 다 정상 경로."""
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(API_BODY).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            return {k.lower(): v for k, v in resp.headers.items()}, resp.status
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise PollerError("auth_expired", "token rejected (401)")
        if e.code == 429:
            return {k.lower(): v for k, v in e.headers.items()}, 429
        raise PollerError("network", f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PollerError("network", str(getattr(e, "reason", e)))


def poll_once(now, dump_headers=False):
    """1회 폴링 후 state dict를 반환한다.

    PollerError(인증·네트워크·파싱)는 error_state로 변환해 반환한다 — raise하지 않는다.
    단, write_state의 OSError 등 그 외 예외는 **의도적으로 전파**한다: 캐시 쓰기 실패는
    시스템 이상이라 CLI는 traceback으로 진단하는 게 낫고, 이전 state.json도 보존된다.
    따라서 GUI 스레드에서 호출하는 in-process 프론트엔드(macOS worker)는 절대 raise하지
    않는 poll_once_safe()를 써서 worker가 조용히 죽지 않게 해야 한다.

    성공: 헤더 파싱 후 write_state. 429면 error에 rate_limited 주입(ok는 True 유지).
    PollerError: error_state를 직전 값 위에 써서 반환(ok False).

    spawn 기반 프론트엔드(GNOME/Windows)와 CLI는 main을 통해 호출한다.
    """
    try:
        token = read_token(now)
        headers, status = fetch_headers(token)
        if dump_headers:
            print(f"# HTTP {status}", file=sys.stderr)
            for k in sorted(headers):
                print(f"{k}: {headers[k]}", file=sys.stderr)
        state = parse_state(headers, now)
        if status == 429:
            state["error"] = {"type": "rate_limited", "message": "HTTP 429"}
        write_state(state)
        return state
    except PollerError as e:
        state = error_state(e, load_prev(), now)
        write_state(state)
        return state


def poll_once_safe(now, prev):
    """poll_once를 감싸 **어떤 예외도** state로 변환한다 — 절대 raise하지 않는다.

    poll_once는 PollerError만 state로 바꾸고 write_state OSError 등은 전파한다.
    in-process GUI 프론트엔드(macOS worker)는 스레드가 조용히 죽으면 메뉴바가 영영
    갱신되지 않으므로 이 래퍼를 쓴다. 전파된 예외는 prev 값을 보존한 error_state로
    변환해 '오래된 값 + 오류'로 표시되게 한다.

    Args:
        now: 현재 unix epoch(초).
        prev: 직전 state(없으면 None) — 전파 예외 시 표시값 보존에 사용.
    """
    try:
        return poll_once(now)
    except Exception as e:
        return error_state(PollerError("internal", f"poll 실패: {e}"), prev, now)


def main(argv):
    # write_state의 OSError는 의도적으로 전파한다 — 캐시 쓰기 실패는 시스템 이상이며
    # traceback 그대로가 진단에 유리. 이전 state.json은 보존되어 데이터 손실도 없다.
    now = int(time.time())
    state = poll_once(now, dump_headers=("--dump-headers" in argv))
    if not state.get("ok"):
        err = state.get("error") or {}
        print(f"error[{err.get('type')}]: {err.get('message')}", file=sys.stderr)
        return 1
    return 0  # 429(rate_limited)는 ok=True라 0을 반환 — 기존 동작 보존


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
