"""Selective headless-browser rendering (Playwright) for JavaScript-built pages.

The normal crawler tries the light HTML method first. Only when a page looks like an empty JavaScript shell
(see looks_js) does it call render(). The browser is optional: if Playwright / Chromium is not installed,
available() is False and the source is simply recorded as "needs browser".

All browser work happens in ONE dedicated thread (Playwright's sync API is not thread-safe); crawl workers
submit requests to it and wait. A global time budget (RENDER_BUDGET_MIN) keeps the run short.
"""
import os, queue, re, threading, time
from bs4 import BeautifulSoup

UA = os.environ.get('CRAWLER_UA', 'ApplyLaunchBot/1.0 (academic opportunity search; respects robots.txt)')
MORE_RX = re.compile(r'^\s*(load more|show more|more results|view more|see more|more jobs|more positions|mehr (laden|anzeigen|ergebnisse)|weitere|voir plus|afficher plus|plus de résultats|cargar más|ver más|mostrar más|mostra altri|carica altri|toon meer|daha fazla|devamı|więcej)', re.I)
NEXT_RX = re.compile(r'^\s*(next|next page|›|»|>|weiter|nächste|suivant|siguiente|volgende|successiva|sonraki|następna)\s*(page|seite|›|»|>)?\s*$', re.I)
COOKIE_RX = re.compile(r'^\s*(accept( all)?( cookies)?|i agree|agree|allow all|got it|ok|alle akzeptieren|akzeptieren|accepter|aceptar|kabul et)\s*$', re.I)

_state = dict(ok=None, deadline=0.0, q=None, thread=None, rendered=0, failed=0, seconds=0.0)
_lock = threading.Lock()


def looks_js(html):
    """True if the HTML is (almost) an empty shell that a browser must fill in."""
    soup = BeautifulSoup(html or '', 'lxml')
    n_script = len(soup.find_all('script', src=True))
    nos = ' '.join(t.get_text(' ') for t in soup.find_all('noscript')).lower()
    for t in soup(['script', 'style', 'noscript']):
        t.decompose()
    txt = soup.get_text(' ', strip=True)
    marker = bool(re.search(r'id="(root|app|__next|__nuxt)"|__NEXT_DATA__|ng-app|data-reactroot|window\.__INITIAL_STATE__|<app-root', html or ''))
    needs = 'enable javascript' in nos or 'requires javascript' in nos or 'javascript is required' in nos or 'javascript to run' in nos
    return (len(txt) < 600 and (n_script >= 2 or marker)) or needs or (marker and len(txt) < 1500 and n_script >= 4)


def available():
    if _state['ok'] is None:
        try:
            import playwright.sync_api  # noqa: F401
            _state['ok'] = True
        except Exception:
            _state['ok'] = False
    return _state['ok']


def configure(budget_min):
    _state['deadline'] = time.time() + budget_min * 60


def stats():
    return dict(rendered=_state['rendered'], failed=_state['failed'], seconds=int(_state['seconds']), available=bool(_state['ok']))


def _worker(q):
    from playwright.sync_api import sync_playwright
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch()
    except Exception as e:
        _state['ok'] = False
        _state['err'] = str(e)[:120]
        while True:                                   # answer every waiting request with an error
            item = q.get()
            if item is None:
                return
            item[1]['err'] = 'browser unavailable'
            item[2].set()
    ctx = browser.new_context(user_agent=UA, viewport={'width': 1280, 'height': 1600}, java_script_enabled=True)
    ctx.route('**/*', lambda r: r.abort() if r.request.resource_type in ('image', 'media', 'font') else r.continue_())
    while True:
        item = q.get()
        if item is None:
            break
        url, out, ev, pages = item
        t0 = time.time()
        page = None
        try:
            page = ctx.new_page()
            page.set_default_timeout(15000)
            page.goto(url, wait_until='domcontentloaded', timeout=25000)
            try:
                page.wait_for_load_state('networkidle', timeout=10000)
            except Exception:
                pass
            _click(page, COOKIE_RX, ('button', 'a'), 1)
            snaps = []
            for i in range(max(1, pages)):
                for _ in range(3):                    # scroll: lazy loading
                    page.mouse.wheel(0, 4000)
                    page.wait_for_timeout(500)
                clicked = 0
                for _ in range(4):                    # "load more" buttons (content is appended)
                    if not _click(page, MORE_RX, ('button', 'a', '[role=button]'), 1):
                        break
                    clicked += 1
                    _settle(page)
                snaps.append(page.content())
                if i + 1 >= pages:
                    break
                if not (_click(page, NEXT_RX, ('a[rel=next]', 'a', 'button', '[aria-label*=ext]'), 1) or _click_sel(page, 'a[rel=next],[aria-label="Next"],[aria-label="Next page"],li.next a,a.next')):
                    break
                _settle(page)
            out['html'] = snaps
            out['final'] = page.url
            _state['rendered'] += 1
        except Exception as e:
            out['err'] = str(e)[:100]
            _state['failed'] += 1
        finally:
            try:
                if page:
                    page.close()
            except Exception:
                pass
            _state['seconds'] += time.time() - t0
            ev.set()
    try:
        browser.close()
        pw.stop()
    except Exception:
        pass


def _settle(page):
    try:
        page.wait_for_load_state('networkidle', timeout=6000)
    except Exception:
        pass
    page.wait_for_timeout(600)


def _click_sel(page, sel):
    try:
        el = page.query_selector(sel)
        if el and el.is_visible():
            el.click(timeout=3000)
            return True
    except Exception:
        pass
    return False


def _click(page, rx, selectors, limit):
    for sel in selectors:
        try:
            for el in page.query_selector_all(sel)[:300]:
                try:
                    t = (el.inner_text() or '').strip()
                    if t and len(t) < 40 and rx.match(t) and el.is_visible():
                        el.click(timeout=3000)
                        return True
                except Exception:
                    continue
        except Exception:
            continue
    return False


def render(url, pages=3, timeout=60):
    """Render a URL in the browser. Returns (list_of_html_snapshots, final_url). Raises RuntimeError when not possible."""
    if not available():
        raise RuntimeError('playwright not installed')
    if time.time() > _state['deadline']:
        raise RuntimeError('render budget used up')
    with _lock:
        if _state['thread'] is None:
            _state['q'] = queue.Queue()
            t = threading.Thread(target=_worker, args=(_state['q'],), daemon=True)
            t.start()
            _state['thread'] = t
    out, ev = {}, threading.Event()
    _state['q'].put((url, out, ev, pages))
    if not ev.wait(max(120.0, _state['deadline'] - time.time() + 90)):   # requests queue up behind each other
        raise RuntimeError('render timeout')
    if 'err' in out:
        raise RuntimeError(out['err'])
    return out['html'], out['final']
