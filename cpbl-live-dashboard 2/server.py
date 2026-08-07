#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os, re, time, sys, tempfile
import requests

VENDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'vendor')
if os.path.isdir(VENDOR) and VENDOR not in sys.path:
    sys.path.insert(0, VENDOR)

ROOT = os.path.dirname(os.path.abspath(__file__))
REMINDERS_PATH = os.path.join(ROOT, 'reminders.json')
CPBL = 'https://www.cpbl.com.tw'
UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X) CPBL-Live-Dashboard/0.2'


def cpbl_session():
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept-Language': 'zh-TW,zh;q=0.9'})
    html = s.get(CPBL + '/', timeout=12).text
    m = re.search(r'name="__RequestVerificationToken"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="__RequestVerificationToken"', html)
    if not m:
        raise RuntimeError('找不到 CPBL 驗證 token，網站格式可能改了')
    token = next(g for g in m.groups() if g)
    return s, token


def post_cpbl(path, payload):
    s, token = cpbl_session()
    data = {'__RequestVerificationToken': token, **payload}
    r = s.post(CPBL + path, data=data, headers={
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': CPBL + '/',
    }, timeout=12)
    r.raise_for_status()
    return r.json()


def post_cpbl_live(year, kind_code, game_sno):
    s = requests.Session()
    s.headers.update({'User-Agent': UA, 'Accept-Language': 'zh-TW,zh;q=0.9'})
    referer = f'{CPBL}/box/live?year={year}&kindCode={kind_code}&gameSno={game_sno}'
    html = s.get(referer, timeout=12).text
    payload = {}
    for name in ['__RequestVerificationToken', 'GameSno', 'KindCode', 'Year', 'PrevOrNext']:
        m = re.search(r'name="%s"[^>]*value="([^"]*)"|value="([^"]*)"[^>]*name="%s"' % (re.escape(name), re.escape(name)), html)
        if m:
            payload[name] = next(g for g in m.groups() if g is not None)
    payload.update({'GameSno': str(game_sno), 'KindCode': str(kind_code), 'Year': str(year)})
    payload.setdefault('PrevOrNext', '0')
    r = s.post(CPBL + '/box/getlive', data=payload, headers={
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': referer,
    }, timeout=12)
    r.raise_for_status()
    return r.json()


def strip_html(html):
    if not html:
        return ''
    text = re.sub(r'<br\s*/?>', '\n', html)
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\n{2,}', '\n', text).strip()


def inning_text(seq, side, status_code):
    if status_code == 1:
        return '尚未開賽'
    if not seq:
        return '—'
    side_text = {'V': '▲', 'H': '▼', '1': '▲', '2': '▼', '客': '▲', '主': '▼'}.get(str(side), '')
    return f"{seq}局 {side_text}" if side_text else f"第{seq}局"


def pause_reason_from(*parts):
    txt = ' '.join(str(p or '') for p in parts)
    if re.search(r'更換投手|投手更換|換投|換上投手|投手交代|投手丘.*換', txt):
        return '更換投手暫停'
    if re.search(r'教練.*暫停|暫停.*教練|教練喊停|教練上投手丘|投手教練', txt):
        return '教練暫停'
    if not re.search(r'暫停|中斷|保留|裁定|延賽', txt):
        return ''
    if re.search(r'因雨|雨勢|天候因素|天候|雷雨', txt):
        return '天候暫停'
    if '保留' in txt:
        return '保留比賽'
    if '裁定' in txt:
        return '裁定比賽'
    if '因故' in txt:
        return '因故暫停'
    if '中斷' in txt:
        return '比賽中斷'
    if '暫停' in txt:
        return '暫停原因確認中'
    return ''


def batting_state(g):
    cb = g.get('CurtBatting') or {}
    if isinstance(cb, list):
        cb = cb[0] if cb else {}
    return batting_state_from_log(cb)


