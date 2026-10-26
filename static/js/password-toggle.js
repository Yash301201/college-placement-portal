(function () {
  function addPasswordToggle(input) {
    if (input.dataset.passwordToggleReady === "true") return;
    input.dataset.passwordToggleReady = "true";

    const wrapper = document.createElement("div");
    wrapper.className = "password-input-wrap";
    input.parentNode.insertBefore(wrapper, input);
    wrapper.appendChild(input);

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "password-visibility-toggle";
    toggle.textContent = "Show";
    toggle.setAttribute("aria-label", "Show password");
    toggle.setAttribute("aria-pressed", "false");
    if (input.id) toggle.setAttribute("aria-controls", input.id);

    toggle.addEventListener("click", function () {
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      toggle.textContent = isHidden ? "Hide" : "Show";
      toggle.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
      toggle.setAttribute("aria-pressed", String(isHidden));
    });

    wrapper.appendChild(toggle);
  }

  function initializePasswordToggles() {
    document.querySelectorAll('input[type="password"]').forEach(addPasswordToggle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePasswordToggles, { once: true });
  } else {
    initializePasswordToggles();
  }
})();