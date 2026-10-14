// ChatGPT Theme - JS injection
(function() {
  document.title = 'ChatGPT';

  function run() {
    // 1. Replace model name with greeting
    document.querySelectorAll('div').forEach(function(el) {
      var t = el.textContent.trim();
      if (t === 'gemma4-uncensored:latest' && el.children.length <= 2) {
        var style = window.getComputedStyle(el);
        var fontSize = parseInt(style.fontSize);
        if (fontSize >= 24) {
          el.textContent = '\u6211\u80FD\u5E2E\u4EC0\u4E48\u5FD9\u5417\uFF0CLucas\uFF1F';
        }
      }
    });

    // 2. Hide model selector in sidebar top
    document.querySelectorAll('nav > div > div').forEach(function(el) {
      var t = el.textContent.trim();
      if (t.includes('gemma4-uncensored') && t.length < 100) {
        var parent = el.closest('div.flex');
        if (parent) parent.style.display = 'none';
      }
    });

    // 3. Hide suggestion cards
    document.querySelectorAll('button').forEach(function(el) {
      var t = el.textContent.trim();
      if (t.includes('Give me ideas') || t.includes('code snippet') || t.includes('Help me study') || t.includes('options trading') || t.includes('fun fact') || t.includes('procrastination')) {
        el.style.display = 'none';
      }
    });

    // 4. Hide "建议" label
    document.querySelectorAll('div').forEach(function(el) {
      var t = el.textContent.trim();
      if (t === '\u5EFA\u8BAE' && el.children.length <= 2) {
        el.style.display = 'none';
      }
    });

    // 5. Hide suggestion container
    document.querySelectorAll('.svelte-6tnq1o').forEach(function(el) {
      el.style.display = 'none';
    });

    // 6. Hide "分组" and "对话" labels
    document.querySelectorAll('div, span').forEach(function(el) {
      var t = el.textContent.trim();
      if ((t === '\u5206\u7EC4' || t === '\u5BF9\u8BDD') && el.children.length === 0) {
        el.style.display = 'none';
      }
    });

    // 7. Rename sidebar items via TreeWalker
    var renameMap = {
      '\u65B0\u5BF9\u8BDD': '\u65B0\u804A\u5929',
      '\u7B14\u8BB0': '\u5E93',
      '\u5DE5\u4F5C\u7A7A\u95F4': '\u5E94\u7528',
      '\u641C\u7D22': '\u641C\u7D22\u804A\u5929'
    };
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null, false);
    var textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach(function(node) {
      var t = node.textContent.trim();
      if (renameMap[t]) node.textContent = node.textContent.replace(t, renameMap[t]);
    });

    // 8. Hide "ChatGPT (Open WebUI)" text and add logo only in sidebar
    if (!document.querySelector('.gpt-logo')) {
      document.querySelectorAll('div, span, a').forEach(function(el) {
        if (el.textContent.trim() === 'ChatGPT (Open WebUI)' && el.children.length === 0) {
          var parent = el.parentElement;
          if (parent) {
            // Create logo image only
            var logoImg = document.createElement('img');
            logoImg.src = '/static/gpt-logo.jpg';
            logoImg.className = 'gpt-logo';
            logoImg.alt = 'ChatGPT';
            logoImg.style.cssText = 'width:24px;height:24px;border-radius:4px;object-fit:contain;';

            el.style.display = 'none';
            parent.insertBefore(logoImg, el);
          }
        }
      });
    }

    // 9. Add "ChatGPT" title with dropdown in main content top center
    if (!document.querySelector('.gpt-main-title')) {
      var mainArea = document.querySelector('.h-full.flex.relative.max-w-full.flex-col');
      if (mainArea) {
        var titleDiv = document.createElement('div');
        titleDiv.className = 'gpt-main-title';
        titleDiv.innerHTML = '<span style="font-size:16px;font-weight:600;color:#000;">ChatGPT</span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#000" stroke-width="2.5" style="margin-left:4px;"><path d="M6 9l6 6 6-6"/></svg>';
        titleDiv.style.cssText = 'position:absolute;top:10px;left:50%;transform:translateX(-50%);display:flex;align-items:center;z-index:10;cursor:pointer;';
        mainArea.appendChild(titleDiv);
      }
    }

    // 10. Inject action buttons below input area
    var editor = document.querySelector('.ProseMirror');
    if (editor && !document.querySelector('.chatgpt-actions')) {
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
          editor.focus();
          document.execCommand('insertText', false, btn.text);
        };
        container.appendChild(b);
      });

      var el = editor;
      var borderedBox = null;
      while (el && el !== document.body) {
        var s = window.getComputedStyle(el);
        if (s.border && s.borderRadius && parseInt(s.borderRadius) >= 16) {
          borderedBox = el;
          break;
        }
        el = el.parentElement;
      }
      if (borderedBox && borderedBox.parentNode) {
        borderedBox.parentNode.insertBefore(container, borderedBox.nextSibling);
      }
    }

    // 11. Update user display at bottom
    document.querySelectorAll('div, span, button').forEach(function(el) {
      var t = el.textContent.trim();
      if (t === 'Lucas' && el.children.length === 0) {
        el.innerHTML = '<strong>Lucas Lu</strong><div style="font-size:12px;color:#999;font-weight:normal">\u514D\u8D39\u7248</div>';
      }
    });
  }

  var tries = 0;
  var timer = setInterval(function() {
    if (document.querySelector('.ProseMirror') || document.querySelector('nav') || tries > 40) {
      clearInterval(timer);
      setTimeout(run, 500);
      setInterval(run, 2000);
    }
    tries++;
  }, 500);
})();