def batting_state_from_log(cb):
    cb = cb or {}
    return {
        'balls': int(cb.get('BallCnt') or 0),
        'strikes': int(cb.get('StrikeCnt') or 0),
        'outs': int(cb.get('OutCnt') or 0),
        'bases': {
            'first': bool(cb.get('FirstBase')),
            'second': bool(cb.get('SecondBase')),
            'third': bool(cb.get('ThirdBase')),
        },
        'baseNames': {
            'first': cb.get('FirstBase') or '',
            'second': cb.get('SecondBase') or '',
            'third': cb.get('ThirdBase') or '',
        },
        'pitcher': cb.get('PitcherName') or '',
        'hitter': cb.get('HitterName') or ''
    }


TEAM_COLORS = {
    'AAA011': '#c8102e',  # 味全龍
    'AEO011': '#004b9b',  # 富邦悍將
    'AKP011': '#0b5f4a',  # 台鋼雄鷹
    'ADD011': '#f97316',  # 統一7-ELEVEn獅
    'AJL011': '#8a1538',  # 樂天桃猿 酒紅
    'ACN011': '#facc15',  # 中信兄弟
}

FIELD_NAMES = {
    'F01': '台北大巨蛋',
    'F02': '新莊',
    'F03': '桃園',
    'F04': '台中洲際',
    'F05': '台南',
    'F06': '澄清湖',
    'F07': '嘉義市',
    'F08': '斗六',
    'F09': '亞太主',
    'F10': '花蓮',
    'F11': '天母',
}


def field_name(value):
    if not value:
        return ''
    return FIELD_NAMES.get(str(value), str(value))


def team_color(code, name=''):
    code = str(code or '')
    if code in TEAM_COLORS:
        return TEAM_COLORS[code]
    # 二軍/農場隊常用同一隊前三碼、不同尾碼（例如 ACN022），顏色沿用一軍 ACN011。
    if len(code) >= 3:
        parent_code = code[:3] + '011'
        if parent_code in TEAM_COLORS:
            return TEAM_COLORS[parent_code]
    name = str(name or '')
    name_map = {
        '味全': TEAM_COLORS['AAA011'],
        '富邦': TEAM_COLORS['AEO011'],
        '台鋼': TEAM_COLORS['AKP011'],
        '統一': TEAM_COLORS['ADD011'],
        '樂天': TEAM_COLORS['AJL011'],
        '桃猿': TEAM_COLORS['AJL011'],
        '兄弟': TEAM_COLORS['ACN011'],
        '中信': TEAM_COLORS['ACN011'],
    }
    for key, color in name_map.items():
        if key in name:
            return color
    return '#9fc3ff'


def asset_url(path):
    if not path:
        return ''
    if str(path).startswith('http'):
        return path
    return CPBL + str(path)


def normalize_game(g):
    status_map = {1: '未開賽', 2: '比賽中', 3: '已結束', 4: '先發打序', 8: '比賽暫停'}
    status_code = g.get('GameStatus')
    seq = g.get('CurtSeq') or ''
    side = g.get('CurtVisitingHomeType') or ''
    state = batting_state(g)
    return {
        'id': f"{g.get('Year')}-{g.get('KindCode')}-{g.get('GameSno')}",
        'year': g.get('Year'), 'kindCode': g.get('KindCode'), 'gameSno': g.get('GameSno'),
        'field': field_name(g.get('FieldAbbe') or g.get('FieldNo') or ''),
        'fieldCode': g.get('FieldNo') or g.get('FieldAbbe') or '',
        'date': g.get('GameDate') or '', 'time': g.get('GameDateTimeS') or '',
        'statusCode': g.get('GameStatus'), 'status': g.get('GameStatusChi') or status_map.get(g.get('GameStatus'), '未知'),
        'away': g.get('VisitingTeamName'), 'home': g.get('HomeTeamName'),
        'awayCode': g.get('VisitingTeamCode'), 'homeCode': g.get('HomeTeamCode'),
        'awayColor': team_color(g.get('VisitingTeamCode'), g.get('VisitingTeamName')), 'homeColor': team_color(g.get('HomeTeamCode'), g.get('HomeTeamName')),
        'awayLogo': asset_url(g.get('VisitingClubBigImgPath') or g.get('VisitingClubSmallImgPath')),
        'homeLogo': asset_url(g.get('HomeClubBigImgPath') or g.get('HomeClubSmallImgPath')),
        'awayScore': g.get('VisitingTotalScore') if g.get('VisitingTotalScore') is not None else g.get('VisitingScore'),
        'homeScore': g.get('HomeTotalScore') if g.get('HomeTotalScore') is not None else g.get('HomeScore'),
        'awayStarter': g.get('VisitingFirstMover') or '', 'homeStarter': g.get('HomeFirstMover') or '',
        'inning': seq, 'battingSide': side, 'inningText': inning_text(seq, side, status_code),
        'pitcher': g.get('PitcherName') or state.get('pitcher') or '', 'hitter': g.get('HitterName') or state.get('hitter') or '',
        **state,
        'briefing': strip_html(g.get('Briefing') or ''),
        'weather': g.get('WeatherDesc') or g.get('Weather') or '',
        'pauseReason': '' if g.get('GameStatus') == 3 else pause_reason_from(g.get('GameStatusChi'), g.get('Briefing'), g.get('GameResult')),
        'audienceCnt': g.get('AudienceCnt') or g.get('AudienceCntBackend') or 0,
        'winningPitcher': g.get('WinningPitcherName') or '',
        'losingPitcher': g.get('LosePitcherName') or '',
        'savePitcher': g.get('CloserPitcherName') or '',
        'mvp': g.get('MvpName') or g.get('MvpEnName') or '',
        'liveUrl': g.get('LiveUrl') or '', 'vodUrl': g.get('VodUrl') or '',
    }


