import BigWorld, Keys, time

# ---- tunables ----
MIN_SPEED = 10.0     # px/s: slower releases don't start a spin
MAX_SPEED = 600.0    # px/s: cap
FIXED_SPEED = None   # e.g. 250.0 = always spin at this speed in the release direction
DECAY = 0.0          # 1/s; 0 = never slows. e.g. 0.3 = gentle coast-down
WINDOW = 0.1         # s, width of each speed-measuring window
HISTORY = 0.4        # s of drag history considered at release
# ------------------

_samples = []
_spin = 0.0
_lastT = None
_injecting = False
_evCls = None
_evType = None


def _onMove(event):
    global _evCls, _evType
    if _injecting:
        return
    _evCls, _evType = type(event), event.eventType
    now = time.time()
    _samples.append((now, event.ctx.get('dx', 0.0)))
    while _samples and now - _samples[0][0] > HISTORY:
        _samples.pop(0)


def _peakSpeed():
    best = 0.0
    for t0, _ in _samples:
        s = sum(dx for t, dx in _samples if t0 <= t < t0 + WINDOW) / WINDOW
        if abs(s) > abs(best):
            best = s
    return best


def _down():
    return BigWorld.isKeyDown(Keys.KEY_LEFTMOUSE) or BigWorld.isKeyDown(Keys.KEY_RIGHTMOUSE)


def _tick():
    global _spin, _lastT, _injecting
    BigWorld.callback(0.0, _tick)
    try:
        now = time.time()
        dt = 0.0 if _lastT is None else min(now - _lastT, 0.1)
        _lastT = now
        if _down():
            _spin = 0.0
            return
        if _samples and now - _samples[-1][0] > 0.02:
            speed = _peakSpeed()
            del _samples[:]
            if abs(speed) >= MIN_SPEED:
                sign = 1.0 if speed > 0 else -1.0
                _spin = sign * (FIXED_SPEED if FIXED_SPEED else min(abs(speed), MAX_SPEED))
        if _spin == 0.0 or dt <= 0.0 or _evCls is None:
            return
        if DECAY:
            _spin *= max(0.0, 1.0 - DECAY * dt)
            if abs(_spin) < MIN_SPEED * 0.25:
                _spin = 0.0
                return
        from gui.shared import g_eventBus
        _injecting = True
        try:
            g_eventBus.handleEvent(_evCls(_evType, ctx={'dx': _spin * dt, 'dy': 0.0, 'dz': 0.0}))
        finally:
            _injecting = False
    except Exception:
        _spin = 0.0


def init():
    try:
        from gui.shared import g_eventBus
        from gui.hangar_cameras.hangar_camera_common import CameraRelatedEvents
        g_eventBus.addListener(CameraRelatedEvents.LOBBY_VIEW_MOUSE_MOVE, _onMove)
        BigWorld.callback(0.0, _tick)
    except Exception:
        pass