// Main JavaScript for Uber Style theme
document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu functionality
    initMobileMenu();
    
    // Search functionality  
    initSearch();
    
    // Smooth scrolling for anchor links
    initSmoothScrolling();
    
    // Reading progress indicator
    initReadingProgress();
});

// Mobile menu
function initMobileMenu() {
    const menuToggle = document.querySelector('.nav__toggle');
    const mobileMenu = document.querySelector('.nav__mobile');
    
    if (menuToggle && mobileMenu) {
        menuToggle.addEventListener('click', function() {
            mobileMenu.classList.toggle('nav__mobile--open');
            menuToggle.classList.toggle('nav__toggle--active');
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', function(e) {
            if (!menuToggle.contains(e.target) && !mobileMenu.contains(e.target)) {
                mobileMenu.classList.remove('nav__mobile--open');
                menuToggle.classList.remove('nav__toggle--active');
            }
        });
    }
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
                    behavior: 'smooth',
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
    
    function updateProgress() {
        const articleTop = article.offsetTop;
        const articleHeight = article.offsetHeight;
        const windowHeight = window.innerHeight;
        const scrollTop = window.pageYOffset;
        
        const progress = Math.min(
            Math.max((scrollTop - articleTop + windowHeight) / articleHeight, 0),
            1
        );
        
        progressBarFill.style.width = (progress * 100) + '%';
    }
    
    window.addEventListener('scroll', updateProgress);
    updateProgress(); // Initial call
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