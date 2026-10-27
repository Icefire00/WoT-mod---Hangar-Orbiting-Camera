import BigWorld, Keys, time, os, json

# CineHangar - free-spin orbit, smooth dolly zoom, pivot shift with saved positions, clean-screen toggle.
# All settings live in  <game folder>/mods/cinehangar.json  (created on first run, hot-reloaded when edited).

_CONFIG_FILE = os.path.join(os.getcwd(), 'mods/configs', 'cinehangar.json')
_OLD_SLOTS_FILE = os.path.join(os.getcwd(), 'mods/configs', 'hangarspin_slots.json')   # imported once if present
_DEBUG_FILE = os.path.join(os.getcwd(), 'mods/configs', 'cinehangar_debug.log')
_ERROR_FILE = os.path.join(os.getcwd(), 'mods/configs', 'cinehangar_error.log')   # only written when something fails
DEBUG = False


def _logError(where, detail=None):
    try:
        import traceback
        with open(_ERROR_FILE, 'a') as f:
            f.write('%s %s%s\n%s\n' % (time.strftime('%H:%M:%S'), where,
                                       '' if detail is None else ' - ' + str(detail), traceback.format_exc()))
    except Exception:
        pass


def _debug(where):
    if not DEBUG:
        return
    try:
        import traceback
        with open(_DEBUG_FILE, 'a') as f:
            f.write('%s %s\n%s\n' % (time.strftime('%H:%M:%S'), where, traceback.format_exc()))
    except Exception:
        pass


class _OD(object):
    """Tiny insertion-ordered mapping. (The game replaces collections.OrderedDict with a weakref-based
    version whose copies break on iteration, so we deliberately don't use it.)"""
    __slots__ = ('_keys', '_data')

    def __init__(self, pairs=()):
        self._keys = []
        self._data = {}
        for k, v in pairs:
            self[k] = v

    def __setitem__(self, k, v):
        if k not in self._data:
            self._keys.append(k)
        self._data[k] = v

    def __getitem__(self, k):
        return self._data[k]

    def __contains__(self, k):
        return k in self._data

    def __iter__(self):
        return iter(list(self._keys))

    def __len__(self):
        return len(self._keys)

    def get(self, k, default=None):
        return self._data.get(k, default)

    def items(self):
        return [(k, self._data[k]) for k in self._keys]


def _od(*pairs):
    return _OD(pairs)


def _clone(o):
    if isinstance(o, _OD):
        return _OD([(k, _clone(v)) for k, v in o.items()])
    if isinstance(o, list):
        return [_clone(x) for x in o]
    return o


def _plain(o):
    if isinstance(o, _OD):
        return dict((k, _plain(v)) for k, v in o.items())
    if isinstance(o, list):
        return [_plain(x) for x in o]
    return o


_README = ('Edit while the game runs: changes apply within about a second. A typo keeps the last good settings. '
           'Key names are the part after KEY_ in the game Keys module, e.g. A, F10, BACKSPACE, LSHIFT, 1. '
           'Use null for none. pivot.keys maps a key to an [x, y, z] direction (held with Shift). '
           'Shift+1..5 recalls a saved position, Ctrl+Shift+1..5 saves one into saved_positions.')

