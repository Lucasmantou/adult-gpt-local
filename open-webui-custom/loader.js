// ChatGPT Custom Theme - loader.js injection
(function() {
  document.title = 'ChatGPT';

  var observer = new MutationObserver(function() {
    // 1. Change greeting text
    document.querySelectorAll('h1, h2, h3').forEach(function(el) {
      var t = el.textContent || '';
      if (t.includes('\u4F60\u597D') || t.includes('Hello') || t.includes('Howdy') || t.includes('What can I help') || t.includes('\u6709\u4EC0\u4E48\u6211\u80FD\u5E2E')) {
        el.textContent = '\u6211\u80FD\u5E2E\u4EC0\u4E48\u5FD9\u5417\uFF0CLucas\uFF1F';
      }
    });

    // 2. Hide model name display
    document.querySelectorAll('div, span, p, a').forEach(function(el) {
      var t = el.textContent || '';
      if ((t.includes('gemma4-uncensored') || t.includes('gemma-4')) && el.children.length === 0) {
        el.style.display = 'none';
        if (el.parentNode && el.parentNode.children.length <= 2) {
          el.parentNode.style.display = 'none';
        }
      }
    });

    // 3. Hide suggestion/hint section
    document.querySelectorAll('[class*="suggestion"], [class*="Suggestion"], [class*="hint"], [class*="Hint"]').forEach(function(el) {
      el.style.display = 'none';
    });

    // 4. Hide Open WebUI logo
    var logo = document.getElementById('logo');
    if (logo) logo.style.display = 'none';

    // 5. Change sidebar items
    document.querySelectorAll('nav a, aside a, [class*="sidebar"] a, nav button, aside button, [class*="sidebar"] button').forEach(function(el) {
      var t = el.textContent.trim();
      if (t === '\u65B0\u5BF9\u8BDD') el.textContent = '\u65B0\u804A\u5929';
      if (t === '\u7B14\u8BB0') el.textContent = '\u5E93';
      if (t === '\u5DE5\u4F5C\u7A7A\u95F4') el.textContent = '\u5E94\u7528';
      if (t === '\u641C\u7D22') el.textContent = '\u641C\u7D22\u804A\u5929';
    });

    // 6. Hide "ChatGPT (Open WebUI)" - replace with just "ChatGPT"
    document.querySelectorAll('span, div, a').forEach(function(el) {
      var t = el.textContent.trim();
      if (t === 'ChatGPT (Open WebUI)' || t.includes('ChatGPT (Open')) {
        el.textContent = 'ChatGPT';
      }
    });

    // 7. Inject action buttons below textarea
    var textarea = document.querySelector('textarea');
    if (textarea && !document.querySelector('.chatgpt-actions')) {
      var container = document.createElement('div');
      container.className = 'chatgpt-actions';
      container.style.cssText = 'display:flex;justify-content:center;gap:12px;margin-top:12px;flex-wrap:wrap;';

      var btns = [
        {text: '\u751F\u6210\u56FE\u7247', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>'},
        {text: '\u64B0\u5199\u6216\u7F16\u8F91', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.828 2.828 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z"/></svg>'},
        {text: '\u67E5\u627E\u8D44\u6599', icon: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>'}
      ];

      btns.forEach(function(btn) {
        var b = document.createElement('button');
        b.className = 'chatgpt-action-btn';
        b.innerHTML = btn.icon + ' ' + btn.text;
        b.onclick = function() {
          textarea.value = btn.text;
          textarea.dispatchEvent(new Event('input', {bubbles: true}));
          textarea.focus();
        };
        container.appendChild(b);
      });

      var inputWrapper = textarea.closest('div');
      if (inputWrapper && inputWrapper.parentNode) {
        inputWrapper.parentNode.insertBefore(container, inputWrapper.nextSibling);
      }
    }

    // 8. Change "Lucas" at bottom to "Lucas Lu" with subtitle
    document.querySelectorAll('div, span, a, button').forEach(function(el) {
      var t = el.textContent.trim();
      if (t === 'Lucas' && el.children.length === 0) {
        el.innerHTML = '<strong>Lucas Lu</strong><br><small style="color:#999">\u514D\u8D39\u7248</small>';
      }
    });

    // 9. Hide "gemma4-uncensored:latest" at top (model selector area)
    document.querySelectorAll('button, div, span').forEach(function(el) {
      var t = el.textContent.trim();
      if (t.startsWith('gemma4-uncensored') || t.startsWith('gemma-4')) {
        var parent = el;
        for (var i = 0; i < 5; i++) {
          if (parent.parentNode) parent = parent.parentNode;
          if (parent.tagName === 'HEADER' || (parent.className && parent.className.includes && parent.className.includes('nav'))) {
            parent.style.display = 'none';
            break;
          }
        }
      }
    });
  });

  observer.observe(document.body, {childList: true, subtree: true, characterData: true});

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { observer.takeRecords(); });
  }
  setTimeout(function() { observer.takeRecords(); }, 2000);
})();
