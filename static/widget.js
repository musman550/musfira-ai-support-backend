/*
 * Embeddable support widget.
 * Usage (paste this exact line into any page, anywhere in the HTML):
 *   <script src="https://<your-deployed-backend>/widget.js"></script>
 * That's it — no other setup needed. The script auto-detects its own
 * backend URL from its own <script src>, so nothing needs to be edited.
 *
 * Layout is done with CSS (not JS measurements), so it stays inside the
 * screen at any size, and keeps adapting if the window is resized or a
 * phone is rotated after the page has loaded:
 *   - roomy screens: a floating panel above the bottom-right icon
 *   - phones / short screens: the chat goes full-screen, and the icon is
 *     hidden while it is open (the chat has its own close button), so the
 *     icon can never cover the Send button.
 */
(function () {
  "use strict";

  var thisScript = document.currentScript;
  var backendOrigin = (function () {
    try {
      return new URL(thisScript.src).origin;
    } catch (e) {
      return window.location.origin;
    }
  })();

  function injectStyles() {
    if (document.getElementById("musfira-widget-styles")) return;
    var css = [
      "#musfira-widget-launcher{position:fixed;bottom:20px;right:20px;width:60px;height:60px;",
      "border-radius:50%;border:none;padding:0;background:linear-gradient(120deg,#6c5ce7,#00d9c0);",
      "color:#fff;font-size:26px;line-height:60px;text-align:center;cursor:pointer;",
      "box-shadow:0 8px 24px rgba(0,0,0,0.35);z-index:2147483000;transition:transform .15s ease;}",
      "#musfira-widget-launcher:hover{transform:scale(1.08);}",
      "#musfira-widget-panel{position:fixed;z-index:2147482999;display:none;",
      "bottom:92px;right:20px;",
      "width:min(380px,calc(100vw - 40px));",
      "height:min(600px,calc(100vh - 112px));height:min(600px,calc(100dvh - 112px));",
      "border-radius:18px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.4);",
      "opacity:0;transform:translateY(12px);transition:opacity .18s ease,transform .18s ease;}",
      "#musfira-widget-panel iframe{width:100%;height:100%;border:none;display:block;}",
      /* phones and short (landscape) screens: full-screen, launcher hidden while open */
      "@media (max-width:479px),(max-height:500px){",
      "#musfira-widget-panel{inset:0;bottom:0;right:0;width:auto;height:auto;border-radius:0;}",
      "#musfira-widget-launcher.musfira-open{display:none;}",
      "}"
    ].join("");
    var style = document.createElement("style");
    style.id = "musfira-widget-styles";
    style.appendChild(document.createTextNode(css));
    document.head.appendChild(style);
  }

  function build() {
    if (document.getElementById("musfira-widget-launcher")) return; // avoid double-init

    injectStyles();

    var launcher = document.createElement("button");
    launcher.id = "musfira-widget-launcher";
    launcher.type = "button";
    launcher.setAttribute("aria-label", "Open support chat");
    launcher.textContent = "💬";

    var panel = document.createElement("div");
    panel.id = "musfira-widget-panel";

    var iframe = document.createElement("iframe");
    iframe.src = backendOrigin + "/";
    iframe.title = "Support chat";
    panel.appendChild(iframe);

    var open = false;
    function setOpen(next) {
      open = next;
      if (open) {
        panel.style.display = "block";
        requestAnimationFrame(function () {
          panel.style.opacity = "1";
          panel.style.transform = "translateY(0)";
        });
        launcher.textContent = "✕";
        launcher.classList.add("musfira-open");
        launcher.setAttribute("aria-label", "Close support chat");
      } else {
        panel.style.opacity = "0";
        panel.style.transform = "translateY(12px)";
        launcher.textContent = "💬";
        launcher.classList.remove("musfira-open");
        launcher.setAttribute("aria-label", "Open support chat");
        setTimeout(function () { if (!open) panel.style.display = "none"; }, 180);
      }
    }
    launcher.addEventListener("click", function () { setOpen(!open); });

    // The chat page (inside the iframe) has its own close button; it asks us to close via postMessage.
    window.addEventListener("message", function (e) {
      if (e.origin !== backendOrigin) return;
      if (e.data && e.data.musfira === "close") setOpen(false);
    });

    document.body.appendChild(panel);
    document.body.appendChild(launcher);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