DEFAULTS = _od(
    ('_readme', _README),
    ('settings', _od(
        ('spin', _od(
            ('min_speed', 20.0),         # px/s: slower releases don't start a spin
            ('max_speed', 600.0),        # px/s: cap
            ('fixed_speed', None),       # e.g. 250.0 = always spin at this speed, in the release direction
            ('decay', 0.0),              # 1/s; 0 = never slows, e.g. 0.3 = gentle coast-down
            ('window', 0.1),             # s, width of each speed-measuring window
            ('history', 0.4))),          # s of drag history considered at release
        ('gui', _od(
            ('hide_key', 'F10'),         # toggles all hangar GUI; null = disabled
            ('auto_hide', True),         # hide the GUI automatically while spinning
            ('debug', False))),          # write exceptions to mods/cinehangar_debug.log
        ('zoom', _od(
            ('smooth', True),            # false = original stepped zoom
            ('speed', 1.2),              # metres/second cruise speed
            ('ramp', 0.3),               # seconds to reach full speed / glide to a stop; bigger = gentler
            ('queue_max', 8.0))),        # metres of scrolling that can be queued at once
        ('pivot', _od(
            ('speed', 0.6),              # units/second while a Shift+key is held
            ('allowed_cameras', None),   # null = every hangar camera, or a list e.g. ["Tank", "Customization"]
            ('per_camera_offset', False),# true = each camera keeps its own offset and saved positions
            ('reset_key', 'BACKSPACE'),  # Shift+this resets the offset; null = disabled
            ('keys', _od(
                ('A', [-1.0, 0.0, 0.0]), ('D', [1.0, 0.0, 0.0]),       # X
                ('Q', [0.0, -1.0, 0.0]), ('E', [0.0, 1.0, 0.0]),       # Y (down / up)
                ('S', [0.0, 0.0, -1.0]), ('W', [0.0, 0.0, 1.0]))))),   # Z
        ('slots', _od(
            ('recall_time', 0.6))),      # seconds to glide to a recalled position; 0 = jump instantly
    )),
    ('saved_positions', _od()),
)

# (section, json key, module global, kind, minimum)
_SPEC = (
    ('spin', 'min_speed', 'MIN_SPEED', 'float', 0.0),
    ('spin', 'max_speed', 'MAX_SPEED', 'float', 1.0),
    ('spin', 'fixed_speed', 'FIXED_SPEED', 'optfloat', None),
    ('spin', 'decay', 'DECAY', 'float', 0.0),
    ('spin', 'window', 'WINDOW', 'float', 0.01),
    ('spin', 'history', 'HISTORY', 'float', 0.05),
    ('gui', 'hide_key', 'HIDE_GUI_KEY', 'key', None),
    ('gui', 'auto_hide', 'AUTO_HIDE_GUI', 'bool', None),
    ('gui', 'debug', 'DEBUG', 'bool', None),
    ('zoom', 'smooth', 'ZOOM_SMOOTH', 'bool', None),
    ('zoom', 'speed', 'ZOOM_SPEED', 'float', 0.01),
    ('zoom', 'ramp', 'ZOOM_RAMP', 'float', 0.02),
    ('zoom', 'queue_max', 'ZOOM_QUEUE_MAX', 'float', 0.1),
    ('pivot', 'speed', 'PIVOT_SPEED', 'float', 0.0),
    ('pivot', 'allowed_cameras', 'ALLOWED_CAMS', 'cams', None),
    ('pivot', 'per_camera_offset', 'PER_CAMERA_OFFSET', 'bool', None),
    ('pivot', 'reset_key', 'PIVOT_RESET_KEY', 'key', None),
    ('pivot', 'keys', 'PIVOT_KEYS', 'keymap', None),
    ('slots', 'recall_time', 'RECALL_TIME', 'float', 0.0),
)


def _keyCode(name):
    if name is None or name == '':
        return None
    return getattr(Keys, 'KEY_' + str(name).upper())


def _conv(kind, v):
    if kind == 'float':
        return float(v)
    if kind == 'optfloat':
        return None if v is None else float(v)
    if kind == 'bool':
        if not isinstance(v, bool):
            raise ValueError('expected true/false')
        return v
    if kind == 'key':
        return _keyCode(v)
    if kind == 'cams':
        if v is None:
            return None
        return (str(v),) if isinstance(v, (str, type(u''))) else tuple(str(x) for x in v)
    if kind == 'keymap':
        out = []
        for k, axis in v.items():
            try:
                axis = tuple(float(c) for c in axis)
                if len(axis) == 3:
                    out.append((_keyCode(k), axis))
            except Exception:
                _debug('pivot key %r ignored' % (k,))
        return tuple(out)
    raise ValueError(kind)


