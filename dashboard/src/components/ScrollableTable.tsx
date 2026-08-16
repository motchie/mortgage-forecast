import { useEffect, useRef, useState, type ReactNode } from "react";

export function ScrollableTable({ label, className = "", children }: { label: string; className?: string; children: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const [isScrollable, setIsScrollable] = useState(false);

  useEffect(() => {
    const measure = () => {
      const element = container.current;
      setIsScrollable(Boolean(element && element.scrollWidth > element.clientWidth + 1));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [children]);

  return <>
    {isScrollable && <p className="scroll-hint" id={`${label}-scroll-hint`}>この表は横方向にスクロールできます。</p>}
    <div
      ref={container}
      className={`table-scroll ${className}`.trim()}
      tabIndex={isScrollable ? 0 : undefined}
      role={isScrollable ? "region" : undefined}
      aria-label={isScrollable ? label : undefined}
      aria-describedby={isScrollable ? `${label}-scroll-hint` : undefined}
    >
      {children}
    </div>
  </>;
}
