// DOM Inspector - writes to a hidden div for extraction
(function() {
  function inspect() {
    var lines = [];

    // Get all unique class names (non-svelte)
    var allClasses = {};
    document.querySelectorAll('*').forEach(function(el) {
      if (el.className && typeof el.className === 'string') {
        el.className.split(/\s+/).forEach(function(c) {
          if (c && !c.startsWith('svelte-') && c.length > 2) {
            if (!allClasses[c]) allClasses[c] = el.tagName.toLowerCase();
          }
        });
      }
    });

    lines.push('=== ALL CUSTOM CLASSES ===');
    Object.keys(allClasses).sort().forEach(function(c) {
      lines.push(c + ' -> ' + allClasses[c]);
    });

    // Find sidebar/nav
    lines.push('\n=== NAV/SIDEBAR ===');
    document.querySelectorAll('nav, aside').forEach(function(el) {
      lines.push('TAG:' + el.tagName + ' CLASS:' + el.className.substring(0,100));
      el.querySelectorAll('*').forEach(function(child) {
        if (child.textContent.trim().length < 30 && child.textContent.trim().length > 0) {
          lines.push('  ' + child.tagName + '.' + (child.className||'').substring(0,60) + ' => "' + child.textContent.trim() + '"');
        }
      });
    });

    // Find header
    lines.push('\n=== HEADER ===');
    document.querySelectorAll('header').forEach(function(el) {
      lines.push('CLASS:' + el.className.substring(0,100));
      el.querySelectorAll('*').forEach(function(child) {
        if (child.children.length === 0 && child.textContent.trim().length > 0 && child.textContent.trim().length < 50) {
          lines.push('  ' + child.tagName + '.' + (child.className||'').substring(0,60) + ' => "' + child.textContent.trim() + '"');
        }
      });
    });

    // Find main content / greeting
    lines.push('\n=== GREETING ===');
    document.querySelectorAll('h1, h2, h3').forEach(function(el) {
      lines.push(el.tagName + '.' + (el.className||'').substring(0,80) + ' => "' + el.textContent.trim().substring(0,60) + '"');
    });

    // Find textarea/input
    lines.push('\n=== INPUT ===');
    document.querySelectorAll('textarea, input[type="text"]').forEach(function(el) {
      lines.push('TAG:' + el.tagName + ' PH:"' + el.placeholder + '" CLASS:' + el.className.substring(0,80));
      var p = el;
      for (var i = 0; i < 8 && p.parentElement; i++) {
        p = p.parentElement;
        lines.push('  p' + i + ': ' + p.tagName + '.' + (p.className||'').substring(0,80));
      }
    });

    // Find suggestion cards
    lines.push('\n=== SUGGESTIONS ===');
    document.querySelectorAll('*').forEach(function(el) {
      var t = el.textContent.trim();
      if ((t.includes('Help me study') || t.includes('code snippet') || t.includes('ideas')) && el.children.length <= 3) {
        lines.push(el.tagName + '.' + (el.className||'').substring(0,60) + ' => "' + t.substring(0,50) + '"');
      }
    });

    // Bottom user
    lines.push('\n=== USER INFO ===');
    document.querySelectorAll('*').forEach(function(el) {
      var t = el.textContent.trim();
      if (t.includes('Lucas') && el.children.length <= 2 && t.length < 30) {
        lines.push(el.tagName + '.' + (el.className||'').substring(0,60) + ' => "' + t + '"');
      }
    });

    // Logo
    lines.push('\n=== LOGO ===');
    document.querySelectorAll('#logo, [id*="logo"], [class*="logo"], [class*="Logo"]').forEach(function(el) {
      lines.push(el.tagName + '#' + el.id + '.' + (el.className||'').substring(0,80) + ' src=' + (el.src||''));
    });

    // Model name
    lines.push('\n=== MODEL ===');
    document.querySelectorAll('*').forEach(function(el) {
      var t = el.textContent.trim();
      if ((t.includes('gemma') || t.includes(':latest')) && t.length < 60 && el.children.length <= 1) {
        lines.push(el.tagName + '.' + (el.className||'').substring(0,60) + ' => "' + t + '"');
      }
    });

    // Create hidden div with report
    var div = document.createElement('div');
    div.id = 'dom-report';
    div.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:white;z-index:99999;overflow:auto;padding:20px;font-family:monospace;font-size:12px;white-space:pre-wrap;';
    div.textContent = lines.join('\n');
    document.body.appendChild(div);
  }

  var tries = 0;
  var timer = setInterval(function() {
    if (document.querySelector('nav') || document.querySelector('textarea') || tries > 30) {
      clearInterval(timer);
      setTimeout(inspect, 1000);
    }
    tries++;
  }, 500);
})();