def _applySettings(settings):
    g = globals()
    for section, key, name, kind, lo in _SPEC:
        default = DEFAULTS['settings'][section][key]
        try:
            raw = settings[section][key]
        except (KeyError, TypeError):
            raw = default
        try:
            val = _conv(kind, raw)
        except Exception:
            _debug('bad value for %s.%s, using default' % (section, key))
            val = _conv(kind, default)
        if lo is not None and val is not None and val < lo:
            val = lo
        g[name] = val


_applySettings({})   # defaults until the file has been read


def _keysNamed(*names):
    return tuple(getattr(Keys, n) for n in names if hasattr(Keys, n))


_SHIFT_KEYS = _keysNamed('KEY_LSHIFT', 'KEY_RSHIFT', 'KEY_LEFTSHIFT', 'KEY_RIGHTSHIFT')
_CTRL_KEYS = _keysNamed('KEY_LCONTROL', 'KEY_RCONTROL', 'KEY_LEFTCONTROL', 'KEY_RIGHTCONTROL')
SLOT_KEYS = tuple((n, getattr(Keys, 'KEY_%d' % n)) for n in range(1, 6) if hasattr(Keys, 'KEY_%d' % n))

_samples = []
_state = {'spin': 0.0, 'lastT': None, 'injecting': False, 'cls': None, 'type': None,
          'manualHide': False, 'autoHide': False, 'keyPrev': False,
          'offs': {}, 'prev': {}, 'lastCam': None, 'slots': {}, 'glide': None,
          'zpend': 0.0, 'zv': 0.0, 'zdir': 0.0, 'sens': 0.003, 'zd': None, 'zidle': 0.0,
          'cfgMtime': 0.0, 'cfgT': 0.0}
_ZOOM_RESYNC = 0.8            # s of no scrolling before zoom may re-read the camera's real distance...
_ZOOM_RESYNC_MAX = 3.0        # ...once the camera has settled (or after this many seconds regardless)
_origShift = [None]
_origMove = [None]
_origMouse = [None]


# ---------------- config file ----------------

def _mtime():
    try:
        return os.path.getmtime(_CONFIG_FILE)
    except Exception:
        return 0.0


def _readFile():
    """Returns (data, status) with status 'ok', 'missing' or 'bad'."""
    if not os.path.exists(_CONFIG_FILE):
        return None, 'missing'
    try:
        with open(_CONFIG_FILE) as f:
            text = f.read()
        if not text.strip():                     # empty file (e.g. a failed earlier write): same as missing
            return None, 'missing'
        data = json.loads(text, object_pairs_hook=_OD)
        return (data, 'ok') if isinstance(data, _OD) else (None, 'bad')
    except Exception as e:
        _logError('config is not valid JSON, keeping previous settings', e)   # message says line/column
        return None, 'bad'


def _dumps(o, lvl=0):
    # objects expanded one key per line, lists kept on one line
    if isinstance(o, (_OD, dict)):
        if not len(o):
            return '{}'
        pad = '  ' * (lvl + 1)
        items = [pad + json.dumps(str(k)) + ': ' + _dumps(v, lvl + 1) for k, v in o.items()]
        return '{\n' + ',\n'.join(items) + '\n' + '  ' * lvl + '}'
    return json.dumps(o)


def _writeFile(data):
    # build the text BEFORE touching the file, so a failure can never leave an empty file behind
    text = None
    try:
        text = _dumps(data)
    except Exception:
        _logError('pretty serializer failed, using plain json.dumps')
    if text is None:
        try:
            text = json.dumps(_plain(data), indent=2, sort_keys=True)
        except Exception:
            _logError('json.dumps failed, config not written')
            return False
    try:
        with open(_CONFIG_FILE, 'w') as f:
            f.write(text + '\n')
        _state['cfgMtime'] = _mtime()
        return True
    except Exception:
        _logError('could not write %s' % _CONFIG_FILE)
        return False


