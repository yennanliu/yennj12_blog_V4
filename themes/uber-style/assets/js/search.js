/*
 * BlogSearch — shared client-side search engine.
 *
 * Used by both the header search modal (main.js) and the /search/ page.
 * Ranked, multi-term, CJK-aware, no external dependencies.
 *
 * Index shape (see themes/uber-style/layouts/index.json):
 *   { title, url, desc, date, tags[], cats[], read, w, series[], body }
 */
window.BlogSearch = (function () {
  'use strict';

  /* ────────────────────────────────────────────────────────────
   * Text normalisation
   * ──────────────────────────────────────────────────────────── */

  // Full-width ASCII -> half-width, so a full-width "ＡＩ" matches "AI".
  function toHalfWidth(s) {
    return s.replace(/[！-～]/g, function (c) {
      return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
    }).replace(/　/g, ' ');
  }

  // Punctuation authors use as separators becomes whitespace, so
  // "AI 工程從零開始｜Phase 1" is searchable by any of its parts.
  var SEPARATORS = /[、。｜：，．—–…「」『』（）()[\]{}<>"'`,;!?~|/\\]+/g;

  var CJK_CLASS = '\\u3400-\\u4DBF\\u4E00-\\u9FFF\\uF900-\\uFAFF\\u3040-\\u30FF\\uAC00-\\uD7AF';
  var CJK_RE = new RegExp('[' + CJK_CLASS + ']');
  // CJK written flush against Latin/digits ("使用Kafka", "ai工程"). Splitting the
  // two lets a spaceless query match a spaced title, and vice versa.
  var CJK_AFTER_LATIN = new RegExp('([a-z0-9])([' + CJK_CLASS + '])', 'g');
  var LATIN_AFTER_CJK = new RegExp('([' + CJK_CLASS + '])([a-z0-9])', 'g');

  function normalize(s) {
    if (s == null) return '';
    return toHalfWidth(String(s)).toLowerCase()
      .replace(SEPARATORS, ' ')
      .replace(CJK_AFTER_LATIN, '$1 $2')
      .replace(LATIN_AFTER_CJK, '$1 $2')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function hasCJK(s) {
    return CJK_RE.test(s);
  }

  function escapeRe(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  // Overlapping bigrams of a CJK run. Used only by the relaxed fallback pass,
  // where "推論優化" should still surface posts saying "推論" or "優化".
  function bigrams(term) {
    var out = [];
    for (var i = 0; i + 2 <= term.length; i++) out.push(term.substr(i, 2));
    return out;
  }

  /* ────────────────────────────────────────────────────────────
   * Query parsing
   *
   * Supports:  plain terms      -> all must match (AND)
   *            "quoted phrase"  -> matched as one contiguous unit
   *            tag:foo cat:bar  -> field-scoped filters
   *            -foo             -> exclude
   * ──────────────────────────────────────────────────────────── */

  var FIELD_ALIASES = {
    tag: 'tags', tags: 'tags',
    cat: 'cats', category: 'cats', categories: 'cats',
    series: 'series',
    title: 'title'
  };

  function parseQuery(raw) {
    var q = { terms: [], filters: [], excludes: [], phrase: normalize(raw) };
    if (!raw) return q;

    var rest = String(raw);

    // Quoted field filters first — `tag:"System Design"` must not be torn apart
    // by the generic quoted-phrase rule below.
    rest = rest.replace(/(-?)([a-zA-Z]+):"([^"]*)"/g, function (whole, neg, field, val) {
      var key = FIELD_ALIASES[field.toLowerCase()];
      if (!key) return whole;
      var v = normalize(val);
      if (v) q.filters.push({ field: key, value: v, neg: neg === '-' });
      return ' ';
    });

    // Remaining quoted phrases keep their inner spaces as one term.
    var quoted = [];
    rest = rest.replace(/"([^"]*)"/g, function (_, inner) {
      if (inner.trim()) quoted.push(inner);
      return ' ';
    });

    quoted.forEach(function (p) {
      var t = normalize(p);
      if (t) q.terms.push(t);
    });

    rest.split(/\s+/).forEach(function (chunk) {
      if (!chunk) return;

      var neg = false;
      if (chunk.charAt(0) === '-' && chunk.length > 1) { neg = true; chunk = chunk.slice(1); }

      var m = /^([a-zA-Z]+):(.+)$/.exec(chunk);
      if (m && FIELD_ALIASES[m[1].toLowerCase()]) {
        var val = normalize(m[2]);
        if (val) q.filters.push({ field: FIELD_ALIASES[m[1].toLowerCase()], value: val, neg: neg });
        return;
      }

      // normalize() may split one chunk into several ("ai工程" -> "ai 工程").
      normalize(chunk).split(' ').forEach(function (term) {
        if (term) (neg ? q.excludes : q.terms).push(term);
      });
    });

    return q;
  }

  function isEmptyQuery(q) {
    return !q.terms.length && !q.filters.length && !q.excludes.length;
  }

  /* ────────────────────────────────────────────────────────────
   * Matchers
   *
   * Latin terms match at a word boundary and may extend rightwards
   * ("token" hits "tokenization" but not "retoken"). Without that rule an
   * "ai" query would match "chain", "detail" and "domain" in every post.
   * CJK has no word boundaries, so those terms match as plain substrings.
   * ──────────────────────────────────────────────────────────── */

  var matcherCache = Object.create(null);

  function buildMatcher(term) {
    if (matcherCache[term]) return matcherCache[term];

    var m;
    if (hasCJK(term)) {
      m = {
        cjk: true,
        term: term,
        test: function (hay) { return hay.indexOf(term) !== -1; },
        whole: function (hay) { return hay.indexOf(term) !== -1; },
        exact: function (hay) { return hay === term; },
        count: function (hay) {
          var n = 0, i = 0;
          while ((i = hay.indexOf(term, i)) !== -1) { n++; i += term.length; if (n > 20) break; }
          return n;
        }
      };
    } else {
      var e = escapeRe(term);
      var prefixRe = new RegExp('(?:^|[^a-z0-9])' + e, 'g');
      var wholeRe = new RegExp('(?:^|[^a-z0-9])' + e + '(?![a-z0-9])');
      m = {
        cjk: false,
        term: term,
        test: function (hay) { prefixRe.lastIndex = 0; return prefixRe.test(hay); },
        whole: function (hay) { return wholeRe.test(hay); },
        exact: function (hay) { return hay === term; },
        count: function (hay) {
          prefixRe.lastIndex = 0;
          var n = 0;
          while (prefixRe.exec(hay) !== null) { if (++n > 20) break; }
          return n;
        }
      };
    }

    matcherCache[term] = m;
    return m;
  }

  /* ────────────────────────────────────────────────────────────
   * Scoring
   * ──────────────────────────────────────────────────────────── */

  var W = {
    titleWhole: 40,   // whole-word hit in the title
    titlePart: 24,    // partial hit in the title
    titleStart: 12,   // bonus when the title opens with the term
    tagExact: 20,
    tagPart: 10,
    catSeries: 8,
    desc: 6,
    body: 2,
    bodyRepeat: 0.4,  // per extra body occurrence, capped
    phraseTitle: 60,  // the whole query appears verbatim in the title
    phraseDesc: 18,
    phraseBody: 8,
    filterHit: 20
  };

  // Cache each document's normalised fields on first use.
  function fields(doc) {
    if (doc._f) return doc._f;
    doc._f = {
      title: normalize(doc.title),
      desc: normalize(doc.desc),
      body: normalize(doc.body),
      tags: (doc.tags || []).map(normalize),
      cats: (doc.cats || []).map(normalize),
      series: (doc.series || []).map(normalize)
    };
    return doc._f;
  }

  // Score one term against one document. Returns 0 when it appears nowhere.
  function scoreTerm(f, term, weightScale) {
    var m = buildMatcher(term);
    var s = 0;

    if (m.test(f.title)) {
      s += m.whole(f.title) ? W.titleWhole : W.titlePart;
      if (f.title.indexOf(term) === 0) s += W.titleStart;
    }
    if (f.tags.some(function (t) { return m.exact(t); })) s += W.tagExact;
    else if (f.tags.some(function (t) { return m.test(t); })) s += W.tagPart;
    if (f.cats.some(function (t) { return m.test(t); }) ||
        f.series.some(function (t) { return m.test(t); })) s += W.catSeries;
    if (m.test(f.desc)) s += W.desc;
    if (m.test(f.body)) s += W.body + Math.min(m.count(f.body) - 1, 10) * W.bodyRepeat;

    return s * (weightScale == null ? 1 : weightScale);
  }

  function matchesAnyField(f, term) {
    var m = buildMatcher(term);
    return m.test(f.title) || m.test(f.desc) || m.test(f.body) ||
      f.tags.some(function (t) { return m.test(t); }) ||
      f.cats.some(function (t) { return m.test(t); }) ||
      f.series.some(function (t) { return m.test(t); });
  }

  /**
   * @param loose  false -> every term must match (precise).
   *               true  -> terms may partially match; CJK terms fall back to
   *                        bigrams. Score is scaled by term coverage.
   */
  function scoreDoc(doc, q, loose) {
    var f = fields(doc);
    var score = 1; // base, so a filter-only query still yields hits

    // Field filters (tag:/cat:/series:/title:) are hard constraints in both modes.
    for (var i = 0; i < q.filters.length; i++) {
      var flt = q.filters[i];
      var pool = flt.field === 'title' ? [f.title] : f[flt.field];
      var hit = pool.some(function (v) { return v === flt.value || v.indexOf(flt.value) !== -1; });
      if (hit === flt.neg) return 0;
      if (!flt.neg) {
        // Soft relevance boost too, so `tag:rag` still ranks the RAG series first.
        score += W.filterHit + scoreTerm(f, flt.value, 0.5);
      }
    }

    // Exclusions are absolute.
    for (var j = 0; j < q.excludes.length; j++) {
      if (matchesAnyField(f, q.excludes[j])) return 0;
    }

    var matched = 0;
    for (var k = 0; k < q.terms.length; k++) {
      var term = q.terms[k];
      var termScore = scoreTerm(f, term);

      if (termScore === 0 && loose && hasCJK(term) && term.length > 2) {
        // Relaxed pass: credit whichever bigrams of the compound term do appear.
        var grams = bigrams(term);
        var gramHits = 0;
        for (var g = 0; g < grams.length; g++) {
          var gs = scoreTerm(f, grams[g], 0.35);
          if (gs > 0) { gramHits++; termScore += gs; }
        }
        // Require substantial overlap, not one incidental character pair.
        if (gramHits * 3 < grams.length * 2) termScore = 0;
      }

      if (termScore > 0) matched++;
      else if (!loose) return 0; // strict AND
      score += termScore;
    }

    if (q.terms.length) {
      if (!matched) return 0;
      if (loose) {
        // A relaxed hit must still cover most of the query, otherwise a typo
        // in one word would drag in every post sharing the other word.
        if (q.terms.length > 1 && matched * 2 <= q.terms.length) return 0;
        // Rank by how much of the query the document actually covers.
        score *= (matched / q.terms.length);
      }
    }

    // Reward the query appearing as one contiguous phrase.
    if (q.terms.length > 1 && q.phrase) {
      if (f.title.indexOf(q.phrase) !== -1) score += W.phraseTitle;
      else if (f.desc.indexOf(q.phrase) !== -1) score += W.phraseDesc;
      else if (f.body.indexOf(q.phrase) !== -1) score += W.phraseBody;
    }

    return score;
  }

  /* ────────────────────────────────────────────────────────────
   * Public search
   * ──────────────────────────────────────────────────────────── */

  // Minimum score for a relaxed-pass hit. Roughly "more than a single
  // incidental occurrence buried in the body text".
  var LOOSE_FLOOR = 8;

  function runPass(index, q, loose) {
    var hits = [];
    for (var i = 0; i < index.length; i++) {
      var s = scoreDoc(index[i], q, loose);
      if (s > 0) hits.push({ doc: index[i], score: s });
    }
    return hits;
  }

  /**
   * @param opts.limit  cap the number of results
   * @param opts.sort   'relevance' (default) | 'date'
   * @returns array of {doc, score}; also carries `.terms` (for highlighting)
   *          and `.relaxed` (true when the strict pass found nothing).
   */
  function search(raw, index, opts) {
    opts = opts || {};
    index = index || [];
    var q = parseQuery(raw);

    var hits, relaxed = false;
    if (isEmptyQuery(q)) {
      hits = index.map(function (d) { return { doc: d, score: 0 }; });
      hits.sort(function (a, b) { return byDate(a.doc, b.doc); });
    } else {
      hits = runPass(index, q, false);
      if (!hits.length) {
        // Nothing matched every term — retry leniently rather than show a dead
        // end, but discard the weak tail so a nonsense query still returns none.
        hits = runPass(index, q, true).filter(function (h) { return h.score >= LOOSE_FLOOR; });
        relaxed = hits.length > 0;
      }

      if (opts.sort === 'date') {
        hits.sort(function (a, b) { return byDate(a.doc, b.doc); });
      } else {
        hits.sort(function (a, b) {
          if (b.score !== a.score) return b.score - a.score;
          // Equal relevance within one series -> keep Part 1, 2, 3 … order.
          var aw = a.doc.w || 0, bw = b.doc.w || 0;
          if (aw && bw && sameSeries(a.doc, b.doc)) return aw - bw;
          return byDate(a.doc, b.doc);
        });
      }
    }

    var total = hits.length;
    if (opts.limit) hits = hits.slice(0, opts.limit);
    hits.total = total;
    hits.relaxed = relaxed;
    hits.terms = q.terms.concat(
      q.filters.filter(function (f) { return !f.neg; }).map(function (f) { return f.value; })
    );
    return hits;
  }

  function sameSeries(a, b) {
    var as = (a.series || [])[0], bs = (b.series || [])[0];
    return !!as && as === bs;
  }

  function byDate(a, b) {
    return String(b.date || '').localeCompare(String(a.date || ''));
  }

  /* ────────────────────────────────────────────────────────────
   * Presentation helpers
   * ──────────────────────────────────────────────────────────── */

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // Highlights already-escaped text. Longest terms first, so overlapping
  // terms cannot produce nested <mark> tags.
  function highlight(escaped, terms) {
    if (!terms || !terms.length) return escaped;
    var pattern = terms.slice()
      .filter(Boolean)
      .sort(function (a, b) { return b.length - a.length; })
      .map(function (t) {
        var e = escapeRe(esc(t));
        // Latin terms highlight the whole word they prefix ("token" -> "tokenization").
        return hasCJK(t) ? e : e + '[a-z0-9]*';
      })
      .join('|');
    if (!pattern) return escaped;
    try {
      return escaped.replace(new RegExp('(' + pattern + ')', 'gi'), '<mark>$1</mark>');
    } catch (e) {
      return escaped;
    }
  }

  // Window of `body` around the first matching term, so a result shows *why*
  // it matched rather than always the same opening sentence.
  function excerpt(doc, terms, len) {
    len = len || 170;
    var desc = doc.desc || '';
    var body = doc.body || '';

    if (terms && terms.length) {
      // Prefer the description when it already covers the match.
      var nd = normalize(desc);
      for (var i = 0; i < terms.length; i++) {
        if (nd && nd.indexOf(terms[i]) !== -1) return clip(desc, len);
      }
      if (body) {
        var nb = normalize(body);
        var best = -1;
        for (var j = 0; j < terms.length; j++) {
          var at = nb.indexOf(terms[j]);
          if (at !== -1 && (best === -1 || at < best)) best = at;
        }
        if (best !== -1) {
          // normalize() can shift offsets slightly; snap back to a safe window.
          var start = Math.max(0, Math.min(best, body.length - 1) - Math.floor(len / 3));
          var text = body.substr(start, len);
          return (start > 0 ? '…' : '') + text + (start + len < body.length ? '…' : '');
        }
      }
    }
    return clip(desc || body, len);
  }

  function clip(s, len) {
    s = s || '';
    return s.length > len ? s.substr(0, len) + '…' : s;
  }

  /* ────────────────────────────────────────────────────────────
   * Index loading (lazy, shared across callers)
   * ──────────────────────────────────────────────────────────── */

  var indexPromise = null;

  function load() {
    if (indexPromise) return indexPromise;
    var url = window.SEARCH_INDEX_URL || '/index.json';
    indexPromise = fetch(url)
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + url);
        return r.json();
      })
      .catch(function (err) {
        console.error('[search] index load failed:', err);
        indexPromise = null; // let the next interaction retry
        return [];
      });
    return indexPromise;
  }

  // Most frequent tags, for the quick-filter pills.
  function topTags(index, n) {
    var counts = Object.create(null);
    index.forEach(function (d) {
      (d.tags || []).forEach(function (t) { counts[t] = (counts[t] || 0) + 1; });
    });
    return Object.keys(counts)
      .sort(function (a, b) { return counts[b] - counts[a] || a.localeCompare(b); })
      .slice(0, n || 12)
      .map(function (t) { return { tag: t, count: counts[t] }; });
  }

  return {
    load: load,
    search: search,
    parseQuery: parseQuery,
    normalize: normalize,
    highlight: highlight,
    excerpt: excerpt,
    topTags: topTags,
    esc: esc
  };
})();
