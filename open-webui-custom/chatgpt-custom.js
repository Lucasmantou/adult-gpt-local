/* ===== ChatGPT Custom JavaScript ===== */

// Wait for DOM to be ready
document.addEventListener('DOMContentLoaded', function() {
  // Create mutation observer to watch for DOM changes
  const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      // Check for greeting text
      const greetingElements = document.querySelectorAll('h1, h2, [class*="welcome"], [class*="greeting"], [class*="Welcome"], [class*="Greeting"]');
      greetingElements.forEach(function(el) {
        if (el.textContent && el.textContent.includes('你好') || el.textContent.includes('hello') || el.textContent.includes('Hello')) {
          el.textContent = '我能帮什么忙吗，Lucas？';
          el.style.textAlign = 'center';
          el.style.fontSize = '28px';
          el.style.fontWeight = '600';
        }
      });

      // Hide suggestion cards
      const suggestionCards = document.querySelectorAll('[class*="suggestion"], [class*="Suggestion"], [class*="card"], [class*="Card"]');
      suggestionCards.forEach(function(card) {
        if (card.querySelector('h3') || card.querySelector('h4') || card.textContent.includes('尝试问')) {
          card.style.display = 'none';
        }
      });

      // Hide model name in messages
      const modelNames = document.querySelectorAll('[class*="model-name"], [class*="modelName"], [class*="model"], [class*="Model"]');
      modelNames.forEach(function(el) {
        if (el.textContent && (el.textContent.includes('gemma') || el.textContent.includes('model') || el.textContent.includes('llama'))) {
          el.style.display = 'none';
        }
      });
    });
  });

  // Start observing
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true
  });

  // Function to add action buttons
  function addActionButtons() {
    // Find input area
    const inputArea = document.querySelector('textarea, input[type="text"], [class*="input"], [class*="Input"]');
    if (!inputArea) return;

    // Check if buttons already exist
    if (document.querySelector('.chatgpt-actions')) return;

    // Create buttons container
    const buttonsContainer = document.createElement('div');
    buttonsContainer.className = 'chatgpt-actions';
    buttonsContainer.style.cssText = 'display: flex; justify-content: center; gap: 12px; margin-top: 16px;';

    // Button data
    const buttons = [
      { text: '生成图片', icon: '🎨' },
      { text: '撰写或编辑', icon: '✏️' },
      { text: '查找资料', icon: '🔍' }
    ];

    // Create buttons
    buttons.forEach(function(btn) {
      const button = document.createElement('button');
      button.className = 'chatgpt-action-btn';
      button.innerHTML = '<span>' + btn.icon + '</span> ' + btn.text;
      button.onclick = function() {
        // Fill input with button text
        const textarea = document.querySelector('textarea');
        if (textarea) {
          textarea.value = btn.text;
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
      };
      buttonsContainer.appendChild(button);
    });

    // Insert after input area
    inputArea.parentNode.insertBefore(buttonsContainer, inputArea.nextSibling);
  }

  // Try to add buttons periodically
  let attempts = 0;
  const maxAttempts = 50;
  const interval = setInterval(function() {
    if (attempts >= maxAttempts) {
      clearInterval(interval);
      return;
    }

    addActionButtons();
    attempts++;
  }, 1000);

  // Also try immediately
  setTimeout(addActionButtons, 2000);
});
