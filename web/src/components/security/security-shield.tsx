"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Shield, ShieldAlert, ShieldCheck, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

const IS_DEV = process.env.NODE_ENV !== "production";
const STORAGE_KEY_CONFIG = "ue_dev_security_shield_config_v2";

interface ShieldContextValue {
  domPurgedByDebugger: boolean;
  clearDomPurge: () => void;
  config: ShieldModulesConfig;
  freezeNoisePreview: boolean;
  setFreezeNoisePreview: (v: boolean) => void;
  events: ThreatDetectionEvent[];
}

export interface ShieldModulesConfig {
  master: boolean;
  antiF12Shortcuts: boolean;
  antiContextMenu: boolean;
  antiRemoteDebug: boolean;
  antiDomInjection: boolean;
  antiWindowBlur: boolean;
  antiScreenshotCanvas: boolean;
  complementaryTemporalNoise: boolean;
  vlmAdversarialWatermark: boolean;
  domPromptPoisoning: boolean;
}

export interface ThreatDetectionEvent {
  id: string;
  time: string;
  module: keyof Omit<ShieldModulesConfig, "master">;
  moduleLabel: string;
  reason: string;
}

const DEFAULT_DEV_CONFIG: ShieldModulesConfig = {
  master: false,
  antiF12Shortcuts: true,
  antiContextMenu: true,
  antiRemoteDebug: true,
  antiDomInjection: true,
  antiWindowBlur: false,
  antiScreenshotCanvas: true,
  complementaryTemporalNoise: true,
  vlmAdversarialWatermark: true,
  domPromptPoisoning: true,
};

const DEFAULT_PROD_CONFIG: ShieldModulesConfig = {
  master: true,
  antiF12Shortcuts: true,
  antiContextMenu: true,
  antiRemoteDebug: true,
  antiDomInjection: true,
  antiWindowBlur: true,
  antiScreenshotCanvas: true,
  complementaryTemporalNoise: true,
  vlmAdversarialWatermark: true,
  domPromptPoisoning: true,
};

const ShieldContext = React.createContext<ShieldContextValue>({
  domPurgedByDebugger: false,
  clearDomPurge: () => {},
  config: DEFAULT_DEV_CONFIG,
  freezeNoisePreview: false,
  setFreezeNoisePreview: () => {},
  events: [],
});

export function useSecurityShield() {
  return React.useContext(ShieldContext);
}

const MODULE_LABELS: {
  key: keyof Omit<ShieldModulesConfig, "master">;
  label: string;
}[] = [
  { key: "complementaryTemporalNoise", label: "60Hz 互补高频噪点 (Temporal Noise)" },
  { key: "vlmAdversarialWatermark", label: "VLM 视觉注入水印与频域干扰 (VLM Watermark)" },
  { key: "domPromptPoisoning", label: "DOM 大模型提示词投毒与拒答诱导 (LLM Poison)" },
  { key: "antiF12Shortcuts", label: "F12 / 快捷键拦截 (Shortcuts)" },
  { key: "antiContextMenu", label: "右键菜单拦截 (ContextMenu)" },
  { key: "antiRemoteDebug", label: "远程调试 / WebDriver 探针" },
  { key: "antiDomInjection", label: "浏览器插件 / DOM 注入清理" },
  { key: "antiWindowBlur", label: "切屏 / 失焦模糊保护 (Blur)" },
  { key: "antiScreenshotCanvas", label: "截图 / Canvas 导出投毒" },
];

const SUSPICIOUS_ATTRS = [
  "data-immersive-translate-walked",
  "data-immersive-translate-paragraph",
  "data-grammarly-shadow-root",
  "data-darkreader-mode",
  "data-darkreader-scheme",
  "data-violentmonkey",
  "data-tampermonkey",
];

const SUSPICIOUS_SELECTORS = [
  "immersive-translate-div",
  "grammarly-extension",
  "monica-content-root",
  "sider-quick-action",
  '[id^="immersive-translate"]',
  '[class*="immersive-translate"]',
  'script[src^="chrome-extension://"]',
  'script[src^="moz-extension://"]',
  'link[href^="chrome-extension://"]',
];

