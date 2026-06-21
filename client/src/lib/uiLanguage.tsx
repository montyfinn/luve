/**
 * UI language context: persists the chosen interface language in localStorage
 * and exposes a `t()` helper. English is the default; only "vi" is stored as an
 * override. This controls UI chrome only — see lib/i18n.ts for scope.
 */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { translate, type TKey, type TParams, type UiLanguage } from "./i18n";

const STORAGE_KEY = "luve.ui.lang";

function loadLanguage(): UiLanguage {
  try {
    return localStorage.getItem(STORAGE_KEY) === "vi" ? "vi" : "en";
  } catch {
    return "en";
  }
}

function persistLanguage(lang: UiLanguage): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* storage unavailable (private mode) — language stays in-memory only */
  }
  try {
    document.documentElement.lang = lang;
  } catch {
    /* no document (non-browser) — ignore */
  }
}

interface UiLanguageContextValue {
  lang: UiLanguage;
  setLang: (lang: UiLanguage) => void;
  toggle: () => void;
  t: (key: TKey, params?: TParams) => string;
}

const UiLanguageContext = createContext<UiLanguageContextValue | null>(null);

export function UiLanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<UiLanguage>(loadLanguage);

  const setLang = useCallback((next: UiLanguage) => {
    persistLanguage(next);
    setLangState(next);
  }, []);

  const toggle = useCallback(() => {
    setLangState((prev) => {
      const next = prev === "en" ? "vi" : "en";
      persistLanguage(next);
      return next;
    });
  }, []);

  const t = useCallback((key: TKey, params?: TParams) => translate(lang, key, params), [lang]);

  const value = useMemo(() => ({ lang, setLang, toggle, t }), [lang, setLang, toggle, t]);

  return <UiLanguageContext.Provider value={value}>{children}</UiLanguageContext.Provider>;
}

export function useUiLanguage(): UiLanguageContextValue {
  const ctx = useContext(UiLanguageContext);
  if (!ctx) {
    throw new Error("useUiLanguage must be used within a UiLanguageProvider");
  }
  return ctx;
}