def fetch_games(game_date='', first_team_only=False):
    data = post_cpbl('/home/getdetaillist', {'GameSno': '', 'KindCode': '', 'GameDate': game_date})
    games = []
    for key in ['GameADetailJson', 'GameDDetailJson', 'GameDetailJson']:
        raw = data.get(key)
        if raw:
            try:
                games.extend(json.loads(raw))
            except Exception:
                pass
    seen, out = set(), []
    for g in games:
        if first_team_only and g.get('KindCode') != 'A':
            continue
        k = (g.get('Year'), g.get('KindCode'), g.get('GameSno'))
        if k not in seen:
            seen.add(k); out.append(normalize_game(g))
    return {'ok': True, 'updatedAt': time.strftime('%Y-%m-%d %H:%M:%S'), 'source': CPBL, 'games': out}


def load_reminders():
    if not os.path.exists(REMINDERS_PATH):
        return []
    try:
        with open(REMINDERS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def save_reminders(items):
    with open(REMINDERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_reminder(item):
    items = load_reminders()
    item['id'] = f"r{int(time.time()*1000)}"
    item.setdefault('sent', False)
    item.setdefault('createdAt', time.strftime('%Y-%m-%d %H:%M:%S'))
    items.append(item)
    save_reminders(items)
    return item


def delete_reminder(rid):
    items = [x for x in load_reminders() if x.get('id') != rid]
    save_reminders(items)
    return items


def mark_reminder_sent(rid):
    items = load_reminders()
    for item in items:
        if item.get('id') == rid:
            item['sent'] = True
            item['sentAt'] = time.strftime('%Y-%m-%d %H:%M:%S')
    save_reminders(items)
    return items


def expand_date_label(line):
    # 2026-7-24~26 / 2026/7/24-26
    m = re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\s*[~～-]\s*(\d{1,2})(?!\d)', line)
    if m:
        y, mo, d1, d2 = map(int, m.groups())
        if d2 >= d1 and d2 - d1 <= 10:
            return [f'{y:04d}-{mo:02d}-{d:02d}' for d in range(d1, d2 + 1)]
    # 7/24~7/26 or 7/24-26
    m = re.search(r'(?<!\d)(\d{1,2})/(\d{1,2})\s*[~～-]\s*(?:(\d{1,2})/)?(\d{1,2})(?!\d)', line)
    if m:
        mo1, d1, mo2, d2 = m.groups()
        mo1, d1, d2 = int(mo1), int(d1), int(d2)
        mo2 = int(mo2) if mo2 else mo1
        if mo1 == mo2 and d2 >= d1 and d2 - d1 <= 10:
            return [f'{mo1:02d}/{d:02d}' for d in range(d1, d2 + 1)]
    # single date
    m = re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})|(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)|(?<!\d)(\d{1,2})月(\d{1,2})日', line)
    if m:
        if m.group(1): return [f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}']
        if m.group(4): return [f'{int(m.group(4)):02d}/{int(m.group(5)):02d}']
        if m.group(6): return [f'{int(m.group(6)):02d}/{int(m.group(7)):02d}']
    return []