def _parseSlots(raw):
    slots = {}
    try:
        for cam, d in raw.items():
            try:
                slots[str(cam)] = dict((str(k), [float(x) for x in v]) for k, v in d.items() if len(v) == 3)
            except Exception:
                continue
    except Exception:
        pass
    return slots


def _slotsToJson(slots):
    out = _OD()
    for cam in sorted(slots):
        out[cam] = _OD([(k, [round(x, 4) + 0.0 for x in slots[cam][k]]) for k in sorted(slots[cam])])
    return out


def _createConfig():
    data = _clone(DEFAULTS)
    try:
        with open(_OLD_SLOTS_FILE) as f:        # one-time import of positions saved by the older mod
            data['saved_positions'] = _slotsToJson(_parseSlots(json.load(f)))
    except Exception:
        pass
    _writeFile(data)


def _reloadConfig():
    _state['cfgMtime'] = _mtime()
    data, status = _readFile()
    if status == 'missing':
        _createConfig()
        data, status = _readFile()
    if status != 'ok':
        return
    _applySettings(data.get('settings', {}))
    _state['slots'] = _parseSlots(data.get('saved_positions', {}))


def _pollConfig(dt):
    _state['cfgT'] += dt
    if _state['cfgT'] < 1.0:
        return
    _state['cfgT'] = 0.0
    if _mtime() != _state['cfgMtime']:
        _reloadConfig()


def _writeSlots():
    data, status = _readFile()
    if status == 'bad':                          # never overwrite a file the user is mid-edit on
        _logError('saved position kept in memory only (fix the JSON, then save it again)')
        return
    if status == 'missing':
        data = _clone(DEFAULTS)
    data['saved_positions'] = _slotsToJson(_state['slots'])
    _writeFile(data)


# ---------------- helpers ----------------

def _allowed(name):
    return name is not None and (ALLOWED_CAMS is None or name in ALLOWED_CAMS)


def _slotKey(name):
    return name if PER_CAMERA_OFFSET else 'all'


def _offset(name):
    return _state['offs'].setdefault(_slotKey(name), [0.0, 0.0, 0.0])


def _anyDown(keys):
    return any(BigWorld.isKeyDown(k) for k in keys)


def _edge(key, down):
    prev = _state['prev'].get(key, False)
    _state['prev'][key] = bool(down)
    return bool(down) and not prev


# ---------------- camera system access ----------------

def _camSystem():
    try:
        import CGF
        from helpers import dependency
        from skeletons.gui.shared.utils import IHangarSpace
        from cgf_components.hangar_camera_manager import HangarCameraSystem
        return CGF.getSystem(dependency.instance(IHangarSpace).spaceID, HangarCameraSystem)
    except Exception:
        return None


def _addToPivot(system, d):
    cam = system._HangarCameraSystem__cam
    params = system._HangarCameraSystem__mouseMoveParams
    cam.pivotPosition = cam.pivotPosition + d
    params.shiftPivotLows = params.shiftPivotLows + d


def _moveTo(system, off, target):
    import Math
    _addToPivot(system, Math.Vector3(target[0] - off[0], target[1] - off[1], target[2] - off[2]))
    off[0], off[1], off[2] = target[0], target[1], target[2]


def _patchedShift(self, shiftComponent):
    # runs on every camera switch/reset: re-apply our offset on top of the stock shift
    _origShift[0](self, shiftComponent)
    _state['zd'] = None
    try:
        name = self.getCurrentCameraName()
        if _allowed(name):
            import Math
            _addToPivot(self, Math.Vector3(*_offset(name)))
    except Exception:
        _debug('patchedShift')


