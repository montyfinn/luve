import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { AnimationItem } from "lottie-web";
import { CatCompanion } from "./CatCompanion";

type LottieData = Record<string, unknown> & { op?: number };
type LottiePlayer = typeof import("lottie-web").default;

function getReducedMotion() {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

function useReducedMotion() {
  const [reduced, setReduced] = useState(getReducedMotion);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);

  return reduced;
}

async function loadCatHelp() {
  const data = await import("../assets/cats/cat_help.json");
  return data.default as LottieData;
}

async function loadCatSpace() {
  const data = await import("../assets/cats/cat_space.json");
  return data.default as LottieData;
}

async function loadCatFront() {
  const data = await import("../assets/cats/cat_front.json");
  return data.default as LottieData;
}

async function loadCatSleepLuve() {
  const data = await import("../assets/cats/cat_sleepluve.json");
  return data.default as LottieData;
}

async function loadLottiePlayer(): Promise<LottiePlayer> {
  const lottie = await import("lottie-web/build/player/lottie_light");
  return lottie.default;
}

interface ClaudeCatProps {
  width?: number;
  height?: number;
  className?: string;
}

export function ClaudeCat({ width = 74, height = 74, className }: ClaudeCatProps) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (reduced || failed || !ref.current) return;

    let alive = true;
    let anim: AnimationItem | null = null;

    async function mountCat() {
      try {
        const [lottie, animationData] = await Promise.all([loadLottiePlayer(), loadCatHelp()]);
        if (!alive || !ref.current) return;
        anim = lottie.loadAnimation({
          container: ref.current,
          renderer: "svg",
          loop: true,
          autoplay: true,
          animationData,
          rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
        });
      } catch {
        if (alive) setFailed(true);
      }
    }

    void mountCat();

    return () => {
      alive = false;
      anim?.destroy();
      if (ref.current) ref.current.innerHTML = "";
    };
  }, [failed, reduced]);

  if (reduced || failed) {
    return <CatCompanion variant="curious" size={Math.min(width, height)} className={className} />;
  }

  return (
    <span
      ref={ref}
      className={`lottie-box claude-cat claude-cat--help${className ? ` ${className}` : ""}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function CatFront({ width = 82, height = 82, className }: ClaudeCatProps) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (failed || !ref.current) return;

    let alive = true;
    let anim: AnimationItem | null = null;

    async function mountCat() {
      try {
        const [lottie, animationData] = await Promise.all([loadLottiePlayer(), loadCatFront()]);
        if (!alive || !ref.current) return;
        anim = lottie.loadAnimation({
          container: ref.current,
          renderer: "svg",
          loop: !reduced,
          autoplay: !reduced,
          animationData,
          rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
        });
        if (reduced) {
          anim.goToAndStop(0, true);
        }
      } catch {
        if (alive) setFailed(true);
      }
    }

    void mountCat();

    return () => {
      alive = false;
      anim?.destroy();
      if (ref.current) ref.current.innerHTML = "";
    };
  }, [failed, reduced]);

  if (failed) {
    return <CatCompanion variant="curious" size={Math.min(width, height)} className={className} />;
  }

  return (
    <span
      ref={ref}
      className={`lottie-box cat-front${className ? ` ${className}` : ""}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function CatSleepLuveLogo({ width = 82, height = 82, className }: ClaudeCatProps) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const reduced = useReducedMotion();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (failed || !ref.current) return;

    let alive = true;
    let anim: AnimationItem | null = null;

    async function mountCat() {
      try {
        const [lottie, animationData] = await Promise.all([loadLottiePlayer(), loadCatSleepLuve()]);
        if (!alive || !ref.current) return;
        anim = lottie.loadAnimation({
          container: ref.current,
          renderer: "svg",
          loop: !reduced,
          autoplay: !reduced,
          animationData,
          rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
        });
        if (reduced) {
          anim.goToAndStop(0, true);
        }
      } catch {
        if (alive) setFailed(true);
      }
    }

    void mountCat();

    return () => {
      alive = false;
      anim?.destroy();
      if (ref.current) ref.current.innerHTML = "";
    };
  }, [failed, reduced]);

  if (failed) {
    return <CatCompanion variant="sleepy" size={Math.min(width, height)} className={className} />;
  }

  return (
    <span
      ref={ref}
      className={`lottie-box cat-sleepluve${className ? ` ${className}` : ""}`}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function CatSpaceAmbience() {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!mounted || reduced || failed || !boxRef.current) return;

    let alive = true;
    let anim: AnimationItem | null = null;
    let rafId: number | null = null;
    let gapTimer: number | null = null;
    let lottie: LottiePlayer | null = null;
    let animationData: LottieData | null = null;
    const timers = new Set<number>();

    const setTimer = (fn: () => void, delay: number) => {
      const id = window.setTimeout(() => {
        timers.delete(id);
        fn();
      }, delay);
      timers.add(id);
      return id;
    };

    const clearTimer = (id: number | null) => {
      if (id === null) return;
      window.clearTimeout(id);
      timers.delete(id);
    };

    const vw = () => window.innerWidth;
    const vh = () => window.innerHeight;
    const randomBetween = (min: number, max: number) => min + Math.random() * (max - min);

    function choosePath(width: number, height: number) {
      const viewportWidth = vw();
      const viewportHeight = vh();
      const lowerY = viewportHeight - height * randomBetween(0.72, 1.04);
      const cornerY = viewportHeight - height * randomBetween(0.48, 0.78);
      const leftEdgeX = () => -width * randomBetween(0.45, 0.82);
      const rightEdgeX = () => viewportWidth - width * randomBetween(0.18, 0.48);
      const side = Math.random() < 0.5 ? -1 : 1;
      const preset = Math.floor(Math.random() * 4);

      switch (preset) {
        case 0:
          return {
            startX: leftEdgeX(),
            startY: cornerY,
            velocityX: randomBetween(18, 30),
            velocityY: -randomBetween(7, 13),
          };
        case 1:
          return {
            startX: rightEdgeX(),
            startY: cornerY,
            velocityX: -randomBetween(18, 30),
            velocityY: -randomBetween(7, 13),
          };
        case 2:
          return {
            startX: leftEdgeX(),
            startY: lowerY,
            velocityX: randomBetween(16, 27),
            velocityY: -randomBetween(2, 7),
          };
        case 3:
          return {
            startX: rightEdgeX(),
            startY: lowerY,
            velocityX: -randomBetween(16, 27),
            velocityY: -randomBetween(2, 7),
          };
        default:
          return {
            startX: side < 0 ? leftEdgeX() : rightEdgeX(),
            startY: lowerY,
            velocityX: side < 0 ? randomBetween(16, 27) : -randomBetween(16, 27),
            velocityY: -randomBetween(2, 7),
          };
      }
    }

    function destroyAnimation() {
      anim?.destroy();
      anim = null;
      if (boxRef.current) boxRef.current.innerHTML = "";
    }

    function loadCat() {
      if (!boxRef.current || !lottie || !animationData) return;
      destroyAnimation();
      anim = lottie.loadAnimation({
        container: boxRef.current,
        renderer: "svg",
        loop: true,
        autoplay: true,
        animationData,
        rendererSettings: { preserveAspectRatio: "xMidYMid meet" },
      });
    }

    function scheduleRespawnAfterExit() {
      if (rafId !== null) {
        window.cancelAnimationFrame(rafId);
        rafId = null;
      }
      if (boxRef.current) boxRef.current.style.opacity = "0";
      clearTimer(gapTimer);
      const reappearMs = randomBetween(300, 800);
      gapTimer = setTimer(() => {
        if (!alive) return;
        destroyAnimation();
        spawn();
      }, reappearMs);
    }

    function spawn() {
      const box = boxRef.current;
      if (!box || !lottie || !animationData) return;

      const width = randomBetween(108, 166);
      const height = width * 1.6;
      box.style.width = `${width}px`;
      box.style.height = `${height}px`;

      const { startX, startY, velocityX, velocityY } = choosePath(width, height);
      const wobblePhase = Math.random() * Math.PI * 2;
      const face = velocityX < 0 ? " scaleX(-1)" : "";

      const applyTransform = (x: number, y: number) => {
        box.style.transform = `translate(${x}px, ${y}px)${face}`;
      };

      applyTransform(startX, startY);
      box.style.opacity = "0";
      loadCat();
      setTimer(() => {
        if (alive && boxRef.current) boxRef.current.style.opacity = "0.9";
      }, 60);

      const startTime = performance.now();
      let lastTime = startTime;
      let currentX = startX;
      let currentY = startY;

      const step = (now: number) => {
        if (!alive || !boxRef.current) return;
        const delta = Math.min(0.05, (now - lastTime) / 1000);
        lastTime = now;
        const elapsed = now - startTime;
        currentX += velocityX * delta;
        currentY += velocityY * delta;
        const bobbedY = currentY + Math.sin(elapsed / 700 + wobblePhase) * 8;
        applyTransform(currentX, bobbedY);

        const gone =
          currentX + width < -40 || currentX > vw() + 40 || bobbedY + height < -40;
        if (gone) {
          scheduleRespawnAfterExit();
          return;
        }
        rafId = window.requestAnimationFrame(step);
      };

      rafId = window.requestAnimationFrame(step);
    }

    const bootTimer = setTimer(() => {
      void Promise.all([loadLottiePlayer(), loadCatSpace()])
        .then(([lottiePlayer, catData]) => {
          if (!alive) return;
          lottie = lottiePlayer;
          animationData = catData;
          spawn();
        })
        .catch(() => {
          if (alive) setFailed(true);
        });
    }, 1400);

    return () => {
      alive = false;
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      clearTimer(gapTimer);
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
      window.clearTimeout(bootTimer);
      destroyAnimation();
    };
  }, [failed, mounted, reduced]);

  if (!mounted) return null;

  const layer =
    reduced || failed ? (
      <div className="cat-space-layer cat-space-layer--fallback" aria-hidden="true">
        <CatCompanion variant="idle" size={78} className="cat-space-fallback" />
      </div>
    ) : (
      <div className="cat-space-layer" aria-hidden="true">
        <div ref={boxRef} className="cat-space-cat" />
      </div>
    );

  return createPortal(layer, document.body);
}
