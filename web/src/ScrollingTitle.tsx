import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";

export function ScrollingTitle({ children }: { children: string }) {
  const viewport = useRef<HTMLSpanElement>(null);
  const text = useRef<HTMLSpanElement>(null);
  const [distance, setDistance] = useState(0);
  useLayoutEffect(() => {
    const measure = () => {
      const width = text.current?.getBoundingClientRect().width || 0;
      setDistance(
        width > (viewport.current?.clientWidth || 0) + 1 ? width + 32 : 0,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (viewport.current) observer.observe(viewport.current);
    if (text.current) observer.observe(text.current);
    return () => observer.disconnect();
  }, [children]);
  return (
    <span
      ref={viewport}
      className={`scrolling-title ${distance ? "is-scrolling" : ""}`}
      title={children}
      style={
        {
          "--scroll-distance": `${distance}px`,
          "--scroll-duration": `${Math.max(10, distance / 30)}s`,
        } as CSSProperties
      }
    >
      <span className="scrolling-title-strip" key={children}>
        <span ref={text}>{children}</span>
        {distance > 0 && <span aria-hidden="true">{children}</span>}
      </span>
    </span>
  );
}
