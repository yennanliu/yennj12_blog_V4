// Main JavaScript for Uber Style theme
document.addEventListener('DOMContentLoaded', function() {
    // Every initialiser runs inside safeInit: they are independent, and one
    // throwing must not skip the rest. That matters most for initReveal,
    // which is what un-hides the scroll-reveal content.
    safeInit(initReveal);

    // Primary navigation (drawer + dropdowns)
    safeInit(initNav);

    // Search functionality
    safeInit(initSearch);

    // Smooth scrolling for anchor links
    safeInit(initSmoothScrolling);

    // Reading progress indicator
    safeInit(initReadingProgress);

    // Presentation layer (scroll state, spotlights, counters, back to top).
    // All of it is decoration: each initialiser is a no-op when its markup
    // hook is absent, and every one bails out under prefers-reduced-motion.
    safeInit(initHeaderScroll);
    safeInit(initSpotlight);
    safeInit(initCountUp);
    safeInit(initBackToTop);
});

// Runs one initialiser, keeping its failure to itself. Reported rather than
// swallowed, so a broken feature still shows up in the console.
function safeInit(fn) {
    try {
        fn();
    } catch (err) {
        if (window.console && console.error) {
            console.error('init failed: ' + fn.name, err);
        }
    }
}

// True when the visitor has asked the OS for less animation. Checked at call
// time rather than cached, so a mid-session change to the setting is honoured.
function prefersReducedMotion() {
    return window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

// Primary navigation — drawer toggle (below lg) plus the dropdown disclosures,
// which are shared by both layouts. CSS handles hover/focus opening on desktop;
// this only manages the explicit click/keyboard state so touch and keyboard
// users get the same panels.
const NAV_DESKTOP_QUERY = '(min-width: 1024px)';

function initNav() {
    const menu    = document.getElementById('primaryNav');
    const toggle  = document.getElementById('navToggle');
    const scrim   = document.getElementById('navScrim');
    const header  = document.getElementById('siteHeader');
    if (!menu) return;

    const dropdowns = Array.from(menu.querySelectorAll('[data-nav-dropdown]'));
    const isDesktop = () => window.matchMedia(NAV_DESKTOP_QUERY).matches;

    function closeDropdowns(except) {
        dropdowns.forEach(function (item) {
            if (item === except) return;
            item.classList.remove('nav__item--open');
            const caret = item.querySelector('.nav__caret');
            if (caret) caret.setAttribute('aria-expanded', 'false');
        });
    }

    function setDrawer(open) {
        if (!toggle) return;
        menu.classList.toggle('nav__menu--open', open);
        toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
        toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
        document.body.classList.toggle('nav-open', open);
        if (scrim) scrim.hidden = !open;
        if (!open) closeDropdowns(null);
    }

    const drawerOpen = () => menu.classList.contains('nav__menu--open');

    if (toggle) {
        toggle.addEventListener('click', function () {
            setDrawer(!drawerOpen());
        });
    }
    if (scrim) scrim.addEventListener('click', function () { setDrawer(false); });

    dropdowns.forEach(function (item) {
        const caret = item.querySelector('.nav__caret');
        if (!caret) return;
        caret.addEventListener('click', function (e) {
            e.stopPropagation();
            const willOpen = !item.classList.contains('nav__item--open');
            // On desktop the panels are mutually exclusive; in the drawer they
            // are accordion sections and may sit open side by side.
            if (isDesktop()) closeDropdowns(item);
            item.classList.toggle('nav__item--open', willOpen);
            caret.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        });
    });

    // Click outside closes whatever is open.
    document.addEventListener('click', function (e) {
        if (header && header.contains(e.target)) {
            if (!menu.contains(e.target)) closeDropdowns(null);
            return;
        }
        closeDropdowns(null);
        if (drawerOpen()) setDrawer(false);
    });

    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        const open = dropdowns.find(function (i) { return i.classList.contains('nav__item--open'); });
        if (open) {
            closeDropdowns(null);
            const caret = open.querySelector('.nav__caret');
            if (caret) caret.focus();
            return;
        }
        if (drawerOpen()) {
            setDrawer(false);
            if (toggle) toggle.focus();
        }
    });

    // Crossing into the desktop layout leaves the drawer classes stale.
    const mq = window.matchMedia(NAV_DESKTOP_QUERY);
    const onChange = function () { if (isDesktop()) setDrawer(false); };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange);
}