export function SecurityShieldProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfig] = useState<ShieldModulesConfig>(() =>
    IS_DEV ? DEFAULT_DEV_CONFIG : DEFAULT_PROD_CONFIG
  );
  const [mounted, setMounted] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [events, setEvents] = useState<ThreatDetectionEvent[]>([]);
  const [activeReasons, setActiveReasons] = useState<string[]>([]);
  const [domPurgedByDebugger, setDomPurgedByDebugger] = useState(false);
  const [freezeNoisePreview, setFreezeNoisePreview] = useState(false);

  const clearDomPurge = useCallback(() => {
    setDomPurgedByDebugger(false);
    setActiveReasons([]);
    if (typeof document !== "undefined") {
      document.documentElement.classList.remove("ue-shield-obscured");
    }
  }, []);

  useEffect(() => {
    setMounted(true);
    if (IS_DEV) {
      try {
        const raw = localStorage.getItem(STORAGE_KEY_CONFIG);
        if (raw) {
          const parsed = JSON.parse(raw);
          setConfig((prev) => ({ ...prev, ...parsed }));
        }
      } catch {}
    }
  }, []);

  const updateConfig = useCallback((patch: Partial<ShieldModulesConfig>) => {
    setConfig((prev) => {
      const next = { ...prev, ...patch };
      if (IS_DEV) {
        try {
          localStorage.setItem(STORAGE_KEY_CONFIG, JSON.stringify(next));
        } catch {}
      }
      return next;
    });
  }, []);

  const recordAnomaly = useCallback(
    (
      module: keyof Omit<ShieldModulesConfig, "master">,
      moduleLabel: string,
      reason: string,
      obscureMs = 0
    ) => {
      const now = new Date();
      const timeStr = now.toTimeString().slice(0, 8);
      setEvents((prev) => {
        // Deduplicate identical consecutive reasons within the last item
        if (prev.length > 0 && prev[0].reason === reason && prev[0].time === timeStr) {
          return prev;
        }
        const entry: ThreatDetectionEvent = {
          id: `${now.getTime()}-${Math.random().toString(36).slice(2, 6)}`,
          time: timeStr,
          module,
          moduleLabel,
          reason,
        };
        return [entry, ...prev].slice(0, 25);
      });

      if (obscureMs > 0 && typeof document !== "undefined") {
        const root = document.documentElement;
        root.classList.add("ue-shield-obscured");
        setActiveReasons((prev) => (prev.includes(reason) ? prev : [...prev, reason]));
        window.setTimeout(() => {
          setActiveReasons((prev) => {
            const next = prev.filter((r) => r !== reason);
            if (next.length === 0) {
              root.classList.remove("ue-shield-obscured");
            }
            return next;
          });
        }, obscureMs);
      }
    },
    []
  );

  useEffect(() => {
    const root = document.documentElement;
    if (!config.master) {
      root.classList.remove("ue-shield-active", "ue-shield-obscured");
      setActiveReasons([]);
      setDomPurgedByDebugger(false);
      return;
    }

    root.classList.add("ue-shield-active");

    // 1. Silent F12 / DevTools Shortcut Detection & PrintScreen Interception
    // Note: For F12 / Ctrl+Shift+I/J/C, we DO NOT call e.preventDefault() so DevTools opens
    // normally as if no anti-debug exists, while we silently purge all question/option text
    // from DOM Elements and seamlessly switch rendering to CSSOM pseudo-elements!
    const handleKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toUpperCase();
      const isF12 = e.key === "F12" || e.keyCode === 123;
      const isInspect =
        (e.ctrlKey || e.metaKey) && e.shiftKey && (key === "I" || key === "J" || key === "C");
      const isViewSource = (e.ctrlKey || e.metaKey) && (key === "U" || key === "S" || key === "P");
      const isPrintScreen = e.key === "PrintScreen" || e.keyCode === 44;

      if (config.antiF12Shortcuts && (isF12 || isInspect)) {
        const combo = isF12
          ? "检测到 F12 开启开发者工具 (已静默清空 DOM 题干并切换至 CSSOM 渲染)"
          : `检测到调试热键 Ctrl+Shift+${key} (已静默清空 DOM 题干并切换至 CSSOM 渲染)`;
        setDomPurgedByDebugger(true);
        recordAnomaly("antiF12Shortcuts", "静默 F12 诱捕", combo, 0);
        return;
      }

      if (config.antiF12Shortcuts && isViewSource) {
        e.preventDefault();
        e.stopPropagation();
        recordAnomaly(
          "antiF12Shortcuts",
          "快捷键防护",
          `拦截源码/保存/打印热键 Ctrl+${key}`,
          0
        );
        return false;
      }

      if (config.antiScreenshotCanvas && isPrintScreen) {
        e.preventDefault();
        e.stopPropagation();
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText("").catch(() => {});
        }
        recordAnomaly("antiScreenshotCanvas", "防截图保护", "检测到 PrintScreen 截屏按键", 1200);
        return false;
      }
    };

    // 2. Anti-ContextMenu
    const handleContextMenu = (e: MouseEvent) => {
      if (!config.antiContextMenu) return;
      e.preventDefault();
      e.stopPropagation();
      recordAnomaly("antiContextMenu", "右键菜单拦截", "触发页面右键 ContextMenu");
    };

    // 3. Anti-Window Blur / Visibility Protection
    const handleBlur = () => {
      if (!config.antiWindowBlur) return;
      root.classList.add("ue-shield-obscured");
      setActiveReasons((prev) =>
        prev.includes("窗口失焦 (window.blur)") ? prev : [...prev, "窗口失焦 (window.blur)"]
      );
      recordAnomaly("antiWindowBlur", "失焦模糊保护", "窗口失焦 (window.blur)");
    };

    const handleFocus = () => {
      setActiveReasons((prev) => {
        const next = prev.filter(
          (r) => r !== "窗口失焦 (window.blur)" && r !== "页面切至后台 (visibilityState=hidden)"
        );
        if (next.length === 0) {
          root.classList.remove("ue-shield-obscured");
        }
        return next;
      });
    };

    const handleVisibilityChange = () => {
      if (!config.antiWindowBlur) return;
      if (document.visibilityState !== "visible") {
        root.classList.add("ue-shield-obscured");
        setActiveReasons((prev) =>
          prev.includes("页面切至后台 (visibilityState=hidden)")
            ? prev
            : [...prev, "页面切至后台 (visibilityState=hidden)"]
        );
        recordAnomaly(
          "antiWindowBlur",
          "失焦模糊保护",
          "页面切至后台 (visibilityState=hidden)"
        );
      } else {
        handleFocus();
      }
    };

    // 4. Anti-Canvas / DOM-to-Image Screenshot Poisoning
    const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const origToBlob = HTMLCanvasElement.prototype.toBlob;
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;

    if (config.antiScreenshotCanvas) {
      HTMLCanvasElement.prototype.toDataURL = function () {
        recordAnomaly(
          "antiScreenshotCanvas",
          "防截图保护",
          "拦截 HTMLCanvasElement.toDataURL() 像素导出",
          1000
        );
        return "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";
      };
      HTMLCanvasElement.prototype.toBlob = function (callback) {
        recordAnomaly(
          "antiScreenshotCanvas",
          "防截图保护",
          "拦截 HTMLCanvasElement.toBlob() 图像导出",
          1000
        );
        if (callback) callback(null);
      };
      CanvasRenderingContext2D.prototype.getImageData = function (sx, sy, sw, sh) {
        recordAnomaly(
          "antiScreenshotCanvas",
          "防截图保护",
          "拦截 CanvasRenderingContext2D.getImageData() 读取",
          1000
        );
        return new ImageData(Math.max(1, sw), Math.max(1, sh));
      };
    }

    // 5. Anti-Extension / Anti-Injection DOM Sanitizer (MutationObserver)
    let observer: MutationObserver | null = null;
    if (config.antiDomInjection) {
      const sanitizeNode = () => {
        try {
          for (const sel of SUSPICIOUS_SELECTORS) {
            const found = document.querySelectorAll(sel);
            if (found.length > 0) {
              found.forEach((el) => el.remove());
              recordAnomaly(
                "antiDomInjection",
                "DOM 注入清理",
                `移除外部插件注入节点 (${sel})`
              );
            }
          }
        } catch {}
      };

      observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
          if (m.type === "childList" && m.addedNodes.length > 0) {
            sanitizeNode();
          } else if (m.type === "attributes" && m.attributeName) {
            const attr = m.attributeName.toLowerCase();
            if (
              attr.startsWith("data-immersive") ||
              attr.startsWith("data-grammarly") ||
              attr.startsWith("data-monica") ||
              SUSPICIOUS_ATTRS.includes(attr)
            ) {
              (m.target as Element).removeAttribute(m.attributeName);
              recordAnomaly(
                "antiDomInjection",
                "DOM 注入清理",
                `剥离插件篡改属性 (${m.attributeName})`
              );
            }
          }
        }
      });

      observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
      });
    }

    // 6. Silent Anti-Remote-Debugging / WebDriver / Docked & Undocked (Pop-Out) DevTools Probe
    // Zero `debugger` statements are used so DevTools never pauses or alerts the user!
    let probeInterval: number | null = null;
    if (config.antiRemoteDebug) {
      // Console serializer property-getter trap: triggers even when DevTools is undocked into
      // a floating window whenever the Console serializer inspects logged objects
      const probeEl = document.createElement("div");
      Object.defineProperty(probeEl, "id", {
        get() {
          setDomPurgedByDebugger(true);
          recordAnomaly(
            "antiRemoteDebug",
            "静默远程调试探针",
            "检测到独立弹出/停靠 DevTools 控制台序列化探针 (已静默清空 DOM 题干并转入 CSSOM 渲染)",
            0
          );
          return "ue-probe";
        },
        configurable: true,
      });

      probeInterval = window.setInterval(() => {
        if (navigator.webdriver) {
          setDomPurgedByDebugger(true);
          recordAnomaly(
            "antiRemoteDebug",
            "静默远程调试探针",
            "检测到受控浏览器特征 (navigator.webdriver=true，已静默清空 DOM 题干)",
            0
          );
        }

        // 6a. Docked DevTools: Compare zoom-compensated outer vs inner viewport dimensions
        const dpr = window.devicePixelRatio || 1;
        const widthGap = window.outerWidth - window.innerWidth * dpr;
        const heightGap = window.outerHeight - window.innerHeight * dpr;
        if (widthGap > 240 || heightGap > 240) {
          setDomPurgedByDebugger(true);
          recordAnomaly(
            "antiRemoteDebug",
            "静默远程调试探针",
            `检测到停靠式 DevTools 面板视口特征 (ΔW=${Math.round(widthGap)}, ΔH=${Math.round(heightGap)}，已静默清空 DOM 题干)`,
            0
          );
        }

        // 6b. Undocked / Pop-Out Floating F12 Window:
        // When DevTools is undocked into a separate floating window, the exam page remains
        // visible behind it (`document.visibilityState === "visible"`), while `document.hasFocus()`
        // immediately drops to `false`!
        if (document.visibilityState === "visible" && !document.hasFocus()) {
          setDomPurgedByDebugger(true);
          recordAnomaly(
            "antiRemoteDebug",
            "静默远程调试探针",
            "检测到弹出式 F12 调试窗口或外部悬浮工具夺取焦点 (visibilityState=visible & hasFocus=false，已静默清空 DOM 题干)",
            0
          );
        }

        // 6c. Fire Console getter trap for undocked/docked Console serializer
        try {
          console.debug(probeEl);
          console.clear();
        } catch {}
      }, 1000);
    }

    // Also trigger silent DOM purge immediately on window blur when page stays visible
    // (instantaneous reaction the moment an undocked F12 window pops out)
    const handleUndockedDevToolsBlur = () => {
      if (!config.antiRemoteDebug) return;
      window.setTimeout(() => {
        if (document.visibilityState === "visible" && !document.hasFocus()) {
          setDomPurgedByDebugger(true);
          recordAnomaly(
            "antiRemoteDebug",
            "静默远程调试探针",
            "检测到弹出式 F12 独立窗口焦点脱离 (已静默清空 DOM 题干并切换至 CSSOM 渲染)",
            0
          );
        }
      }, 60);
    };

    window.addEventListener("keydown", handleKeyDown, true);
    window.addEventListener("keyup", handleKeyDown, true);
    window.addEventListener("contextmenu", handleContextMenu, true);
    window.addEventListener("blur", handleBlur);
    window.addEventListener("blur", handleUndockedDevToolsBlur);
    window.addEventListener("focus", handleFocus);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      root.classList.remove("ue-shield-active", "ue-shield-obscured");
      window.removeEventListener("keydown", handleKeyDown, true);
      window.removeEventListener("keyup", handleKeyDown, true);
      window.removeEventListener("contextmenu", handleContextMenu, true);
      window.removeEventListener("blur", handleBlur);
      window.removeEventListener("blur", handleUndockedDevToolsBlur);
      window.removeEventListener("focus", handleFocus);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (probeInterval !== null) window.clearInterval(probeInterval);
      if (observer !== null) observer.disconnect();
      HTMLCanvasElement.prototype.toDataURL = origToDataURL;
      HTMLCanvasElement.prototype.toBlob = origToBlob;
      CanvasRenderingContext2D.prototype.getImageData = origGetImageData;
    };
  }, [config, recordAnomaly]);

  return (
    <ShieldContext.Provider
      value={{
        domPurgedByDebugger,
        clearDomPurge,
        config,
        freezeNoisePreview,
        setFreezeNoisePreview,
        events,
      }}
    >
      {children}
      {mounted && IS_DEV && (
        <div className="fixed bottom-3 right-3 z-50 select-none font-mono text-xs">
          {panelOpen && (
            <div className="mb-2 w-84 rounded border border-border bg-card p-3 shadow-lg space-y-2.5 text-foreground">
              <div className="flex items-center justify-between border-b pb-2">
                <span className="font-semibold flex items-center gap-1.5">
                  <Shield className="h-3.5 w-3.5" />
                  <span>Anti-Cheat Shield (Dev)</span>
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setFreezeNoisePreview((v) => !v)}
                    title="暂停 60Hz 互补抵消并增强对比度，直观预览截屏 Agent / VLM 看到的干扰与注入水印"
                    className={cn(
                      "px-1.5 py-0.5 rounded border text-[10px] font-medium transition-colors",
                      freezeNoisePreview
                        ? "border-amber-500 bg-amber-500 text-black"
                        : "border-border bg-muted text-muted-foreground hover:bg-muted/80"
                    )}
                  >
                    {freezeNoisePreview ? "恢复 60Hz 抵消" : "模拟 Agent 截屏视角"}
                  </button>
                  <button
                    type="button"
                    onClick={() => updateConfig({ master: !config.master })}
                    className={cn(
                      "px-2 py-0.5 rounded border text-[11px] font-semibold transition-colors",
                      config.master
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-muted text-muted-foreground hover:bg-muted/80"
                    )}
                  >
                    {config.master ? "总开关: 已开启" : "总开关: 已关闭"}
                  </button>
                </div>
              </div>

              {domPurgedByDebugger && (
                <div className="rounded border border-amber-500/50 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-600 dark:text-amber-400 space-y-1">
                  <div className="font-semibold">
                    已触发 F12 / 远程调试防护：DOM 题干与选项文本已从 Elements 物理移除（转入 CSSOM 伪元素渲染，答题不受影响）
                  </div>
                  <button
                    type="button"
                    onClick={clearDomPurge}
                    className="rounded border border-amber-500/40 bg-background px-1.5 py-0.5 text-[10px] hover:bg-muted"
                  >
                    恢复 DOM 节点显示
                  </button>
                </div>
              )}

              {/* Active blocking reason banner */}
              {activeReasons.length > 0 && (
                <div className="rounded border border-destructive/50 bg-destructive/10 px-2 py-1.5 text-[11px] text-destructive space-y-0.5">
                  <div className="font-semibold">当前触发画面模糊保护的原因：</div>
                  {activeReasons.map((r, idx) => (
                    <div key={idx} className="truncate">
                      • {r}
                    </div>
                  ))}
                </div>
              )}

              {/* Per-module individual switches */}
              <div className="space-y-1">
                <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  子模块独立开关 (Individual Modules)
                </div>
                {MODULE_LABELS.map(({ key, label }) => {
                  const isOn = config[key];
                  return (
                    <label
                      key={key}
                      className="flex items-center justify-between gap-2 rounded px-1.5 py-1 hover:bg-muted/50 cursor-pointer text-[11px]"
                    >
                      <span className={cn(!config.master && "opacity-60")}>{label}</span>
                      <input
                        type="checkbox"
                        checked={isOn}
                        onChange={(e) => updateConfig({ [key]: e.target.checked })}
                        className="h-3.5 w-3.5 accent-primary cursor-pointer"
                      />
                    </label>
                  );
                })}
              </div>

              {/* Named anomaly log */}
              <div className="border-t pt-2 space-y-1">
                <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                  <span>已检测到的异常触发记录 ({events.length})</span>
                  {events.length > 0 && (
                    <button
                      type="button"
                      onClick={() => {
                        setEvents([]);
                        setActiveReasons([]);
                        setDomPurgedByDebugger(false);
                        document.documentElement.classList.remove("ue-shield-obscured");
                      }}
                      className="inline-flex items-center gap-0.5 hover:text-foreground"
                    >
                      <Trash2 className="h-3 w-3" />
                      <span>清空</span>
                    </button>
                  )}
                </div>
                {events.length === 0 ? (
                  <div className="text-[11px] text-muted-foreground py-1">
                    暂无异常触发记录
                  </div>
                ) : (
                  <div className="max-h-36 overflow-y-auto space-y-1 pr-1">
                    {events.map((ev) => (
                      <div
                        key={ev.id}
                        className="rounded border border-border bg-muted/30 px-2 py-1 text-[10px] leading-tight space-y-0.5"
                      >
                        <div className="flex items-center justify-between text-muted-foreground">
                          <span className="font-semibold text-foreground">{ev.moduleLabel}</span>
                          <span>{ev.time}</span>
                        </div>
                        <div className="text-destructive break-words">{ev.reason}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => setPanelOpen((o) => !o)}
            title="Toggle Dev Anti-Cheat Shield Controls"
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-3 py-1.5 shadow-md transition-colors",
              config.master
                ? activeReasons.length > 0
                  ? "border-destructive bg-destructive text-destructive-foreground"
                  : "border-primary bg-primary text-primary-foreground"
                : "border-border bg-neutral-900 text-neutral-100 hover:bg-neutral-800 dark:bg-neutral-800"
            )}
          >
            {config.master ? (
              activeReasons.length > 0 ? (
                <ShieldAlert className="h-3.5 w-3.5" />
              ) : (
                <ShieldCheck className="h-3.5 w-3.5" />
              )
            ) : (
              <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
            )}
            <span>
              Shield: {config.master ? (activeReasons.length > 0 ? "ALERT" : "ON") : "OFF"}
            </span>
            {events.length > 0 && (
              <span className="ml-0.5 rounded-full bg-destructive px-1.5 py-0.2 text-[10px] text-destructive-foreground">
                {events.length}
              </span>
            )}
          </button>
        </div>
      )}
    </ShieldContext.Provider>
  );
}