def _patchedMouse(self, event):
    # swallow the wheel step here and feed it back gradually from _tick
    try:
        if ZOOM_SMOOTH and not _state['injecting']:
            ctx = event.ctx
            dz = ctx.get('dz', 0.0)
            if dz:
                try:
                    _state['sens'] = self._HangarCameraSystem__mouseMoveParams.zoomSensitivity or _state['sens']
                except Exception:
                    pass
                ctx['dz'] = 0.0
                cap = ZOOM_QUEUE_MAX / _state['sens']
                _state['zpend'] = max(-cap, min(cap, _state['zpend'] + dz))
    except Exception:
        _debug('patchedMouse')
    return _origMouse[0](self, event)


def _patchedMove(self, *args, **kwargs):
    # camera was moved by the game (customization, reset...): forget our tracked distance
    result = _origMove[0](self, *args, **kwargs)
    _state['zd'] = None
    return result


# ---------------- saved slots ----------------

def _saveSlot(name, n, off):
    _state['slots'].setdefault(_slotKey(name), {})[str(n)] = [off[0], off[1], off[2]]
    _writeSlots()


def _recallSlot(system, name, off, n):
    v = _state['slots'].get(_slotKey(name), {}).get(str(n))
    if v is None:
        return
    if RECALL_TIME <= 0.0:
        _state['glide'] = None
        _moveTo(system, off, v)
    else:
        _state['glide'] = {'name': name, 'from': list(off), 'to': list(v), 't': 0.0}


def _glideStep(system, name, off, dt):
    g = _state['glide']
    if g is None:
        return
    if g['name'] != name:
        _state['glide'] = None
        return
    g['t'] += dt
    k = min(1.0, g['t'] / RECALL_TIME)
    e = k * k * (3.0 - 2.0 * k)
    f, to = g['from'], g['to']
    _moveTo(system, off, [f[i] + (to[i] - f[i]) * e for i in range(3)])
    if k >= 1.0:
        _state['glide'] = None


# ---------------- pivot keys ----------------

def _pivotKeys(dt):
    shift = _anyDown(_SHIFT_KEYS)
    ctrl = _anyDown(_CTRL_KEYS)
    reset = _edge('reset', shift and PIVOT_RESET_KEY is not None and BigWorld.isKeyDown(PIVOT_RESET_KEY))
    slot = None
    for n, key in SLOT_KEYS:
        if _edge(('slot', n), shift and BigWorld.isKeyDown(key)):
            slot = n
    if not (shift or _state['glide']):
        return
    system = _camSystem()
    if system is None:
        return
    name = system.getCurrentCameraName()
    if DEBUG and name != _state['lastCam']:
        _state['lastCam'] = name
        _debug('camera is now %r' % (name,))
    if not _allowed(name):
        return
    off = _offset(name)
    if reset:
        _state['glide'] = None
        _moveTo(system, off, (0.0, 0.0, 0.0))
        return
    if slot is not None:
        if ctrl:
            _saveSlot(name, slot, off)
        else:
            _recallSlot(system, name, off, slot)
    _glideStep(system, name, off, dt)
    if shift and dt > 0.0:
        d = [0.0, 0.0, 0.0]
        for key, axis in PIVOT_KEYS:
            if key is not None and BigWorld.isKeyDown(key):
                for i in range(3):
                    d[i] += axis[i] * PIVOT_SPEED * dt
        if d[0] or d[1] or d[2]:
            import Math
            _state['glide'] = None
            _addToPivot(system, Math.Vector3(*d))
            for i in range(3):
                off[i] += d[i]


# ---------------- GUI hide ----------------

def _lobbyApp():
    try:
        from gui.shared.personality import ServicesLocator
        return ServicesLocator.appLoader.getDefLobbyApp()
    except Exception:
        pass
    try:
        from helpers import dependency
        from skeletons.gui.app_loader import IAppLoader
        return dependency.instance(IAppLoader).getDefLobbyApp()
    except Exception:
        return None


def _applyGui():
    want = not (_state['manualHide'] or _state['autoHide'])
    app = _lobbyApp()
    if app is not None:
        try:
            app.component.visible = want
        except Exception:
            pass