// Search functionality — header modal.
// Ranking, matching and index loading live in assets/js/search.js (BlogSearch).
function initSearch() {
    const searchToggle  = document.querySelector('.search__toggle');
    const searchOverlay = document.querySelector('.search__overlay');
    const searchClose   = document.querySelector('.search__close');
    const searchInput   = document.querySelector('.search__input');
    const searchResults = document.querySelector('.search__results');
    const searchFooter  = document.querySelector('.search__footer');
    const searchViewAll = document.querySelector('.search__view-all');

    if (!searchToggle || !searchOverlay || !window.BlogSearch) return;

    const MAX_RESULTS = 8;
    let index = null;
    let active = -1;      // keyboard-highlighted result
    let lastHits = [];

    // The index is a few hundred KB, so it is only fetched once the user
    // shows intent to search — not on every page load.
    function ensureIndex() {
        if (index) return Promise.resolve(index);
        return BlogSearch.load().then(data => { index = data; return index; });
    }

    function openModal() {
        searchOverlay.classList.add('search__overlay--open');
        document.body.classList.add('search-open');
        // A visibility:hidden element cannot take focus, so the overlay's
        // visibility must flip synchronously (see _header.scss). The deferred
        // retry is a no-op safety net for slower style application.
        focusInput();
        setTimeout(focusInput, 0);
        ensureIndex().then(() => { if (searchInput.value.trim()) run(); });
    }

    function focusInput() {
        if (document.activeElement === searchInput) return;
        searchInput.focus();
        searchInput.select();
    }

    function closeModal() {
        const wasFocused = searchOverlay.contains(document.activeElement);
        searchOverlay.classList.remove('search__overlay--open');
        document.body.classList.remove('search-open');
        searchInput.setAttribute('aria-expanded', 'false');
        searchInput.removeAttribute('aria-activedescendant');
        // The overlay becomes visibility:hidden with focus still inside it, so
        // focus would fall back to <body> and a keyboard user would lose their
        // place. Hand it back to the control that opened the modal.
        if (wasFocused && searchToggle.focus) searchToggle.focus();
    }

    function isOpen() {
        return searchOverlay.classList.contains('search__overlay--open');
    }

    searchToggle.addEventListener('click', openModal);
    searchToggle.addEventListener('mouseenter', ensureIndex);  // warm the cache
    if (searchClose) searchClose.addEventListener('click', closeModal);

    searchOverlay.addEventListener('click', function (e) {
        if (e.target === searchOverlay) closeModal();
    });

    document.addEventListener('keydown', function (e) {
        if (!e.key || e.isComposing) return;

        // Cmd/Ctrl+K or "/" opens search from anywhere.
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            openModal();
            return;
        }
        if (e.key === '/' && !isOpen() && !isTypingTarget(e.target)) {
            e.preventDefault();
            openModal();
            return;
        }
        if (e.key === 'Escape' && isOpen()) closeModal();
    });

    function isTypingTarget(el) {
        if (!el) return false;
        const tag = el.tagName;
        return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
    }

    /* ── Query execution ── */

    function searchPageURL(q) {
        const base = window.SEARCH_PAGE_URL ||
            (searchViewAll && (searchViewAll.dataset.base || searchViewAll.href.split('?')[0])) ||
            '/search/';
        return base + '?q=' + encodeURIComponent(q);
    }

    function run() {
        const q = searchInput.value.trim();
        active = -1;
        searchInput.removeAttribute('aria-activedescendant'); // options are about to be replaced

        if (!q) {
            lastHits = [];
            searchResults.innerHTML = '';
            if (searchFooter) searchFooter.style.display = 'none';
            searchInput.setAttribute('aria-expanded', 'false');
            return;
        }
        if (!index) {
            searchResults.innerHTML = '<div class="search__status">Loading…</div>';
            return;
        }

        const hits = BlogSearch.search(q, index, { limit: MAX_RESULTS });
        lastHits = hits;
        renderResults(hits, q);

        if (searchFooter && searchViewAll) {
            const base = searchViewAll.dataset.base || searchViewAll.href.split('?')[0];
            searchViewAll.dataset.base = base;
            searchViewAll.href = searchPageURL(q);
            searchViewAll.textContent = hits.total > hits.length
                ? `See all ${hits.total} results →`
                : 'Open in search page →';
            searchFooter.style.display = 'flex';
        }
        searchInput.setAttribute('aria-expanded', String(hits.length > 0));
    }

    function renderResults(hits, q) {
        if (!hits.length) {
            searchResults.innerHTML =
                '<div class="search__no-results">No results for <strong>' +
                BlogSearch.esc(q) + '</strong></div>';
            return;
        }

        const banner = hits.relaxed
            ? '<div class="search__status search__status--relaxed">No exact match — showing closest results.</div>'
            : '';

        searchResults.innerHTML = banner + hits.map(function (hit, i) {
            const d = hit.doc;
            const title = BlogSearch.highlight(BlogSearch.esc(d.title), hits.terms);
            const snippet = BlogSearch.highlight(
                BlogSearch.esc(BlogSearch.excerpt(d, hits.terms, 130)), hits.terms);
            const tags = (d.tags || []).slice(0, 3)
                .map(t => '<span class="search__result-tag">' + BlogSearch.esc(t) + '</span>').join('');
            return '' +
                '<a class="search__result" role="option" id="search-opt-' + i + '"' +
                   ' aria-selected="false" data-i="' + i + '" href="' + BlogSearch.esc(d.url) + '">' +
                  '<h3 class="search__result-title">' + title + '</h3>' +
                  (snippet ? '<p class="search__result-excerpt">' + snippet + '</p>' : '') +
                  '<div class="search__result-meta">' +
                    '<span class="search__result-date">' + formatDate(d.date) + '</span>' +
                    (d.read ? '<span class="search__result-read">' + BlogSearch.esc(d.read) + '</span>' : '') +
                    tags +
                  '</div>' +
                '</a>';
        }).join('');
    }

    /* ── Input + keyboard navigation ── */

    if (searchInput) {
        let timer;
        // While a CJK IME is composing, the field holds provisional romaji /
        // zhuyin and Enter/arrows belong to the IME candidate list, not to us.
        let composing = false;

        searchInput.addEventListener('compositionstart', function () { composing = true; });
        searchInput.addEventListener('compositionend', function () {
            composing = false;
            clearTimeout(timer);
            timer = setTimeout(() => ensureIndex().then(run), 60);
        });

        searchInput.addEventListener('input', function () {
            if (composing) return;
            clearTimeout(timer);
            timer = setTimeout(() => ensureIndex().then(run), 120);
        });

        searchInput.addEventListener('keydown', function (e) {
            if (composing || e.isComposing || e.keyCode === 229) return;

            const items = searchResults.querySelectorAll('.search__result');

            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                if (!items.length) return;
                e.preventDefault();
                active += (e.key === 'ArrowDown' ? 1 : -1);
                if (active < 0) active = items.length - 1;
                if (active >= items.length) active = 0;
                setActive(items);
                return;
            }

            if (e.key === 'Enter') {
                e.preventDefault();
                const q = this.value.trim();
                if (active >= 0 && items[active]) {
                    window.location.href = items[active].getAttribute('href');
                } else if (q) {
                    window.location.href = searchPageURL(q);
                }
            }
        });
    }

    function setActive(items) {
        items.forEach((el, i) => {
            const on = i === active;
            el.classList.toggle('search__result--active', on);
            el.setAttribute('aria-selected', String(on));
            if (on) el.scrollIntoView({ block: 'nearest' });
        });
        // Focus stays in the input while arrows move the highlight, so the
        // combobox has to point at the active option for it to be announced.
        const current = items[active];
        if (current && current.id) searchInput.setAttribute('aria-activedescendant', current.id);
        else searchInput.removeAttribute('aria-activedescendant');
    }
}

