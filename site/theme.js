// Theme toggle for the Korvin site.
// Without a saved choice, the page follows the system setting (prefers-color-scheme).
// The choice is stored only in this browser, under the key "korvin-theme".
(function () {
  var root = document.documentElement;
  var KEY = 'korvin-theme';

  function readSaved() {
    try {
      return localStorage.getItem(KEY);
    } catch (error) {
      return null;
    }
  }

  function save(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (error) {
      // Storage can be off, for example for files opened from disk. The toggle still works for this visit.
    }
  }

  var saved = readSaved();
  if (saved === 'light' || saved === 'dark') {
    root.setAttribute('data-theme', saved);
  }

  var query = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;

  function current() {
    var chosen = root.getAttribute('data-theme');
    if (chosen) {
      return chosen;
    }
    return query && query.matches ? 'light' : 'dark';
  }

  function label(button) {
    var next = current() === 'light' ? 'dark' : 'light';
    button.textContent = next === 'light' ? 'Light' : 'Dark';
    button.setAttribute('aria-label', 'Switch to the ' + next + ' theme');
  }

  function setUp() {
    var button = document.getElementById('themeToggle');
    if (!button) {
      return;
    }
    button.hidden = false;
    label(button);
    button.addEventListener('click', function () {
      var next = current() === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      save(next);
      label(button);
    });
    if (query) {
      var update = function () {
        label(button);
      };
      if (query.addEventListener) {
        query.addEventListener('change', update);
      } else if (query.addListener) {
        query.addListener(update);
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setUp);
  } else {
    setUp();
  }
})();