def _keyToggle():
    if HIDE_GUI_KEY is None:
        return
    pressed = BigWorld.isKeyDown(HIDE_GUI_KEY)
    if pressed and not _state['keyPrev']:
        _state['manualHide'] = not _state['manualHide']
        _applyGui()
    _state['keyPrev'] = pressed


def _setAuto(hidden):
    if AUTO_HIDE_GUI and _state['autoHide'] != hidden:
        _state['autoHide'] = hidden
        _applyGui()


# ---------------- spin ----------------

def _onMove(event):
    if _state['injecting']:
        return
    _state['cls'] = type(event)
    _state['type'] = event.eventType
    dx = event.ctx.get('dx', 0.0)
    if not dx and not event.ctx.get('dy', 0.0):
        return                       # wheel-only event: not part of a drag
    now = time.time()
    _samples.append((now, dx))
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


def _decay(dt):
    if not DECAY:
        return True
    _state['spin'] *= max(0.0, 1.0 - DECAY * dt)
    if abs(_state['spin']) < MIN_SPEED * 0.25:
        _state['spin'] = 0.0
        return False
    return True


def _spinStep(now, dt):
    """Returns the dx to inject this frame."""
    if _down():
        _state['spin'] = 0.0
        _setAuto(False)
        return 0.0
    if _samples and now - _samples[-1][0] > 0.02:
        speed = _peakSpeed()
        del _samples[:]
        if abs(speed) >= MIN_SPEED:
            sign = 1.0 if speed > 0 else -1.0
            mag = FIXED_SPEED if FIXED_SPEED else min(abs(speed), MAX_SPEED)
            _state['spin'] = sign * mag
            _setAuto(True)
    if _state['spin'] == 0.0 or dt <= 0.0 or _state['cls'] is None:
        _setAuto(False)
        return 0.0
    if not _decay(dt):
        _setAuto(False)
        return 0.0
    return _state['spin'] * dt


# ---------------- smooth zoom ----------------

def _zoomStep(dt):
    """Returns the dz to apply this frame (trapezoidal speed profile, constant cruise speed)."""
    p = _state['zpend']
    if not p:
        _state['zv'] = 0.0
        return 0.0
    if dt <= 0.0:
        return 0.0
    if _camSystem() is None:         # left the hangar: drop the queue
        _state['zpend'] = 0.0
        _state['zv'] = 0.0
        _state['zd'] = None
        return 0.0
    d = 1.0 if p > 0 else -1.0
    if d != _state['zdir']:          # scrolled the other way: restart from rest
        _state['zv'] = 0.0
        _state['zdir'] = d
    sens = _state['sens']
    vmax = ZOOM_SPEED / sens         # in dz units per second
    a = vmax / max(ZOOM_RAMP, 0.02)
    rem = abs(p)
    vt = min(vmax, (2.0 * a * rem) ** 0.5)   # fastest speed that can still stop in time
    v = min(vt, _state['zv'] + a * dt)
    step = v * dt
    if step >= rem or rem - step < 0.001 / sens:
        step = rem
        _state['zv'] = 0.0
        _state['zpend'] = 0.0
    else:
        _state['zv'] = v
        _state['zpend'] = p - d * step
    return d * step


def _camSettled():
    try:
        cam = _camSystem()._HangarCameraSystem__cam
        return abs(cam.pivotMaxDist - cam.targetMaxDist) < 0.02
    except Exception:
        return True