// Format date for search results.
// The index stores plain "YYYY-MM-DD"; new Date() would read that as UTC
// midnight and render the previous day for anyone west of Greenwich.
function formatDate(dateString) {
    if (!dateString) return '';
    const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(dateString);
    const date = parts
        ? new Date(+parts[1], +parts[2] - 1, +parts[3])
        : new Date(dateString);
    if (isNaN(date)) return '';
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Smooth scrolling
function initSmoothScrolling() {
    const links = document.querySelectorAll('a[href^="#"]');
    
    links.forEach(link => {
        link.addEventListener('click', function(e) {
            const targetId = this.getAttribute('href');
            const targetElement = document.querySelector(targetId);
            
            if (targetElement) {
                e.preventDefault();
                targetElement.scrollIntoView({
                    // CSS `scroll-behavior: auto !important` under
                    // prefers-reduced-motion does not reach a scroll that
                    // asks for smoothing explicitly, so check it here too.
                    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

// Reading progress indicator
function initReadingProgress() {
    const article = document.querySelector('.article__content');
    if (!article) return;
    
    // Create progress bar
    const progressBar = document.createElement('div');
    progressBar.className = 'reading-progress';
    progressBar.innerHTML = '<div class="reading-progress__bar"></div>';
    document.body.appendChild(progressBar);
    
    const progressBarFill = progressBar.querySelector('.reading-progress__bar');
    let queued = false;

    function updateProgress() {
        queued = false;
        const articleTop = article.offsetTop;
        const articleHeight = article.offsetHeight;
        const windowHeight = window.innerHeight;
        const scrollTop = window.pageYOffset;

        const progress = Math.min(
            Math.max((scrollTop - articleTop + windowHeight) / articleHeight, 0),
            1
        );

        // scaleX, not width: the bar is then a compositor-only update, so it
        // keeps up with a fast scroll instead of laying out on every event.
        progressBarFill.style.transform = 'scaleX(' + progress + ')';
    }

    // Coalesce bursts of scroll events onto one frame.
    function onScroll() {
        if (queued) return;
        queued = true;
        requestAnimationFrame(updateProgress);
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    updateProgress(); // Initial call
}

// ---------------------------------------------------------------------------
// Sticky header state.
// Adds .header--scrolled once the page has moved, which tightens the bar and
// gives it a shadow (see _header.scss). Threshold is deliberately small: the
// point is to mark "not at the top" rather than to wait for a scroll distance.
// ---------------------------------------------------------------------------
function initHeaderScroll() {
    const header = document.getElementById('siteHeader');
    if (!header) return;

    const THRESHOLD = 24;
    let queued = false;

    function apply() {
        queued = false;
        header.classList.toggle('header--scrolled', window.pageYOffset > THRESHOLD);
    }

    window.addEventListener('scroll', function () {
        if (queued) return;
        queued = true;
        requestAnimationFrame(apply);
    }, { passive: true });

    apply();
}

// ---------------------------------------------------------------------------
// Back-to-top button.
// Shown once the reader is a screen and a half down the page, which is far
// enough that scrolling back by hand is a chore but not so early that the
// button appears on a short page that never needed it.
// ---------------------------------------------------------------------------
function initBackToTop() {
    const button = document.getElementById('toTop');
    if (!button) return;

    let queued = false;

    function apply() {
        queued = false;
        const trigger = (window.innerHeight || 800) * 1.5;
        button.classList.toggle('to-top--visible', window.pageYOffset > trigger);
    }

    window.addEventListener('scroll', function () {
        if (queued) return;
        queued = true;
        requestAnimationFrame(apply);
    }, { passive: true });

    // The href is a real #main jump for the no-JS case; with JS we animate,
    // unless the visitor asked for less motion.
    button.addEventListener('click', function (e) {
        e.preventDefault();
        window.scrollTo({
            top: 0,
            behavior: prefersReducedMotion() ? 'auto' : 'smooth'
        });
    });

    apply();
}

// ---------------------------------------------------------------------------
// Scroll reveal.
// Elements marked [data-reveal] start faded/offset and get .is-revealed as
// they enter the viewport; --reveal-i (set by the layout, or derived from DOM
// order here) staggers a grid so it arrives as a wave rather than a block.
// Each element is unobserved once revealed — nothing re-animates on scroll-up.
//
// Contract with the CSS: elements are only hidden while <html> carries
// `reveal-armed`, which head.html sets before first paint and takes back on a
// 1.5s timer unless this function has added `reveal-ready`. So the class is
// set at the *end* of each path here, once the reveal is genuinely handled —
// if anything above throws, the failsafe un-hides the page instead.
// ---------------------------------------------------------------------------
function initReveal() {
    const root = document.documentElement;
    const targets = document.querySelectorAll('[data-reveal]');

    // Nothing to reveal: disarm the hidden state and let the head failsafe go.
    if (!targets.length) {
        root.classList.remove('reveal-armed');
        root.classList.add('reveal-ready');
        return;
    }

    // No observer, or the visitor wants no motion: show everything as-is.
    if (!('IntersectionObserver' in window) || prefersReducedMotion()) {
        targets.forEach(function (el) { el.classList.add('is-revealed'); });
        root.classList.remove('reveal-armed');
        root.classList.add('reveal-ready');
        return;
    }

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            entry.target.classList.add('is-revealed');
            observer.unobserve(entry.target);
        });
    }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });

    targets.forEach(function (el, i) {
        // A layout can pin its own order; otherwise cap the stagger at 8 steps
        // so a long list does not end up with a two-second tail.
        if (!el.style.getPropertyValue('--reveal-i')) {
            el.style.setProperty('--reveal-i', String(i % 8));
        }
        observer.observe(el);
    });

    // Anything already on screen is revealed directly, without waiting to be
    // told. The observer is the mechanism for content further down the page;
    // above the fold it is a single point of failure, and an environment that
    // never delivers the callback (a prerenderer, a screenshot service, a
    // paused background tab) would otherwise leave the hero blank.
    function revealInView() {
        const height = window.innerHeight || document.documentElement.clientHeight;
        targets.forEach(function (el) {
            if (el.classList.contains('is-revealed')) return;
            const rect = el.getBoundingClientRect();
            if (rect.top < height && rect.bottom > 0) {
                el.classList.add('is-revealed');
                observer.unobserve(el);
            }
        });
    }

    revealInView();
    window.addEventListener('load', revealInView);

    // Setup succeeded: from here the observer owns the hidden state, so the
    // head failsafe can stand down. Set last on purpose — if anything above
    // had thrown, the failsafe would still un-hide the page.
    root.classList.add('reveal-ready');
}

// ---------------------------------------------------------------------------
// Cursor spotlight.
// Feeds pointer position into --mx/--my on .u-spotlight cards, which paint a
// soft accent highlight under the cursor. Pointer-fine only: on a touch screen
// there is no hover to follow, and the listener would just cost battery.
// ---------------------------------------------------------------------------
function initSpotlight() {
    const cards = document.querySelectorAll('.u-spotlight');
    if (!cards.length) return;
    if (prefersReducedMotion()) return;
    if (window.matchMedia && !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;

    cards.forEach(function (card) {
        let queued = false;
        let x = 0;
        let y = 0;

        function paint() {
            queued = false;
            card.style.setProperty('--mx', x + 'px');
            card.style.setProperty('--my', y + 'px');
        }

        card.addEventListener('pointermove', function (e) {
            // getBoundingClientRect per move is a read on an element that is
            // already being composited; batching into rAF keeps it off the
            // event's critical path.
            const rect = card.getBoundingClientRect();
            x = e.clientX - rect.left;
            y = e.clientY - rect.top;
            if (queued) return;
            queued = true;
            requestAnimationFrame(paint);
        });

        // Reset to the centre so the next hover starts from a neutral sheen.
        card.addEventListener('pointerleave', function () {
            card.style.removeProperty('--mx');
            card.style.removeProperty('--my');
        });
    });
}

// ---------------------------------------------------------------------------
// Count-up for the hero stats.
// [data-count-to] already contains its final value in the markup, so a visitor
// without JS (or with reduced motion) sees the real number and this only ever
// replaces a correct value with the same correct value.
// ---------------------------------------------------------------------------
function initCountUp() {
    const counters = document.querySelectorAll('[data-count-to]');
    if (!counters.length) return;
    if (prefersReducedMotion() || !('IntersectionObserver' in window)) return;

    const DURATION = 1100;

    function run(el) {
        const target = parseInt(el.getAttribute('data-count-to'), 10);
        if (!isFinite(target) || target <= 0) return;
        const start = performance.now();

        function step(now) {
            const t = Math.min((now - start) / DURATION, 1);
            // easeOutExpo, matching --ease-out-expo in the stylesheet.
            const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
            el.textContent = String(Math.round(target * eased));
            if (t < 1) requestAnimationFrame(step);
        }

        requestAnimationFrame(step);
    }

    const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
            if (!entry.isIntersecting) return;
            observer.unobserve(entry.target);
            run(entry.target);
        });
    }, { threshold: 0.4 });

    counters.forEach(function (el) { observer.observe(el); });
}

// Utility function to debounce events
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}