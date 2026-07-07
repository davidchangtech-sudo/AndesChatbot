(function () {
  "use strict";

  var script = document.currentScript;
  var apiUrl =
    (window.ANDES_CHAT_CONFIG && window.ANDES_CHAT_CONFIG.apiUrl) ||
    (script && script.src ? new URL(script.src).origin : "");

  if (!apiUrl) {
    console.error("[Andes Chat] Missing apiUrl");
    return;
  }

  var C = {
    primary: "#00709e",
    primaryDark: "#004561",
    bg: "#f4f8fa",
    userBubble: "#00709e",
    botBubble: "#ffffff",
    text: "#333",
    muted: "#777",
    border: "#e6e6e6",
  };

  var cfg = window.ANDES_CHAT_CONFIG || {};
  var widgetBase = "";
  if (script && script.src) {
    var scriptUrl = new URL(script.src, window.location.href);
    widgetBase = scriptUrl.origin + scriptUrl.pathname.replace(/\/[^/]*$/, "");
  }
  var logoUrl =
    cfg.logoUrl ||
    (apiUrl ? apiUrl + "/static/assets/andes-logo.png" : widgetBase + "/assets/andes-logo.png");
  var logoWhiteUrl =
    cfg.logoWhiteUrl ||
    (apiUrl
      ? apiUrl + "/static/assets/andes-logo-white.png"
      : widgetBase + "/assets/andes-logo-white.png");
  var launcherImageUrl = cfg.launcherImageUrl || null;
  var siteLinks = cfg.siteLinks || [
    { label: "Products", url: "https://www.andestech.com/en/products/" },
    { label: "Solutions", url: "https://www.andestech.com/en/applications/" },
    { label: "About", url: "https://www.andestech.com/en/about/" },
  ];

  var siteLinksHtml = siteLinks
    .map(function (l) {
      return (
        '<a href="' +
        l.url +
        '" target="_blank" rel="noopener noreferrer">' +
        l.label +
        "</a>"
      );
    })
    .join("");

  var CHAT_STATE_KEY = "andes_chat_state";
  var CHAT_TTL_MS = 30 * 60 * 1000;

  function newSessionId() {
    return "s_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  function loadChatState() {
    try {
      var raw = localStorage.getItem(CHAT_STATE_KEY);
      if (raw) {
        var st = JSON.parse(raw);
        if (st && st.lastActivityAt && Date.now() - st.lastActivityAt < CHAT_TTL_MS) {
          return {
            sessionId: st.sessionId || newSessionId(),
            userMsgCount: st.userMsgCount || 0,
            messages: Array.isArray(st.messages) ? st.messages : [],
            conversationSummary: typeof st.conversationSummary === "string" ? st.conversationSummary : "",
          };
        }
        localStorage.removeItem(CHAT_STATE_KEY);
      }
    } catch (e) {}
    try {
      localStorage.removeItem("andes_chat_session");
    } catch (e2) {}
    return { sessionId: newSessionId(), userMsgCount: 0, messages: [], conversationSummary: "" };
  }

  function saveChatState() {
    try {
      localStorage.setItem(
        CHAT_STATE_KEY,
        JSON.stringify({
          sessionId: sessionId,
          messages: chatHistory,
          userMsgCount: userMsgCount,
          conversationSummary: conversationSummary,
          lastActivityAt: Date.now(),
        })
      );
    } catch (e) {}
  }

  try {
    localStorage.removeItem("andes_chat_panel_size");
    localStorage.removeItem("andes_chat_panel_size_v2");
  } catch (e) {}

  var chatBoot = loadChatState();
  var sessionId = chatBoot.sessionId;
  var userMsgCount = chatBoot.userMsgCount;
  var chatHistory = chatBoot.messages;
  var conversationSummary = chatBoot.conversationSummary || "";

  var launcherTooltip = cfg.launcherTooltip || "Chat with the Andes AI Assistant";

  var launcherBubbleSvg =
    '<svg class="andes-launcher-svg" viewBox="0 0 72 72" aria-hidden="true">' +
    "<defs>" +
    '<linearGradient id="andes-launcher-grad" x1="18%" y1="0%" x2="82%" y2="100%">' +
    '<stop offset="0%" stop-color="#0a8bb8"/><stop offset="50%" stop-color="#00709e"/><stop offset="100%" stop-color="#004561"/>' +
    "</linearGradient></defs>" +
    '<path fill="url(#andes-launcher-grad)" d="M36 8 A28 28 0 1 0 64 36 A28 28 0 1 0 46 62 L48 70 L57 54 A28 28 0 1 0 8 36 A28 28 0 1 0 36 8 Z"/>' +
    "</svg>";

  var launcherBubbleHtml = launcherImageUrl
    ? '<span class="andes-bubble-launcher-inner">' +
      '<span class="andes-launcher-tooltip" role="tooltip">' +
      launcherTooltip +
      "</span>" +
      '<img src="' +
      launcherImageUrl +
      '" alt="Open Andes AI Assistant" class="andes-launcher-chip-img" width="72" height="72" /></span>'
    : '<span class="andes-bubble-launcher-inner">' +
      '<span class="andes-launcher-tooltip" role="tooltip">' +
      launcherTooltip +
      "</span>" +
      '<span class="andes-speech-bubble andes-launcher-chip" role="presentation">' +
      launcherBubbleSvg +
      '<img src="' +
      logoWhiteUrl +
      '" alt="Andes Technology" class="andes-launcher-logo" /></span></span>';

  var font = '"Helvetica Neue",Helvetica,Arial,sans-serif';

  var styles =
    "#andes-chat-root{font-family:" +
    font +
    ";font-size:15px;z-index:99999;-webkit-font-smoothing:antialiased}" +
    "#andes-chat-backdrop{position:fixed;inset:0;background:rgba(0,22,31,.5);z-index:100000;opacity:0;pointer-events:none;transition:opacity .2s ease}" +
    "#andes-chat-backdrop.visible{opacity:1;pointer-events:auto}" +
    "#andes-chat-btn{position:fixed;right:20px;bottom:20px;z-index:100003;border:none;cursor:pointer;padding:0;background:transparent;overflow:visible}" +
    "#andes-chat-btn.panel-open{opacity:0;pointer-events:none}" +
    ".andes-bubble-launcher{display:block;animation:andes-float 2.8s ease-in-out infinite;transform-origin:center bottom}" +
    ".andes-bubble-launcher-inner{position:relative;display:inline-block;overflow:visible}" +
    "#andes-chat-btn:hover .andes-bubble-launcher{animation-duration:2.2s}" +
    "#andes-chat-btn:hover .andes-speech-bubble{transform:scale(1.05)}" +
    "#andes-chat-btn:hover .andes-launcher-tooltip{opacity:1;visibility:visible;transform:translate(-10px,-50%)}" +
    "#andes-chat-btn.panel-open .andes-launcher-tooltip{display:none}" +
    ".andes-launcher-tooltip{position:absolute;right:calc(100% + 8px);top:50%;transform:translate(4px,-50%);opacity:0;visibility:hidden;transition:opacity .2s ease,transform .2s ease,visibility .2s;white-space:nowrap;background:" +
    C.primaryDark +
    ";color:#fff;padding:9px 14px;border-radius:12px;font-size:13px;font-weight:600;line-height:1.3;box-shadow:0 6px 18px rgba(0,70,97,.35);pointer-events:none;z-index:1}" +
    ".andes-launcher-tooltip::after{content:\"\";position:absolute;right:-6px;top:50%;margin-top:-6px;border:6px solid transparent;border-left-color:" +
    C.primaryDark +
    "}" +
    ".andes-speech-bubble{position:relative;display:block;transition:transform .25s ease}" +
    ".andes-launcher-chip{position:relative;display:inline-block;width:72px;height:72px;overflow:visible}" +
    ".andes-launcher-chip-img{display:block;width:72px;height:72px;object-fit:contain;filter:drop-shadow(0 4px 12px rgba(0,70,97,.35));transition:transform .25s ease}" +
    "#andes-chat-btn:hover .andes-launcher-chip-img{transform:scale(1.05)}" +
    ".andes-launcher-svg{display:block;width:72px;height:72px;overflow:visible}" +
    ".andes-launcher-logo{position:absolute;left:50%;top:36px;width:38px;height:auto;max-height:14px;transform:translate(-50%,-50%);object-fit:contain;pointer-events:none}" +
    "@keyframes andes-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}" +
    "#andes-chat-panel{display:none;position:fixed;right:20px;bottom:20px;width:400px;max-width:calc(100vw - 24px);height:min(720px,calc(100vh - 40px));max-height:calc(100vh - 40px);" +
    "background:" +
    C.bg +
    ";border-radius:16px;box-shadow:0 12px 40px rgba(0,22,31,.2);flex-direction:column;overflow:hidden;z-index:100001;border:1px solid " +
    C.border +
    ";opacity:0;transform:translateY(10px);transition:opacity .2s ease,transform .2s ease}" +
    "#andes-chat-panel.open{display:flex;opacity:1;transform:translateY(0)}" +
    "#andes-chat-panel.andes-user-sized.open{transform:none}" +
    "#andes-chat-panel.andes-resizing{transition:none;user-select:none}" +
    "#andes-chat-panel.andes-user-sized{right:auto;bottom:auto;max-width:none;max-height:none}" +
    "#andes-chat-panel.andes-no-transition{transition:none !important}" +
    "#andes-chat-panel.andes-expanded{top:50%;left:50%;right:auto;bottom:auto;width:min(520px,94vw);height:min(700px,90vh);max-height:90vh;z-index:100002}" +
    "#andes-chat-panel.andes-expanded.open{transform:translate(-50%,-50%)}" +
    ".andes-resize-layer{position:absolute;inset:0;z-index:40;pointer-events:none}" +
    ".andes-resize-handle{position:absolute;pointer-events:auto;background:transparent}" +
    ".andes-resize-n{top:-4px;left:14px;right:14px;height:10px;cursor:ns-resize}" +
    ".andes-resize-s{bottom:-4px;left:14px;right:14px;height:10px;cursor:ns-resize}" +
    ".andes-resize-e{right:-4px;top:14px;bottom:14px;width:10px;cursor:ew-resize}" +
    ".andes-resize-w{left:-4px;top:14px;bottom:14px;width:10px;cursor:ew-resize}" +
    ".andes-resize-nw{top:-5px;left:-5px;width:16px;height:16px;cursor:nwse-resize}" +
    ".andes-resize-ne{top:-5px;right:-5px;width:16px;height:16px;cursor:nesw-resize}" +
    ".andes-resize-sw{bottom:-5px;left:-5px;width:16px;height:16px;cursor:nesw-resize}" +
    ".andes-resize-se{bottom:-5px;right:-5px;width:16px;height:16px;cursor:nwse-resize}" +
    "body.andes-chat-modal-open{overflow:hidden}" +
    "#andes-chat-header{background:linear-gradient(135deg," +
    C.primary +
    "," +
    C.primaryDark +
    ");color:#fff;padding:8px 12px 6px;position:relative;flex-shrink:0}" +
    "#andes-chat-header-actions{position:absolute;right:8px;top:8px;display:flex;gap:4px;z-index:50}" +
    "#andes-chat-close,#andes-chat-expand,#andes-chat-refresh{width:28px;height:28px;border:none;border-radius:6px;background:rgba(255,255,255,.2);color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center}" +
    "#andes-chat-header .andes-header-brand{padding-right:100px}" +
    "#andes-chat-header .andes-header-logo{height:24px;width:auto}" +
    "#andes-chat-header .andes-header-title{margin:4px 0 0;font-size:13px;font-weight:600;color:#fff;letter-spacing:.01em}" +
    "#andes-chat-header .andes-header-tagline{margin:1px 0 0;font-size:10px;font-weight:400;color:rgba(255,255,255,.85);line-height:1.25}" +
    "#andes-chat-messages{flex:1 1 auto;min-height:0;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px}" +
    ".andes-row{display:flex;gap:8px;align-items:flex-end;opacity:0;animation:andes-fade .18s ease forwards}" +
    "@keyframes andes-fade{to{opacity:1}}" +
    ".andes-row.user{align-self:flex-end;max-width:88%}" +
    ".andes-row.bot{align-self:flex-start;max-width:92%}" +
    ".andes-bubble{padding:10px 14px;border-radius:14px;line-height:1.5;white-space:pre-wrap;overflow-wrap:break-word}" +
    ".andes-row.user .andes-bubble{background:" +
    C.userBubble +
    ";color:#fff;border-bottom-right-radius:4px}" +
    ".andes-row.bot .andes-bubble{background:" +
    C.botBubble +
    ";color:" +
    C.text +
    ";border:1px solid " +
    C.border +
    ";border-bottom-left-radius:4px}" +
    ".andes-avatar{width:28px;height:28px;border-radius:50%;background:#fff;border:1px solid " +
    C.border +
    ";display:flex;align-items:center;justify-content:center;flex-shrink:0;overflow:hidden}" +
    ".andes-avatar svg{width:22px;height:22px}" +
    ".andes-readmore-wrap{margin-left:34px;max-width:92%}" +
    ".andes-readmore-wrap a{display:inline-flex;align-items:center;gap:4px;font-size:12px;font-weight:600;color:" +
    C.primary +
    ";background:#fff;border:1px solid " +
    C.border +
    ";padding:6px 12px;border-radius:999px;text-decoration:none}" +
    ".andes-readmore-wrap a:hover{background:#e8f4f8;border-color:" +
    C.primary +
    "}" +
    ".andes-media-wrap{margin-left:34px;max-width:92%;margin-top:2px}" +
    ".andes-media-wrap img{display:block;max-width:100%;max-height:200px;width:auto;border-radius:10px;border:1px solid " +
    C.border +
    ";background:#fff;object-fit:contain}" +
    ".andes-media-wrap figcaption{font-size:10px;color:" +
    C.muted +
    ";margin-top:4px;line-height:1.3}" +
    "#andes-site-links{display:flex;flex-wrap:wrap;gap:5px;padding:6px 12px 8px;background:rgba(255,255,255,.1);border-bottom:1px solid rgba(255,255,255,.12)}" +
    "#andes-site-links a{font-size:11px;color:#fff;text-decoration:none;padding:4px 9px;border-radius:999px;background:rgba(255,255,255,.15);white-space:nowrap}" +
    "#andes-site-links a:hover{background:rgba(255,255,255,.28)}" +
    "#andes-chat-footer{flex-shrink:0;background:#fff;border-top:1px solid " +
    C.border +
    ";padding-bottom:2px}" +
    "#andes-chat-disclaimer{font-size:10px;color:" +
    C.muted +
    ";text-align:center;margin:0;padding:0 12px 8px;line-height:1.35}" +
    "#andes-lead-panel{display:none;flex-direction:column;flex-shrink:0;max-height:42%;overflow-y:auto;padding:12px;background:#fff;border-top:1px solid " +
    C.border +
    "}" +
    "#andes-lead-panel.show{display:flex}" +
    "#andes-lead-panel .andes-lead-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:4px}" +
    "#andes-lead-panel .andes-lead-head h3{margin:0;flex:1}" +
    "#andes-lead-close{background:transparent;border:none;color:" +
    C.muted +
    ";font-size:22px;line-height:1;padding:0 4px;cursor:pointer;border-radius:4px}" +
    "#andes-lead-close:hover{color:" +
    C.primaryDark +
    "}" +
    "#andes-lead-panel .andes-meeting-row{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:4px}" +
    "#andes-lead-panel .andes-meeting-row label{grid-column:span 1}" +
    "#andes-lead-panel .andes-meeting-row input{grid-column:span 1}" +
    "#andes-lead-panel h3{margin:0;font-size:15px;color:" +
    C.primaryDark +
    "}" +
    "#andes-lead-panel .andes-lead-sub{margin:0 0 10px;font-size:12px;color:" +
    C.muted +
    "}" +
    "#andes-lead-panel label{font-size:12px;color:" +
    C.muted +
    ";display:block;margin:8px 0 4px}" +
    "#andes-lead-panel input,#andes-lead-panel select,#andes-lead-panel textarea{width:100%;padding:9px 10px;border:1px solid " +
    C.border +
    ";border-radius:8px;font-size:14px;font-family:inherit;box-sizing:border-box}" +
    "#andes-lead-panel input.andes-invalid{border-color:#c62828;background:#fff8f8;box-shadow:0 0 0 1px #ffcdd2}" +
    "#andes-lead-panel input.andes-invalid:focus{border-color:#c62828;outline:none}" +
    ".andes-field-error-msg{display:none;color:#c62828;font-size:12px;margin:-2px 0 8px;line-height:1.35}" +
    ".andes-field-error-msg.show{display:block}" +
    "#andes-lead-message{min-height:72px;padding:12px;line-height:1.45;resize:vertical}" +
    "#andes-lead-submit{margin-top:10px;background:" +
    C.primary +
    ";color:#fff;border:none;border-radius:8px;padding:12px;font-weight:600;cursor:pointer;width:100%}" +
    "#andes-lead-submit:disabled{opacity:.65;cursor:not-allowed}" +
    "#andes-lead-success{display:none;flex-direction:column;gap:10px}" +
    "#andes-lead-success.show{display:flex}" +
    "#andes-lead-success .andes-success-icon{width:44px;height:44px;border-radius:50%;background:#e8f4f8;color:" +
    C.primary +
    ";display:flex;align-items:center;justify-content:center;font-size:22px;font-weight:700;margin:4px auto 0}" +
    "#andes-lead-success h3{margin:0;text-align:center;font-size:16px;color:" +
    C.primaryDark +
    "}" +
    "#andes-lead-success .andes-success-sub{margin:0;text-align:center;font-size:13px;color:" +
    C.muted +
    "}" +
    "#andes-lead-done{margin-top:4px;background:" +
    C.primary +
    ";color:#fff;border:none;border-radius:8px;padding:12px;font-weight:600;cursor:pointer;width:100%}" +
    "#andes-lead-form-fields{display:flex;flex-direction:column}" +
    "#andes-lead-form-fields.hide{display:none}" +
    "#andes-lead-bar{display:flex;gap:6px;padding:10px 12px 6px;background:transparent;border:none}" +
    "#andes-lead-bar button{flex:1;background:#fff;border:1px solid " +
    C.primary +
    ";color:" +
    C.primary +
    ";border-radius:8px;padding:8px;font-size:13px;font-weight:600;cursor:pointer}" +
    "#andes-lead-bar button.active{background:" +
    C.primary +
    ";color:#fff}" +
    "#andes-chat-form{display:flex;gap:8px;padding:10px 12px 12px;background:#fff;align-items:flex-end;border-top:1px solid " +
    C.border +
    "}" +
    "#andes-chat-input{flex:1;border:1px solid " +
    C.border +
    ";border-radius:10px;padding:10px 12px;font-size:15px;resize:none;min-height:42px;max-height:96px;font-family:inherit;outline:none}" +
    "#andes-chat-input:focus{border-color:" +
    C.primary +
    "}" +
    "#andes-chat-send{width:40px;height:40px;border:none;border-radius:10px;background:" +
    C.primary +
    ";color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0}" +
    ".andes-typing{display:flex;gap:8px;padding:4px 0;opacity:.7}" +
    ".andes-typing span{width:6px;height:6px;background:" +
    C.primary +
    ";border-radius:50%;animation:andes-blink 1s ease-in-out infinite}" +
    ".andes-typing span:nth-child(2){animation-delay:.15s}" +
    ".andes-typing span:nth-child(3){animation-delay:.3s}" +
    "@keyframes andes-blink{0%,100%{opacity:.25}50%{opacity:1}}";

  var root = document.createElement("div");
  root.id = "andes-chat-root";
  root.innerHTML =
    "<style>" +
    styles +
    "</style>" +
    '<div id="andes-chat-backdrop"></div>' +
    '<button type="button" id="andes-chat-btn" aria-label="Open Andes AI Assistant">' +
    '<span class="andes-bubble-launcher">' +
    launcherBubbleHtml +
    "</span></button>" +
    '<div id="andes-chat-panel" role="dialog">' +
    '<div id="andes-chat-header">' +
    '<div id="andes-chat-header-actions">' +
    '<button type="button" id="andes-chat-refresh" aria-label="Start new chat"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg></button>' +
    '<button type="button" id="andes-chat-expand" aria-label="Enlarge"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg></button>' +
    '<button type="button" id="andes-chat-close" aria-label="Close">×</button></div>' +
    '<div class="andes-header-brand"><img src="' +
    logoWhiteUrl +
    '" alt="" class="andes-header-logo" /><p class="andes-header-title">Andes AI Assistant</p>' +
    '<p class="andes-header-tagline">Product guidance &amp; support</p></div>' +
    '<nav id="andes-site-links" aria-label="Andes website">' +
    siteLinksHtml +
    "</nav></div>" +
    '<div id="andes-chat-messages"></div>' +
    '<div id="andes-lead-panel">' +
    '<div class="andes-lead-head"><h3>Book a meeting</h3><button type="button" id="andes-lead-close" aria-label="Close form">×</button></div>' +
    '<div id="andes-lead-success">' +
    '<div class="andes-success-icon" aria-hidden="true">✓</div>' +
    "<h3>Meeting requested!</h3>" +
    '<p class="andes-success-sub">We received your preferred time. Our team will confirm by email soon.</p>' +
    '<button type="button" id="andes-lead-done">Back to chat</button></div>' +
    '<div id="andes-lead-form-fields">' +
    '<input type="text" id="andes-hp" tabindex="-1" autocomplete="off" aria-hidden="true" style="position:absolute;left:-9999px;width:1px;height:1px;opacity:0;pointer-events:none" />' +
    '<p class="andes-lead-sub">Choose a date and time — we\'ll confirm with you by email.</p>' +
    "<label>Name *</label><input id=\"andes-lead-name\" autocomplete=\"name\" />" +
    "<label for=\"andes-lead-email\">Work email *</label><input id=\"andes-lead-email\" type=\"email\" autocomplete=\"email\" aria-describedby=\"andes-lead-email-error\" />" +
    '<p id="andes-lead-email-error" class="andes-field-error-msg" role="alert">Please enter a valid email address.</p>' +
    "<label>Phone <span style=\"font-weight:400;color:" +
    C.muted +
    "\">(optional)</span></label><input id=\"andes-lead-phone\" type=\"tel\" autocomplete=\"tel\" placeholder=\"+1 555 123 4567\" />" +
    "<label>Company</label><input id=\"andes-lead-company\" autocomplete=\"organization\" />" +
    '<div class="andes-meeting-row">' +
    "<label for=\"andes-lead-date\">Preferred date *</label>" +
    "<label for=\"andes-lead-time\">Preferred time *</label>" +
    '<input type="date" id="andes-lead-date" />' +
    '<input type="time" id="andes-lead-time" step="900" />' +
    "</div>" +
    "<label>I'm interested in</label>" +
    '<select id="andes-lead-interest"><option value="">Select…</option>' +
    "<option>Product demo</option><option>Licensing / quote</option><option>Partnership</option>" +
    "<option>Technical support</option><option>Other</option></select>" +
    "<label>Notes</label><textarea id=\"andes-lead-message\" rows=\"4\" placeholder=\"What would you like to discuss?\"></textarea>" +
    '<button type="button" id="andes-lead-submit">Book meeting</button></div></div>' +
    '<form id="andes-chat-form">' +
    '<textarea id="andes-chat-input" rows="1" placeholder="Ask the Andes AI Assistant…"></textarea>' +
    '<button type="submit" id="andes-chat-send" aria-label="Send"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg></button>' +
    "</form>" +
    '<div id="andes-chat-footer">' +
    '<div id="andes-lead-bar"><button type="button" id="andes-lead-bar-btn">Book a meeting</button></div>' +
    '<p id="andes-chat-disclaimer">AI can make mistakes. Verify important details before making decisions.</p></div>' +
    '<div class="andes-resize-layer" aria-hidden="true">' +
    '<div class="andes-resize-handle andes-resize-n" data-dir="n"></div>' +
    '<div class="andes-resize-handle andes-resize-s" data-dir="s"></div>' +
    '<div class="andes-resize-handle andes-resize-e" data-dir="e"></div>' +
    '<div class="andes-resize-handle andes-resize-w" data-dir="w"></div>' +
    '<div class="andes-resize-handle andes-resize-nw" data-dir="nw"></div>' +
    '<div class="andes-resize-handle andes-resize-ne" data-dir="ne"></div>' +
    '<div class="andes-resize-handle andes-resize-sw" data-dir="sw"></div>' +
    '<div class="andes-resize-handle andes-resize-se" data-dir="se"></div></div></div>';

  document.body.appendChild(root);

  var $ = function (id) {
    return document.getElementById(id);
  };
  var backdrop = $("andes-chat-backdrop");
  var btn = $("andes-chat-btn");
  var panel = $("andes-chat-panel");
  var messages = $("andes-chat-messages");
  var input = $("andes-chat-input");
  var form = $("andes-chat-form");
  var leadPanel = $("andes-lead-panel");
  var leadBarBtn = $("andes-lead-bar-btn");
  var lastUserRow = null;
  var lastChatAt = 0;
  var hpField = null;
  hpField = $("andes-hp");
  var expandBtn = $("andes-chat-expand");
  var expandOn =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/></svg>';
  var expandOff =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 14h6v6M20 10h-6V4M14 10l7-7M3 21l7-7"/></svg>';

  var botAvatarSvg =
    '<svg viewBox="0 0 32 32" aria-hidden="true">' +
    '<ellipse cx="16" cy="18" rx="9" ry="8" fill="#fff"/>' +
    '<ellipse cx="16" cy="12" rx="10" ry="9" fill="#fff"/>' +
    '<rect x="7" y="10" width="18" height="7" rx="4" fill="#004561"/>' +
    '<circle cx="12" cy="13" r="2.2" fill="#9ee5f7"/><circle cx="20" cy="13" r="2.2" fill="#9ee5f7"/>' +
    '<circle cx="12.5" cy="12.5" r=".9" fill="#fff"/><circle cx="20.5" cy="12.5" r=".9" fill="#fff"/>' +
    '<path d="M12 16 Q16 17.5 20 16" stroke="#004561" stroke-width=".9" fill="none" stroke-linecap="round"/>' +
    '<circle cx="16" cy="3" r="1.5" fill="#fff"/></svg>';

  function botAv() {
    return '<div class="andes-avatar">' + botAvatarSvg + "</div>";
  }

  function isLeadFormOpen() {
    return leadPanel.classList.contains("show");
  }

  function setMeetingDateMin() {
    var el = $("andes-lead-date");
    if (!el) return;
    el.min = new Date().toISOString().slice(0, 10);
  }

  function setLeadBarActive(on) {
    leadBarBtn.classList.toggle("active", on);
    leadBarBtn.setAttribute("aria-expanded", on ? "true" : "false");
    leadBarBtn.textContent = on ? "Close" : "Book a meeting";
  }

  var leadFormFields = $("andes-lead-form-fields");
  var leadSuccess = $("andes-lead-success");

  function resetLeadFormView() {
    leadSuccess.classList.remove("show");
    leadFormFields.classList.remove("hide");
    $("andes-lead-submit").disabled = false;
    $("andes-lead-submit").textContent = "Book meeting";
    clearEmailInvalid();
  }

  function closeLeadForm() {
    if (!isLeadFormOpen()) return;
    leadPanel.classList.remove("show");
    setLeadBarActive(false);
    resetLeadFormView();
  }

  function openLeadForm() {
    resetLeadFormView();
    setMeetingDateMin();
    leadPanel.classList.add("show");
    setLeadBarActive(true);
    $("andes-lead-name").focus();
  }

  function formatApiError(d) {
    if (!d || !d.detail) return "Could not send. Check your email and try again.";
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail)) {
      return d.detail
        .map(function (e) {
          return (e.msg || e.type || "") + (e.loc ? " (" + e.loc.join(".") + ")" : "");
        })
        .join(" ");
    }
    return "Could not send. Try again.";
  }

  function showLeadSuccess() {
    leadFormFields.classList.add("hide");
    leadSuccess.classList.add("show");
    setLeadBarActive(true);
    leadBarBtn.textContent = "Close";
  }

  var leadEmailInput = $("andes-lead-email");
  var leadEmailError = $("andes-lead-email-error");

  function isValidEmail(value) {
    if (!value) return false;
    return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(value);
  }

  function setEmailInvalid(on, message) {
    leadEmailInput.classList.toggle("andes-invalid", on);
    leadEmailInput.setAttribute("aria-invalid", on ? "true" : "false");
    if (message) leadEmailError.textContent = message;
    leadEmailError.classList.toggle("show", on);
  }

  function clearEmailInvalid() {
    setEmailInvalid(false);
  }

  leadEmailInput.addEventListener("input", clearEmailInvalid);
  leadEmailInput.addEventListener("blur", function () {
    var v = leadEmailInput.value.trim();
    if (v && !isValidEmail(v)) setEmailInvalid(true, "Please enter a valid email address.");
  });

  function toggleLeadForm() {
    if (isLeadFormOpen()) closeLeadForm();
    else openLeadForm();
  }

  function scrollRowToTop(row) {
    if (!row) return;
    var offset =
      row.getBoundingClientRect().top -
      messages.getBoundingClientRect().top +
      messages.scrollTop;
    messages.scrollTop = Math.max(0, offset - 8);
  }

  function appendMsg(text, role, skipRecord) {
    var row = document.createElement("div");
    row.className = "andes-row " + role;
    if (role === "bot") row.insertAdjacentHTML("afterbegin", botAv());
    var b = document.createElement("div");
    b.className = "andes-bubble";
    b.textContent = text;
    row.appendChild(b);
    messages.appendChild(row);
    if (!skipRecord && (role === "user" || role === "bot")) {
      chatHistory.push({
        role: role === "user" ? "user" : "assistant",
        content: text,
      });
      saveChatState();
    }
    if (role === "user") {
      lastUserRow = row;
      scrollRowToTop(row);
    } else if (role === "bot" && lastUserRow) {
      scrollRowToTop(lastUserRow);
    } else {
      messages.scrollTop = 0;
    }
    return row;
  }

  function clearChatSession() {
    chatHistory = [];
    userMsgCount = 0;
    conversationSummary = "";
    sessionId = newSessionId();
    messages.innerHTML = "";
    delete messages.dataset.welcomed;
    lastUserRow = null;
    try {
      localStorage.removeItem(CHAT_STATE_KEY);
    } catch (e) {}
  }

  function showWelcomeMessage() {
    messages.dataset.welcomed = "1";
    appendMsg(
      "Hello — I'm the Andes AI Assistant.\n\nI can help with our RISC-V processors, development tools, and solutions. Use the quick links above, or Book a meeting if you'd like to speak with our team.",
      "bot"
    );
  }

  function refreshChat() {
    closeLeadForm();
    setExpanded(false);
    clearChatSession();
    lastChatAt = 0;
    showWelcomeMessage();
    input.focus();
  }

  function ensureFreshChat() {
    try {
      var raw = localStorage.getItem(CHAT_STATE_KEY);
      if (!raw) return;
      var st = JSON.parse(raw);
      if (!st.lastActivityAt || Date.now() - st.lastActivityAt >= CHAT_TTL_MS) {
        clearChatSession();
      }
    } catch (e) {
      clearChatSession();
    }
  }

  if (chatHistory.length) {
    messages.dataset.welcomed = "1";
    chatHistory.forEach(function (m) {
      appendMsg(m.content, m.role === "user" ? "user" : "bot", true);
    });
  }

  function appendReadMore(link) {
    if (!link || !link.url) return;
    var w = document.createElement("div");
    w.className = "andes-readmore-wrap";
    var a = document.createElement("a");
    a.href = link.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = link.title || "Read more on our site";
    w.appendChild(a);
    messages.appendChild(w);
    if (lastUserRow) scrollRowToTop(lastUserRow);
  }

  function appendMedia(media) {
    if (!media || !media.url) return;
    var w = document.createElement("figure");
    w.className = "andes-media-wrap";
    var img = document.createElement("img");
    img.src = media.url;
    img.alt = media.alt || "From andestech.com";
    img.loading = "lazy";
    img.referrerPolicy = "no-referrer-when-downgrade";
    img.onerror = function () {
      w.remove();
    };
    w.appendChild(img);
    if (media.alt) {
      var cap = document.createElement("figcaption");
      cap.textContent = media.alt;
      w.appendChild(cap);
    }
    messages.appendChild(w);
    if (lastUserRow) scrollRowToTop(lastUserRow);
  }

  function showTyping() {
    var el = document.createElement("div");
    el.className = "andes-typing";
    el.id = "andes-typing-indicator";
    el.innerHTML = botAv() + "<span></span><span></span><span></span>";
    messages.appendChild(el);
    if (lastUserRow) scrollRowToTop(lastUserRow);
    return el;
  }

  function afterChatResponse(data) {
    if (data.suggest_lead_form) openLeadForm();
  }

  function honeypotValue() {
    return hpField ? (hpField.value || "").trim() : "";
  }

  function sendMessage() {
    var text = (input.value || "").trim();
    if (!text) return;
    var now = Date.now();
    if (now - lastChatAt < 800) return;
    lastChatAt = now;
    input.value = "";
    userMsgCount += 1;
    appendMsg(text, "user");
    requestChatReply(text, 0);
  }

  var CHAT_MAX_ATTEMPTS = 4;
  var CHAT_RETRY_DELAY_MS = 1200;

  function isRetryableChatStatus(status) {
    return status === 500 || status === 502 || status === 503 || status === 504;
  }

  function isRetryableChatReply(reply) {
    return !!reply && /having trouble|try again in a few seconds|assistant is busy/i.test(reply);
  }

  function removeTypingIndicator() {
    var el = document.getElementById("andes-typing-indicator");
    if (el) el.remove();
  }

  function scheduleChatRetry(text, attempt) {
    setTimeout(function () {
      requestChatReply(text, attempt + 1);
    }, CHAT_RETRY_DELAY_MS * (attempt + 1));
  }

  function chatHistoryPayload() {
    return chatHistory.slice(0, -1).slice(-20).map(function (m) {
      return { role: m.role, content: m.content };
    });
  }

  function appendStreamingBot() {
    var row = document.createElement("div");
    row.className = "andes-row bot";
    row.insertAdjacentHTML("afterbegin", botAv());
    var b = document.createElement("div");
    b.className = "andes-bubble";
    b.textContent = "";
    row.appendChild(b);
    messages.appendChild(row);
    if (lastUserRow) scrollRowToTop(lastUserRow);
    else messages.scrollTop = 0;
    return { row: row, bubble: b };
  }

  function finalizeStreamedBot(streamRow, reply) {
    streamRow.bubble.textContent = reply;
    chatHistory.push({ role: "assistant", content: reply });
    saveChatState();
    if (lastUserRow) scrollRowToTop(lastUserRow);
  }

  function applyChatMeta(data) {
    if (data.conversation_summary) {
      conversationSummary = data.conversation_summary;
      saveChatState();
    }
    if (data.read_more) appendReadMore(data.read_more);
    if (data.media) appendMedia(data.media);
    afterChatResponse(data);
  }

  function handleChatDone(data, streamRow, attempt, text) {
    if (isRetryableChatReply(data && data.reply) && attempt + 1 < CHAT_MAX_ATTEMPTS) {
      if (streamRow && streamRow.row.parentNode) streamRow.row.remove();
      scheduleChatRetry(text, attempt);
      return;
    }
    if (!data || !data.reply) {
      if (streamRow && streamRow.row.parentNode) streamRow.row.remove();
      if (attempt + 1 < CHAT_MAX_ATTEMPTS) {
        scheduleChatRetry(text, attempt);
        return;
      }
      appendMsg("Please try sending that again.", "bot");
      return;
    }
    if (streamRow) {
      finalizeStreamedBot(streamRow, data.reply);
    } else {
      appendMsg(data.reply, "bot");
    }
    applyChatMeta(data);
  }

  function requestChatReply(text, attempt) {
    if (!document.getElementById("andes-typing-indicator")) {
      showTyping();
    }
    fetch(apiUrl + "/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        user_message_count: userMsgCount,
        history: chatHistoryPayload(),
        conversation_summary: conversationSummary || null,
        website: honeypotValue(),
      }),
    })
      .then(function (r) {
        if (!r.ok) {
          if (r.status === 429) {
            throw { rateLimited: true };
          }
          if (isRetryableChatStatus(r.status) && attempt + 1 < CHAT_MAX_ATTEMPTS) {
            throw { retryable: true };
          }
          return r.text().then(function (body) {
            var d = {};
            try {
              d = body ? JSON.parse(body) : {};
            } catch (e) {
              d = {};
            }
            var detail = d.detail;
            if (typeof detail === "string") throw new Error(detail);
            throw new Error("Request failed (" + r.status + ")");
          });
        }
        if (!r.body || !r.body.getReader) {
          throw { fallback: true };
        }
        var reader = r.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";
        var streamRow = null;
        var doneData = null;

        function processLine(line) {
          line = (line || "").trim();
          if (!line) return;
          var evt;
          try {
            evt = JSON.parse(line);
          } catch (e) {
            return;
          }
          if (evt.type === "token" && evt.text) {
            if (!streamRow) {
              removeTypingIndicator();
              streamRow = appendStreamingBot();
            }
            streamRow.bubble.textContent += evt.text;
            if (lastUserRow) scrollRowToTop(lastUserRow);
          } else if (evt.type === "done") {
            doneData = evt;
          } else if (evt.type === "error") {
            throw { retryable: true };
          }
        }

        function pump() {
          return reader.read().then(function (result) {
            if (result.done) {
              if (buffer) processLine(buffer);
              removeTypingIndicator();
              handleChatDone(doneData, streamRow, attempt, text);
              return;
            }
            buffer += decoder.decode(result.value, { stream: true });
            var parts = buffer.split("\n");
            buffer = parts.pop() || "";
            parts.forEach(processLine);
            return pump();
          });
        }
        return pump();
      })
      .catch(function (err) {
        if (err && err.fallback) {
          return requestChatReplyFallback(text, attempt);
        }
        if (err && err.rateLimited) {
          removeTypingIndicator();
          appendMsg("Too many messages — please wait a moment and try again.", "bot");
          return;
        }
        if (attempt + 1 < CHAT_MAX_ATTEMPTS) {
          scheduleChatRetry(text, attempt);
          return;
        }
        removeTypingIndicator();
        appendMsg("Please try sending that again.", "bot");
      });
  }

  function requestChatReplyFallback(text, attempt) {
    fetch(apiUrl + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        user_message_count: userMsgCount,
        history: chatHistoryPayload(),
        conversation_summary: conversationSummary || null,
        website: honeypotValue(),
      }),
    })
      .then(function (r) {
        return r.text().then(function (body) {
          var d = {};
          try {
            d = body ? JSON.parse(body) : {};
          } catch (e) {
            d = {};
          }
          if (!r.ok) {
            if (r.status === 429) {
              throw { rateLimited: true };
            }
            if (isRetryableChatStatus(r.status) && attempt + 1 < CHAT_MAX_ATTEMPTS) {
              throw { retryable: true };
            }
            var detail = d.detail;
            if (typeof detail === "string") throw new Error(detail);
            if (Array.isArray(detail) && detail[0] && detail[0].msg) throw new Error(detail[0].msg);
            throw new Error("Request failed (" + r.status + ")");
          }
          return d;
        });
      })
      .then(function (data) {
        removeTypingIndicator();
        handleChatDone(data, null, attempt, text);
      })
      .catch(function (err) {
        if (err && err.rateLimited) {
          removeTypingIndicator();
          appendMsg("Too many messages — please wait a moment and try again.", "bot");
          return;
        }
        if (attempt + 1 < CHAT_MAX_ATTEMPTS) {
          scheduleChatRetry(text, attempt);
          return;
        }
        removeTypingIndicator();
        appendMsg("Please try sending that again.", "bot");
      });
  }

  var PANEL_MIN_W = 300;
  var PANEL_MIN_H = 380;

  function clampPanel(n, min, max) {
    return Math.min(max, Math.max(min, n));
  }

  function clearPanelInlineSize() {
    panel.classList.remove("andes-user-sized");
    panel.style.top = "";
    panel.style.left = "";
    panel.style.width = "";
    panel.style.height = "";
    panel.style.right = "";
    panel.style.bottom = "";
    panel.style.maxWidth = "";
    panel.style.maxHeight = "";
    panel.style.transform = "";
    delete panel.dataset.pinned;
  }

  function dockPanelDefault() {
    clearPanelInlineSize();
    panel.style.right = "20px";
    panel.style.bottom = "20px";
  }

  function pinPanelForResize() {
    if (panel.dataset.pinned === "1") return;
    var r = panel.getBoundingClientRect();
    panel.classList.add("andes-user-sized");
    panel.style.top = Math.round(r.top) + "px";
    panel.style.left = Math.round(r.left) + "px";
    panel.style.width = Math.round(r.width) + "px";
    panel.style.height = Math.round(r.height) + "px";
    panel.style.right = "auto";
    panel.style.bottom = "auto";
    panel.style.transform = "";
    panel.dataset.pinned = "1";
  }

  function setupPanelResize() {
    var handles = panel.querySelectorAll(".andes-resize-handle");
    handles.forEach(function (handle) {
      handle.addEventListener("mousedown", function (e) {
        if (!panel.classList.contains("open")) return;
        e.preventDefault();
        e.stopPropagation();
        var dir = handle.getAttribute("data-dir") || "";
        if (panel.classList.contains("andes-expanded")) {
          setExpanded(false);
        }
        pinPanelForResize();
        var startX = e.clientX;
        var startY = e.clientY;
        var startW = panel.offsetWidth;
        var startH = panel.offsetHeight;
        var startL = parseInt(panel.style.left, 10) || 0;
        var startT = parseInt(panel.style.top, 10) || 0;
        var maxW = window.innerWidth - 8;
        var maxH = window.innerHeight - 8;
        panel.classList.add("andes-resizing");
        document.body.style.cursor = window.getComputedStyle(handle).cursor;

        function onMove(ev) {
          var dx = ev.clientX - startX;
          var dy = ev.clientY - startY;
          var w = startW;
          var h = startH;
          var l = startL;
          var t = startT;
          if (dir.indexOf("e") >= 0) w = startW + dx;
          if (dir.indexOf("w") >= 0) {
            w = startW - dx;
            l = startL + dx;
          }
          if (dir.indexOf("s") >= 0) h = startH + dy;
          if (dir.indexOf("n") >= 0) {
            h = startH - dy;
            t = startT + dy;
          }
          w = clampPanel(w, PANEL_MIN_W, maxW);
          h = clampPanel(h, PANEL_MIN_H, maxH);
          if (dir.indexOf("w") >= 0) l = startL + (startW - w);
          if (dir.indexOf("n") >= 0) t = startT + (startH - h);
          l = clampPanel(l, 8, maxW - w);
          t = clampPanel(t, 8, maxH - h);
          panel.style.width = Math.round(w) + "px";
          panel.style.height = Math.round(h) + "px";
          panel.style.left = Math.round(l) + "px";
          panel.style.top = Math.round(t) + "px";
        }

        function onUp() {
          panel.classList.remove("andes-resizing");
          document.body.style.cursor = "";
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        }

        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  }

  function setExpanded(on) {
    panel.classList.add("andes-no-transition");
    if (on) {
      clearPanelInlineSize();
      panel.classList.add("andes-expanded");
    } else {
      panel.classList.remove("andes-expanded");
      dockPanelDefault();
    }
    backdrop.classList.toggle("visible", on);
    document.body.classList.toggle("andes-chat-modal-open", on);
    expandBtn.innerHTML = on ? expandOff : expandOn;
    requestAnimationFrame(function () {
      panel.classList.remove("andes-no-transition");
    });
  }

  function openPanel() {
    ensureFreshChat();
    panel.classList.add("open");
    btn.classList.add("panel-open");
    if (!panel.dataset.pinned) {
      dockPanelDefault();
    }
    setTimeout(function () {
      input.focus();
    }, 150);
    if (!messages.dataset.welcomed) {
      showWelcomeMessage();
    }
  }

  function closePanel() {
    panel.classList.remove("open");
    setExpanded(false);
    btn.classList.remove("panel-open");
  }

  btn.addEventListener("click", function () {
    panel.classList.contains("open") ? closePanel() : openPanel();
  });
  $("andes-chat-close").addEventListener("click", closePanel);
  $("andes-chat-refresh").addEventListener("click", refreshChat);
  expandBtn.addEventListener("click", function () {
    if (!panel.classList.contains("open")) openPanel();
    setExpanded(!panel.classList.contains("andes-expanded"));
  });
  backdrop.addEventListener("click", function () {
    setExpanded(false);
  });

  setupPanelResize();

  window.addEventListener("resize", function () {
    if (!panel.classList.contains("open") || panel.classList.contains("andes-expanded")) return;
    if (!panel.dataset.pinned) return;
    var maxW = window.innerWidth - 16;
    var maxH = window.innerHeight - 48;
    var w = parseInt(panel.style.width, 10) || panel.offsetWidth;
    var h = parseInt(panel.style.height, 10) || panel.offsetHeight;
    var t = parseInt(panel.style.top, 10) || 0;
    var l = parseInt(panel.style.left, 10) || 0;
    w = clampPanel(w, PANEL_MIN_W, maxW);
    h = clampPanel(h, PANEL_MIN_H, maxH);
    l = clampPanel(l, 8, Math.max(8, maxW - w));
    t = clampPanel(t, 8, Math.max(8, maxH - h));
    panel.style.width = Math.round(w) + "px";
    panel.style.height = Math.round(h) + "px";
    panel.style.top = Math.round(t) + "px";
    panel.style.left = Math.round(l) + "px";
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    sendMessage();
  });
  input.addEventListener(
    "keydown",
    function (e) {
      if ((e.key === "Enter" || e.keyCode === 13) && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    true
  );

  $("andes-lead-bar-btn").addEventListener("click", toggleLeadForm);
  $("andes-lead-close").addEventListener("click", closeLeadForm);

  messages.addEventListener("click", closeLeadForm);
  input.addEventListener("focus", closeLeadForm);
  $("andes-lead-done").addEventListener("click", function () {
    closeLeadForm();
    appendMsg("Thank you — your meeting request was sent. We'll confirm your time by email soon.", "bot");
  });

  $("andes-lead-submit").addEventListener("click", function () {
    var interest = $("andes-lead-interest").value;
    var meetDate = $("andes-lead-date").value;
    var meetTime = $("andes-lead-time").value;
    var notes = $("andes-lead-message").value.trim();
    var meetingLine = meetDate && meetTime ? "Preferred meeting: " + meetDate + " at " + meetTime : "";
    var messageParts = [];
    if (meetingLine) messageParts.push(meetingLine);
    if (notes) messageParts.push(notes);
    var payload = {
      name: $("andes-lead-name").value.trim(),
      email: $("andes-lead-email").value.trim(),
      phone: $("andes-lead-phone").value.trim() || null,
      company: $("andes-lead-company").value.trim() || null,
      topic: interest || "Book a meeting",
      message: messageParts.join("\n\n") || meetingLine || "Meeting request",
      session_id: sessionId,
      source_url: window.location.href,
      conversation: chatHistory.slice(),
      website: honeypotValue(),
    };
    clearEmailInvalid();
    if (!payload.name || !payload.email) {
      if (!payload.email) setEmailInvalid(true, "Email is required.");
      else if (!isValidEmail(payload.email)) setEmailInvalid(true, "Please enter a valid email address.");
      if (!payload.name) alert("Please add your name.");
      return;
    }
    if (!meetDate || !meetTime) {
      alert("Please choose a preferred date and time for your meeting.");
      if (!meetDate) $("andes-lead-date").focus();
      else $("andes-lead-time").focus();
      return;
    }
    if (!isValidEmail(payload.email)) {
      setEmailInvalid(true, "Please enter a valid email address.");
      leadEmailInput.focus();
      return;
    }
    $("andes-lead-submit").disabled = true;
    $("andes-lead-submit").textContent = "Sending…";
    fetch(apiUrl + "/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (d) {
          if (!r.ok) {
            var err = new Error(formatApiError(d));
            err.detail = d;
            throw err;
          }
          if (!d.lead_id && !d.ok) throw new Error(formatApiError(d));
          return d;
        });
      })
      .then(function (data) {
        showLeadSuccess();
        $("andes-lead-name").value = "";
        $("andes-lead-email").value = "";
        $("andes-lead-phone").value = "";
        clearEmailInvalid();
        $("andes-lead-company").value = "";
        $("andes-lead-interest").value = "";
        $("andes-lead-date").value = "";
        $("andes-lead-time").value = "";
        $("andes-lead-message").value = "";
        $("andes-lead-submit").disabled = false;
        $("andes-lead-submit").textContent = "Book meeting";
      })
      .catch(function (err) {
        $("andes-lead-submit").disabled = false;
        $("andes-lead-submit").textContent = "Book meeting";
        var msg = err.message || "Could not send. Try again or use andestech.com contact page.";
        if (/email/i.test(msg)) {
          setEmailInvalid(true, "Please enter a valid email address.");
          leadEmailInput.focus();
        } else {
          alert(msg);
        }
      });
  });
})();