def _applyZoom(dz):
    """Apply a zoom step directly, replicating the stock handler's zoom block but accumulating
    on our own commanded distance, so zooming in and out behave identically."""
    system = _camSystem()
    if system is None:
        return
    cam = system._HangarCameraSystem__cam
    p = system._HangarCameraSystem__mouseMoveParams
    if system.isCameraSwitching() or cam.isInTransition() or not system._HangarCameraSystem__zoomEnabled:
        return
    zd = _state['zd']
    if zd is None:                   # first step after idle: same starting point as the stock handler
        zd = cam.targetMaxDist if dz > 0.0 else cam.pivotMaxDist
    # NOTE: never read the distance back from the camera mid-scroll: it may report the eased (lagging)
    # value, which would make one zoom direction restart from the lag every frame.
    lo, hi = p.distConstraints[0], p.distConstraints[1]
    zd = max(lo, min(hi, zd - dz * p.zoomSensitivity))
    if p.distLength > 0.0:
        pivotPos = p.shiftPivotDistances * ((zd - lo) / p.distLength)
    else:
        import Math
        pivotPos = Math.Vector3(0.0, 0.0, 0.0)
    if not system._HangarCameraSystem__vehicleToCameraCompIsActive:
        cam.pivotPosition = pivotPos + p.shiftPivotLows
    cam.pivotMaxDist = zd
    _state['zd'] = zd


def _inject(dx, dz):
    if _state['cls'] is None:
        return
    from gui.shared import g_eventBus
    _state['injecting'] = True
    try:
        ctx = {'dx': dx, 'dy': 0.0, 'dz': dz}
        g_eventBus.handleEvent(_state['cls'](_state['type'], ctx=ctx))
    finally:
        _state['injecting'] = False


# ---------------- main loop ----------------

def _tick():
    BigWorld.callback(0.0, _tick)
    now = time.time()
    last = _state['lastT']
    dt = 0.0 if last is None else min(now - last, 0.1)
    _state['lastT'] = now
    try:
        _pollConfig(dt)
    except Exception:
        _debug('pollConfig')
    try:
        _keyToggle()
    except Exception:
        _debug('keyToggle')
    try:
        _pivotKeys(dt)
    except Exception:
        _debug('pivotKeys')
    dx = dz = 0.0
    try:
        dx = _spinStep(now, dt)
    except Exception:
        _state['spin'] = 0.0
        _debug('spin')
    try:
        dz = _zoomStep(dt)
        if dz:
            _applyZoom(dz)
        if _state['zpend']:
            _state['zidle'] = 0.0
        elif _state['zd'] is not None:       # keep our commanded distance briefly after a scroll
            _state['zidle'] += dt            # so a follow-up scroll doesn't snap back to the lagging camera
            if _state['zidle'] > _ZOOM_RESYNC and (_camSettled() or _state['zidle'] > _ZOOM_RESYNC_MAX):
                _state['zd'] = None
    except Exception:
        _state['zpend'] = 0.0
        _state['zv'] = 0.0
        _state['zd'] = None
        _debug('zoom')
    if dx:
        try:
            _inject(dx, 0.0)
        except Exception:
            _state['spin'] = 0.0
            _debug('inject')


def init():
    try:
        from gui.shared import g_eventBus
        from gui.hangar_cameras.hangar_camera_common import CameraRelatedEvents
        from cgf_components.hangar_camera_manager import HangarCameraSystem
        _reloadConfig()
        g_eventBus.addListener(CameraRelatedEvents.LOBBY_VIEW_MOUSE_MOVE, _onMove)
        if _origShift[0] is None:
            name = '_HangarCameraSystem__setCameraShift'
            _origShift[0] = getattr(HangarCameraSystem, name)
            setattr(HangarCameraSystem, name, _patchedShift)
        if _origMove[0] is None:
            _origMove[0] = getattr(HangarCameraSystem, 'moveCamera')
            setattr(HangarCameraSystem, 'moveCamera', _patchedMove)
        if _origMouse[0] is None:
            name = '_HangarCameraSystem__handleLobbyViewMouseEvent'
            _origMouse[0] = getattr(HangarCameraSystem, name)
            setattr(HangarCameraSystem, name, _patchedMouse)
        BigWorld.callback(0.0, _tick)
    except Exception:
        _debug('init')