def parse_workflow_text(text):
    items = []
    time_re = re.compile(r'(?<![\d-])(\d{1,2})[:：]?(\d{2})(?:\s*[~～]\s*(\d{1,2})[:：]?(\d{2}))?\s*(.*)')
    current_dates = []
    for raw in (text or '').splitlines():
        line = re.sub(r'\s+', ' ', raw).strip()
        if not line:
            continue
        found_dates = expand_date_label(line)
        if found_dates:
            current_dates = found_dates
            # 日期標題本身不是流程，但同一行可能也有時間，所以不立刻 continue
        if re.match(r'^20\d{2}[-/]', line) and not time_re.search(line):
            continue
        m = time_re.search(line)
        if not m:
            continue
        hour, minute, end_hour, end_minute, rest = m.groups()
        hour_i, minute_i = int(hour), int(minute)
        if hour_i > 29 or minute_i > 59:
            continue
        time_text = f'{hour_i:02d}:{minute_i:02d}'
        if end_hour and end_minute and int(end_hour) <= 29 and int(end_minute) <= 59:
            time_text += f'~{int(end_hour):02d}:{int(end_minute):02d}'
        task = rest.strip(' -–—,，&\t') or line
        dates = current_dates or ['未分類']
        # 若 PDF 只抽成一行日期範圍，無法知道每個欄位屬於哪天；先複製到範圍內每一天，避免選日期時漏掉。
        for date_label in dates:
            items.append({'date': date_label, 'time': time_text, 'task': task})
    # 去重
    seen, out = set(), []
    for item in items:
        key = (item.get('date'), item['time'], item['task'])
        if key not in seen:
            seen.add(key); out.append(item)
    return out


def extract_pdf_text(pdf_bytes):
    try:
        from pypdf import PdfReader
    except Exception as e:
        raise RuntimeError(f'PDF 解析套件不可用：{e}')
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as f:
        f.write(pdf_bytes)
        path = f.name
    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or '')
        text = '\n'.join(parts).strip()
        if not text:
            raise RuntimeError('PDF 沒有抽到文字，可能是掃描圖片版，需要 OCR')
        return text
    finally:
        try: os.unlink(path)
        except Exception: pass


def parse_multipart(body, content_type):
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', content_type or '')
    if not m:
        raise RuntimeError('缺少 multipart boundary')
    boundary = ('--' + (m.group(1) or m.group(2))).encode()
    for part in body.split(boundary):
        if b'\r\n\r\n' not in part:
            continue
        head, data = part.split(b'\r\n\r\n', 1)
        if b'name="file"' in head:
            return data.rstrip(b'\r\n-')
    raise RuntimeError('找不到上傳檔案')


