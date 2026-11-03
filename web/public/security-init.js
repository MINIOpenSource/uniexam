(function () {
  if (typeof window === "undefined") return;

  var earlyReasons = [];
  function flagEarlyAnomaly(reason) {
    window.__ue_early_dom_purged = true;
    if (earlyReasons.indexOf(reason) === -1) {
      earlyReasons.push(reason);
    }
    window.__ue_early_anomalies = earlyReasons;
    try {
      window.dispatchEvent(new CustomEvent("ue-early-security-anomaly", { detail: reason }));
    } catch (e) {}
  }

  try {
    // 1. Pre-emptively seal FontFace / FontFaceSet / CSSStyleSheet against @run-at document-start
    // monkey-patching by malicious userscripts
    if (typeof window.FontFace === "function" && window.FontFace.prototype) {
      var origFontLoad = window.FontFace.prototype.load;
      Object.defineProperty(window.FontFace.prototype, "load", {
        value: origFontLoad,
        writable: false,
        configurable: false,
      });
    }
    if (typeof window.CSSStyleSheet === "function" && window.CSSStyleSheet.prototype) {
      var origReplaceSync = window.CSSStyleSheet.prototype.replaceSync;
      if (origReplaceSync) {
        Object.defineProperty(window.CSSStyleSheet.prototype, "replaceSync", {
          value: origReplaceSync,
          writable: false,
          configurable: false,
        });
      }
    }
  } catch (e) {}

  try {
    // 2. Synchronous document-start CDP / WebDriver / Automation & Pre-Opened DevTools Detection
    var nav = window.navigator || {};
    var hasAutomationGlobals =
      Boolean(nav.webdriver) ||
      Boolean(window.__playwright__binding__) ||
      Boolean(window.__pwInitScripts) ||
      Boolean(window._phantom) ||
      Boolean(window.__nightmare) ||
      Boolean(window.callPhantom) ||
      Boolean(document.__webdriver_evaluate) ||
      Boolean(document.__selenium_unwrapped) ||
      Boolean(document.__fxdriver_evaluate);

    if (!hasAutomationGlobals) {
      var winKeys = Object.getOwnPropertyNames(window);
      for (var i = 0; i < winKeys.length; i++) {
        var k = winKeys[i];
        if (k.indexOf("cdc_") === 0 || k.indexOf("$cdc_") === 0 || k.indexOf("__puppeteer") === 0) {
          hasAutomationGlobals = true;
          break;
        }
      }
    }

    if (hasAutomationGlobals) {
      flagEarlyAnomaly("document-start 检测到 CDP / WebDriver 自动化控制环境 (已预先启用 CSSOM 零文本渲染)");
    }

    var dpr = window.devicePixelRatio || 1;
    var wGap = window.outerWidth - window.innerWidth * dpr;
    var hGap = window.outerHeight - window.innerHeight * dpr;
    if (wGap > 240 || hGap > 240) {
      flagEarlyAnomaly("document-start 检测到预开启的 DevTools 视口特征 (已预先启用 CSSOM 零文本渲染)");
    }

    // Immediate Console getter probe at document-start
    var earlyProbe = document.createElement("div");
    Object.defineProperty(earlyProbe, "id", {
      get: function () {
        flagEarlyAnomaly("document-start 捕获到 DevTools 控制台序列化探针 (已预先启用 CSSOM 零文本渲染)");
        return "ue-early-probe";
      },
      configurable: true,
    });
    console.debug(earlyProbe);
    console.clear();
  } catch (e) {}
})();
