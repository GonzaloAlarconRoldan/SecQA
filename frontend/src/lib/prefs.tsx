import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { dictionaries, translateEnum, type I18nKey, type Lang } from "./i18n";
import { storage } from "./storage";

export type Theme = "system" | "light" | "dark";

interface Prefs {
  theme: Theme;
  setTheme: (t: Theme) => void;
  isDark: boolean;
  lang: Lang;
  setLang: (l: Lang) => void;
  actor: string;
  setActor: (a: string) => void;
  token: string;
  setToken: (t: string) => void;
  t: (key: I18nKey) => string;
  te: (value: string | null | undefined) => string;
}

const PrefsContext = createContext<Prefs | null>(null);

function systemDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => (storage.get("secqa.theme") as Theme) || "system");
  const [lang, setLangState] = useState<Lang>(() => (storage.get("secqa.lang") === "es" ? "es" : "en"));
  const [actor, setActorState] = useState(() => storage.get("secqa.actor") || "reviewer");
  const [token, setTokenState] = useState(() => storage.get("secqa.token") || "");
  const [sysDark, setSysDark] = useState(systemDark);

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => setSysDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const isDark = theme === "dark" || (theme === "system" && sysDark);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDark);
  }, [isDark]);
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const setTheme = useCallback((t: Theme) => {
    storage.set("secqa.theme", t);
    setThemeState(t);
  }, []);
  const setLang = useCallback((l: Lang) => {
    storage.set("secqa.lang", l);
    setLangState(l);
  }, []);
  const setActor = useCallback((a: string) => {
    storage.set("secqa.actor", a);
    setActorState(a);
  }, []);
  const setToken = useCallback((t: string) => {
    storage.set("secqa.token", t || null);
    setTokenState(t);
  }, []);

  const value = useMemo<Prefs>(
    () => ({
      theme, setTheme, isDark, lang, setLang, actor, setActor, token, setToken,
      t: (key) => dictionaries[lang][key] ?? key,
      te: (v) => (v ? translateEnum(lang, v) : "—"),
    }),
    [theme, setTheme, isDark, lang, setLang, actor, setActor, token, setToken],
  );
  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): Prefs {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs outside PrefsProvider");
  return ctx;
}