def fetch_game_detail(year, kind_code, game_sno, status):
    data = post_cpbl('/home/gamedetail', {
        'GameSno': str(game_sno), 'Year': str(year), 'KindCode': str(kind_code), 'GameStatus': str(status or '')
    })
    raw = data.get('CurtGameDetailJson')
    d = json.loads(raw) if raw else {}
    base = normalize_game(d)
    live_logs = []
    live_detail = {}
    try:
        live = post_cpbl_live(year, kind_code, game_sno)
        live_logs = json.loads(live.get('LiveLogJson') or '[]')
        live_detail = json.loads(live.get('CurtGameDetailJson') or '{}')
    except Exception:
        live_logs = []
        live_detail = {}
    batting_rows = []
    pitching_rows = []
    try:
        batting_rows = json.loads(live.get('BattingJson') or '[]') if 'live' in locals() else []
        pitching_rows = json.loads(live.get('PitchingJson') or '[]') if 'live' in locals() else []
    except Exception:
        batting_rows, pitching_rows = [], []
    def player_name_by_acnt(acnt):
        if not acnt:
            return ''
        for row in batting_rows:
            if row.get('HitterAcnt') == acnt:
                return row.get('HitterName') or ''
        for row in pitching_rows:
            if row.get('PitcherAcnt') == acnt:
                return row.get('PitcherName') or ''
        return ''
    recent_logs = []
    for log in live_logs[-6:]:
        content = strip_html(log.get('Content') or '')
        if content:
            side = '上' if str(log.get('VisitingHomeType')) == '1' else '下' if str(log.get('VisitingHomeType')) == '2' else ''
            recent_logs.append({
                'inning': f"{log.get('InningSeq')}局 {'▲' if side == '上' else '▼'}" if log.get('InningSeq') and side else f"第{log.get('InningSeq')}局" if log.get('InningSeq') else '',
                'text': content,
                'hitter': log.get('HitterName') or '',
                'pitcher': log.get('PitcherName') or '',
            })
    scoring_plays = []
    prev_away = prev_home = None
    for log in live_logs:
        away_score = log.get('VisitingScore')
        home_score = log.get('HomeScore')
        try:
            away_score = int(away_score) if away_score is not None else None
            home_score = int(home_score) if home_score is not None else None
        except Exception:
            continue
        if away_score is None or home_score is None:
            continue
        if prev_away is None or prev_home is None:
            prev_away, prev_home = away_score, home_score
            continue
        away_runs = max(0, away_score - prev_away)
        home_runs = max(0, home_score - prev_home)
        if away_runs or home_runs:
            side = '上' if str(log.get('VisitingHomeType')) == '1' else '下' if str(log.get('VisitingHomeType')) == '2' else ''
            scoring_plays.append({
                'inning': f"{log.get('InningSeq')}局 {'▲' if side == '上' else '▼'}" if log.get('InningSeq') and side else f"第{log.get('InningSeq')}局" if log.get('InningSeq') else '',
                'teamSide': 'away' if away_runs else 'home',
                'runs': away_runs or home_runs,
                'hitter': log.get('HitterName') or '',
                'text': strip_html(log.get('Content') or ''),
                'awayScore': away_score,
                'homeScore': home_score,
            })
        prev_away, prev_home = away_score, home_score
    latest = live_logs[-1] if live_logs else {}
    latest_text = strip_html(latest.get('Content') or '')
    latest_log_time = latest.get('UpdateTime') or latest.get('CreateTime') or ''
    current_hitter_stats = {}
    latest_hitter_acnt = latest.get('HitterAcnt') if latest else ''
    for row in batting_rows:
        if latest_hitter_acnt and row.get('HitterAcnt') == latest_hitter_acnt:
            current_hitter_stats = {
                'pa': row.get('PlateAppearances') or 0,
                'ab': row.get('HittingCnt') or 0,
                'h': row.get('HitCnt') or 0,
                'rbi': row.get('RunBattedINCnt') or 0,
                'r': row.get('ScoreCnt') or 0,
                'hr': row.get('HomeRunCnt') or 0,
                'bb': row.get('BasesONBallsCnt') or 0,
                'so': row.get('StrikeOutCnt') or 0,
            }
            break
    if latest:
        live_state = batting_state_from_log(latest)
        base.update(live_state)
        latest_away_score = latest.get('VisitingScore')
        latest_home_score = latest.get('HomeScore')
        base.update({
            'pitcher': latest.get('PitcherName') or live_detail.get('PitcherName') or d.get('PitcherName') or base.get('pitcher') or '',
            'hitter': latest.get('HitterName') or live_detail.get('HitterName') or d.get('HitterName') or base.get('hitter') or '',
            'inning': latest.get('InningSeq') or base.get('inning'),
            'battingSide': latest.get('VisitingHomeType') or base.get('battingSide'),
            'inningText': inning_text(latest.get('InningSeq'), latest.get('VisitingHomeType'), base.get('statusCode')),
            'pitchCnt': latest.get('PitchCnt') or base.get('pitchCnt') or '',
            'latestLogTime': latest_log_time,
            'pauseReason': '' if int(live_detail.get('GameStatus') or base.get('statusCode') or 0) == 3 else (pause_reason_from(live_detail.get('GameStatusChi'), latest_text, live_detail.get('Briefing'), live_detail.get('GameResult')) or base.get('pauseReason') or ''),
            'awayScore': latest_away_score if latest_away_score is not None else base.get('awayScore'),
            'homeScore': latest_home_score if latest_home_score is not None else base.get('homeScore'),
        })
    base.update({
        'scoreboard': {
            'away': d.get('VisitingScoreboards') or [],
            'home': d.get('HomeScoreboards') or [],
        },
        'liveText': latest_text,
        'recentLiveTexts': recent_logs,
        'scoringPlays': scoring_plays[-4:],
        'currentBatting': d.get('CurtBatting') or [],
        'currentHitters': d.get('CurtHitterBattings') or [],
        'currentHitterStats': current_hitter_stats,
        'awayPitchers': d.get('VisitingPitcherData') or [],
        'homePitchers': d.get('HomePitcherData') or [],
        'winningPitcher': live_detail.get('WinningPitcherName') or d.get('WinningPitcherName') or base.get('winningPitcher') or '',
        'losingPitcher': live_detail.get('LosePitcherName') or d.get('LosePitcherName') or base.get('losingPitcher') or '',
        'savePitcher': live_detail.get('CloserPitcherName') or d.get('CloserPitcherName') or base.get('savePitcher') or '',
        'mvp': player_name_by_acnt(live_detail.get('MvpAcnt') or d.get('MvpAcnt')) or live_detail.get('MvpName') or d.get('MvpName') or live_detail.get('MvpEnName') or d.get('MvpEnName') or base.get('mvp') or '',
        'awayStarterReport': strip_html(d.get('VisitingStatersPitcherHtml') or ''),
        'homeStarterReport': strip_html(d.get('HomeStatersPitcherHtml') or ''),
        'awayTeamReport': strip_html(d.get('VisitingStartersHtml') or ''),
        'homeTeamReport': strip_html(d.get('HomeStartersHtml') or ''),
    })
    return {'ok': True, 'updatedAt': time.strftime('%Y-%m-%d %H:%M:%S'), 'source': CPBL, 'game': base}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def json_response(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        try:
            if parsed.path == '/api/games':
                self.json_response(fetch_games(qs.get('date', [''])[0], qs.get('first', ['1'])[0] != '0'))
                return
            if parsed.path == '/api/game':
                self.json_response(fetch_game_detail(qs['year'][0], qs['kindCode'][0], qs['gameSno'][0], qs.get('status', [''])[0]))
                return
            if parsed.path == '/api/reminders':
                self.json_response({'ok': True, 'reminders': load_reminders()})
                return
        except Exception as e:
            self.json_response({'ok': False, 'error': str(e)}, 502)
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get('Content-Length') or '0')
            raw_body = self.rfile.read(length) if length else b'{}'
            if parsed.path == '/api/workflow/pdf':
                pdf_bytes = parse_multipart(raw_body, self.headers.get('Content-Type'))
                text = extract_pdf_text(pdf_bytes)
                items = parse_workflow_text(text)
                self.json_response({'ok': True, 'items': items, 'textPreview': text[:1200]})
                return
            body = raw_body.decode('utf-8')
            data = json.loads(body or '{}')
            if parsed.path == '/api/reminders':
                self.json_response({'ok': True, 'reminder': add_reminder(data)})
                return
            if parsed.path == '/api/reminders/delete':
                self.json_response({'ok': True, 'reminders': delete_reminder(data.get('id'))})
                return
            if parsed.path == '/api/reminders/sent':
                self.json_response({'ok': True, 'reminders': mark_reminder_sent(data.get('id'))})
                return
        except Exception as e:
            self.json_response({'ok': False, 'error': str(e)}, 502)
            return
        self.json_response({'ok': False, 'error': 'not found'}, 404)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '8787'))
    print(f'CPBL live dashboard: http://127.0.0.1:{port}')
    ThreadingHTTPServer(('127.0.0.1', port), Handler).serve_forever()
