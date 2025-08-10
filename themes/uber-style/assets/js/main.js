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

// Search functionality
function initSearch() {
    const searchToggle = document.querySelector('.search__toggle');
    const searchOverlay = document.querySelector('.search__overlay');
    const searchClose = document.querySelector('.search__close');
    const searchInput = document.querySelector('.search__input');
    const searchResults = document.querySelector('.search__results');
    
    if (!searchToggle || !searchOverlay) return;
    
    let searchIndex = null;
    
    // Load search index
    loadSearchIndex().then(index => {
        searchIndex = index;
    });
    
    searchToggle.addEventListener('click', function() {
        searchOverlay.classList.add('search__overlay--open');
        searchInput.focus();
    });
    
    if (searchClose) {
        searchClose.addEventListener('click', function() {
            searchOverlay.classList.remove('search__overlay--open');
        });
    }
    
    searchOverlay.addEventListener('click', function(e) {
        if (e.target === searchOverlay) {
            searchOverlay.classList.remove('search__overlay--open');
        }
    });
    
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            searchOverlay.classList.remove('search__overlay--open');
        }
        
        // Keyboard shortcut to open search (Cmd/Ctrl + K)
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            searchOverlay.classList.add('search__overlay--open');
            searchInput.focus();
        }
    });
    
    // Search input handling
    if (searchInput && searchResults) {
        let searchTimeout;
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                performSearch(this.value.trim(), searchIndex, searchResults);
            }, 150);
        });
    }
}

// Load search index
async function loadSearchIndex() {
    try {
        const response = await fetch('/index.json');
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Failed to load search index:', error);
        return [];
    }
}

// Perform search
function performSearch(query, searchIndex, resultsContainer) {
    if (!query || !searchIndex) {
        resultsContainer.innerHTML = '';
        return;
    }
    
    const results = searchIndex.filter(item => {
        const searchText = (item.title + ' ' + item.content + ' ' + item.tags.join(' ')).toLowerCase();
        return searchText.includes(query.toLowerCase());
    }).slice(0, 10); // Limit to 10 results
    
    if (results.length === 0) {
        resultsContainer.innerHTML = '<div class="search__no-results">No results found</div>';
        return;
    }
    
    const resultsHTML = results.map(result => `
        <div class="search__result">
            <h3 class="search__result-title">
                <a href="${result.permalink}">${highlightText(result.title, query)}</a>
            </h3>
            <p class="search__result-excerpt">${highlightText(result.summary || result.content.substring(0, 150) + '...', query)}</p>
            <div class="search__result-meta">
                <span class="search__result-date">${formatDate(result.date)}</span>
                ${result.tags.map(tag => `<span class="search__result-tag">${tag}</span>`).join('')}
            </div>
        </div>
    `).join('');
    
    resultsContainer.innerHTML = resultsHTML;
}

// Highlight search terms
function highlightText(text, query) {
    if (!query) return text;
    const regex = new RegExp(`(${query})`, 'gi');
    return text.replace(regex, '<mark>$1</mark>');
}

// Format date for search results
function formatDate(dateString) {
    const date = new Date(dateString);
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